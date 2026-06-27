"""
Observability — Metricas Prometheus-compatible
================================================

Definiciones de metricas y helpers para el sistema de telemetria.
Usa OpenTelemetry Metrics API con exportador Prometheus-compatible.

Workflow:
- workflow_executions_total: contador por status (completed/failed/timeout)
- workflow_executions_by_tool: contador por tool
- workflow_branches_taken: contador de branches ejecutados
- workflow_loops_executed: contador de loops ejecutados
- workflow_errors_total: contador de errores
- workflow_step_duration_seconds: histograma por tool/action
- workflow_total_duration_seconds: histograma
- workflow_active_executions: gauge

Conectores:
- connector_calls_total: contador por connector/status
- connector_errors_total: contador de errores
- connector_call_duration_seconds: histograma

NLU:
- nlu_intent_classification_total: contador por intent
- nlu_confidence_distribution: contador por rango de confianza
- nlu_pipeline_duration_seconds: histograma

Agentes (NUEVOS):
- agent_executions_total: contador por agent_id/action/status
- agent_tool_calls_total: contador por tool
- agent_memory_operations_total: contador por operation
- agent_execution_duration_seconds: histograma
- agent_active_instances: gauge

Marketplace (NUEVOS):
- marketplace_connector_publishes_total: contador
- marketplace_connector_installs_total: contador
- marketplace_searches_total: contador
- marketplace_latency_seconds: histograma
- marketplace_connectors_available: gauge

Sync (NUEVOS):
- sync_packages_sent_total: contador
- sync_packages_received_total: contador
- sync_conflicts_total: contador
- sync_bytes_transferred_total: contador
- sync_transfer_duration_seconds: histograma
- sync_pending_packages: gauge

Partnership (NUEVOS):
- partnership_registrations_total: contador
- partnership_revenue_shared_total: contador
- partnership_referrals_total: contador

Security (NUEVOS):
- security_login_attempts_total: contador
- security_login_failures_total: contador
- security_api_keys_created_total: contador
- security_rbac_checks_total: contador

Compliance (NUEVOS):
- compliance_audit_checks_total: contador
- compliance_violations_total: contador
- compliance_reports_generated_total: contador

Mobile (NUEVOS):
- mobile_push_notifications_sent_total: contador
- mobile_api_calls_total: contador

Tenant (NUEVOS):
- tenant_operations_total: contador
- tenant_active_count: gauge

BPMN (NUEVOS):
- bpmn_diagrams_imported_total: contador
- bpmn_diagrams_exported_total: contador

Sistema (NUEVOS):
- system_memory_usage_bytes: gauge
- system_db_size_bytes: gauge

Infraestructura:
- event_bus_events_published: contador por event_type
- db_query_duration_seconds: histograma por operation
- http_request_duration_seconds: histograma por method/path/status
"""

from __future__ import annotations

