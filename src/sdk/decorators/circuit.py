"""circuit_breaker decorator — Circuit breaker por accion.

Extracted from src/sdk/decorators.py.
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.sdk.decorators._helpers import _get_connector_name
from src.sdk.exceptions import CircuitBreakerOpenError
from src.core.logging import setup_logging

logger = setup_logging(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def circuit_breaker(threshold: int = 5, recovery: float = 30.0) -> Callable[[F], F]:
    """Circuit breaker por accion con tres estados: CLOSED, OPEN, HALF_OPEN."""
    def decorator(func: F) -> F:
        cb_state: dict[str, dict[str, Any]] = {}
        cb_lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            cb_key = f"sdk:circuitbreaker:{connector_name}:{action_name}"

            state_data = _get_cb_state_redis(cb_key)
            if state_data is None:
                with cb_lock:
                    state_data = cb_state.get(cb_key, {"state": "CLOSED", "failure_count": 0, "last_failure_time": 0})

            current_state = state_data["state"]
            failure_count = state_data["failure_count"]
            last_failure_time = state_data.get("last_failure_time", 0)

            if current_state == "OPEN":
                time_since_failure = time.time() - last_failure_time
                if time_since_failure >= recovery:
                    current_state = "HALF_OPEN"
                    logger.info(f"Circuit breaker HALF_OPEN para {connector_name}.{action_name}")
                else:
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker OPEN para {connector_name}.{action_name}",
                        connector_name=connector_name, state="OPEN",
                        failure_count=failure_count, recovery_timeout=recovery,
                        last_failure_time=last_failure_time,
                    )

            try:
                result = func(*args, **kwargs)
                if current_state == "HALF_OPEN":
                    _update_cb_state(cb_key, cb_state, cb_lock, "CLOSED", 0)
                    logger.info(f"Circuit breaker CLOSED para {connector_name}.{action_name}")
                elif current_state == "CLOSED" and failure_count > 0:
                    _update_cb_state(cb_key, cb_state, cb_lock, "CLOSED", 0)
                return result
            except CircuitBreakerOpenError:
                raise
            except Exception as e:
                new_failure_count = failure_count + 1
                now = time.time()
                if current_state == "HALF_OPEN":
                    _update_cb_state(cb_key, cb_state, cb_lock, "OPEN", new_failure_count, now)
                    logger.warning(f"Circuit breaker OPEN (falla en HALF_OPEN) para {connector_name}.{action_name}")
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker OPEN para {connector_name}.{action_name}",
                        connector_name=connector_name, state="OPEN", failure_count=new_failure_count,
                        recovery_timeout=recovery,
                    ) from e
                elif new_failure_count >= threshold:
                    _update_cb_state(cb_key, cb_state, cb_lock, "OPEN", new_failure_count, now)
                    logger.warning(f"Circuit breaker OPEN ({new_failure_count} fallos consecutivos) para {connector_name}.{action_name}")
                    raise CircuitBreakerOpenError(
                        message=f"Circuit breaker OPEN para {connector_name}.{action_name}",
                        connector_name=connector_name, state="OPEN", failure_count=new_failure_count,
                        recovery_timeout=recovery, last_failure_time=now,
                    ) from e
                else:
                    _update_cb_state(cb_key, cb_state, cb_lock, "CLOSED", new_failure_count, now)
                    logger.debug(f"Circuit breaker: fallo {new_failure_count}/{threshold} para {connector_name}.{action_name}")
                raise

        wrapper._circuit_breaker_config = {"threshold": threshold, "recovery": recovery}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def _get_cb_state_redis(cb_key: str) -> dict[str, Any] | None:
    """Obtiene el estado del circuit breaker desde Redis."""
    try:
        from src.core.db import RedisService
        redis = RedisService()
        return redis.get_json(cb_key)
    except Exception:
        return None


def _update_cb_state(cb_key: str, cb_local_state: dict[str, dict[str, Any]],
                     cb_lock: threading.Lock, state: str, failure_count: int,
                     last_failure_time: float | None = None) -> None:
    """Actualiza el estado del circuit breaker en Redis y localmente."""
    now = last_failure_time or time.time()
    state_data = {"state": state, "failure_count": failure_count, "last_failure_time": now}
    try:
        from src.core.db import RedisService
        redis = RedisService()
        redis.set_json(cb_key, state_data, ttl=300)
    except Exception:
        pass
    with cb_lock:
        cb_local_state[cb_key] = state_data
