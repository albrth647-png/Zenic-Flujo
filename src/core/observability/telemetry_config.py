"""
Configuracion de telemetria — constantes y variables de entorno.

Centraliza los valores de configuracion leidos al arrancar el proceso
para que tanto ``TelemetryService`` como sus mixins y otros modulos
puedan consultarlos sin duplicar logicas de lectura de entorno.

Variables de entorno reconocidas:
- ``WFD_OTEL_METRICS_PORT``: puerto de scrape Prometheus (default 9090).
"""

from __future__ import annotations

import os

# ── Configuracion ─────────────────────────────────────────────

#: Puerto de scrape Prometheus para el exportador de metricas OTel.
#: Leido una sola vez al importar el modulo para evitar re-lecturas
#: durante la ejecucion (mismo comportamiento que la version previa
#: del coordinator).
OTEL_METRICS_PORT: int = int(os.environ.get("WFD_OTEL_METRICS_PORT", "9090"))


__all__ = ["OTEL_METRICS_PORT"]
