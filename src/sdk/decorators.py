"""
Connector SDK — Decoradores para Desarrollo de Conectores
===========================================================

Provee decoradores que simplifican el desarrollo de conectores:

- @connector_action: Registra un metodo como accion del conector
- @rate_limit: Rate limiting por accion (sliding window via Redis)
- @retry: Reintento con backoff exponencial por accion
- @circuit_breaker: Circuit breaker por accion
- @validate_input: Validacion de entrada contra modelo Pydantic
- @validate_output: Validacion de salida contra modelo Pydantic
- @track_metrics: Registro automatico de metricas via TelemetryService

Los decoradores pueden combinarse para construir acciones robustas:

    @connector_action("send_email", "Envia un correo")
    @rate_limit(max_calls=100, period=60)
    @retry(max_retries=3, backoff=2.0)
    @validate_input(SendEmailInput)
    @validate_output(SendEmailOutput)
    @track_metrics()
    def send_email(self, params):
        ...
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from src.sdk.exceptions import (
    CircuitBreakerOpenError,
    RateLimitError,
    ValidationError,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ── Registro de acciones ──────────────────────────────────────

# Almacen global de acciones registradas por conector
_ACTIONS_REGISTRY: dict[str, dict[str, dict[str, Any]]] = {}


def connector_action(name: str, description: str = "") -> Callable[[F], F]:
    """
    Registra un metodo como accion del conector.

    Marca el metodo decorado como una accion disponible del conector,
    almacenando su nombre y descripcion en el registro de acciones.
    El BaseConnector usa esta informacion para construir el esquema
    automaticamente y despachar llamadas a la accion correcta.

    Args:
        name: Nombre unico de la accion (kebab-case recomendado)
        description: Descripcion legible de lo que hace la accion

    Retorna:
        Decorador que registra la accion y deja el metodo inalterado

    Ejemplo:
        @connector_action("list_contacts", "Lista contactos del CRM")
        def list_contacts(self, params):
            return self._api.get("/contacts", params)
    """

    def decorator(func: F) -> F:
        # Almacenar metadata de la accion en el metodo
        func._connector_action_name = name  # type: ignore[attr-defined]
        func._connector_action_description = description  # type: ignore[attr-defined]
        func._is_connector_action = True  # type: ignore[attr-defined]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        # Copiar la metadata al wrapper tambien
        wrapper._connector_action_name = name  # type: ignore[attr-defined]
        wrapper._connector_action_description = description  # type: ignore[attr-defined]
        wrapper._is_connector_action = True  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator


# ── Rate Limiting ─────────────────────────────────────────────


def rate_limit(max_calls: int = 60, period: int = 60) -> Callable[[F], F]:
    """
    Rate limiting por accion usando sliding window.

    Usa RedisService para implementar rate limiting distribuido
    con ventana deslizante. Si Redis no esta disponible, usa
    un fallback en memoria local.

    Args:
        max_calls: Maximo de llamadas permitidas en el periodo
        period: Duracion de la ventana en segundos

    Retorna:
        Decorador que aplica rate limiting a la accion

    Raises:
        RateLimitError: Si se excede el limite de frecuencia

    Ejemplo:
        @rate_limit(max_calls=100, period=60)
        def send_message(self, params):
            ...
    """

    def decorator(func: F) -> F:
        # Fallback en memoria si Redis no esta disponible
        local_calls: dict[str, list[float]] = {}
        local_lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Obtener nombre del conector para la clave de rate limit
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            rate_key = f"sdk:ratelimit:{connector_name}:{action_name}"

            # Intentar usar Redis primero
            try:
                from src.data.redis_service import RedisService

                redis = RedisService()
                result = redis.check_rate_limit(rate_key, max_calls, period)
                if not result["allowed"]:
                    raise RateLimitError(
                        message=f"Rate limit excedido para {connector_name}.{action_name}",
                        connector_name=connector_name,
                        max_calls=max_calls,
                        period_seconds=period,
                        remaining=result.get("remaining", 0),
                        reset_at=result.get("reset_at"),
                    )
            except RateLimitError:
                raise
            except Exception:
                # Fallback a rate limiting local en memoria
                with local_lock:
                    now = time.time()
                    window_start = now - period
                    calls = local_calls.get(rate_key, [])
                    # Filtrar llamadas dentro de la ventana
                    calls = [t for t in calls if t > window_start]
                    if len(calls) >= max_calls:
                        raise RateLimitError(
                            message=f"Rate limit excedido para {connector_name}.{action_name}",
                            connector_name=connector_name,
                            max_calls=max_calls,
                            period_seconds=period,
                            remaining=0,
                        ) from None
                    calls.append(now)
                    local_calls[rate_key] = calls

            return func(*args, **kwargs)

        wrapper._rate_limit = {"max_calls": max_calls, "period": period}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


# ── Retry con Backoff Exponencial ─────────────────────────────


def retry(max_retries: int = 3, backoff: float = 2.0, max_delay: float = 60.0) -> Callable[[F], F]:
    """
    Reintento automatico con backoff exponencial por accion.

    Cuando la accion lanza una excepcion, la reintentara hasta
    max_retries veces con un delay que aumenta exponencialmente:
    delay = min(base_delay * backoff ** attempt, max_delay)

    Args:
        max_retries: Numero maximo de reintentos (default: 3)
        backoff: Factor de multiplicacion del delay entre reintentos (default: 2.0)
        max_delay: Delay maximo entre reintentos en segundos (default: 60.0)

    Retorna:
        Decorador que aplica reintento automatico a la accion

    Ejemplo:
        @retry(max_retries=5, backoff=2.0, max_delay=120.0)
        def fetch_data(self, params):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(0.1 * (backoff**attempt), max_delay)
                        logger.warning(
                            f"Retry [{attempt + 1}/{max_retries}] para {connector_name}.{action_name}: "
                            f"{type(e).__name__}: {e}. Reintentando en {delay:.1f}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Retry agotado [{max_retries}] para {connector_name}.{action_name}: "
                            f"{type(e).__name__}: {e}"
                        )

            raise last_exception  # type: ignore[misc]

        wrapper._retry_config = {"max_retries": max_retries, "backoff": backoff, "max_delay": max_delay}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


