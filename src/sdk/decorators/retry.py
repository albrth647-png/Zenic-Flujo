"""retry decorator — Reintento automatico con backoff exponencial.

Extracted from src/sdk/decorators.py.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.sdk.decorators._helpers import _get_connector_name
from src.core.logging import setup_logging

logger = setup_logging(__name__)
F = TypeVar("F", bound=Callable[..., Any])


def retry(max_retries: int = 3, backoff: float = 2.0, max_delay: float = 60.0) -> Callable[[F], F]:
    """Reintento automatico con backoff exponencial por accion."""
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
                        logger.warning(f"Retry [{attempt + 1}/{max_retries}] para {connector_name}.{action_name}: {type(e).__name__}: {e}. Reintentando en {delay:.1f}s")
                        time.sleep(delay)
                    else:
                        logger.error(f"Retry agotado [{max_retries}] para {connector_name}.{action_name}: {type(e).__name__}: {e}")
            raise last_exception  # type: ignore[misc]

        wrapper._retry_config = {"max_retries": max_retries, "backoff": backoff, "max_delay": max_delay}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
