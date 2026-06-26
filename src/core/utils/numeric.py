"""src.core.utils.numeric — Coercion numerica.

Split de ``src/utils/helpers.py`` (M1.4).
"""

from __future__ import annotations

from typing import Any


def coerce_numeric(value: Any, default: float | None = None) -> float | None:
    """Convierte un valor a numérico (float), con manejo graceful de errores.

    Fix Sprint 4 bug #51: antes esta lógica estaba duplicada en
    `step_executor.py:_coerce_numeric` y `workflow_variables.py` (lógica
    similar inline). Centralizada aquí para evitar drift.

    Reglas:
    - int/float → float(value)
    - str numérica ("123", "1.5") → float(value)
    - str no numérica → default (None si no se pasa)
    - bool → float(value) (True=1.0, False=0.0)
    - None → default
    - otros tipos → default

    Args:
        value: Valor a coercer.
        default: Valor a retornar si no se puede coercer. Default None.

    Returns:
        float | None: El valor coerceado, o default si no se pudo.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        # bool es subclass de int en Python, manejarlo primero
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    # Otros tipos (dict, list, object) → no numeric
    return default


__all__ = ["coerce_numeric"]