# ── Circuit Breaker ────────────────────────────────────────────


def circuit_breaker(threshold: int = 5, recovery: float = 30.0) -> Callable[[F], F]:
    """
    Circuit breaker por accion.

    Implementa el patron Circuit Breaker con tres estados:
    - CLOSED: Funcionamiento normal, se cuentan los fallos
    - OPEN: Se bloquean todas las llamadas hasta que pase recovery_timeout
    - HALF_OPEN: Se permite una llamada de prueba para verificar si el servicio se recupero

    El estado se almacena en Redis para compartirse entre instancias.
    Si Redis no esta disponible, se usa un fallback en memoria local.

    Args:
        threshold: Numero de fallos consecutivos para abrir el circuito (default: 5)
        recovery: Segundos hasta pasar de OPEN a HALF_OPEN (default: 30.0)

    Retorna:
        Decorador que aplica circuit breaker a la accion

    Raises:
        CircuitBreakerOpenError: Si el circuito esta abierto

    Ejemplo:
        @circuit_breaker(threshold=3, recovery=60.0)
        def call_external_api(self, params):
            ...
    """

    def decorator(func: F) -> F:
        # Fallback local en memoria
        cb_state: dict[str, dict[str, Any]] = {}
        cb_lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            cb_key = f"sdk:circuitbreaker:{connector_name}:{action_name}"

            # Intentar usar Redis para estado del circuit breaker
            state_data = _get_cb_state_redis(cb_key)
            if state_data is None:
                # Fallback a memoria local
                with cb_lock:
                    state_data = cb_state.get(cb_key, {"state": "CLOSED", "failure_count": 0, "last_failure_time": 0})

            current_state = state_data["state"]
            failure_count = state_data["failure_count"]
            last_failure_time = state_data.get("last_failure_time", 0)

            # Verificar si debemos pasar de OPEN a HALF_OPEN
            if current_state == "OPEN":
                time_since_failure = time.time() - last_failure_time
                if time_since_failure >= recovery:
                    current_state = "HALF_OPEN"
                    logger.info(f"Circuit breaker HALF_OPEN para {connector_name}.{action_name}")
                else:
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker OPEN para {connector_name}.{action_name}",
                        connector_name=connector_name,
                        state="OPEN",
                        failure_count=failure_count,
                        recovery_timeout=recovery,
                        last_failure_time=last_failure_time,
                    )

            # Ejecutar la accion
            try:
                result = func(*args, **kwargs)

                # Si la llamada fue exitosa y estabamos en HALF_OPEN, cerrar el circuito
                if current_state == "HALF_OPEN":
                    _update_cb_state(cb_key, cb_state, cb_lock, "CLOSED", 0)
                    logger.info(f"Circuit breaker CLOSED para {connector_name}.{action_name}")
                elif current_state == "CLOSED" and failure_count > 0:
                    # Resetear el contador de fallos en exito
                    _update_cb_state(cb_key, cb_state, cb_lock, "CLOSED", 0)

                return result

            except CircuitBreakerOpenError:
                raise
            except Exception as e:
                # Incrementar contador de fallos
                new_failure_count = failure_count + 1
                now = time.time()

                if current_state == "HALF_OPEN":
                    # Si falla en HALF_OPEN, volver a OPEN
                    _update_cb_state(cb_key, cb_state, cb_lock, "OPEN", new_failure_count, now)
                    logger.warning(f"Circuit breaker OPEN (falla en HALF_OPEN) para {connector_name}.{action_name}")
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker OPEN para {connector_name}.{action_name}",
                        connector_name=connector_name,
                        state="OPEN",
                        failure_count=new_failure_count,
                        recovery_timeout=recovery,
                    ) from e
                elif new_failure_count >= threshold:
                    # Alcanzo el umbral, abrir el circuito
                    _update_cb_state(cb_key, cb_state, cb_lock, "OPEN", new_failure_count, now)
                    logger.warning(
                        f"Circuit breaker OPEN ({new_failure_count} fallos consecutivos) "
                        f"para {connector_name}.{action_name}"
                    )
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker OPEN para {connector_name}.{action_name}",
                        connector_name=connector_name,
                        state="OPEN",
                        failure_count=new_failure_count,
                        recovery_timeout=recovery,
                        last_failure_time=now,
                    ) from e
                else:
                    # Aun en CLOSED, solo incrementar contador
                    _update_cb_state(cb_key, cb_state, cb_lock, "CLOSED", new_failure_count, now)
                    logger.debug(
                        f"Circuit breaker: fallo {new_failure_count}/{threshold} para {connector_name}.{action_name}"
                    )
                raise

        wrapper._circuit_breaker_config = {"threshold": threshold, "recovery": recovery}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def _get_cb_state_redis(cb_key: str) -> dict[str, Any] | None:
    """Obtiene el estado del circuit breaker desde Redis."""
    try:
        from src.data.redis_service import RedisService

        redis = RedisService()
        return redis.get_json(cb_key)
    except Exception:
        return None


