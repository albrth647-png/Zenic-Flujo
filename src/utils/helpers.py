"""
Workflow Determinista — Funciones Auxiliares
"""

import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import TypeVar, Any

T = TypeVar("T")


def generate_id() -> str:
    """Genera un ID único alfanumérico de 8 caracteres."""
    return uuid.uuid4().hex[:8]


def generate_secure_token(length: int = 32) -> str:
    """Genera un token criptográficamente seguro usando secrets module."""
    return secrets.token_hex(length // 2)


def now_iso() -> str:
    """Retorna timestamp actual en ISO 8601."""
    return datetime.now(UTC).isoformat()


def truncate(text: str, max_length: int = 100) -> str:
    """Trunca texto a max_length caracteres."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def safe_get[T](data: dict[str, Any], path: str, default: T | None = None) -> T | None:
    """
    Obtiene un valor de un dict anidado usando notación de puntos.
    Ejemplo: safe_get({"a": {"b": 1}}, "a.b") → 1
    Retorna el valor en su tipo original (str, int, float, list, dict) o None.
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current


def resolve_variables(template: str, context: dict[str, Any]) -> str | int | float | list | dict | None:
    """
    Resuelve variables en formato $input.nombre, $output.step1.email, etc.
    Busca en context usando notación de puntos.

    - Si el template es una sola variable (ej: "$input.cantidad"), retorna el
      valor original preservando su tipo (int, float, str, etc.).
    - Si el template mezcla texto con variables (ej: "Hola $input.nombre"),
      retorna un string con todas las variables resueltas.
    - Si la variable no existe, retorna el placeholder "${path}".
    """
    pattern = r"\$(\w+(?:\.\w+)*)"
    matches = list(re.finditer(pattern, template))

    if not matches:
        return template

    # Caso especial: template es UNA SOLA variable (ej: "$input.cantidad")
    if len(matches) == 1 and matches[0].start() == 0 and matches[0].end() == len(template):
        path = matches[0].group(1)
        value = safe_get(context, path)
        if value is None:
            return f"${{{path}}}"
        return value  # Preserva el tipo original (int, float, list, dict, etc.)

    # Caso general: template con texto + variables
    def replacer(match):
        path = match.group(1)
        value = safe_get(context, path)
        if value is None:
            return f"${{{path}}}"
        return str(value)

    return re.sub(pattern, replacer, template)


def parse_cron_expression(expr: str) -> dict[str, list[int]]:
    """
    Parsea expresión cron de 5 campos estándar.
    Retorna dict con campos: minute, hour, day_of_month, month, day_of_week
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
            values = list(range(min_val, max_val + 1))
            break
        else:
            values.append(int(part))

    return sorted({v for v in values if min_val <= v <= max_val})


def should_run_now(cron_fields: dict[str, list[int]], dt: datetime | None = None) -> bool:
    """Verifica si la fecha/hora actual coincide con la expresión cron."""
    from datetime import datetime as dt_mod

    now = dt or dt_mod.now()

    checks = [
        now.minute in cron_fields.get("minute", []),
        now.hour in cron_fields.get("hour", []),
        now.day in cron_fields.get("day_of_month", []),
        now.month in cron_fields.get("month", []),
        now.weekday() in cron_fields.get("day_of_week", []),
    ]

    return all(checks)
