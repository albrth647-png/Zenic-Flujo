"""
Metricas de DB — consultas a la base de datos.

Responsabilidad:
- ``record_db_query``: histograma de duracion por operacion
  (select/insert/update/delete).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class DBMetricsMixin:
    """Metricas de consultas a la base de datos."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_db_query(self, operation: str, duration: float) -> None:
        """
        Registra una consulta a la base de datos.

        Args:
            operation: Tipo de operacion (select, insert, update, delete)
            duration: Duracion en segundos
        """
        self._metrics.observe_histogram(
            "db_query_duration_seconds",
            duration,
            labels={"operation": operation},
        )
