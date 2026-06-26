"""
Metricas de Connector — llamadas a conectores externos.

Responsabilidad:
- ``record_connector_call``: contador por connector+status e histograma
  de duracion por connector.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class ConnectorMetricsMixin:
    """Metricas de llamadas a conectores externos (Slack, Stripe, etc.)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_connector_call(
        self,
        connector: str,
        action: str,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra una llamada a un conector externo.

        Args:
            connector: Nombre del conector (ej: "slack", "stripe")
            action: Accion realizada (ej: "send_message")
            status: Estado de la llamada (success, error, timeout)
            duration: Duracion en segundos
        """
        self._metrics.increment_counter(
            "connector_calls_total",
            labels={"connector": connector, "status": status},
        )
        self._metrics.observe_histogram(
            "connector_call_duration_seconds",
            duration,
            labels={"connector": connector},
        )
