"""
Metricas de Sync — paquetes enviados/recibidos, bytes transferidos,
conflictos, paquetes pendientes.

Responsabilidad:
- ``record_sync_package_sent``: contador de envios + bytes outbound +
  histograma de duracion outbound.
- ``record_sync_package_received``: contador de recepciones + bytes
  inbound + histograma de duracion inbound + contador de conflictos.
- ``set_sync_pending_packages``: gauge de paquetes pendientes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class SyncMetricsMixin:
    """Metricas de sincronizacion offline/cloud entre nodos."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_sync_package_sent(
        self,
        tenant_id: str,
        package_size: int,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra el envio de un paquete de sync.

        Args:
            tenant_id: ID del tenant
            package_size: Tamano del paquete en bytes
            status: Estado (success, failed)
            duration: Duracion en segundos
        """
        self._metrics.increment_counter(
            "sync_packages_sent_total",
            labels={"tenant_id": tenant_id, "status": status},
        )
        self._metrics.increment_counter(
            "sync_bytes_transferred_total",
            value=float(package_size),
            labels={"direction": "outbound", "tenant_id": tenant_id},
        )
        self._metrics.observe_histogram(
            "sync_transfer_duration_seconds",
            duration,
            labels={"tenant_id": tenant_id, "direction": "outbound"},
        )

    def record_sync_package_received(
        self,
        tenant_id: str,
        package_size: int,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra la recepcion de un paquete de sync.

        Args:
            tenant_id: ID del tenant
            package_size: Tamano del paquete en bytes
            status: Estado (success, conflict, failed)
            duration: Duracion en segundos
        """
        self._metrics.increment_counter(
            "sync_packages_received_total",
            labels={"tenant_id": tenant_id, "status": status},
        )
        self._metrics.increment_counter(
            "sync_bytes_transferred_total",
            value=float(package_size),
            labels={"direction": "inbound", "tenant_id": tenant_id},
        )
        self._metrics.observe_histogram(
            "sync_transfer_duration_seconds",
            duration,
            labels={"tenant_id": tenant_id, "direction": "inbound"},
        )
        if status == "conflict":
            self._metrics.increment_counter(
                "sync_conflicts_total",
                labels={"tenant_id": tenant_id},
            )

    def set_sync_pending_packages(self, count: int) -> None:
        """
        Establece el gauge de paquetes de sync pendientes.

        Args:
            count: Numero de paquetes pendientes
        """
        self._metrics.set_gauge("sync_pending_packages", float(count))
