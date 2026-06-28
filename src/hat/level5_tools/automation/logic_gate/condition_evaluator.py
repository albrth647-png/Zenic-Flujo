"""
ORBITAL — ConditionEvaluator Orbital (OVC Compartido)
=======================================================

ConditionEvaluator con resonancia orbital usando OVC compartido via OrbitalContext.

Estrategia dual:
1. Intenta evaluacion textual (parser preciso para condiciones concretas)
2. Si no hay suficientes variables orbitales, fallback orbital (resonancia)

MEJORA vs version anterior:
- Ahora usa OrbitalContext → OVC compartido con todos los demas componentes
- Las condiciones retroalimentan al mismo OVC que usan los pasos del workflow

Compatibilidad: mantiene la misma API que ConditionEvaluator.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar, Any

from src.core.logging import setup_logging
from src.core.utils import safe_get
from src.orbital.context import OrbitalContext
from src.orbital.models import TWO_PI

logger = setup_logging(__name__)


class ConditionEvaluator:
    """
    ResonanceDetector — Evaluacion de condiciones por resonancia orbital (OVC compartido).

    Usa OrbitalContext para compartir el OVC con StepExecutor, WorkflowEngine, etc.

    1. Cada variable del contexto se convierte en variable orbital (OVC compartido)
    2. Cada condicion se convierte en variable orbital con fase umbral
    3. TOR(context_var, condition_var) determina si hay resonancia
    4. Si TOR > umbral → condicion verdadera (resonancia)
    5. Fallback al parser textual para condiciones complejas

    VENTAJA del OVC compartido:
    - Las condiciones ven las mismas variables orbitales que los pasos
    - La retroalimentacion es unificada y coherente
    - Determinista: mismas condiciones + mismo contexto → mismo resultado
    """

    # Operadores soportados (para fallback textual)
    SUPPORTED_OPERATORS: ClassVar[list[str]] = ["==", "!=", ">=", "<=", ">", "<", "in", "contains"]

    def __init__(self):
        self._ctx = OrbitalContext()
        self._resonance_threshold = 0.0  # TOR > 0 = alineados = verdadero

    def evaluate(self, condition: str, context: dict[str, object]) -> bool:
        """
        Evalua una condicion contra el contexto.

        Estrategia:
        1. Intentar evaluacion textual (parser original) — preciso para condiciones concretas
        2. Si el parser falla, intentar evaluacion orbital (resonancia)
        3. Las variables orbitales se crean y retroalimentan via OrbitalContext compartido

        Args:
            condition: "stock < 10 AND producto == 'Tornillos'"
            context: {"stock": 5, "producto": "Tornillos"}

        Returns:
            bool: Resultado de la evaluacion

        Raises:
            ValueError: Si la expresion es invalida
        """
        if not condition or not condition.strip():
            return True

        # 1. Intentar evaluacion textual (parser original — preciso)
        try:
            tokens = self._tokenize(condition)
            ast = self._parse(tokens)
            result = self._eval_ast(ast, context)
            # Retroalimentar al orbital compartido
            self._orbital_retrofeed(condition, context, result)
            return result
        except (ValueError, KeyError, TypeError, IndexError) as e:
            logger.debug(f"Parser textual fallo para '{condition}': {e}")

        # 2. Fallback: evaluacion orbital
        orbital_result = self._evaluate_orbital(condition, context)
        if orbital_result is not None:
            return orbital_result

        raise ValueError(f"Error evaluando condicion: '{condition}' — ni textual ni orbital")

    def validate_expression(self, expression: str) -> dict[str, Any]:
        """Valida que una expresion sea sintacticamente correcta."""
        try:
            tokens = self._tokenize(expression)
            self._parse(tokens)
            return {"valid": True}
        except ValueError as e:
            return {"valid": False, "error": str(e)}

    # ── Evaluacion Orbital (OVC compartido) ──────────────────

    def _orbital_retrofeed(self, condition: str, context: dict[str, Any], result: bool) -> None:
        """Retroalimenta el resultado al OVC compartido."""
        # Fix BUG-W8: usar prefijo de execution_id para aislar workflows
        orbital_prefix = context.get("_orbital_var_prefix", "")
        # Hash no criptográfico: identificador determinista para variable orbital (B324 mitigado).
        condition_name = f"{orbital_prefix}cond_{hashlib.md5(condition.encode(), usedforsecurity=False).hexdigest()[:8]}"
        if self._ctx.ovc.get_variable(condition_name) is None:
            # Hash no criptográfico: deriva theta determinista de la condición (B324 mitigado).
            hash_val = int(hashlib.md5(condition.encode(), usedforsecurity=False).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=condition_name,
                theta=theta,
                amplitude=1.5,
                velocity=0.1,
                orbit_group="condition_eval",
                metadata={"source": "condition", "condition": condition},
            )

        cond_var = self._ctx.ovc.get_variable(condition_name)
        if cond_var:
            if result:
                cond_var.advance(dt=1.0)
            else:
                cond_var.retrofeed(-0.1, damping=0.3)

    def _evaluate_orbital(self, condition: str, context: dict[str, Any]) -> bool | None:
        """Evalua una condicion usando resonancia orbital (OVC compartido)."""
        # Fix BUG-W8: usar prefijo de execution_id para aislar workflows
        orbital_prefix = context.get("_orbital_var_prefix", "")
        numeric_vars = {}
        for key, value in context.items():
            if isinstance(value, (int, float)):
                numeric_vars[key] = value
            elif isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, (int, float)):
                        numeric_vars[f"{key}.{subkey}"] = subvalue

        if not numeric_vars:
            return None

        for var_name, var_value in numeric_vars.items():
            orbital_name = f"{orbital_prefix}ctx_{var_name}"
            if self._ctx.ovc.get_variable(orbital_name) is None:
                theta = abs(var_value) % TWO_PI
                amplitude = abs(var_value) if var_value != 0 else 1.0
                amplitude = min(amplitude, 10.0)
                self._ctx.ovc.create_variable(
                    name=orbital_name,
                    theta=theta,
                    amplitude=amplitude,
                    velocity=0.05,
                    orbit_group="condition_context",
                    metadata={"source": "context", "original_name": var_name},
                )
            else:
                var = self._ctx.ovc.get_variable(orbital_name)
                theta = abs(var_value) % TWO_PI
                var.amplitude = min(abs(var_value) if var_value != 0 else 1.0, 10.0)

        # Fix BUG-W8: usar prefijo de execution_id
        condition_name = f"{orbital_prefix}cond_{hashlib.md5(condition.encode(), usedforsecurity=False).hexdigest()[:8]}"
        if self._ctx.ovc.get_variable(condition_name) is None:
            # Hash no criptográfico: deriva theta determinista de la condición (B324 mitigado).
            hash_val = int(hashlib.md5(condition.encode(), usedforsecurity=False).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=condition_name,
                theta=theta,
                amplitude=1.5,
                velocity=0.1,
                orbit_group="condition_eval",
                metadata={"source": "condition", "condition": condition},
            )

        cond_var = self._ctx.ovc.get_variable(condition_name)
        if not cond_var:
            return None

        total_alignment = 0.0
        count = 0
        for var_name in numeric_vars:
            orbital_name = f"{orbital_prefix}ctx_{var_name}"
            try:
                tor_result = self._ctx.tor.calculate(condition_name, orbital_name)
                total_alignment += tor_result.tor_value
                count += 1
            except KeyError:
                pass

        if count == 0:
            return None

        avg_alignment = total_alignment / count
        result = avg_alignment > self._resonance_threshold

        logger.debug(
            f"ResonanceDetector: '{condition}' → alineacion={avg_alignment:.4f} "
            f"→ {'RESONANCIA (True)' if result else 'sin resonancia (False)'}"
        )

        if result:
            cond_var.advance(dt=1.0)
        else:
            cond_var.retrofeed(-0.1, damping=0.3)

        return result

    # ── Parser Textual (Fallback) ───────────────────────────

    def _tokenize(self, text: str) -> list[dict]:
        """Convierte la condicion en tokens (parser original como fallback)."""
        tokens = []
        i = 0
        while i < len(text):
            char = text[i]

            if char.isspace():
                i += 1
                continue

            if char in "()":
                tokens.append({"type": "paren", "value": char})
                i += 1
                continue

            for op in self.SUPPORTED_OPERATORS:
                if text[i : i + len(op)] == op:
                    tokens.append({"type": "operator", "value": op})
                    i += len(op)
                    break
            else:
                if char in ("'", '"'):
                    quote = char
                    j = i + 1
                    while j < len(text) and text[j] != quote:
                        j += 1
                    if j >= len(text):
                        raise ValueError(f"String sin cerrar: {text[i:]}")
                    tokens.append({"type": "string", "value": text[i + 1 : j]})
                    i = j + 1
                    continue

                if char.isdigit() or (char == "-" and i + 1 < len(text) and text[i + 1].isdigit()):
                    j = i + 1
                    while j < len(text) and (text[j].isdigit() or text[j] == "."):
                        j += 1
                    num_str = text[i:j]
                    tokens.append(
                        {
                            "type": "number",
                            "value": float(num_str) if "." in num_str else int(num_str),
                        }
                    )
                    i = j
                    continue

                if char.isalpha() or char in "_$":
                    j = i + 1
                    while j < len(text) and (text[j].isalnum() or text[j] in "._"):
                        j += 1
                    word = text[i:j]
                    if word.upper() in ("AND", "OR"):
                        tokens.append({"type": "boolean_op", "value": word.upper()})
                    elif word in ("True", "False"):
                        tokens.append({"type": "value", "value": word == "True"})
                    elif word == "None":
                        tokens.append({"type": "value", "value": None})
                    elif word.startswith("$"):
                        tokens.append({"type": "variable", "value": word})
                    else:
                        tokens.append({"type": "variable", "value": word})
                    i = j
                    continue

                raise ValueError(f"Caracter inesperado: '{char}'")

        return tokens

    def _parse(self, tokens: list[dict]) -> dict[str, Any]:
        """Parsea tokens a AST usando índice local (thread-safe)."""
        pos = 0

        def parse_boolean_expr() -> dict[str, Any]:
            nonlocal pos
            left = parse_comparison_expr()
            while pos < len(tokens) and tokens[pos]["type"] == "boolean_op":
                op = tokens[pos]["value"]
                pos += 1
                right = parse_comparison_expr()
                left = {"type": "boolean", "op": op, "left": left, "right": right}
            return left

        def parse_comparison_expr() -> dict[str, Any]:
            nonlocal pos
            if pos < len(tokens) and tokens[pos]["type"] == "paren" and tokens[pos]["value"] == "(":
                pos += 1
                expr = parse_boolean_expr()
                if pos >= len(tokens) or tokens[pos]["type"] != "paren" or tokens[pos]["value"] != ")":
                    raise ValueError("Parentesis sin cerrar")
                pos += 1
                return expr

            left = parse_value()
            if pos < len(tokens) and tokens[pos]["type"] == "operator":
                op = tokens[pos]["value"]
                pos += 1
                right = parse_value()
                return {"type": "comparison", "op": op, "left": left, "right": right}

            return left

        def parse_value() -> dict[str, Any]:
            nonlocal pos
            if pos >= len(tokens):
                raise ValueError("Se esperaba un valor")
            token = tokens[pos]
            if token["type"] in ("value", "string", "number", "variable"):
                pos += 1
                return {"type": token["type"], "value": token["value"]}
            raise ValueError(f"Se esperaba un valor, pero se encontro: {token}")

        ast = parse_boolean_expr()
        if pos < len(tokens):
            raise ValueError(f"Tokens inesperados: {tokens[pos:]}")
        return ast

    def _eval_ast(self, ast: dict[str, Any], context: dict[str, Any]) -> bool:
        if ast["type"] == "boolean":
            left = self._eval_ast(ast["left"], context)
            right = self._eval_ast(ast["right"], context)
            if ast["op"] == "AND":
                return left and right
            elif ast["op"] == "OR":
                return left or right
        elif ast["type"] == "not":
            return not self._eval_ast(ast["expr"], context)
        elif ast["type"] == "comparison":
            left_val = self._resolve_value(ast["left"], context)
            right_val = self._resolve_value(ast["right"], context)
            return self._apply_operator(left_val, ast["op"], right_val)
        elif ast["type"] in ("value", "string", "number", "variable"):
            return bool(self._resolve_value(ast, context))
        raise ValueError(f"Nodo AST desconocido: {ast}")

    def _resolve_value(self, node: dict[str, Any], context: dict[str, Any]) -> bool | str | int | float | list | None:
        if node["type"] == "string" or node["type"] == "number" or node["type"] == "value":
            return node["value"]
        elif node["type"] == "variable":
            var_path = node["value"][1:] if node["value"].startswith("$") else node["value"]
            result = safe_get(context, var_path)
            if result is not None:
                return result
            if not node["value"].startswith("$"):
                logger.warning(f"Variable '{var_path}' no encontrada, usando como string literal")
                return node["value"]
            logger.warning(f"Variable no encontrada en contexto: {var_path}")
            return None
        return None

    def _apply_operator(self, left: object, op: str, right: object) -> bool:
        if op == "==":
            return left == right
        elif op == "!=":
            return left != right
        elif op == ">":
            return left > right
        elif op == "<":
            return left < right
        elif op == ">=":
            return left >= right
        elif op == "<=":
            return left <= right
        elif op == "in":
            return left in (right if isinstance(right, (list, tuple, set)) else [right])
        elif op == "contains":
            return right in left if isinstance(left, str) else False
        raise ValueError(f"Operador no soportado: {op}")
