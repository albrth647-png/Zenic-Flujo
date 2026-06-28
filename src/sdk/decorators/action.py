"""connector_action decorator and get_action_metadata function.

Extracted from src/sdk/decorators.py.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def connector_action(name: str, description: str = "") -> Callable[[F], F]:
    """Registra un metodo como accion del conector."""
    def decorator(func: F) -> F:
        func._connector_action_name = name  # type: ignore[attr-defined]
        func._connector_action_description = description  # type: ignore[attr-defined]
        func._is_connector_action = True  # type: ignore[attr-defined]

        @functools.wraps(func)
        # legítimo: wrapper transparente (skill §1.2)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper._connector_action_name = name  # type: ignore[attr-defined]
        wrapper._connector_action_description = description  # type: ignore[attr-defined]
        wrapper._is_connector_action = True  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def get_action_metadata(cls: type) -> dict[str, dict[str, Any]]:
    """Extrae metadata de todas las acciones registradas en una clase."""
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