def _update_cb_state(
    cb_key: str,
    cb_local_state: dict[str, dict[str, Any]],
    cb_lock: threading.Lock,
    state: str,
    failure_count: int,
    last_failure_time: float | None = None,
) -> None:
    """Actualiza el estado del circuit breaker en Redis y localmente."""
    now = last_failure_time or time.time()
    state_data = {"state": state, "failure_count": failure_count, "last_failure_time": now}

    # Actualizar Redis
    try:
        from src.data.redis_service import RedisService

        redis = RedisService()
        redis.set_json(cb_key, state_data, ttl=300)
    except Exception:
        pass

    # Actualizar estado local como fallback
    with cb_lock:
        cb_local_state[cb_key] = state_data


# ── Validacion de Entrada/Salida ──────────────────────────────


def validate_input(schema: type[BaseModel]) -> Callable[[F], F]:
    """
    Valida los parametros de entrada de una accion contra un modelo Pydantic.

    El decorador asume que el primer argumento posicional despues de self
    (params) es un diccionario que sera validado contra el modelo Pydantic.
    Si la validacion falla, se lanza una ValidationError con detalles.

    Args:
        schema: Modelo Pydantic contra el cual validar los parametros

    Retorna:
        Decorador que valida la entrada antes de ejecutar la accion

    Raises:
        ValidationError: Si los datos de entrada no cumplen el esquema

    Ejemplo:
        class SendEmailInput(BaseModel):
            to: str
            subject: str

        @validate_input(SendEmailInput)
        def send_email(self, params):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)

            # Buscar el parametro 'params' en args (despues de self) o en kwargs
            if len(args) > 1 and isinstance(args[1], dict):
                params_data = args[1]
            elif "params" in kwargs and isinstance(kwargs["params"], dict):
                params_data = kwargs["params"]
            else:
                params_data = kwargs

            try:
                validated = schema.model_validate(params_data)
                # Reemplazar params con datos validados
                if len(args) > 1 and isinstance(args[1], dict):
                    args = (args[0], validated.model_dump(), *args[2:])  # type: ignore[assignment]
                elif "params" in kwargs:
                    kwargs["params"] = validated.model_dump()
                else:
                    kwargs = validated.model_dump()
            except Exception as e:
                raise ValidationError.from_pydantic(
                    validation_exception=e,
                    connector_name=connector_name,
                    action=action_name,
                ) from e

            return func(*args, **kwargs)

        wrapper._input_schema = schema  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def validate_output(schema: type[BaseModel]) -> Callable[[F], F]:
    """
    Valida el resultado de una accion contra un modelo Pydantic.

    Despues de ejecutar la accion, valida que el resultado cumpla
    con el esquema de salida definido. Si la validacion falla,
    se lanza una ValidationError.

    Args:
        schema: Modelo Pydantic contra el cual validar el resultado

    Retorna:
        Decorador que valida la salida despues de ejecutar la accion

    Raises:
        ValidationError: Si el resultado no cumple el esquema de salida

    Ejemplo:
        class SendEmailOutput(BaseModel):
            message_id: str
            status: str

        @validate_output(SendEmailOutput)
        def send_email(self, params):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)

            result = func(*args, **kwargs)

            # Solo validar si el resultado es un diccionario
            if isinstance(result, dict):
                try:
                    schema.model_validate(result)
                except Exception as e:
                    raise ValidationError.from_pydantic(
                        validation_exception=e,
                        connector_name=connector_name,
                        action=action_name,
                    ) from e

            return result

        wrapper._output_schema = schema  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


