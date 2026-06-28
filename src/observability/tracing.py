"""
Observability — Tracing con OpenTelemetry
===========================================

Configuracion y helpers para distributed tracing con OpenTelemetry.
Proporciona:

- Configuracion de TracerProvider con samplers y exportadores
- Exportadores: Jaeger, OTLP, o Console (debug)
- Context manager para spans con atributos automaticos
- Propagacion de contexto de traza a traves de la cadena de ejecucion
- Integracion con structured logging (trace_id, span_id)

Configuracion via variables de entorno:
- WFD_OTEL_ENABLED: habilitar/deshabilitar telemetria (default: false)
- WFD_OTEL_SERVICE_NAME: nombre del servicio (default: "zenic-flijo")
- WFD_OTEL_EXPORTER: tipo de exportador (prometheus, jaeger, otlp, none)
- WFD_OTEL_EXPORTER_ENDPOINT: URL del exportador
- WFD_OTEL_SAMPLING_RATE: tasa de muestreo 0.0-1.0 (default: 0.1)
"""

from __future__ import annotations

import os
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Configuracion ─────────────────────────────────────────────

OTEL_ENABLED: bool = os.environ.get("WFD_OTEL_ENABLED", "false").lower() == "true"
OTEL_SERVICE_NAME: str = os.environ.get("WFD_OTEL_SERVICE_NAME", "zenic-flijo")
OTEL_EXPORTER: str = os.environ.get("WFD_OTEL_EXPORTER", "none")
OTEL_EXPORTER_ENDPOINT: str = os.environ.get("WFD_OTEL_EXPORTER_ENDPOINT", "")
OTEL_SAMPLING_RATE: float = float(os.environ.get("WFD_OTEL_SAMPLING_RATE", "0.1"))


