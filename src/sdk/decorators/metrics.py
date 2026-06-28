"""track_metrics decorator — Registro automatico de metricas via TelemetryService.

Extracted from src/sdk/decorators.py.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.sdk.decorators._helpers import _get_connector_name, _record_metrics

F = TypeVar("F", bound=Callable[..., Any])


def track_metrics() -> Callable[[F], F]:
    """Registro automatico de metricas de la accion via TelemetryService."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        # legítimo: wrapper transparente (skill §1.2)
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
