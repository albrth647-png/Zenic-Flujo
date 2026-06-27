"""src.core.utils.templating — Resolucion de variables y acceso a datos anidados.

Split de ``src/utils/helpers.py`` (M1.4).
"""

from __future__ import annotations

import re
from typing import Any, TypeVar

T = TypeVar("T")


def safe_get[T](data: dict[str, Any], path: str, default: T | None = None) -> T | None:
    """
    Obtiene un valor de un dict[str, Any] anidado usando notación de puntos.
    Ejemplo: safe_get({"a": {"b": 1}}, "a.b") → 1
    Retorna el valor en su tipo original (str, int, float, list, dict[str, Any]) o None.
    """
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict[str, Any]):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current


def resolve_variables(template: str, context: dict[str, Any]) -> str | int | float | list[Any] | dict[str, Any] | None:
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
    matches = list[Any](re.finditer(pattern, template))

    if not matches:
        return template

    # Caso especial: template es UNA SOLA variable (ej: "$input.cantidad")
    if len(matches) == 1 and matches[0].start() == 0 and matches[0].end() == len(template):
        path = matches[0].group(1)
        value = safe_get(context, path)
        if value is None:
            return f"${{{path}}}"
        return value  # Preserva el tipo original (int, float, list, dict[str, Any], etc.)

    # Caso general: template con texto + variables
    def replacer(match):
        path = match.group(1)
        value = safe_get(context, path)
        if value is None:
            return f"${{{path}}}"
        return str(value)

    return re.sub(pattern, replacer, template)


__all__ = ["resolve_variables", "safe_get"]
