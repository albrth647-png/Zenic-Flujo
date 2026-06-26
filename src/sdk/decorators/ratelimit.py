"""rate_limit decorator — Rate limiting por accion con sliding window.

Extracted from src/sdk/decorators.py.
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.sdk.decorators._helpers import _get_connector_name
from src.sdk.exceptions import RateLimitError

F = TypeVar("F", bound=Callable[..., Any])


def rate_limit(max_calls: int = 60, period: int = 60) -> Callable[[F], F]:
    """Rate limiting por accion usando sliding window."""
    def decorator(func: F) -> F:
        local_calls: dict[str, list[float]] = {}
        local_lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            connector_name = _get_connector_name(args)
            action_name = getattr(func, "_connector_action_name", func.__name__)
            rate_key = f"sdk:ratelimit:{connector_name}:{action_name}"
            try:
                from src.core.db import RedisService
                redis = RedisService()
                result = redis.check_rate_limit(rate_key, max_calls, period)
                if not result["allowed"]:
                    raise RateLimitError(
                        message=f"Rate limit excedido para {connector_name}.{action_name}",
                        connector_name=connector_name, max_calls=max_calls,
                        period_seconds=period, remaining=result.get("remaining", 0),
                        reset_at=result.get("reset_at"),
                    )
            except RateLimitError:
                raise
            except Exception:
                with local_lock:
                    now = time.time()
                    window_start = now - period
                    calls = local_calls.get(rate_key, [])
                    calls = [t for t in calls if t > window_start]
                    if len(calls) >= max_calls:
                        raise RateLimitError(
                            message=f"Rate limit excedido para {connector_name}.{action_name}",
                            connector_name=connector_name, max_calls=max_calls,
                            period_seconds=period, remaining=0,
                        ) from None
                    calls.append(now)
                    local_calls[rate_key] = calls
            return func(*args, **kwargs)

        wrapper._rate_limit = {"max_calls": max_calls, "period": period}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
