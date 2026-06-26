"""
Metricas de NLU — resultados del pipeline de NLU.

Responsabilidad:
- ``record_nlu_result``: contador por intent + histograma de duracion
  del pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class NLUMetricsMixin:
    """Metricas del pipeline de NLU (intent classification + duracion)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_nlu_result(self, intent: str, confidence: float, duration: float) -> None:
        """
        Registra el resultado del pipeline NLU.

        Args:
            intent: Intent clasificado
            confidence: Confianza de la clasificacion (0.0-1.0)
            duration: Duracion del pipeline en segundos
        """
        self._metrics.increment_counter(
            "nlu_intent_classification_total",
            labels={"intent": intent},
        )
        self._metrics.observe_histogram(
            "nlu_pipeline_duration_seconds",
            duration,
        )
