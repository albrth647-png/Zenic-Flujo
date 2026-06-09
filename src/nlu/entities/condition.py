"""
DDE v3 — ConditionExtractor

Extrae condiciones lógicas del texto y construye un AST seguro.
Soporta: "si el total es mayor a 500", "if stock < 10", "when amount >= 1000"

CRÍTICO: NO usa eval(). Construye un AST (dict) con tokens seguros.
Determinista. Sin IA.
"""
from __future__ import annotations
import re
from src.nlu.entities.base import Entity


# Operadores permitidos (whitelist)
SAFE_OPS = {">=", "<=", "!=", "==", ">", "<", "="}

# Mapeo de palabras a operadores
WORD_TO_OP: dict[str, str] = {
    "mayor o igual que": ">=", "mayor o igual a": ">=",
    "menor o igual que": "<=", "menor o igual a": "<=",
    "mayor que": ">", "mayor a": ">", "mayor": ">",
    "menor que": "<", "menor a": "<", "menor": "<",
    "diferente de": "!=", "distinto de": "!=",
    "igual a": "==", "igual que": "==", "igual": "==",
    "es exactamente": "==", "exactamente": "==",
    "greater or equal to": ">=", "greater than or equal to": ">=",
    "less or equal to": "<=", "less than or equal to": "<=",
    "greater than": ">", "more than": ">", "greater": ">",
    "less than": "<", "fewer than": "<", "less": "<",
    "different from": "!=", "not equal to": "!=",
    "equal to": "==", "equals": "==", "equal": "==", "is exactly": "==",
}

# Patrones de condición: "si [variable] [op] [valor]"
# NOTA: cada patrón documenta sus grupos capturados para saber
# si son operadores de símbolo (>, <) o palabra ("mayor", "less than")

# Patrón A: si/if/when X (símbolo) Y  → grupos: (match_ando?, var, op_símbolo, val)
PAT_SYMBOL_WITH_IF = re.compile(
    r'(?:si|if|when|c(uando|ando))\s+'
    r'(?:\b(?:el|la|the|un|una|an)\b\s*)?'  # artículo opcional con word boundary
    r'(\w[\w.]*)\s*'  # variable
    r'(>=|<=|!=|==|>|<|=)\s*'  # operador símbolo
    r'(\d+[\.,]?\d*)',  # valor
    re.IGNORECASE
)

# Patrón B: X (palabra) Y  → grupos: (var, word_op, val)
# Ej: "total mayor que 500", "si el total es mayor a 500", "stock less than 10"
PAT_WORD_OP = re.compile(
    r'(?:cuando|when|si|if)?\s*'  # prefijo (sin artículos)
    r'(?:\b(?:el|la|the|un|una|an)\b\s*)?'  # artículo opcional con word boundary
    r'(\w[\w.]*)\s+(?:es\s+|is\s+)?'
    r'(mayor|menor|igual|distinto|diferente|greater|less|equal|different'
    r'|mayor o igual|menor o igual|greater or equal|less or equal'
    r'|greater than|less than|more than|fewer than)'
    r'(?:\s+o\s+igual)?'
    r'(?:\s+que|\s+a|\s+than|\s+to)?\s*'
    r'(\d+[\.,]?\d*)',
    re.IGNORECASE
)

# Patrón C: X (símbolo) Y  → grupos: (var, op_símbolo, val)
# Ej: "stock < 10", "total > 500"
PAT_SYMBOL = re.compile(
    r'(\w[\w.]+)\s+(>=|<=|!=|==|>|<|=)\s+(\d+[\.,]?\d*)',
    re.IGNORECASE
)

COND_PATTERNS = [PAT_SYMBOL_WITH_IF, PAT_WORD_OP, PAT_SYMBOL]


class ConditionExtractor:
    """Extrae condiciones y construye AST seguro (dict, no eval())."""

    def extract(self, text: str) -> list[Entity]:
        """Extrae condiciones del texto.

        Returns:
            Lista de Entity con type='condition', value=dict con AST seguro:
            {'left': str, 'op': str, 'right': float}
        """
        entities: list[Entity] = []
        text_lower = text.lower().strip()

        if not text_lower:
            return entities

        for pattern in COND_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                ngroups = len(groups)

                var_name = ""
                op = ""
                val = 0.0

                if ngroups == 4:
                    # Patrón A: (match_ando?, var, op_símbolo, val)
                    var_name = groups[1].strip()
                    op_raw = groups[2].strip()
                    val_raw = groups[3]
                    op = self._normalize_op(op_raw)
                    if op not in SAFE_OPS:
                        continue
                    try:
                        val = float(val_raw.replace(",", "."))
                    except (ValueError, AttributeError):
                        continue

                elif ngroups == 3:
                    var_name = groups[0].strip()
                    middle = groups[1].strip()
                    val_raw = groups[2]

                    # Detectar si middle es operador símbolico o palabra
                    if middle in SAFE_OPS or middle == "=":
                        # Patrón C: X (símbolo) Y
                        op = self._normalize_op(middle)
                    else:
                        # Patrón B: X (palabra) Y
                        op = self._word_to_op(middle.lower())

                    if op not in SAFE_OPS:
                        continue
                    try:
                        val = float(val_raw.replace(",", "."))
                    except (ValueError, AttributeError):
                        continue
                else:
                    continue

                # Construir AST seguro (dict, no eval)
                entity_value: dict[str, object] = {
                    "left": var_name,
                    "op": op,
                    "right": val,
                }

                entities.append(Entity(
                    type="condition",
                    value=entity_value,
                    raw=match.group(),
                    span=(match.start(), match.end()),
                    score=0.95,
                ))

        return entities

    def _normalize_op(self, op_raw: str) -> str:
        """Normaliza operador a forma canónica."""
        op = op_raw.strip()
        if op == "=":
            return "=="
        return op

    def _word_to_op(self, word: str) -> str:
        """Convierte palabra a operador usando whitelist."""
        return WORD_TO_OP.get(word, "")

    @staticmethod
    def eval_condition(condition: dict[str, object], context: dict[str, object]) -> bool:
        """Evalúa un AST de condición contra un contexto de forma segura.

        NO usa eval(). Solo accede a context dict con keys conocidas.

        Args:
            condition: AST dict con {'left': str, 'op': str, 'right': float}
            context: Dict con valores de variables

        Returns:
            bool resultado de la evaluación
        """
        left_key = condition.get("left")
        op = condition.get("op")
        right_val = condition.get("right")

        if not isinstance(left_key, str) or not isinstance(op, str):
            return False

        left_val = context.get(left_key)
        if left_val is None:
            return False

        try:
            left_float = float(left_val)
            right_float = float(right_val) if right_val is not None else 0.0
        except (ValueError, TypeError):
            return False

        if op == ">":
            return left_float > right_float
        elif op == "<":
            return left_float < right_float
        elif op == ">=":
            return left_float >= right_float
        elif op == "<=":
            return left_float <= right_float
        elif op == "==":
            return left_float == right_float
        elif op == "!=":
            return left_float != right_float
        else:
            return False
