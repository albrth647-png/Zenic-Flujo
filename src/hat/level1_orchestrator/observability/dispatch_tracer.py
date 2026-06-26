"""
HAT-ORBITAL Observability — Dispatch Tracer.

Propaga dispatch_id a través de todos los niveles HAT usando OpenTelemetry
spans. Si OTel no está instalado, usa un tracer no-op que no rompe nada.

Uso:
    tracer = DispatchTracer()
    with tracer.span("route", dispatch_id="disp_123"):
        # ... ruteo ORBITAL ...
    with tracer.span("dispatch", dispatch_id="disp_123", domain="research"):
        # ... despacho al supervisor ...
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


class DispatchTracer:
    """Tracer que propaga dispatch_id via OpenTelemetry spans.

    Si opentelemetry no está instalado, usa un context manager no-op
    que no hace nada pero no rompe el flujo.
    """

    def __init__(self) -> None:
        self._tracer = self._get_tracer()
        tracer_type = "opentelemetry" if "opentelemetry" in type(self._tracer).__module__ else "no-op"
        logger.debug("DispatchTracer initialized with tracer=%s", tracer_type)

    @staticmethod
    def _get_tracer() -> _NoOpTracer | Any:
        """Obtiene el tracer de OpenTelemetry o un no-op si no está instalado."""
        try:
            from opentelemetry import trace
            return trace.get_tracer("hat-orbital")
        except ImportError:
            return _NoOpTracer()

    def span(
        self,
        name: str,
        dispatch_id: str = "",
        domain: str = "",
        **extra_attrs: str,
    ) -> Any:
        """Crea un span con atributos HAT estándar."""
        attrs: dict[str, str] = {"hat.dispatch_id": dispatch_id}
        if domain:
            attrs["hat.domain"] = domain
        attrs.update({f"hat.{k}": v for k, v in extra_attrs.items()})
        return self._tracer.start_as_current_span(name, attributes=attrs)


class _NoOpTracer:
    """Tracer no-op para cuando OpenTelemetry no está instalado."""

    def start_as_current_span(self, name: str, attributes: dict[str, str] | None = None) -> _NoOpSpan:
        """Retorna un context manager no-op."""
        return _NoOpSpan()


class _NoOpSpan:
    """Span no-op que implementa el protocolo context manager."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        return None
