"""
Metricas de Sistema — uso de memoria y tamano de DB.

Responsabilidad:
- ``set_system_memory_usage``: gauge de bytes de memoria usados.
- ``set_system_db_size``: gauge de bytes de la DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class SystemMetricsMixin:
    """Metricas de sistema (memoria, tamano DB)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def set_system_memory_usage(self, bytes_used: int) -> None:
        """
        Establece el gauge de uso de memoria del sistema.

        Args:
            bytes_used: Bytes de memoria usados
        """
        self._metrics.set_gauge("system_memory_usage_bytes", float(bytes_used))

    def set_system_db_size(self, bytes_used: int) -> None:
        """
        Establece el gauge de tamano de la base de datos.

        Args:
            bytes_used: Tamano de la DB en bytes
        """
        self._metrics.set_gauge("system_db_size_bytes", float(bytes_used))
