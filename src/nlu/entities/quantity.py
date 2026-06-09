"""
DDE v3 — QuantityExtractor

Extrae cantidades con operadores de comparación.
Soporta: "más de 10 unidades", "< 50", "al menos 100", "menos de 5"

Determinista. Sin eval(). Sin IA.
"""
from __future__ import annotations
import re
from src.nlu.entities.base import Entity

# Patrones: cantidad + unidad opcional
QTY_PATTERNS = [
    re.compile(r'(\d+)\s*(unidades?|items?|uds?|piezas?|productos?)', re.IGNORECASE),
    re.compile(r'(\d+)\s*$'),  # número suelto al final (backup)
]

# Palabras de operador para cantidades
OPERATOR_WORDS_QTY = {
    "mayor o igual": ">=", "menor o igual": "<=",
    "mayor": ">", "menor": "<",
    "mas de": ">=", "más de": ">=",
    "menos de": "<=",
    "al menos": ">=", "por lo menos": ">=",
    "como minimo": ">=", "como mínimo": ">=",
    "maximo": "<=", "máximo": "<=",
    "exactamente": "==", "exacto": "==",
    "at least": ">=", "at most": "<=",
    "more than": ">", "less than": "<",
    "greater than": ">", "less than": "<",
    "exactly": "==", "equal to": "==",
}

OPERATOR_SYMBOLS_QTY = re.compile(r'(>=|<=|!=|==|>|<)')


class QuantityExtractor:
    """Extrae entidades de tipo 'qty' con operador y valor."""

    def extract(self, text: str) -> list[Entity]:
        """Extrae cantidades del texto.

        Returns:
            Lista de Entity con type='qty', value={'op': str, 'value': int}
        """
        entities: list[Entity] = []
        text_lower = text.lower()

        op = self._detect_operator(text_lower)

        for pattern in QTY_PATTERNS:
            for match in pattern.finditer(text):
                raw = match.group()
                num_str = match.group(1)

                try:
                    value_num = int(num_str)
                except ValueError:
                    continue

                entity_value: dict[str, object] = {
                    "op": op,
                    "value": value_num,
                }

                entities.append(Entity(
                    type="qty",
                    value=entity_value,
                    raw=raw,
                    span=(match.start(), match.end()),
                    score=0.85,
                ))

        return entities

    def _detect_operator(self, text_lower: str) -> str:
        """Detecta operador de comparación."""
        # Símbolos directos
        sym_match = OPERATOR_SYMBOLS_QTY.search(text_lower)
        if sym_match:
            return sym_match.group(1)

        # Palabras
        for phrase, op in sorted(OPERATOR_WORDS_QTY.items(), key=lambda x: -len(x[0])):
            if phrase in text_lower:
                return op

        return "=="
