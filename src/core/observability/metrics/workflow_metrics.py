"""
Metricas de Workflow — inicio y fin de ejecucion.

Responsabilidad:
- ``record_workflow_start``: crea root span + incrementa gauge de
  ejecuciones activas.
- ``record_workflow_end``: cierra root span + decrementa gauge +
  registra duracion y estado final.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


class WorkflowMetricsMixin:
    """Metricas y tracing de ejecuciones de workflow (root spans)."""

    # Atributos provistos por ``TelemetryService`` (coordinador).
    _metrics: Any
    _tracing: Any
    _active_spans: dict[str, Any]
    _active_workflow_timers: dict[str, float]

    def record_workflow_start(self, workflow_id: int, execution_id: int) -> None:
        """
        Registra el inicio de una ejecucion de workflow.

        Crea un root span y actualiza el gauge de ejecuciones activas.

        Args:
            workflow_id: ID del workflow
            execution_id: ID de la ejecucion
        """
        # Metricas
        self._metrics.increment_counter("workflow_executions_total", labels={"status": "started"})

        # Gauge: incrementar activos
        current = self._metrics.get_gauge("workflow_active_executions")
        self._metrics.set_gauge("workflow_active_executions", current + 1)

        # Tracing: root span
        exec_key = str(execution_id)
        self._active_workflow_timers[exec_key] = time.monotonic()

        if self._tracing.get_tracer():
            span = self._tracing.start_span(
                "workflow.execute",
                attributes={
                    "workflow.id": workflow_id,
                    "execution.id": execution_id,
                },
            )
            self._active_spans[exec_key] = span

        logger.debug(
            f"TelemetryService: workflow start registrado "
            f"(workflow_id={workflow_id}, execution_id={execution_id})"
        )

    def record_workflow_end(
        self,
        workflow_id: int,
        execution_id: int,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra el fin de una ejecucion de workflow.

        Cierra el root span y actualiza contadores y gauge.

        Args:
            workflow_id: ID del workflow
            execution_id: ID de la ejecucion
            status: Estado final (completed, failed, timeout)
            duration: Duracion en segundos
        """
        # Metricas
        self._metrics.increment_counter("workflow_executions_total", labels={"status": status})

        # Gauge: decrementar activos
        current = self._metrics.get_gauge("workflow_active_executions")
        self._metrics.set_gauge("workflow_active_executions", max(0, current - 1))

        # Tracing: cerrar span
        exec_key = str(execution_id)
        span = self._active_spans.pop(exec_key, None)
        if span:
            if hasattr(span, "set_attribute"):
                span.set_attribute("workflow.status", status)
                span.set_attribute("workflow.duration_seconds", duration)
            self._tracing.end_span(span)

        self._active_workflow_timers.pop(exec_key, None)

        logger.debug(
            f"TelemetryService: workflow end registrado "
            f"(workflow_id={workflow_id}, execution_id={execution_id}, "
            f"status={status}, duration={duration:.3f}s)"
        )
