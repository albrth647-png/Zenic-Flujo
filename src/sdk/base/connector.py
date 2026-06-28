"""
Connector SDK — Clase Base Abstracta del Conector
===================================================

BaseConnector es la clase base que todos los conectores deben heredar.
Provee funcionalidad integrada para conexion, ejecucion, reintentos,
circuit breaker, rate limiting, metricas y validacion.
"""

from __future__ import annotations

import types

import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from src.core.db import RedisService
from src.core.logging import setup_logging
from src.core.observability.telemetry import TelemetryService
from src.sdk.auth import AuthProvider
from src.sdk.base.configs import CircuitBreakerConfig, CircuitState, RateLimitConfig, RetryConfig
from src.sdk.decorators import get_action_metadata
from src.sdk.exceptions import CircuitBreakerOpenError, RateLimitError
from src.sdk.schema import ActionDefinition, ConnectorSchema, SchemaValidator

logger = setup_logging(__name__)


class BaseConnector(ABC):
    """Clase base abstracta para todos los conectores de Zenic-Flijo.

    Subclases deben implementar: connect(), execute(), validate(), disconnect().
    """

    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    category: str = "general"
    icon: str = "plug"
    author: str = ""
    _is_connector: bool = True

    def __init__(
        self,
        auth_provider: AuthProvider | None = None,
        retry_config: RetryConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        schema: ConnectorSchema | None = None,
    ) -> None:
        self._connected = False
        self._auth_provider = auth_provider
        self._retry_config = retry_config or RetryConfig()
        self._circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._rate_limit_config = rate_limit_config or RateLimitConfig()
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._connection_time: float | None = None
        self._lock = threading.RLock()
        self._schema = schema
        self._schema_validator: SchemaValidator | None = None
        self._redis = RedisService()
        self._telemetry = TelemetryService()
        self._action_metadata: dict[str, dict[str, Any]] = {}

        self._discover_actions()
        if self._schema is None:
            self._schema = self._build_auto_schema()
        if self._schema:
            self._schema_validator = SchemaValidator(self._schema)
        logger.debug(f"BaseConnector: instancia creada para '{self.name}'")

    @abstractmethod
    def connect(self) -> bool:
        """Establece la conexion con el servicio externo."""

    @abstractmethod
    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector."""

    @abstractmethod
    def validate(self) -> bool:
        """Valida la configuracion del conector."""

    @abstractmethod
    def disconnect(self) -> bool:
        """Cierra la conexion con el servicio externo."""

    def ping(self) -> bool:
        """Verifica la salud del conector."""
        if not self._connected:
            return False
        if self._circuit_state == CircuitState.OPEN and self._last_failure_time > 0:
            elapsed = time.time() - self._last_failure_time
            if elapsed < self._circuit_breaker_config.recovery_timeout:
                return False
        try:
            if not self._redis.ping():
                logger.warning(f"BaseConnector.ping: Redis no disponible para {self.name}")
        except Exception:
            pass
        return True

    def safe_execute(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ejecuta una accion de forma segura con todas las protecciones."""
        start_time = time.monotonic()
        params = params or {}
        last_exception: Exception | None = None
        retries_used = 0
        logger.info(f"BaseConnector.safe_execute: {self.name}.{action} inicio")

        self._check_circuit_breaker(action)
        self._check_rate_limit(action)

        if self._schema_validator:
            try:
                params = self._schema_validator.validate_input(action, params)
            except Exception as e:
                logger.warning(f"BaseConnector.safe_execute: validacion de entrada fallida para {action}: {e}")
                return self._build_result(success=False, error=str(e), start_time=start_time, action=action, retries=0)

        for attempt in range(self._retry_config.max_retries + 1):
            try:
                if not self._connected:
                    self.connect()
                if self._auth_provider and self._auth_provider.is_expired():
                    self._auth_provider.refresh()
                result = self.execute(action, params)
                if self._schema_validator and isinstance(result, dict):
                    try:
                        result = self._schema_validator.validate_output(action, result)
                    except Exception as e:
                        logger.warning(f"BaseConnector.safe_execute: validacion de salida fallida para {action}: {e}")
                self._on_success()
                duration = time.monotonic() - start_time
                self._record_metrics(action, "success", duration)
                logger.info(f"BaseConnector.safe_execute: {self.name}.{action} exito (duration={duration:.3f}s, retries={retries_used})")
                return self._build_result(success=True, data=result, start_time=start_time, action=action, retries=retries_used)
            except (CircuitBreakerOpenError, RateLimitError) as e:
                self._on_failure(action)
                duration = time.monotonic() - start_time
                self._record_metrics(action, "error", duration)
                return self._build_result(success=False, error=str(e), start_time=start_time, action=action, retries=retries_used)
            except Exception as e:
                last_exception = e
                retries_used = attempt
                if attempt < self._retry_config.max_retries:
                    delay = self._retry_config.get_delay(attempt)
                    logger.warning(f"BaseConnector.safe_execute: {self.name}.{action} fallo (intento {attempt + 1}/{self._retry_config.max_retries}): {type(e).__name__}: {e}. Reintentando en {delay:.1f}s")
                    time.sleep(delay)
                else:
                    self._on_failure(action)
                    duration = time.monotonic() - start_time
                    self._record_metrics(action, "error", duration)
                    logger.error(f"BaseConnector.safe_execute: {self.name}.{action} fallo definitivo despues de {self._retry_config.max_retries} reintentos: {e}")

        error_msg = str(last_exception) if last_exception else "Error desconocido"
        return self._build_result(success=False, error=error_msg, start_time=start_time, action=action, retries=retries_used)

    def get_schema(self) -> ConnectorSchema | None:
        return self._schema

    def get_action_names(self) -> list[str]:
        names = set(self._action_metadata.keys())
        if self._schema:
            names.update(self._schema.get_action_names())
        return sorted(names)

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.name, "version": self.version,
            "connected": self._connected, "healthy": self.ping(),
            "circuit_breaker": {
                "state": self._circuit_state, "failure_count": self._failure_count,
                "failure_threshold": self._circuit_breaker_config.failure_threshold,
                "recovery_timeout": self._circuit_breaker_config.recovery_timeout,
                "last_failure_time": self._last_failure_time,
            },
            "rate_limit": {"max_calls": self._rate_limit_config.max_calls, "period_seconds": self._rate_limit_config.period_seconds},
            "retry": {"max_retries": self._retry_config.max_retries, "backoff_factor": self._retry_config.backoff_factor},
            "actions": self.get_action_names(),
            "has_auth": self._auth_provider is not None,
            "auth_type": self._auth_provider.get_auth_type() if self._auth_provider else None,
            "connection_time": self._connection_time,
            "uptime_seconds": time.time() - self._connection_time if self._connection_time else 0,
        }

    def set_auth_provider(self, provider: AuthProvider) -> None:
        self._auth_provider = provider
        logger.debug(f"BaseConnector: auth provider configurado ({provider.get_auth_type()}) para {self.name}")

    def __enter__(self) -> BaseConnector:
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: types.TracebackType | None) -> bool:
        self.disconnect()
        if exc_type:
            logger.error(f"BaseConnector: excepcion en context manager para {self.name}: {exc_val}")
        return False

    def _check_circuit_breaker(self, action: str) -> None:
        if self._circuit_state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._circuit_breaker_config.recovery_timeout:
                self._circuit_state = CircuitState.HALF_OPEN
                logger.info(f"BaseConnector: circuit breaker HALF_OPEN para {self.name}.{action}")
            else:
                raise CircuitBreakerOpenError(
                    message=f"Circuit breaker OPEN para {self.name}.{action}", connector_name=self.name,
                    state=CircuitState.OPEN, failure_count=self._failure_count,
                    recovery_timeout=self._circuit_breaker_config.recovery_timeout,
                    last_failure_time=self._last_failure_time,
                )

    def _check_rate_limit(self, action: str) -> None:
        rate_key = f"sdk:ratelimit:{self.name}:{action}"
        try:
            result = self._redis.check_rate_limit(rate_key, self._rate_limit_config.max_calls, self._rate_limit_config.period_seconds)
            if not result["allowed"]:
                raise RateLimitError(
                    message=f"Rate limit excedido para {self.name}.{action}", connector_name=self.name,
                    max_calls=self._rate_limit_config.max_calls, period_seconds=self._rate_limit_config.period_seconds,
                    remaining=result.get("remaining", 0), reset_at=result.get("reset_at"),
                )
        except RateLimitError:
            raise
        except Exception:
            logger.debug(f"BaseConnector: rate limit check via Redis fallo para {self.name}.{action}, permitiendo")

    def _on_success(self) -> None:
        with self._lock:
            if self._circuit_state == CircuitState.HALF_OPEN:
                self._circuit_state = CircuitState.CLOSED
                logger.info(f"BaseConnector: circuit breaker CLOSED para {self.name}")
            self._failure_count = 0

    def _on_failure(self, action: str) -> None:
        with self._lock:
            self._failure_count += 1
            now = time.time()
            self._last_failure_time = now
            if self._circuit_state == CircuitState.HALF_OPEN:
                self._circuit_state = CircuitState.OPEN
                logger.warning(f"BaseConnector: circuit breaker OPEN (fallo en HALF_OPEN) para {self.name}")
            elif self._failure_count >= self._circuit_breaker_config.failure_threshold:
                self._circuit_state = CircuitState.OPEN
                logger.warning(f"BaseConnector: circuit breaker OPEN ({self._failure_count} fallos consecutivos) para {self.name}")

    def _record_metrics(self, action: str, status: str, duration: float) -> None:
        try:
            self._telemetry.record_connector_call(connector=self.name, action=action, status=status, duration=duration)
        except Exception:
            logger.debug(f"BaseConnector: error registrando metricas para {self.name}.{action}")

    # legítimo: data dinámica del resultado de conector
    def _build_result(self, success: bool, data: Any = None, error: str | None = None,
                      start_time: float = 0, action: str = "", retries: int = 0) -> dict[str, Any]:
        duration_ms = (time.monotonic() - start_time) * 1000 if start_time else 0
        return {
            "success": success, "data": data, "error": error,
            "duration_ms": round(duration_ms, 2), "action": action,
            "connector": self.name, "retries": retries,
            "circuit_breaker_state": self._circuit_state,
        }

    def _discover_actions(self) -> None:
        self._action_metadata = get_action_metadata(self.__class__)
        if self._action_metadata:
            logger.debug(f"BaseConnector: {len(self._action_metadata)} accion(es) descubierta(s) en {self.name}: {list(self._action_metadata.keys())}")

    def _build_auto_schema(self) -> ConnectorSchema:
        from src.sdk.schema import AuthRequirement
        actions = []
        for action_name, meta in self._action_metadata.items():
            action_def = ActionDefinition(
                name=action_name, description=meta.get("description", ""),
                input_schema=meta.get("input_schema"), output_schema=meta.get("output_schema"),
            )
            if meta.get("rate_limit"):
                action_def.rate_limit = meta["rate_limit"]
            if meta.get("retry_config"):
                action_def.timeout = 30
            actions.append(action_def)
        auth_reqs = []
        if self._auth_provider:
            auth_reqs.append(AuthRequirement(
                auth_type=self._auth_provider.get_auth_type(),
                description=f"Autenticacion {self._auth_provider.get_auth_type()} requerida",
            ))
        return ConnectorSchema(
            name=self.name or self.__class__.__name__.lower(), version=self.version,
            description=self.description, category=self.category, icon=self.icon,
            author=self.author, actions=actions, auth_requirements=auth_reqs,
        )

    def _log_operation(self, operation: str, details: str = "") -> None:
        msg = f"Connector[{self.name}].{operation}"
        if details:
            msg += f": {details}"
        logger.info(msg)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', version='{self.version}', connected={self._connected}, circuit={self._circuit_state})>"

    def __str__(self) -> str:
        return f"{self.name} v{self.version} ({'conectado' if self._connected else 'desconectado'})"
