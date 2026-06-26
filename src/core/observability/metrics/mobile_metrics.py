"""
Metricas de Mobile — push notifications y API mobile.

Responsabilidad:
- ``record_push_notification``: contador por platform+status.
- ``record_mobile_api_call``: contador por endpoint+method+status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class MobileMetricsMixin:
    """Metricas de la capa mobile (push + API)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_push_notification(
        self,
        platform: str,
        status: str,
    ) -> None:
        """
        Registra el envio de una notificacion push.

        Args:
            platform: Plataforma (ios, android)
            status: Estado (sent, delivered, failed)
        """
        self._metrics.increment_counter(
            "mobile_push_notifications_sent_total",
            labels={"platform": platform, "status": status},
        )

    def record_mobile_api_call(self, endpoint: str, method: str, status: str) -> None:
        """
        Registra una llamada a la API mobile.

        Args:
            endpoint: Endpoint llamado
            method: Metodo HTTP
            status: Estado (success, error)
        """
        self._metrics.increment_counter(
            "mobile_api_calls_total",
            labels={"endpoint": endpoint, "method": method, "status": status},
        )
