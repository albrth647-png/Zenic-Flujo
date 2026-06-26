"""
Structured Logging Formatter — formateador de logs JSON con trace context.

Extraido de ``telemetry.py`` para mantener el coordinator focalizado en
el ciclo de vida del servicio. ``TelemetryService._setup_json_logging``
instala este formateador en los handlers del root logger cuando OTel
instrumentation no esta disponible.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


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


__all__ = ["JsonLogFormatter"]
