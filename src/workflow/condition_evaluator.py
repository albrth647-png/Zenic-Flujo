"""
Workflow Determinista — ConditionEvaluator
Evalúa condiciones en runtime usando un parser recursivo descendente seguro.
NUNCA usa eval() ni exec().
"""
from typing import Any

from src.utils.helpers import safe_get
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class ConditionEvaluator:
    """
    Evalúa condiciones en formato de texto usando un parser seguro.
    
    Operadores soportados:
    - == (igual)
    - != (distinto)
    - > (mayor que)
    - < (menor que)
    - >= (mayor o igual)
    - <= (menor o igual)
    - in (está en lista)
    - contains (contiene texto)
    - AND / OR (combinación lógica)
    """

    SUPPORTED_OPERATORS = ["==", "!=", ">=", "<=", ">", "<", "in", "contains"]

    def evaluate(self, condition: str, context: dict[str, Any]) -> bool:
        """
        Evalúa una condición contra el contexto dado.
        
        Args:
            condition: "stock < 10 AND producto == 'Tornillos'"
            context: {"stock": 5, "producto": "Tornillos"}
        
        Returns:
            bool: Resultado de la evaluación
        
        Raises:
            ValueError: Si la expresión es inválida o contiene operaciones no permitidas
        """
        if not condition or not condition.strip():
            return True

        try:
            tokens = self._tokenize(condition)
            ast = self._parse(tokens)
            return self._eval_ast(ast, context)
        except Exception as e:
            logger.error(f"Error evaluando condición '{condition}': {e}")
            raise ValueError(f"Error evaluando condición: {e}")

    def validate_expression(self, expression: str) -> dict:
        """
        Valida que una expresión sea sintácticamente correcta.
        
        Returns:
            dict: {"valid": True} o {"valid": False, "error": "mensaje"}
        """
        try:
            tokens = self._tokenize(expression)
            self._parse(tokens)
            return {"valid": True}
        except ValueError as e:
            return {"valid": False, "error": str(e)}

    def _tokenize(self, text: str) -> list[dict]:
        """
        Convierte la condición en tokens.
        Token types: 'value', 'operator', 'paren', 'string', 'number', 'variable'
        """
        tokens = []
        i = 0
        while i < len(text):
            char = text[i]

            # Espacios
            if char.isspace():
                i += 1
                continue

            # Paréntesis
            if char in "()":
                tokens.append({"type": "paren", "value": char})
                i += 1
                continue

            # Operadores de múltiples caracteres
            for op in self.SUPPORTED_OPERATORS:
                if text[i:i + len(op)] == op:
                    tokens.append({"type": "operator", "value": op})
                    i += len(op)
                    break
            else:
                # Strings con comillas
                if char in ("'", '"'):
                    quote = char
                    j = i + 1
                    while j < len(text) and text[j] != quote:
                        j += 1
                    if j >= len(text):
                        raise ValueError(f"String sin cerrar: {text[i:]}")
                    tokens.append({"type": "string", "value": text[i + 1:j]})
                    i = j + 1
                    continue

                # Números
                if char.isdigit() or (char == '-' and i + 1 < len(text) and text[i + 1].isdigit()):
                    j = i + 1
                    while j < len(text) and (text[j].isdigit() or text[j] == '.'):
                        j += 1
                    num_str = text[i:j]
                    tokens.append({
                        "type": "number",
                        "value": float(num_str) if '.' in num_str else int(num_str),
                    })
                    i = j
                    continue

                # Variables/palabras
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
                        # Bare words (no $ prefix) are treated as context variable references
                        # This allows: "stock < 10" where 'stock' resolves from context
                        tokens.append({"type": "variable", "value": word})
                    i = j
                    continue

                raise ValueError(f"Carácter inesperado: '{char}'")

        return tokens

    def _parse(self, tokens: list[dict]) -> dict:
        """
        Parsea tokens en un AST (Abstract Syntax Tree).
        Gramática:
        expression → boolean_expr
        boolean_expr → comparison_expr (("AND" | "OR") comparison_expr)*
        comparison_expr → value (operator value)?
        """
        self._pos = 0
        self._tokens = tokens
        ast = self._parse_boolean_expr()
        if self._pos < len(tokens):
            raise ValueError(f"Tokens inesperados después de la expresión: {tokens[self._pos:]}")
        return ast

    def _parse_boolean_expr(self) -> dict:
        left = self._parse_comparison_expr()
        while self._pos < len(self._tokens) and self._tokens[self._pos]["type"] == "boolean_op":
            op = self._tokens[self._pos]["value"]
            self._pos += 1
            right = self._parse_comparison_expr()
            left = {"type": "boolean", "op": op, "left": left, "right": right}
        return left

    def _parse_comparison_expr(self) -> dict:
        # Paréntesis
        if self._pos < len(self._tokens) and self._tokens[self._pos]["type"] == "paren" and self._tokens[self._pos]["value"] == "(":
            self._pos += 1
            expr = self._parse_boolean_expr()
            if self._pos >= len(self._tokens) or self._tokens[self._pos]["type"] != "paren" or self._tokens[self._pos]["value"] != ")":
                raise ValueError("Paréntesis sin cerrar")
            self._pos += 1
            return expr

        left = self._parse_value()

        if self._pos < len(self._tokens) and self._tokens[self._pos]["type"] == "operator":
            op = self._tokens[self._pos]["value"]
            self._pos += 1
            right = self._parse_value()
            return {"type": "comparison", "op": op, "left": left, "right": right}

        # NOT operator (not value)
        if self._pos < len(self._tokens) and self._tokens[self._pos]["type"] == "value" and str(self._tokens[self._pos]["value"]).upper() == "NOT":
            self._pos += 1
            expr = self._parse_comparison_expr()
            return {"type": "not", "expr": expr}

        return left

    def _parse_value(self) -> dict:
        if self._pos >= len(self._tokens):
            raise ValueError("Se esperaba un valor, pero no hay más tokens")
        token = self._tokens[self._pos]
        if token["type"] in ("value", "string", "number", "variable"):
            self._pos += 1
            return {"type": token["type"], "value": token["value"]}
        raise ValueError(f"Se esperaba un valor, pero se encontró: {token}")

    def _eval_ast(self, ast: dict, context: dict) -> bool:
        """Evalúa el AST recursivamente."""
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

    def _resolve_value(self, node: dict, context: dict) -> Any:
        """Resuelve un nodo valor a su valor concreto."""
        if node["type"] == "string":
            return node["value"]
        elif node["type"] == "number":
            return node["value"]
        elif node["type"] == "value":
            return node["value"]
        elif node["type"] == "variable":
            # Resolver $input.nombre, $output.step1.email, o bare words como 'stock'
            var_path = node["value"][1:] if node["value"].startswith("$") else node["value"]
            result = safe_get(context, var_path)
            if result is not None:
                return result
            # Si no está en contexto, podría ser un valor literal (e.g. True/False ya manejados)
            # Pero si era un bare word como 'stock' y no está en contexto, log warning
            if not node["value"].startswith("$"):
                logger.warning(f"Variable '{var_path}' no encontrada en contexto, usando como string literal")
                return node["value"]
            logger.warning(f"Variable no encontrada en contexto: {var_path}")
            return None
        return None

    def _apply_operator(self, left: Any, op: str, right: Any) -> bool:
        """Aplica un operador de comparación."""
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
