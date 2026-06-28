"""Shared helpers for connector decorators.

Contains _get_connector_name, _record_metrics, and the _ACTIONS_REGISTRY
that are used by multiple decorator modules.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


def _get_connector_name(args: tuple[Any, ...]) -> str:
    """Extrae el nombre del conector desde los argumentos del metodo."""
    if args and hasattr(args[0], "name"):
        return str(args[0].name)
    if args and hasattr(args[0], "__class__"):
        return args[0].__class__.__name__.lower()
    return "unknown"


def _record_metrics(connector_name: str, action: str, status: str, duration: float) -> None:
    """Registra metricas de una accion via TelemetryService."""
    try:
        from src.core.observability.telemetry import TelemetryService
        telemetry = TelemetryService()
        telemetry.record_connector_call(connector=connector_name, action=action, status=status, duration=duration)
    except Exception:
        logger.debug(f"Metrics: {connector_name}.{action} status={status} duration={duration:.3f}s")
