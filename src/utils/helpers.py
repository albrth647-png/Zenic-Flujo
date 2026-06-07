"""
Workflow Determinista — Funciones Auxiliares
"""
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any


def generate_id() -> str:
    """Genera un ID único alfanumérico de 8 caracteres."""
    return uuid.uuid4().hex[:8]


def generate_secure_token(length: int = 32) -> str:
    """Genera un token criptográficamente seguro usando secrets module."""
    return secrets.token_hex(length // 2)


def now_iso() -> str:
    """Retorna timestamp actual en ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def truncate(text: str, max_length: int = 100) -> str:
    """Trunca texto a max_length caracteres."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def safe_get(data: dict, path: str, default: Any = None) -> Any:
    """
    Obtiene un valor de un dict anidado usando notación de puntos.
    Ejemplo: safe_get({"a": {"b": 1}}, "a.b") → 1
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


def resolve_variables(template: str, context: dict) -> str:
    """
    Resuelve variables en formato $input.nombre, $output.step1.email, etc.
    Busca en context usando notación de puntos.
    """
    pattern = r'\$(\w+(?:\.\w+)*)'

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
    for field_name, part in zip(fields, parts):
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

    return sorted(set(v for v in values if min_val <= v <= max_val))


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