class TracingManager:
    """
    Gestor de tracing con OpenTelemetry.

    Configura el TracerProvider, los exportadores y proporciona
    helpers para crear y gestionar spans.

    Cuando OpenTelemetry no esta disponible o esta deshabilitado,
    opera en modo no-op (sin overhead).
    """

    _instance: TracingManager | None = None
    _lock = threading.RLock()

    def __new__(cls) -> TracingManager:
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
            self._tracer: Any | None = None
            self._tracer_provider: Any | None = None
            self._initialized_otel = False

    # ── Inicializacion ───────────────────────────────────────

    def initialize(self) -> None:
        """
        Configura el TracerProvider y los exportadores de OpenTelemetry.

        Intenta importar los paquetes de OpenTelemetry. Si no estan
        disponibles, opera en modo no-op.
        """
        if not OTEL_ENABLED:
            logger.info("TracingManager: telemetria deshabilitada (WFD_OTEL_ENABLED=false)")
            return

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
            from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

            # Recurso del servicio
            resource = Resource.create(
                {
                    "service.name": OTEL_SERVICE_NAME,
                    "service.version": "1.0.0",
                }
            )

            # Sampler con tasa configurable
            sampler = TraceIdRatioBased(rate=OTEL_SAMPLING_RATE)

            # TracerProvider
            self._tracer_provider = SDKTracerProvider(
                resource=resource,
                sampler=sampler,
            )

            # Configurar exportador
            exporter = self._create_exporter()
            if exporter:
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                self._tracer_provider.add_span_processor(BatchSpanProcessor(exporter))

            # Registrar como provider global
            trace.set_tracer_provider(self._tracer_provider)

            # Obtener tracer
            self._tracer = trace.get_tracer(OTEL_SERVICE_NAME)
            self._initialized_otel = True

            logger.info(
                f"TracingManager: OpenTelemetry configurado "
                f"(service={OTEL_SERVICE_NAME}, exporter={OTEL_EXPORTER}, "
                f"sampling_rate={OTEL_SAMPLING_RATE})"
            )

        except ImportError:
            logger.warning(
                "TracingManager: paquetes opentelemetry no instalados. "
                "Instalar con: pip install opentelemetry-api opentelemetry-sdk"
            )
        except Exception as e:
            logger.warning(f"TracingManager: error configurando OpenTelemetry: {e}")

    def _create_exporter(self) -> Any | None:
        """Crea el exportador de traces segun la configuracion."""
        if OTEL_EXPORTER == "jaeger":
            return self._create_jaeger_exporter()
        elif OTEL_EXPORTER == "otlp":
            return self._create_otlp_exporter()
        elif OTEL_EXPORTER == "console":
            return self._create_console_exporter()
        elif OTEL_EXPORTER == "none":
            return None
        else:
            logger.warning(f"TracingManager: exportador desconocido '{OTEL_EXPORTER}', usando none")
            return None

    def _create_jaeger_exporter(self) -> Any | None:
        """Crea exportador Jaeger."""
        try:
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter

            endpoint = OTEL_EXPORTER_ENDPOINT or "localhost:14268"
            return JaegerExporter(agent_host_name=endpoint.split(":")[0], agent_port=int(endpoint.split(":")[1]))
        except ImportError:
            logger.warning("TracingManager: opentelemetry-exporter-jaeger no instalado")
            return None

    def _create_otlp_exporter(self) -> Any | None:
        """Crea exportador OTLP."""
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            endpoint = OTEL_EXPORTER_ENDPOINT or "localhost:4317"
            return OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            logger.warning("TracingManager: opentelemetry-exporter-otlp no instalado")
            return None

    def _create_console_exporter(self) -> Any | None:
        """Crea exportador Console (para debug)."""
        try:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            return ConsoleSpanExporter()
        except ImportError:
            return None

    # ── Operaciones de tracing ───────────────────────────────

    def get_tracer(self) -> Any | None:
        """
        Retorna el tracer de OpenTelemetry.

        Returns:
            Tracer de OTel, o None si no esta configurado
        """
        return self._tracer

    @contextmanager
    # legítimo: opentelemetry.trace.Span, no tipado por compatibilidad
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Any, None, None]:
        """
        Context manager para crear y gestionar un span.

        Si OTel no esta disponible, es un no-op.

        Args:
            name: Nombre del span
            attributes: Atributos iniciales del span

        Yields:
            Span object (o None si OTel no esta disponible)
        """
        if not self._tracer:
            yield None
            return

        with self._tracer.start_as_current_span(name, attributes=attributes or {}) as span:
            yield span

    # legítimo: opentelemetry.trace.Span, no tipado por compatibilidad
    def start_span(
        self,
        name: str,
        parent: Any | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """
        Inicia un span manualmente.

        Args:
            name: Nombre del span
            parent: Span padre (opcional)
            attributes: Atributos del span

        Returns:
            Span object, o None si OTel no esta disponible
        """
        if not self._tracer:
            return None

        kwargs: dict[str, Any] = {"attributes": attributes or {}}
        if parent is not None:
            from opentelemetry.trace import set_span_in_context

            kwargs["context"] = set_span_in_context(parent)

        return self._tracer.start_span(name, **kwargs)

    # legítimo: opentelemetry.trace.Span no tipado por compatibilidad
    def end_span(self, span: Any) -> None:
        """Finaliza un span manualmente."""
        if span and hasattr(span, "end"):
            span.end()

    # ── Contexto de traza ────────────────────────────────────

    def get_current_trace_id(self) -> str:
        """
        Obtiene el trace_id del contexto actual.

        Returns:
            trace_id hex string, o "" si no hay traza activa
        """
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                return format(span.get_span_context().trace_id, "032x")
        except ImportError:
            pass
        return ""

    def get_current_span_id(self) -> str:
        """
        Obtiene el span_id del contexto actual.

        Returns:
            span_id hex string, o "" si no hay span activo
        """
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                return format(span.get_span_context().span_id, "016x")
        except ImportError:
            pass
        return ""

    def get_trace_context(self) -> dict[str, str]:
        """
        Obtiene el contexto de traza actual para correlacion de logs.

        Returns:
            dict con trace_id y span_id
        """
        return {
            "trace_id": self.get_current_trace_id(),
            "span_id": self.get_current_span_id(),
        }

    # ── Shutdown ─────────────────────────────────────────────

    def shutdown(self) -> None:
        """Cierra el TracerProvider y hace flush de los spans pendientes."""
        if self._tracer_provider and hasattr(self._tracer_provider, "shutdown"):
            try:
                self._tracer_provider.shutdown()
                logger.info("TracingManager: TracerProvider cerrado correctamente")
            except Exception as e:
                logger.warning(f"TracingManager: error al cerrar TracerProvider: {e}")

    # ── Reset para testing ───────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None
