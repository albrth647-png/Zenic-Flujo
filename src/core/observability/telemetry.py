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

Arquitectura:

Este modulo es el **coordinador** del servicio. La API de metricas
(``record_*`` / ``set_*``) vive en mixins especializados en
``src/observability/metrics/`` (un mixin por dominio: workflow, step,
connector, NLU, db, agent, marketplace, sync, partner, auth,
compliance, mobile, tenant, bpmn, system). ``TelemetryService`` hereda
de todos los mixins para componer la API publica completa sin
duplicar codigo. Esto mantiene este archivo focalizado en
inicializacion, configuracion por tenant, acceso a componentes y
shutdown (~250 LOC).

Backward compatibility: ``from src.core.observability.telemetry import
TelemetryService`` y ``from src.core.observability.telemetry import
OTEL_METRICS_PORT, JsonLogFormatter, MetricsRegistry`` siguen
funcionando sin cambios.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from src.core.db.sqlite_manager import DatabaseManager
from src.core.observability.logging import JsonLogFormatter
from src.core.observability.metrics import (
    AgentMetricsMixin,
    AuthMetricsMixin,
    BPMNMetricsMixin,
    ComplianceMetricsMixin,
    ConnectorMetricsMixin,
    DBMetricsMixin,
    MarketplaceMetricsMixin,
    MobileMetricsMixin,
    NLUMetricsMixin,
    PartnerMetricsMixin,
    StepMetricsMixin,
    SyncMetricsMixin,
    SystemMetricsMixin,
    TenantMetricsMixin,
    WorkflowMetricsMixin,
)
from src.core.observability.metrics import MetricsRegistry  # re-export para compat
from src.core.observability.telemetry_config import OTEL_METRICS_PORT
from src.core.observability.tracing import (
    OTEL_ENABLED,
    OTEL_EXPORTER,
    OTEL_SERVICE_NAME,
    TracingManager,
)
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TelemetryService(
    WorkflowMetricsMixin,
    StepMetricsMixin,
    ConnectorMetricsMixin,
    NLUMetricsMixin,
    DBMetricsMixin,
    AgentMetricsMixin,
    MarketplaceMetricsMixin,
    SyncMetricsMixin,
    PartnerMetricsMixin,
    AuthMetricsMixin,
    ComplianceMetricsMixin,
    MobileMetricsMixin,
    TenantMetricsMixin,
    BPMNMetricsMixin,
    SystemMetricsMixin,
):
    """
    Servicio unificado de telemetria OpenTelemetry.

    Integra metricas (MetricsRegistry), tracing (TracingManager) y
    structured logging en un solo servicio. Se inicializa al arrancar
    la aplicacion y se cierra al apagar.

    Cuando WFD_OTEL_ENABLED=false, opera en modo no-op sin overhead.

    La API de metricas (``record_*`` / ``set_*``) se hereda de mixins
    especializados por dominio en ``src.observability.metrics``. Este
    coordinador mantiene singleton, inicializacion, configuracion por
    tenant, acceso a componentes y shutdown.
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
                    logger.info(
                        f"TelemetryService: exportador Prometheus configurado en puerto {OTEL_METRICS_PORT}"
                    )
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


# ``JsonLogFormatter`` se re-exporta aqui para mantener backward
# compatibility con ``from src.core.observability.telemetry import JsonLogFormatter``.
# La implementacion vive en ``src.core.observability.logging``.
__all__ = [
    "JsonLogFormatter",
    "MetricsRegistry",
    "OTEL_METRICS_PORT",
    "TelemetryService",
]
