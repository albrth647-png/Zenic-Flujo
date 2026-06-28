"""Constantes compartidas del módulo workflow.

Fix Sprint 4 bug #52: antes MAX_SUBWORKFLOW_DEPTH estaba duplicado en
step_execution.py:15 y subworkflow.py:15. Centralizado aquí para evitar
drift futuro.

Cualquier constante que se use en 2+ archivos del módulo workflow debe
vivir aquí.
"""

from __future__ import annotations

# ── Subworkflows ─────────────────────────────────────────
# Profundidad máxima de anidamiento de subworkflows.
# 10 es suficiente para casos reales sin riesgo de stack overflow.
# Si se necesita más, revisar el diseño (probablemente sea un workflow
# mal diseñado con recursión excesiva).
MAX_SUBWORKFLOW_DEPTH = 10

# ── Steps ────────────────────────────────────────────────
# Timeout por defecto para ejecución de steps (segundos).
# Las tools pueden overridear via step.timeout.
DEFAULT_STEP_TIMEOUT = 30

# ── Workflows ────────────────────────────────────────────
# Número máximo de steps por workflow (defensa contra workflows maliciosos
# o mal diseñados que podrían causar OOM).
MAX_STEPS_PER_WORKFLOW = 500

# ── Retención ───────────────────────────────────────────
# Número máximo de versiones por workflow (política de retención).
DEFAULT_VERSION_RETENTION = 20

# ── Dead Letter Queue ───────────────────────────────────
# Número máximo de reintentos antes de mandar a DLQ.
DEFAULT_MAX_RETRIES = 3