# ── Tracking de Metricas ──────────────────────────────────────


def track_metrics() -> Callable[[F], F]:
    """
    Registro automatico de metricas de la accion via TelemetryService.

    Registra automaticamente la duracion de la accion, el estado
    (success/error) y la incrementa el contador de llamadas al
    conector. Usa TelemetryService para la observabilidad.

    Retorna:
        Decorador que registra metricas de la accion

    Ejemplo:
        @track_metrics()
        def fetch_data(self, params):
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            start_time = time.monotonic()

            try:
                result = func(*args, **kwargs)
                duration = time.monotonic() - start_time
                _record_metrics(connector_name, action_name, "success", duration)
                return result
            except Exception:
                duration = time.monotonic() - start_time
                _record_metrics(connector_name, action_name, "error", duration)
                raise

        wrapper._track_metrics = True  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def _record_metrics(connector_name: str, action: str, status: str, duration: float) -> None:
    """
    Registra metricas de una accion via TelemetryService.

    Intenta usar TelemetryService para registrar las metricas.
    Si no esta disponible, registra solo en el log.

    Args:
        connector_name: Nombre del conector
        action: Nombre de la accion
        status: Estado de la ejecucion ('success' o 'error')
        duration: Duracion en segundos
    """
    try:
        from src.observability.telemetry import TelemetryService

        telemetry = TelemetryService()
        telemetry.record_connector_call(
            connector=connector_name,
            action=action,
            status=status,
            duration=duration,
        )
    except Exception:
        # Si TelemetryService no esta disponible, solo log
        logger.debug(f"Metrics: {connector_name}.{action} status={status} duration={duration:.3f}s")


# ── Utilidades ────────────────────────────────────────────────


def _get_connector_name(args: tuple[Any, ...]) -> str:
    """
    Extrae el nombre del conector desde los argumentos del metodo.

    Busca el atributo 'name' en el primer argumento (self),
    o usa el nombre de la clase como fallback.

    Args:
        args: Argumentos posicionales del metodo decorado

    Retorna:
        Nombre del conector o 'unknown'
    """
    if args and hasattr(args[0], "name"):
        return str(args[0].name)
    if args and hasattr(args[0], "__class__"):
        return args[0].__class__.__name__.lower()
    return "unknown"


def get_action_metadata(cls: type) -> dict[str, dict[str, Any]]:
    """
    Extrae metadata de todas las acciones registradas en una clase.

    Inspecciona los metodos de la clase buscando los marcados con
    @connector_action y recopila su metadata (nombre, descripcion,
    configuracion de rate limiting, retry, circuit breaker, etc.).

    Args:
        cls: Clase del conector a inspeccionar

    Retorna:
        Diccionario de nombre_accion -> metadata
    """
    actions: dict[str, dict[str, Any]] = {}
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if attr is None:
            continue
        if not getattr(attr, "_is_connector_action", False):
            continue

        action_name = getattr(attr, "_connector_action_name", attr_name)
        actions[action_name] = {
            "method_name": attr_name,
            "description": getattr(attr, "_connector_action_description", ""),
            "rate_limit": getattr(attr, "_rate_limit", None),
            "retry_config": getattr(attr, "_retry_config", None),
            "circuit_breaker_config": getattr(attr, "_circuit_breaker_config", None),
            "input_schema": getattr(attr, "_input_schema", None),
            "output_schema": getattr(attr, "_output_schema", None),
            "track_metrics": getattr(attr, "_track_metrics", False),
        }

    return actions
