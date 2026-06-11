"""
Observability — Servicio de Telemetria OpenTelemetry
=====================================================

Servicio unificado de telemetria que integra metricas, tracing y
structured logging usando OpenTelemetry.

Funcionalidades:

- Metricas Prometheus-compatible: contadores, histogramas y gauges
  para workflows, steps, conectores, NLU, DB y HTTP.
- Tracing distribuido: root spans para workflows, child spans para
  steps y llamadas a conectores, propagacion de contexto.
- Structured logging: logs JSON con trace_id, span_id y tenant_id.

Configuracion via variables de entorno:
- WFD_OTEL_ENABLED: habilitar/deshabilitar telemetria (default: false)
- WFD_OTEL_SERVICE_NAME: nombre del servicio (default: "zenic-flijo")
- WFD_OTEL_EXPORTER: tipo de exportador (prometheus, jaeger, otlp, none)
- WFD_OTEL_EXPORTER_ENDPOINT: URL del exportador
- WFD_OTEL_METRICS_PORT: puerto de scrape Prometheus (default: 9090)
- WFD_OTEL_SAMPLING_RATE: tasa de muestreo 0.0-1.0 (default: 0.1)

Tabla DB:
- telemetry_config: configuracion de telemetria por tenant o global
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from src.data.database_manager import DatabaseManager
from src.observability.metrics import MetricsRegistry
from src.observability.tracing import (
    OTEL_ENABLED,
    OTEL_EXPORTER,
    OTEL_SERVICE_NAME,
    TracingManager,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Configuracion ─────────────────────────────────────────────

OTEL_METRICS_PORT: int = int(os.environ.get("WFD_OTEL_METRICS_PORT", "9090"))


class TelemetryService:
    """
    Servicio unificado de telemetria OpenTelemetry.

    Integra metricas (MetricsRegistry), tracing (TracingManager) y
    structured logging en un solo servicio. Se inicializa al arrancar
    la aplicacion y se cierra al apagar.

    Cuando WFD_OTEL_ENABLED=false, opera en modo no-op sin overhead.
    """

    _instance: TelemetryService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> TelemetryService:
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
            self._metrics = MetricsRegistry()
            self._tracing = TracingManager()
            self._db = DatabaseManager()
            self._active_spans: dict[str, Any] = {}  # execution_id -> span
            self._active_workflow_timers: dict[str, float] = {}  # execution_id -> start_time
            self._initialized_telemetry = False

    # ── Inicializacion ───────────────────────────────────────

    def initialize(self) -> None:
        """
        Configura los providers de OpenTelemetry.

        Inicializa el TracerProvider con exportadores y el MeterProvider
        con el exportador Prometheus. Configura structured logging.

        Debe llamarse al arrancar la aplicacion.
        """
        if self._initialized_telemetry:
            logger.debug("TelemetryService: ya inicializado")
            return

        logger.info(
            f"TelemetryService: inicializando (enabled={OTEL_ENABLED}, "
            f"exporter={OTEL_EXPORTER}, service={OTEL_SERVICE_NAME})"
        )

        # Inicializar tracing
        self._tracing.initialize()

        # Inicializar metricas OTel si esta disponible
        self._initialize_otel_metrics()

        # Configurar structured logging
        self._setup_structured_logging()

        # Cargar configuracion desde DB
        self._load_config_from_db()

        self._initialized_telemetry = True
        logger.info("TelemetryService: inicializacion completada")

    def _initialize_otel_metrics(self) -> None:
        """Configura el MeterProvider de OpenTelemetry si esta disponible."""
        if not OTEL_ENABLED:
            return

        try:
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource

            resource = Resource.create(
                {
                    "service.name": OTEL_SERVICE_NAME,
                    "service.version": "1.0.0",
                }
            )

            if OTEL_EXPORTER == "prometheus":
                try:
                    from opentelemetry.exporter.prometheus import PrometheusMetricReader

                    reader = PrometheusMetricReader(f"0.0.0.0:{OTEL_METRICS_PORT}")
                    provider = MeterProvider(resource=resource, metric_readers=[reader])
                    metrics.set_meter_provider(provider)
                    meter = metrics.get_meter(OTEL_SERVICE_NAME)
                    self._metrics.set_otel_meter(meter)
                    logger.info(f"TelemetryService: exportador Prometheus configurado en puerto {OTEL_METRICS_PORT}")
                except ImportError:
                    logger.warning("TelemetryService: opentelemetry-exporter-prometheus no instalado")

            elif OTEL_EXPORTER == "otlp":
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                        OTLPMetricExporter,
                    )

                    endpoint = os.environ.get("WFD_OTEL_EXPORTER_ENDPOINT", "localhost:4317")
                    exporter = OTLPMetricExporter(endpoint=endpoint)
                    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)
                    provider = MeterProvider(resource=resource, metric_readers=[reader])
                    metrics.set_meter_provider(provider)
                    meter = metrics.get_meter(OTEL_SERVICE_NAME)
                    self._metrics.set_otel_meter(meter)
                    logger.info("TelemetryService: exportador OTLP metrics configurado")
                except ImportError:
                    logger.warning("TelemetryService: opentelemetry-exporter-otlp no instalado")

        except ImportError:
            logger.debug("TelemetryService: opentelemetry-sdk no instalado, metricas en modo local")

    def _setup_structured_logging(self) -> None:
        """Configura structured logging con JSON y trace context."""
        if not OTEL_ENABLED:
            return

        try:
            from opentelemetry.instrumentation.logging import LoggingInstrumentor

            LoggingInstrumentor().instrument(set_logging_format=True)
            logger.info("TelemetryService: structured logging configurado con OTel")
        except ImportError:
            # Fallback: configurar logging JSON manualmente
            self._setup_json_logging()

    def _setup_json_logging(self) -> None:
        """Configura logging en formato JSON con trace context."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.setFormatter(JsonLogFormatter())

    def _load_config_from_db(self) -> None:
        """Carga configuracion de telemetria desde la tabla telemetry_config."""
        try:
            rows = self._db.fetchall("SELECT * FROM telemetry_config")
            for row in rows:
                logger.debug(
                    f"TelemetryService: config cargada - "
                    f"tenant={row.get('tenant_id', 'default')} "
                    f"key={row.get('config_key', '')}"
                )
        except Exception as e:
            logger.debug(f"TelemetryService: error cargando config de DB: {e}")

    # ── Metricas de Workflow ─────────────────────────────────

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
            f"TelemetryService: workflow start registrado (workflow_id={workflow_id}, execution_id={execution_id})"
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
            f"(workflow_id={workflow_id}, execution_id={execution_id}, status={status}, duration={duration:.3f}s)"
        )

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

    # ── Metricas de Connector ────────────────────────────────

    def record_connector_call(
        self,
        connector: str,
        action: str,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra una llamada a un conector externo.

        Args:
            connector: Nombre del conector (ej: "slack", "stripe")
            action: Accion realizada (ej: "send_message")
            status: Estado de la llamada (success, error, timeout)
            duration: Duracion en segundos
        """
        self._metrics.increment_counter(
            "connector_calls_total",
            labels={"connector": connector, "status": status},
        )
        self._metrics.observe_histogram(
            "connector_call_duration_seconds",
            duration,
            labels={"connector": connector},
        )

    # ── Metricas de NLU ──────────────────────────────────────

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

    # ── Metricas de DB ───────────────────────────────────────

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

    # ── Acceso a componentes ─────────────────────────────────

    def get_tracer(self) -> Any | None:
        """
        Retorna el tracer de OpenTelemetry para instrumentacion personalizada.

        Returns:
            Tracer de OTel, o None si no esta configurado
        """
        return self._tracing.get_tracer()

    def get_meter(self) -> Any | None:
        """
        Retorna el meter de OpenTelemetry para metricas personalizadas.

        Returns:
            Meter de OTel, o None si no esta configurado
        """
        return self._metrics._otel_meter

    def get_metrics(self) -> str:
        """
        Genera la salida de metricas en formato Prometheus text.

        Returns:
            String con todas las metricas en formato Prometheus exposition
        """
        return self._metrics.get_metrics()

    # ── Configuracion por tenant ─────────────────────────────

    def set_telemetry_config(
        self,
        config_key: str,
        config_value: dict[str, Any],
        tenant_id: str = "default",
    ) -> None:
        """
        Guarda configuracion de telemetria para un tenant.

        Args:
            config_key: Clave de configuracion
            config_value: Valor de configuracion (dict serializable)
            tenant_id: ID del tenant (default: global)
        """
        now = datetime.now(UTC).isoformat()
        self._db.execute(
            """INSERT OR REPLACE INTO telemetry_config (tenant_id, config_key, config_value, updated_at)
               VALUES (?, ?, ?, ?)""",
            (tenant_id, config_key, json.dumps(config_value), now),
        )
        self._db.commit()
        logger.info(f"TelemetryService: config guardada - tenant={tenant_id}, key={config_key}")

    def get_telemetry_config(
        self,
        config_key: str,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        """
        Obtiene configuracion de telemetria para un tenant.

        Args:
            config_key: Clave de configuracion
            tenant_id: ID del tenant

        Returns:
            Configuracion como dict, o None si no existe
        """
        row = self._db.fetchone(
            "SELECT config_value FROM telemetry_config WHERE tenant_id = ? AND config_key = ?",
            (tenant_id, config_key),
        )
        if not row:
            return None
        try:
            return json.loads(row["config_value"])
        except (json.JSONDecodeError, TypeError):
            return None

    # ── Shutdown ─────────────────────────────────────────────

    def shutdown(self) -> None:
        """
        Cierra el servicio de telemetria.

        Hace flush de metricas y spans pendientes, y cierra los exportadores.
        Debe llamarse al apagar la aplicacion.
        """
        logger.info("TelemetryService: cerrando...")

        # Cerrar spans pendientes
        for key, span in list(self._active_spans.items()):
            try:
                self._tracing.end_span(span)
            except Exception as e:
                logger.debug(f"Error cerrando span {key}: {e}")
        self._active_spans.clear()

        # Cerrar tracing
        self._tracing.shutdown()

        logger.info("TelemetryService: cerrado correctamente")

    # ── Reset para testing ───────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None


# ── Structured Logging Formatter ──────────────────────────────


class JsonLogFormatter(logging.Formatter):
    """
    Formateador de logs en JSON con trace context.

    Formato de salida:
    {
        "timestamp": "2026-01-01T00:00:00Z",
        "level": "INFO",
        "logger": "module.name",
        "message": "texto del log",
        "trace_id": "abc123...",
        "span_id": "def456...",
        "tenant_id": "default"
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Agregar trace context si esta disponible
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                ctx = span.get_span_context()
                log_entry["trace_id"] = format(ctx.trace_id, "032x")
                log_entry["span_id"] = format(ctx.span_id, "016x")
        except ImportError:
            pass

        # Agregar tenant_id si esta disponible
        tenant_id = getattr(record, "tenant_id", None)
        if tenant_id:
            log_entry["tenant_id"] = tenant_id

        # Agregar campos extras
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)
