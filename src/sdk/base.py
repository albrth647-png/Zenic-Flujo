"""
Connector SDK — Clase Base Abstracta del Conector
===================================================

BaseConnector es la clase base que todos los conectores deben heredar.
Provee funcionalidad integrada para:

- Conectar/desconectar con servicios externos
- Ejecutar acciones con validacion automatica
- Reintentar operaciones fallidas con backoff exponencial
- Proteger el servicio con circuit breaker
- Limitar la tasa de llamadas con rate limiting
- Registrar metricas automaticamente
- Verificar la salud del servicio con ping()
- Gestionar el ciclo de vida como context manager

Uso tipico:
    class SlackConnector(BaseConnector):
        name = "slack"
        version = "1.0.0"
        description = "Conector para Slack"

        def connect(self):
            # Logica de conexion
            pass

        def disconnect(self):
            # Logica de desconexion
            pass

        def execute(self, action, params):
            # Despachar acciones
            pass

        def validate(self):
            # Validar configuracion
            pass

    with SlackConnector() as slack:
        result = slack.execute("send_message", {"channel": "#general", "text": "Hola"})
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from src.data.redis_service import RedisService
from src.observability.telemetry import TelemetryService
from src.sdk.auth import AuthProvider
from src.sdk.decorators import get_action_metadata
from src.sdk.exceptions import (
    CircuitBreakerOpenError,
    RateLimitError,
)
from src.sdk.schema import ActionDefinition, ConnectorSchema, SchemaValidator
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


# ── Estados del Circuit Breaker ────────────────────────────────


class CircuitState:
    """Estados posibles del circuit breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ── Configuracion de Reintentos ────────────────────────────────


class RetryConfig:
    """
    Configuracion de reintentos con backoff exponencial.

    Attributes:
        max_retries: Numero maximo de reintentos
        base_delay: Delay base en segundos para el primer reintento
        max_delay: Delay maximo entre reintentos
        backoff_factor: Factor de multiplicacion del delay
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def get_delay(self, attempt: int) -> float:
        """
        Calcula el delay para un intento dado.

        Args:
            attempt: Numero de intento (0-based)

        Retorna:
            Delay en segundos, limitado por max_delay
        """
        delay = self.base_delay * (self.backoff_factor**attempt)
        return min(delay, self.max_delay)


# ── Configuracion del Circuit Breaker ──────────────────────────


class CircuitBreakerConfig:
    """
    Configuracion del circuit breaker.

    Attributes:
        failure_threshold: Numero de fallos consecutivos para abrir el circuito
        recovery_timeout: Segundos antes de pasar de OPEN a HALF_OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout


# ── Configuracion de Rate Limiting ─────────────────────────────


class RateLimitConfig:
    """
    Configuracion de rate limiting (sliding window).

    Attributes:
        max_calls: Maximo de llamadas permitidas en el periodo
        period_seconds: Duracion de la ventana en segundos
    """

    def __init__(
        self,
        max_calls: int = 60,
        period_seconds: int = 60,
    ) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds


# ── BaseConnector ──────────────────────────────────────────────


