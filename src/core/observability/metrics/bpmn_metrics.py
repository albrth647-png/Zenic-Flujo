"""
Metricas de BPMN — importacion y exportacion de diagramas.

Responsabilidad:
- ``record_bpmn_import``: contador por status.
- ``record_bpmn_export``: contador por status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class BPMNMetricsMixin:
    """Metricas de diagramas BPMN (import/export)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_bpmn_import(self, diagram_name: str, status: str) -> None:
        """
        Registra la importacion de un diagrama BPMN.

        Args:
            diagram_name: Nombre del diagrama
            status: Estado (success, failed)
        """
        self._metrics.increment_counter(
            "bpmn_diagrams_imported_total",
            labels={"status": status},
        )

    def record_bpmn_export(self, diagram_name: str, status: str) -> None:
        """
        Registra la exportacion de un diagrama BPMN.

        Args:
            diagram_name: Nombre del diagrama
            status: Estado (success, failed)
        """
        self._metrics.increment_counter(
            "bpmn_diagrams_exported_total",
            labels={"status": status},
        )
