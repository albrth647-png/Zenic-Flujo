"""src.core.utils.cron — Parser y evaluador de expresiones cron de 5 campos.

Split de ``src/utils/helpers.py`` (M1.4).

Bug fix M1.4: el dia de la semana en cron usa la convencion 0=Domingo,
mientras que ``datetime.weekday()`` de Python devuelve 0=Lunes. La version
anterior comparaba directamente ``now.weekday()`` con la lista
``day_of_week`` y por tanto evaluaba mal cualquier expresion cron que
restriccion el dia de la semana. La conversion correcta es::

    python_weekday = (now.weekday() + 1) % 7  # Monday=0 → Sunday=0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_cron_expression(expr: str) -> dict[str, list[int]]:
    """
    Parsea expresión cron de 5 campos estándar.
    Retorna dict[str, Any] con campos: minute, hour, day_of_month, month, day_of_week
    Cada campo es una lista de valores permitidos.
    """
    fields = ["minute", "hour", "day_of_month", "month", "day_of_week"]
    parts = expr.strip().split()

    if len(parts) != 5:
        raise ValueError(f"Expresión cron inválida: {expr}. Se requieren 5 campos.")

    result = {}
    for field_name, part in zip(fields, parts, strict=False):
        result[field_name] = _parse_cron_field(part, field_name)

    return result


def _parse_cron_field(field: str, field_name: str) -> list[int]:
    """Parsea un campo individual de una expresión cron."""
    ranges = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day_of_month": (1, 31),
        "month": (1, 12),
        "day_of_week": (0, 6),
    }

    min_val, max_val = ranges[field_name]
    values = []

    for part in field.split(","):
        if "/" in part:
            base, step = part.split("/")
            step = int(step)
            if base == "*":
                start = min_val
            elif "-" in base:
                start, end = base.split("-")
                start = int(start)
            else:
                start = int(base)
            values.extend(range(start, max_val + 1, step))
        elif "-" in part:
            start, end = part.split("-")
            values.extend(range(int(start), int(end) + 1))
        elif part == "*":
            values = list[Any](range(min_val, max_val + 1))
            break
        else:
            values.append(int(part))

    return sorted({v for v in values if min_val <= v <= max_val})


def should_run_now(cron_fields: dict[str, list[int]], dt: datetime | None = None) -> bool:
    """Verifica si la fecha/hora actual coincide con la expresión cron.

    Nota sobre ``day_of_week``: cron usa la convencion 0=Domingo, pero
    ``datetime.weekday()`` de Python devuelve 0=Lunes. Se convierte antes
    de comparar (fix M1.4 de bug previo a la migracion).
    """
    now = dt or datetime.now()

    # Conversion Monday=0 (Python) → Sunday=0 (cron).
    # Lunes(0)→1, Martes(1)→2, ..., Sabado(5)→6, Domingo(6)→0
    python_weekday = (now.weekday() + 1) % 7

    checks = [
        now.minute in cron_fields.get("minute", []),
        now.hour in cron_fields.get("hour", []),
        now.day in cron_fields.get("day_of_month", []),
        now.month in cron_fields.get("month", []),
        python_weekday in cron_fields.get("day_of_week", []),
    ]

    return all(checks)


__all__ = ["parse_cron_expression", "should_run_now"]
