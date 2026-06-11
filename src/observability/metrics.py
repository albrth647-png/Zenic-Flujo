"""
Observability — Metricas Prometheus-compatible
================================================

Definiciones de metricas y helpers para el sistema de telemetria.
Usa OpenTelemetry Metrics API con exportador Prometheus-compatible.

Metricas definidas:
- workflow_executions_total: contador por status (completed/failed/timeout)
- workflow_step_duration_seconds: histograma por tool/action
- workflow_active_executions: gauge de workflows ejecutandose
- event_bus_events_published: contador por event_type
- connector_calls_total: contador por connector/status
- connector_call_duration_seconds: histograma por connector
- nlu_pipeline_duration_seconds: histograma
- nlu_intent_classification_total: contador por intent
- db_query_duration_seconds: histograma por operation
- http_request_duration_seconds: histograma por method/path/status
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Configuracion ─────────────────────────────────────────────

OTEL_METRICS_PORT: int = int(os.environ.get("WFD_OTEL_METRICS_PORT", "9090"))


class MetricsRegistry:
    """
    Registro centralizado de metricas Prometheus-compatible.

    Mantiene contadores, histogramas y gauges en memoria con
    capacidad de exportar en formato Prometheus text.
    Cuando OpenTelemetry esta disponible, delega a OTel MeterProvider.
    """

    _instance: MetricsRegistry | None = None
    _lock = threading.RLock()

    def __new__(cls) -> MetricsRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        with self._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True
            self._counters: dict[str, dict[str, float]] = {}
            self._gauges: dict[str, dict[str, float]] = {}
            self._histograms: dict[str, dict[str, list[float]]] = {}
            self._otel_meter: Any | None = None
            self._otel_counters: dict[str, Any] = {}
            self._otel_histograms: dict[str, Any] = {}
            self._otel_gauges: dict[str, Any] = {}
            self._register_default_metrics()

    def _register_default_metrics(self) -> None:
        """Registra las metricas por defecto del sistema."""
        # Contadores
        self._ensure_counter("workflow_executions_total")
        self._ensure_counter("event_bus_events_published")
        self._ensure_counter("connector_calls_total")
        self._ensure_counter("nlu_intent_classification_total")

        # Histogramas
        self._ensure_histogram("workflow_step_duration_seconds")
        self._ensure_histogram("connector_call_duration_seconds")
        self._ensure_histogram("nlu_pipeline_duration_seconds")
        self._ensure_histogram("db_query_duration_seconds")
        self._ensure_histogram("http_request_duration_seconds")

        # Gauges
        self._ensure_gauge("workflow_active_executions")

        logger.debug("Metricas por defecto registradas")

    # ── Operaciones de metricas ──────────────────────────────

    def _ensure_counter(self, name: str) -> None:
        """Asegura que un contador existe en el registro."""
        if name not in self._counters:
            self._counters[name] = {}

    def _ensure_gauge(self, name: str) -> None:
        """Asegura que un gauge existe en el registro."""
        if name not in self._gauges:
            self._gauges[name] = {}

    def _ensure_histogram(self, name: str) -> None:
        """Asegura que un histograma existe en el registro."""
        if name not in self._histograms:
            self._histograms[name] = {}

    def _label_key(self, labels: dict[str, str]) -> str:
        """Genera una clave unica para un set de labels."""
        if not labels:
            return ""
        return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"

    def increment_counter(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """
        Incrementa un contador.

        Args:
            name: Nombre de la metrica
            value: Valor a incrementar (default 1.0)
            labels: Labels para la metrica (ej: {"status": "completed"})
        """
        self._ensure_counter(name)
        label_key = self._label_key(labels or {})
        self._counters[name][label_key] = self._counters[name].get(label_key, 0.0) + value

        # OTel si esta disponible
        if name in self._otel_counters:
            try:
                self._otel_counters[name].add(value, attributes=labels or {})
            except Exception as e:
                logger.debug(f"Error incrementando contador OTel {name}: {e}")

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """
        Establece el valor de un gauge.

        Args:
            name: Nombre de la metrica
            value: Valor actual
            labels: Labels para la metrica
        """
        self._ensure_gauge(name)
        label_key = self._label_key(labels or {})
        self._gauges[name][label_key] = value

    def observe_histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """
        Registra una observacion en un histograma.

        Args:
            name: Nombre de la metrica
            value: Valor observado (ej: duracion en segundos)
            labels: Labels para la metrica
        """
        self._ensure_histogram(name)
        label_key = self._label_key(labels or {})
        if label_key not in self._histograms[name]:
            self._histograms[name][label_key] = []
        self._histograms[name][label_key].append(value)

        # OTel si esta disponible
        if name in self._otel_histograms:
            try:
                self._otel_histograms[name].record(value, attributes=labels or {})
            except Exception as e:
                logger.debug(f"Error registrando histograma OTel {name}: {e}")

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Obtiene el valor actual de un contador."""
        label_key = self._label_key(labels or {})
        return self._counters.get(name, {}).get(label_key, 0.0)

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Obtiene el valor actual de un gauge."""
        label_key = self._label_key(labels or {})
        return self._gauges.get(name, {}).get(label_key, 0.0)

    def get_histogram_stats(self, name: str, labels: dict[str, str] | None = None) -> dict[str, float]:
        """
        Obtiene estadisticas de un histograma.

        Returns:
            dict con count, sum, min, max, avg
        """
        label_key = self._label_key(labels or {})
        values = self._histograms.get(name, {}).get(label_key, [])
        if not values:
            return {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}
        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    # ── Formato Prometheus ───────────────────────────────────

    def get_metrics(self) -> str:
        """
        Genera la salida en formato Prometheus text.

        Returns:
            String con todas las metricas en formato Prometheus exposition
        """
        lines: list[str] = []

        # Contadores
        for name, label_values in sorted(self._counters.items()):
            lines.append(f"# HELP {name} Counter metric")
            lines.append(f"# TYPE {name} counter")
            for label_key, value in sorted(label_values.items()):
                lines.append(f"{name}{label_key} {value}")

        # Gauges
        for name, label_values in sorted(self._gauges.items()):
            lines.append(f"# HELP {name} Gauge metric")
            lines.append(f"# TYPE {name} gauge")
            for label_key, value in sorted(label_values.items()):
                lines.append(f"{name}{label_key} {value}")

        # Histogramas (resumen estadistico)
        for name, label_histograms in sorted(self._histograms.items()):
            lines.append(f"# HELP {name} Histogram metric")
            lines.append(f"# TYPE {name} histogram")
            for label_key, values in sorted(label_histograms.items()):
                if not values:
                    continue
                sorted_values = sorted(values)
                count = len(sorted_values)
                total = sum(sorted_values)
                # Buckets aproximados
                buckets = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
                for bucket in buckets:
                    bucket_count = sum(1 for v in sorted_values if v <= bucket)
                    lines.append(f'{name}_bucket{{le="{bucket}"{label_key[1:] if label_key else "}"} {bucket_count}')
                lines.append(f'{name}_bucket{{le="+Inf"{label_key[1:] if label_key else "}"} {count}')
                lines.append(f"{name}_count{label_key} {count}")
                lines.append(f"{name}_sum{label_key} {total}")

        return "\n".join(lines) + "\n"

    # ── Integracion OTel ─────────────────────────────────────

    def set_otel_meter(self, meter: Any) -> None:
        """Establece el meter de OpenTelemetry para delegar metricas."""
        self._otel_meter = meter
        self._register_otel_instruments()

    def _register_otel_instruments(self) -> None:
        """Registra instrumentos OTel para las metricas por defecto."""
        if not self._otel_meter:
            return

        try:
            # Contadores OTel
            counter_names = [
                "workflow_executions_total",
                "event_bus_events_published",
                "connector_calls_total",
                "nlu_intent_classification_total",
            ]
            for name in counter_names:
                self._otel_counters[name] = self._otel_meter.create_counter(
                    name=name,
                    description=f"Counter: {name}",
                )

            # Histogramas OTel
            histogram_names = [
                "workflow_step_duration_seconds",
                "connector_call_duration_seconds",
                "nlu_pipeline_duration_seconds",
                "db_query_duration_seconds",
                "http_request_duration_seconds",
            ]
            for name in histogram_names:
                self._otel_histograms[name] = self._otel_meter.create_histogram(
                    name=name,
                    description=f"Histogram: {name}",
                    unit="s",
                )

            # Gauges OTel (usando UpDownCounter como aproximacion)
            self._otel_gauges["workflow_active_executions"] = self._otel_meter.create_up_down_counter(
                name="workflow_active_executions",
                description="Gauge: currently running workflows",
            )

            logger.info("Instrumentos OTel registrados para metricas")
        except Exception as e:
            logger.warning(f"Error registrando instrumentos OTel: {e}")

    # ── Context manager para duracion ────────────────────────

    class Timer:
        """Context manager para medir duraciones de forma conveniente."""

        def __init__(self, registry: MetricsRegistry, name: str, labels: dict[str, str] | None = None):
            self._registry = registry
            self._name = name
            self._labels = labels
            self._start: float = 0.0

        def __enter__(self) -> MetricsRegistry.Timer:
            self._start = time.monotonic()
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            duration = time.monotonic() - self._start
            self._registry.observe_histogram(self._name, duration, self._labels)

        @property
        def elapsed(self) -> float:
            """Segundos transcurridos hasta ahora."""
            return time.monotonic() - self._start

    def timer(self, name: str, labels: dict[str, str] | None = None) -> MetricsRegistry.Timer:
        """
        Crea un context manager para medir duraciones.

        Uso:
            with metrics.timer("workflow_step_duration_seconds", {"tool": "crm"}) as t:
                # ... ejecutar paso ...
            # Al salir del contexto, se registra la duracion automaticamente
        """
        return self.Timer(self, name, labels)

    # ── Reset para testing ───────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None
