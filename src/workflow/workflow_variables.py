"""
WorkflowVariables — Sistema de variables de workflow
=======================================================

Sprint 3 del Roadmap Competitivo.
Agrega: set/get/delete/exists de variables, transform functions,
math functions, y agregadores sobre arrays.

Todas las funciones retornan un dict para compatibilidad con
StepExecutor._execute_system_action().
"""

from __future__ import annotations

import math
from typing import Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


class WorkflowVariables:
    """
    Sistema de variables de workflow.

    Proporciona operaciones para manipular variables dentro del contexto
    de ejecución de un workflow: set, get, delete, exists, transform
    (upper, lower, trim, replace, split, join, substring, length),
    math (add, subtract, multiply, divide, floor, ceil, round, abs,
    min, max, power, sqrt, modulo), y aggregate (sum, avg, count,
    min, max sobre listas).

    Uso como system action:
    ```json
    {
        "tool": "system",
        "action": "variable",
        "params": {
            "operation": "set",
            "name": "total",
            "value": 42
        }
    }
    ```
    """

    # ── Variable operations ─────────────────────────────────

    @staticmethod
    def set_variable(name: str, value: Any, context: dict) -> dict:
        """
        Establece una variable en el contexto del workflow.

        Args:
            name: Nombre de la variable (ej: "total", "user.name")
            value: Valor a almacenar (str, int, float, list, dict, bool)
            context: Contexto de ejecución del workflow

        Returns:
            dict con {name, value, status: "set"}
        """
        context[name] = value
        logger.debug(f"WorkflowVariables: set '{name}' = {repr(value)[:100]}")
        return {"name": name, "value": value, "status": "set"}

    @staticmethod
    def get_variable(name: str, context: dict, default: Any = None) -> dict:
        """
        Obtiene una variable del contexto del workflow.

        Args:
            name: Nombre de la variable
            context: Contexto de ejecución
            default: Valor por defecto si no existe

        Returns:
            dict con {name, value, found: bool}
        """
        from src.core.utils import safe_get

        # Soporte para notación de puntos (ej: "steps_output.2.result")
        if "." in name:
            value = safe_get(context, name, default)
            found = value is not None
        else:
            value = context.get(name, default)
            found = name in context

        return {"name": name, "value": value, "found": found}

    @staticmethod
    def delete_variable(name: str, context: dict) -> dict:
        """
        Elimina una variable del contexto del workflow.

        Args:
            name: Nombre de la variable
            context: Contexto de ejecución

        Returns:
            dict con {name, existed: bool, status: "deleted"}
        """
        existed = name in context
        if existed:
            del context[name]
            logger.debug(f"WorkflowVariables: deleted '{name}'")
        return {"name": name, "existed": existed, "status": "deleted"}

    @staticmethod
    def exists_variable(name: str, context: dict) -> dict:
        """
        Verifica si una variable existe en el contexto.

        Args:
            name: Nombre de la variable
            context: Contexto de ejecución

        Returns:
            dict con {name, exists: bool}
        """
        from src.core.utils import safe_get

        if "." in name:
            value = safe_get(context, name)
            exists = value is not None
        else:
            exists = name in context

        return {"name": name, "exists": exists}

    # ── Transform functions ────────────────────────────────

    @staticmethod
    def transform_upper(value: str) -> dict:
        """Convierte a mayúsculas."""
        return {"result": str(value).upper()}

    @staticmethod
    def transform_lower(value: str) -> dict:
        """Convierte a minúsculas."""
        return {"result": str(value).lower()}

    @staticmethod
    def transform_trim(value: str) -> dict:
        """Elimina espacios al inicio y final."""
        return {"result": str(value).strip()}

    @staticmethod
    def transform_replace(value: str, old: str, new: str, count: int = -1) -> dict:
        """Reemplaza una subcadena por otra."""
        if count >= 0:
            return {"result": str(value).replace(old, new, count)}
        return {"result": str(value).replace(old, new)}

    @staticmethod
    def transform_split(value: str, delimiter: str = ",") -> dict:
        """Divide un string en una lista usando un delimitador."""
        return {"result": str(value).split(delimiter)}

    @staticmethod
    def transform_join(values: list, delimiter: str = ",") -> dict:
        """Une una lista en un string usando un delimitador."""
        return {"result": delimiter.join(str(v) for v in values)}

    @staticmethod
    def transform_substring(value: str, start: int = 0, end: int | None = None) -> dict:
        """Extrae una subcadena."""
        s = str(value)
        if end is not None:
            return {"result": s[start:end]}
        return {"result": s[start:]}

    @staticmethod
    def transform_length(value: Any) -> dict:
        """Retorna la longitud de un string, lista o dict."""
        try:
            return {"result": len(value)}
        except TypeError:
            return {"result": len(str(value))}

    # ── Math functions ─────────────────────────────────────

    @staticmethod
    def math_add(a: float, b: float) -> dict:
        """Suma dos números."""
        return {"result": float(a) + float(b), "a": a, "b": b}

    @staticmethod
    def math_subtract(a: float, b: float) -> dict:
        """Resta dos números."""
        return {"result": float(a) - float(b), "a": a, "b": b}

    @staticmethod
    def math_multiply(a: float, b: float) -> dict:
        """Multiplica dos números."""
        return {"result": float(a) * float(b), "a": a, "b": b}

    @staticmethod
    def math_divide(a: float, b: float) -> dict:
        """Divide dos números. Retorna error si b es 0."""
        if float(b) == 0:
            return {"result": None, "error": "division_by_zero", "a": a, "b": b}
        return {"result": float(a) / float(b), "a": a, "b": b}

    @staticmethod
    def math_floor(value: float) -> dict:
        """Redondea hacia abajo."""
        return {"result": math.floor(float(value))}

    @staticmethod
    def math_ceil(value: float) -> dict:
        """Redondea hacia arriba."""
        return {"result": math.ceil(float(value))}

    @staticmethod
    def math_round(value: float, decimals: int = 0) -> dict:
        """Redondea a N decimales."""
        return {"result": round(float(value), decimals)}

    @staticmethod
    def math_abs(value: float) -> dict:
        """Valor absoluto."""
        return {"result": abs(float(value))}

    @staticmethod
    def math_min(a: float, b: float) -> dict:
        """Retorna el menor de dos números."""
        return {"result": min(float(a), float(b))}

    @staticmethod
    def math_max(a: float, b: float) -> dict:
        """Retorna el mayor de dos números."""
        return {"result": max(float(a), float(b))}

    @staticmethod
    def math_power(base: float, exponent: float) -> dict:
        """Potencia: base^exponent."""
        return {"result": math.pow(float(base), float(exponent))}

    @staticmethod
    def math_sqrt(value: float) -> dict:
        """Raíz cuadrada. Retorna error si value < 0."""
        if float(value) < 0:
            return {"result": None, "error": "negative_sqrt", "value": value}
        return {"result": math.sqrt(float(value))}

    @staticmethod
    def math_modulo(a: float, b: float) -> dict:
        """Módulo (resto de división)."""
        return {"result": float(a) % float(b), "a": a, "b": b}

    # ── Aggregators ────────────────────────────────────────

    @staticmethod
    def aggregate_sum(values: list) -> dict:
        """Suma todos los elementos numéricos de una lista."""
        total = sum(float(v) for v in values)
        return {"result": total, "count": len(values)}

    @staticmethod
    def aggregate_avg(values: list) -> dict:
        """Promedio de los elementos numéricos."""
        if not values:
            return {"result": 0, "count": 0, "error": "empty_list"}
        total = sum(float(v) for v in values)
        return {"result": total / len(values), "count": len(values)}

    @staticmethod
    def aggregate_count(values: list) -> dict:
        """Cuenta los elementos de una lista."""
        return {"result": len(values)}

    @staticmethod
    def aggregate_min(values: list) -> dict:
        """Retorna el mínimo de una lista numérica."""
        if not values:
            return {"result": None, "error": "empty_list"}
        return {"result": min(float(v) for v in values)}

    @staticmethod
    def aggregate_max(values: list) -> dict:
        """Retorna el máximo de una lista numérica."""
        if not values:
            return {"result": None, "error": "empty_list"}
        return {"result": max(float(v) for v in values)}

    # ── Context helpers ────────────────────────────────────

    @staticmethod
    def get_context_snapshot(context: dict) -> dict:
        """
        Retorna un snapshot del contexto del workflow.

        Incluye variables clave: input, steps_output, output,
        workflow, settings, y variables personalizadas.

        Útil para debugging o logging.
        """
        safe_keys = {"input", "output", "steps_output", "workflow", "settings", "_last_step_id", "_last_step_var"}
        snapshot = {}
        for key in safe_keys:
            if key in context:
                snapshot[key] = context[key]

        # También incluir variables personalizadas (strings, números)
        custom = {}
        for key, value in context.items():
            if key.startswith("_") or key in safe_keys:
                continue
            if isinstance(value, (str, int, float, bool, list)) and (
                (isinstance(value, list) and len(value) <= 10) or not isinstance(value, list)
            ):
                custom[key] = value
        if custom:
            snapshot["custom_vars"] = custom

        return snapshot

    # ── Dispatch ───────────────────────────────────────────

    @classmethod
    def execute(cls, params: dict, context: dict) -> dict:
        """
        Dispatcher principal para el system action 'variable'.

        Args:
            params: Diccionario con la operación y sus parámetros.
                    Debe incluir 'operation' con uno de:
                    set, get, delete, exists, transform, math, aggregate
            context: Contexto de ejecución del workflow

        Returns:
            dict con el resultado de la operación

        Raises:
            ValueError: Si la operación no es reconocida
        """
        operation = params.get("operation", "")
        name = params.get("name", "")
        value = params.get("value")

        # ── Variable operations ──
        if operation == "set":
            return cls.set_variable(name, value, context)

        if operation == "get":
            default = params.get("default")
            return cls.get_variable(name, context, default)

        if operation == "delete":
            return cls.delete_variable(name, context)

        if operation == "exists":
            return cls.exists_variable(name, context)

        # ── Transform operations ──
        if operation == "transform":
            transform_name = params.get("transform", "")
            val = params.get("value", "")

            if transform_name == "upper":
                return cls.transform_upper(val)
            elif transform_name == "lower":
                return cls.transform_lower(val)
            elif transform_name == "trim":
                return cls.transform_trim(val)
            elif transform_name == "replace":
                return cls.transform_replace(val, params.get("old", ""), params.get("new", ""), params.get("count", -1))
            elif transform_name == "split":
                return cls.transform_split(val, params.get("delimiter", ","))
            elif transform_name == "join":
                return cls.transform_join(params.get("values", []), params.get("delimiter", ","))
            elif transform_name == "substring":
                return cls.transform_substring(val, params.get("start", 0), params.get("end"))
            elif transform_name == "length":
                return cls.transform_length(val)
            else:
                raise ValueError(
                    f"Transform desconocido: {transform_name}. "
                    f"Disponibles: upper, lower, trim, replace, "
                    f"split, join, substring, length"
                )

        # ── Math operations ──
        if operation == "math":
            math_name = params.get("math", "")
            a = params.get("a", 0)
            b = params.get("b", 0)

            if math_name == "add":
                return cls.math_add(a, b)
            elif math_name == "subtract":
                return cls.math_subtract(a, b)
            elif math_name == "multiply":
                return cls.math_multiply(a, b)
            elif math_name == "divide":
                return cls.math_divide(a, b)
            elif math_name == "floor":
                return cls.math_floor(a)
            elif math_name == "ceil":
                return cls.math_ceil(a)
            elif math_name == "round":
                decimals = params.get("decimals", 0)
                return cls.math_round(a, decimals)
            elif math_name == "abs":
                return cls.math_abs(a)
            elif math_name == "min":
                return cls.math_min(a, b)
            elif math_name == "max":
                return cls.math_max(a, b)
            elif math_name == "power":
                return cls.math_power(a, b)
            elif math_name == "sqrt":
                return cls.math_sqrt(a)
            elif math_name == "modulo":
                return cls.math_modulo(a, b)
            else:
                raise ValueError(
                    f"Math desconocido: {math_name}. "
                    f"Disponibles: add, subtract, multiply, divide, "
                    f"floor, ceil, round, abs, min, max, power, "
                    f"sqrt, modulo"
                )

        # ── Aggregate operations ──
        if operation == "aggregate":
            agg_name = params.get("aggregate", "")
            values = params.get("values", [])

            if agg_name == "sum":
                return cls.aggregate_sum(values)
            elif agg_name == "avg":
                return cls.aggregate_avg(values)
            elif agg_name == "count":
                return cls.aggregate_count(values)
            elif agg_name == "min":
                return cls.aggregate_min(values)
            elif agg_name == "max":
                return cls.aggregate_max(values)
            else:
                raise ValueError(f"Aggregate desconocido: {agg_name}. Disponibles: sum, avg, count, min, max")

        # ── Snapshot ──
        if operation == "snapshot":
            return cls.get_context_snapshot(context)

        raise ValueError(
            f"Operación desconocida: {operation}. "
            f"Disponibles: set, get, delete, exists, transform, "
            f"math, aggregate, snapshot"
        )