import threading
import time
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


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
        # Contadores de Workflow
        self._ensure_counter("workflow_executions_total")
        self._ensure_counter("workflow_executions_by_tool")
        self._ensure_counter("workflow_branches_taken")
        self._ensure_counter("workflow_loops_executed")
        self._ensure_counter("workflow_errors_total")

        # Contadores de Eventos
        self._ensure_counter("event_bus_events_published")

        # Contadores de Conectores
        self._ensure_counter("connector_calls_total")
        self._ensure_counter("connector_errors_total")

        # Contadores de NLU
        self._ensure_counter("nlu_intent_classification_total")
        self._ensure_counter("nlu_confidence_distribution")

        # Contadores de Agentes (NUEVOS)
        self._ensure_counter("agent_executions_total")
        self._ensure_counter("agent_tool_calls_total")
        self._ensure_counter("agent_memory_operations_total")

        # Contadores de Marketplace (NUEVOS)
        self._ensure_counter("marketplace_connector_publishes_total")
        self._ensure_counter("marketplace_connector_installs_total")
        self._ensure_counter("marketplace_searches_total")

        # Contadores de Sync (NUEVOS)
        self._ensure_counter("sync_packages_sent_total")
        self._ensure_counter("sync_packages_received_total")
        self._ensure_counter("sync_conflicts_total")
        self._ensure_counter("sync_bytes_transferred_total")

        # Contadores de Partnership (NUEVOS)
        self._ensure_counter("partnership_registrations_total")
        self._ensure_counter("partnership_revenue_shared_total")
        self._ensure_counter("partnership_referrals_total")

        # Contadores de Security (NUEVOS)
        self._ensure_counter("security_login_attempts_total")
        self._ensure_counter("security_login_failures_total")
        self._ensure_counter("security_api_keys_created_total")
        self._ensure_counter("security_rbac_checks_total")

        # Contadores de Compliance (NUEVOS)
        self._ensure_counter("compliance_audit_checks_total")
        self._ensure_counter("compliance_violations_total")
        self._ensure_counter("compliance_reports_generated_total")

        # Contadores de Mobile (NUEVOS)
        self._ensure_counter("mobile_push_notifications_sent_total")
        self._ensure_counter("mobile_api_calls_total")

        # Contadores de Tenants (NUEVOS)
        self._ensure_counter("tenant_operations_total")

        # Contadores de BPMN (NUEVOS)
        self._ensure_counter("bpmn_diagrams_imported_total")
        self._ensure_counter("bpmn_diagrams_exported_total")

        # Histogramas
        self._ensure_histogram("workflow_step_duration_seconds")
        self._ensure_histogram("workflow_total_duration_seconds")
        self._ensure_histogram("connector_call_duration_seconds")
        self._ensure_histogram("nlu_pipeline_duration_seconds")
        self._ensure_histogram("db_query_duration_seconds")
        self._ensure_histogram("http_request_duration_seconds")
        self._ensure_histogram("agent_execution_duration_seconds")  # NUEVO
        self._ensure_histogram("sync_transfer_duration_seconds")     # NUEVO
        self._ensure_histogram("marketplace_latency_seconds")        # NUEVO

        # Gauges
        self._ensure_gauge("workflow_active_executions")
        self._ensure_gauge("agent_active_instances")          # NUEVO
        self._ensure_gauge("marketplace_connectors_available") # NUEVO
        self._ensure_gauge("sync_pending_packages")            # NUEVO
        self._ensure_gauge("tenant_active_count")              # NUEVO
        self._ensure_gauge("system_memory_usage_bytes")        # NUEVO
        self._ensure_gauge("system_db_size_bytes")             # NUEVO

        logger.debug("Metricas por defecto registradas (%d contadores, %d histogramas, %d gauges)",
                     len(self._counters), len(self._histograms), len(self._gauges))

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
        """Genera una clave unica para un set[Any] de labels."""
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
            dict[str, Any] con count, sum, min, max, avg
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
                "workflow_errors_total",
                "event_bus_events_published",
                "connector_calls_total",
                "nlu_intent_classification_total",
                "agent_executions_total",
                "marketplace_connector_installs_total",
                "sync_packages_sent_total",
                "partnership_registrations_total",
                "security_login_attempts_total",
                "compliance_audit_checks_total",
                "mobile_push_notifications_sent_total",
                "tenant_operations_total",
                "bpmn_diagrams_imported_total",
            ]
            for name in counter_names:
                self._otel_counters[name] = self._otel_meter.create_counter(
                    name=name,
                    description=f"Counter: {name}",
                )

            # Histogramas OTel
            histogram_names = [
                "workflow_step_duration_seconds",
                "workflow_total_duration_seconds",
                "connector_call_duration_seconds",
                "nlu_pipeline_duration_seconds",
                "db_query_duration_seconds",
                "http_request_duration_seconds",
                "agent_execution_duration_seconds",
                "sync_transfer_duration_seconds",
                "marketplace_latency_seconds",
            ]
            for name in histogram_names:
                self._otel_histograms[name] = self._otel_meter.create_histogram(
                    name=name,
                    description=f"Histogram: {name}",
                    unit="s",
                )

            # Gauges OTel
            gauge_names = [
                ("workflow_active_executions", "currently running workflows"),
                ("agent_active_instances", "currently active agent instances"),
                ("marketplace_connectors_available", "connectors available in marketplace"),
                ("sync_pending_packages", "sync packages pending delivery"),
                ("tenant_active_count", "active tenant count"),
            ]
            for name, desc in gauge_names:
                self._otel_gauges[name] = self._otel_meter.create_up_down_counter(
                    name=name,
                    description=desc,
                )

            logger.info("Instrumentos OTel registrados para metricas (%d counters, %d histograms, %d gauges)",
                         len(counter_names), len(histogram_names), len(gauge_names))
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


__all__ = ["MetricsRegistry"]