class BaseConnector(ABC):
    """
    Clase base abstracta para todos los conectores de Zenic-Flijo.

    Provee la infraestructura comun que todo conector necesita:
    conexion, ejecucion de acciones, validacion, reintentos,
    circuit breaker, rate limiting, metricas y logging.

    Subclases deben implementar los metodos abstractos:
    - connect(): Establece la conexion con el servicio externo
    - execute(action, params): Ejecuta una accion del conector
    - validate(): Valida la configuracion del conector
    - disconnect(): Cierra la conexion con el servicio externo

    Atributos de clase (sobreescribir en subclases):
        name: Nombre unico del conector
        version: Version del conector (semver)
        description: Descripcion del conector
        category: Categoria del conector
        icon: Icono del conector
        author: Autor del conector

    Attributes:
        _connected: Estado de conexion
        _auth_provider: Proveedor de autenticacion
        _retry_config: Configuracion de reintentos
        _circuit_breaker_config: Configuracion del circuit breaker
        _rate_limit_config: Configuracion de rate limiting
        _circuit_state: Estado actual del circuit breaker
        _failure_count: Contador de fallos consecutivos
        _last_failure_time: Timestamp del ultimo fallo
        _schema: Esquema del conector
        _schema_validator: Validador de esquemas
    """

    # ── Metadata del conector (sobreescribir en subclases) ─────
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

        # Auto-descubrir acciones decoradas
        self._discover_actions()

        # Construir esquema automaticamente si no se proporciono
        if self._schema is None:
            self._schema = self._build_auto_schema()

        if self._schema:
            self._schema_validator = SchemaValidator(self._schema)

        logger.debug(f"BaseConnector: instancia creada para '{self.name}'")

    # ── Metodos abstractos ────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """
        Establece la conexion con el servicio externo.

        Debe ser implementado por cada conector para manejar
        la logica especifica de conexion al servicio.

        Retorna:
            True si la conexion fue exitosa

        Raises:
            ConnectionError: Si no se puede establecer la conexion
            AuthenticationError: Si la autenticacion falla
        """

    @abstractmethod
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """
        Ejecuta una accion del conector.

        Debe ser implementado por cada conector para despachar
        la accion solicitada con los parametros proporcionados.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion

        Retorna:
            Resultado de la accion

        Raises:
            ActionNotFoundError: Si la accion no existe
            ValidationError: Si los parametros son invalidos
            ConnectorError: Si ocurre un error durante la ejecucion
        """

    @abstractmethod
    def validate(self) -> bool:
        """
        Valida la configuracion del conector.

        Verifica que todos los parametros necesarios esten
        configurados correctamente antes de intentar conectar.

        Retorna:
            True si la configuracion es valida
        """

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Cierra la conexion con el servicio externo.

        Debe liberar todos los recursos y cerrar las conexiones
        abiertas de forma elegante.

        Retorna:
            True si la desconexion fue exitosa
        """

    # ── Metodos integrados ────────────────────────────────────

    def ping(self) -> bool:
        """
        Verifica la salud del conector.

        Realiza una verificacion rapida de que el conector esta
        conectado y el servicio responde. Usa Redis para verificar
        la disponibilidad del servicio si es posible.

        Retorna:
            True si el conector esta saludable y conectado
        """
        if not self._connected:
            return False

        # Verificar que el circuit breaker no este abierto
        if self._circuit_state == CircuitState.OPEN and self._last_failure_time > 0:
            elapsed = time.time() - self._last_failure_time
            if elapsed < self._circuit_breaker_config.recovery_timeout:
                return False

        # Verificar conexion con Redis
        try:
            if not self._redis.ping():
                logger.warning(f"BaseConnector.ping: Redis no disponible para {self.name}")
        except Exception:
            pass  # Redis no es obligatorio para el ping

        return True

    def safe_execute(self, action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Ejecuta una accion de forma segura con todas las protecciones.

        Aplica automaticamente:
        1. Validacion de entrada contra esquema
        2. Rate limiting
        3. Verificacion del circuit breaker
        4. Reintento con backoff exponencial en caso de fallo
        5. Validacion de salida contra esquema
        6. Registro de metricas
        7. Logging estructurado

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion

        Retorna:
            Diccionario con resultado y metadata:
            {
                "success": bool,
                "data": Any,
                "error": str | None,
                "duration_ms": float,
                "retries": int,
                "action": str
            }
        """
        start_time = time.monotonic()
        params = params or {}
        last_exception: Exception | None = None
        retries_used = 0

        logger.info(f"BaseConnector.safe_execute: {self.name}.{action} inicio")

        # 1. Verificar circuit breaker
        self._check_circuit_breaker(action)

        # 2. Verificar rate limiting
        self._check_rate_limit(action)

        # 3. Validar entrada contra esquema
        if self._schema_validator:
            try:
                params = self._schema_validator.validate_input(action, params)
            except Exception as e:
                logger.warning(f"BaseConnector.safe_execute: validacion de entrada fallida para {action}: {e}")
                return self._build_result(success=False, error=str(e), start_time=start_time, action=action, retries=0)

        # 4. Ejecutar con reintentos
        for attempt in range(self._retry_config.max_retries + 1):
            try:
                # Auto-conectar si no estamos conectados
                if not self._connected:
                    self.connect()

                # Aplicar autenticacion si hay provider
                if self._auth_provider and self._auth_provider.is_expired():
                    self._auth_provider.refresh()

                # Ejecutar la accion
                result = self.execute(action, params)

                # Validar salida contra esquema
                if self._schema_validator and isinstance(result, dict):
                    try:
                        result = self._schema_validator.validate_output(action, result)
                    except Exception as e:
                        logger.warning(f"BaseConnector.safe_execute: validacion de salida fallida para {action}: {e}")

                # Resetear circuit breaker en exito
                self._on_success()

                # Registrar metricas
                duration = time.monotonic() - start_time
                self._record_metrics(action, "success", duration)

                logger.info(
                    f"BaseConnector.safe_execute: {self.name}.{action} exito "
                    f"(duration={duration:.3f}s, retries={retries_used})"
                )

                return self._build_result(
                    success=True, data=result, start_time=start_time, action=action, retries=retries_used
                )

            except (CircuitBreakerOpenError, RateLimitError) as e:
                # No reintentar errores de circuit breaker o rate limit
                self._on_failure(action)
                duration = time.monotonic() - start_time
                self._record_metrics(action, "error", duration)
                return self._build_result(
                    success=False, error=str(e), start_time=start_time, action=action, retries=retries_used
                )

            except Exception as e:
                last_exception = e
                retries_used = attempt

                if attempt < self._retry_config.max_retries:
                    delay = self._retry_config.get_delay(attempt)
                    logger.warning(
                        f"BaseConnector.safe_execute: {self.name}.{action} fallo "
                        f"(intento {attempt + 1}/{self._retry_config.max_retries}): "
                        f"{type(e).__name__}: {e}. Reintentando en {delay:.1f}s"
                    )
                    time.sleep(delay)
                else:
                    self._on_failure(action)
                    duration = time.monotonic() - start_time
                    self._record_metrics(action, "error", duration)
                    logger.error(
                        f"BaseConnector.safe_execute: {self.name}.{action} fallo definitivo "
                        f"despues de {self._retry_config.max_retries} reintentos: {e}"
                    )

        # No deberia llegar aqui, pero por seguridad
        error_msg = str(last_exception) if last_exception else "Error desconocido"
        return self._build_result(
            success=False, error=error_msg, start_time=start_time, action=action, retries=retries_used
        )

    def get_schema(self) -> ConnectorSchema | None:
        """
        Obtiene el esquema del conector.

        Retorna:
            Esquema del conector, o None si no esta definido
        """
        return self._schema

    def get_action_names(self) -> list[str]:
        """
        Obtiene los nombres de todas las acciones disponibles.

        Incluye acciones definidas en el esquema y acciones
        descubiertas automaticamente por decoradores.

        Retorna:
            Lista de nombres de acciones
        """
        names = set(self._action_metadata.keys())
        if self._schema:
            names.update(self._schema.get_action_names())
        return sorted(names)

    def get_status(self) -> dict[str, Any]:
        """
        Obtiene el estado actual del conector.

        Retorna un diccionario con informacion sobre el estado
        de conexion, circuit breaker, rate limiting y acciones.

        Retorna:
            Diccionario con el estado completo del conector
        """
        return {
            "name": self.name,
            "version": self.version,
            "connected": self._connected,
            "healthy": self.ping(),
            "circuit_breaker": {
                "state": self._circuit_state,
                "failure_count": self._failure_count,
                "failure_threshold": self._circuit_breaker_config.failure_threshold,
                "recovery_timeout": self._circuit_breaker_config.recovery_timeout,
                "last_failure_time": self._last_failure_time,
            },
            "rate_limit": {
                "max_calls": self._rate_limit_config.max_calls,
                "period_seconds": self._rate_limit_config.period_seconds,
            },
            "retry": {
                "max_retries": self._retry_config.max_retries,
                "backoff_factor": self._retry_config.backoff_factor,
            },
            "actions": self.get_action_names(),
            "has_auth": self._auth_provider is not None,
            "auth_type": self._auth_provider.get_auth_type() if self._auth_provider else None,
            "connection_time": self._connection_time,
            "uptime_seconds": time.time() - self._connection_time if self._connection_time else 0,
        }

    def set_auth_provider(self, provider: AuthProvider) -> None:
        """
        Establece el proveedor de autenticacion.

        Args:
            provider: Proveedor de autenticacion a usar
        """
        self._auth_provider = provider
        logger.debug(f"BaseConnector: auth provider configurado ({provider.get_auth_type()}) para {self.name}")

    # ── Context Manager ───────────────────────────────────────

    def __enter__(self) -> BaseConnector:
        """
        Entra al context manager, conectando automaticamente.

        Retorna:
            La instancia del conector conectada
        """
        self.connect()
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any) -> bool:
        """
        Sale del context manager, desconectando automaticamente.

        Args:
            exc_type: Tipo de excepcion si ocurrio una
            exc_val: Valor de la excepcion
            exc_tb: Traceback de la excepcion

        Retorna:
            False para no suprimir excepciones
        """
        self.disconnect()
        if exc_type:
            logger.error(f"BaseConnector: excepcion en context manager para {self.name}: {exc_val}")
        return False

    # ── Metodos protegidos ────────────────────────────────────

    def _check_circuit_breaker(self, action: str) -> None:
        """
        Verifica el estado del circuit breaker antes de ejecutar.

        Lanza excepcion si el circuito esta abierto y no ha pasado
        el tiempo de recuperacion.

        Args:
            action: Nombre de la accion (para logging)

        Raises:
            CircuitBreakerOpenError: Si el circuito esta abierto
        """
        if self._circuit_state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self._circuit_breaker_config.recovery_timeout:
                # Pasar a HALF_OPEN
                self._circuit_state = CircuitState.HALF_OPEN
                logger.info(f"BaseConnector: circuit breaker HALF_OPEN para {self.name}.{action}")
            else:
                raise CircuitBreakerOpenError(
                    message=f"Circuit breaker OPEN para {self.name}.{action}",
                    connector_name=self.name,
                    state=CircuitState.OPEN,
                    failure_count=self._failure_count,
                    recovery_timeout=self._circuit_breaker_config.recovery_timeout,
                    last_failure_time=self._last_failure_time,
                )

    def _check_rate_limit(self, action: str) -> None:
        """
        Verifica el rate limiting antes de ejecutar.

        Usa Redis para rate limiting distribuido. Si Redis no
        esta disponible, permite la ejecucion (fail open).

        Args:
            action: Nombre de la accion

        Raises:
            RateLimitError: Si se excede el limite de frecuencia
        """
        rate_key = f"sdk:ratelimit:{self.name}:{action}"
        try:
            result = self._redis.check_rate_limit(
                rate_key,
                self._rate_limit_config.max_calls,
                self._rate_limit_config.period_seconds,
            )
            if not result["allowed"]:
                raise RateLimitError(
                    message=f"Rate limit excedido para {self.name}.{action}",
                    connector_name=self.name,
                    max_calls=self._rate_limit_config.max_calls,
                    period_seconds=self._rate_limit_config.period_seconds,
                    remaining=result.get("remaining", 0),
                    reset_at=result.get("reset_at"),
                )
        except RateLimitError:
            raise
        except Exception:
            logger.debug(f"BaseConnector: rate limit check via Redis fallo para {self.name}.{action}, permitiendo")

    def _on_success(self) -> None:
        """
        Marca una ejecucion exitosa.

        Resetea el contador de fallos del circuit breaker
        y, si estaba en HALF_OPEN, pasa a CLOSED.
        """
        with self._lock:
            if self._circuit_state == CircuitState.HALF_OPEN:
                self._circuit_state = CircuitState.CLOSED
                logger.info(f"BaseConnector: circuit breaker CLOSED para {self.name}")
            self._failure_count = 0

    def _on_failure(self, action: str) -> None:
        """
        Registra un fallo en la ejecucion.

        Incrementa el contador de fallos del circuit breaker
        y, si alcanza el umbral, abre el circuito.

        Args:
            action: Nombre de la accion que fallo
        """
        with self._lock:
            self._failure_count += 1
            now = time.time()
            self._last_failure_time = now

            if self._circuit_state == CircuitState.HALF_OPEN:
                # Fallo en HALF_OPEN: volver a OPEN
                self._circuit_state = CircuitState.OPEN
                logger.warning(f"BaseConnector: circuit breaker OPEN (fallo en HALF_OPEN) para {self.name}")
            elif self._failure_count >= self._circuit_breaker_config.failure_threshold:
                # Alcanzo el umbral: abrir circuito
                self._circuit_state = CircuitState.OPEN
                logger.warning(
                    f"BaseConnector: circuit breaker OPEN ({self._failure_count} fallos consecutivos) para {self.name}"
                )

    def _record_metrics(self, action: str, status: str, duration: float) -> None:
        """
        Registra metricas de una ejecucion via TelemetryService.

        Args:
            action: Nombre de la accion
            status: Estado de la ejecucion ('success' o 'error')
            duration: Duracion en segundos
        """
        try:
            self._telemetry.record_connector_call(
                connector=self.name,
                action=action,
                status=status,
                duration=duration,
            )
        except Exception:
            logger.debug(f"BaseConnector: error registrando metricas para {self.name}.{action}")

    def _build_result(
        self,
        success: bool,
        data: Any = None,
        error: str | None = None,
        start_time: float = 0,
        action: str = "",
        retries: int = 0,
    ) -> dict[str, Any]:
        """
        Construye el diccionario de resultado estandarizado.

        Args:
            success: Si la ejecucion fue exitosa
            data: Resultado de la ejecucion
            error: Mensaje de error si fallo
            start_time: Timestamp de inicio para calcular duracion
            action: Nombre de la accion ejecutada
            retries: Numero de reintentos utilizados

        Retorna:
            Diccionario con resultado y metadata
        """
        duration_ms = (time.monotonic() - start_time) * 1000 if start_time else 0
        return {
            "success": success,
            "data": data,
            "error": error,
            "duration_ms": round(duration_ms, 2),
            "action": action,
            "connector": self.name,
            "retries": retries,
            "circuit_breaker_state": self._circuit_state,
        }

    def _discover_actions(self) -> None:
        """
        Descubre acciones decoradas con @connector_action en la clase.

        Inspecciona todos los metodos de la clase buscando los
        marcados con el decorador @connector_action y registra
        su metadata para uso interno.
        """
        self._action_metadata = get_action_metadata(self.__class__)
        if self._action_metadata:
            logger.debug(
                f"BaseConnector: {len(self._action_metadata)} accion(es) "
                f"descubierta(s) en {self.name}: {list(self._action_metadata.keys())}"
            )

    def _build_auto_schema(self) -> ConnectorSchema:
        """
        Construye el esquema del conector automaticamente.

        Usa la metadata de la clase y las acciones descubiertas
        para generar un ConnectorSchema completo.

        Retorna:
            Esquema del conector generado automaticamente
        """
        from src.sdk.schema import AuthRequirement

        actions = []
        for action_name, meta in self._action_metadata.items():
            action_def = ActionDefinition(
                name=action_name,
                description=meta.get("description", ""),
                input_schema=meta.get("input_schema"),
                output_schema=meta.get("output_schema"),
            )
            if meta.get("rate_limit"):
                action_def.rate_limit = meta["rate_limit"]
            if meta.get("retry_config"):
                action_def.timeout = 30  # Default timeout
            actions.append(action_def)

        auth_reqs = []
        if self._auth_provider:
            auth_reqs.append(
                AuthRequirement(
                    auth_type=self._auth_provider.get_auth_type(),
                    description=f"Autenticacion {self._auth_provider.get_auth_type()} requerida",
                )
            )

        return ConnectorSchema(
            name=self.name or self.__class__.__name__.lower(),
            version=self.version,
            description=self.description,
            category=self.category,
            icon=self.icon,
            author=self.author,
            actions=actions,
            auth_requirements=auth_reqs,
        )

    # ── Logging integrado ─────────────────────────────────────

    def _log_operation(self, operation: str, details: str = "") -> None:
        """
        Registra una operacion del conector en el log.

        Args:
            operation: Nombre de la operacion (connect, execute, disconnect, etc.)
            details: Detalles adicionales de la operacion
        """
        msg = f"Connector[{self.name}].{operation}"
        if details:
            msg += f": {details}"
        logger.info(msg)

    # ── Representacion ────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}(name='{self.name}', "
            f"version='{self.version}', connected={self._connected}, "
            f"circuit={self._circuit_state})>"
        )

    def __str__(self) -> str:
        return f"{self.name} v{self.version} ({'conectado' if self._connected else 'desconectado'})"
