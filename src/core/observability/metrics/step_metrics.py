"""
Metricas de Step — inicio y fin de pasos de workflow.

Responsabilidad:
- ``record_step_start``: crea child span anclado al root span del
  workflow, registra tool/action.
- ``record_step_end``: cierra child span, observa histograma de
  duracion por tool/action.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class StepMetricsMixin:
    """Metricas y tracing de pasos (child spans de workflow)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any
    _tracing: Any
    _active_spans: dict[str, Any]
    _active_workflow_timers: dict[str, float]

    def record_step_start(
        self,
        execution_id: int,
        step_id: int,
        tool: str,
        action: str,
    ) -> None:
        """
        Registra el inicio de un paso de workflow.

        Crea un child span con atributos de tool y action.

        Args:
            execution_id: ID de la ejecucion
            step_id: ID del paso
            tool: Herramienta del paso
            action: Accion del paso
        """
        step_key = f"{execution_id}_{step_id}"
        self._active_workflow_timers[step_key] = time.monotonic()

        # Tracing: child span
        parent_span = self._active_spans.get(str(execution_id))
        if self._tracing.get_tracer():
            span = self._tracing.start_span(
                f"step.{tool}.{action}",
                parent=parent_span,
                attributes={
                    "step.id": step_id,
                    "step.tool": tool,
                    "step.action": action,
                    "execution.id": execution_id,
                },
            )
            self._active_spans[step_key] = span

    def record_step_end(
        self,
        execution_id: int,
        step_id: int,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra el fin de un paso de workflow.

        Cierra el child span y actualiza histogramas.

        Args:
            execution_id: ID de la ejecucion
            step_id: ID del paso
            status: Estado del paso (completed, failed, skipped)
            duration: Duracion en segundos
        """
        # Histograma de duracion
        step_key = f"{execution_id}_{step_id}"
        span = self._active_spans.pop(step_key, None)

        # Obtener tool/action del span si existe
        tool = "unknown"
        action = "unknown"
        if span and hasattr(span, "attributes"):
            tool = span.attributes.get("step.tool", "unknown")
            action = span.attributes.get("step.action", "unknown")

        self._metrics.observe_histogram(
            "workflow_step_duration_seconds",
            duration,
            labels={"tool": tool, "action": action},
        )

        # Tracing: cerrar span
        if span:
            if hasattr(span, "set_attribute"):
                span.set_attribute("step.status", status)
                span.set_attribute("step.duration_seconds", duration)
            self._tracing.end_span(span)

        self._active_workflow_timers.pop(step_key, None)
