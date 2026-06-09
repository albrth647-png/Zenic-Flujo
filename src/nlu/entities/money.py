"""
DDE v3 — MoneyExtractor

Extrae montos monetarios con operadores de comparación.
Soporta: $500, 500 pesos, más de $500, menos de 1000, mayor a 200, > 300

Determinista: regex + parse de operadores. Sin eval(). Sin IA.
"""
from __future__ import annotations
import re
from src.nlu.entities.base import Entity


# Patrones para montos: $500, 500 pesos, USD 500
MONEY_PATTERNS = [
    re.compile(r'\$\s?(\d+[\.,]?\d*)'),
    re.compile(r'(\d+[\.,]?\d*)\s*(dólares|dolares|pesos|usd|eur|mxn|ars)'),
    re.compile(r'(usd|eur|mxn|ars)\s*(\d+[\.,]?\d*)', re.IGNORECASE),
]

# Palabras de operador
OPERATOR_WORDS = {
    "mayor": ">", "menor": "<", "mas": ">=", "más": ">=",
    "menos": "<=", "al menos": ">=", "por lo menos": ">=",
    "mayor o igual": ">=", "menor o igual": "<=", "exactamente": "==",
    "igual": "==", "exacto": "==",
    "greater": ">", "less": "<", "more": ">=", "less or equal": "<=",
    "greater or equal": ">=", "at least": ">=", "at most": "<=",
    "exactly": "==", "equal": "==",
}

# Símbolos de operador directo
OPERATOR_SYMBOLS = re.compile(r'(>=|<=|!=|==|>|<)')


class MoneyExtractor:
    """Extrae entidades de tipo 'money' con operador y valor."""

    def extract(self, text: str) -> list[Entity]:
        """Extrae montos monetarios del texto.

        Returns:
            Lista de Entity con type='money', value={'op': str, 'value': float}
        """
        entities: list[Entity] = []
        text_lower = text.lower()

        # 1. Buscar patrón "más de $500", "menos de 500 pesos"
        op = self._detect_operator(text_lower)

        for pattern in MONEY_PATTERNS:
            for match in pattern.finditer(text):
                raw = match.group()
                # Extraer el número
                groups = match.groups()
                num_str = ""
                for g in groups:
                    if g and re.match(r'^[\d.,]+$', g):
                        num_str = g
                        break

                if not num_str:
                    continue

                try:
                    value_num = float(num_str.replace(",", ""))
                except ValueError:
                    continue

                entity_value: dict[str, object] = {
                    "op": op,
                    "value": value_num,
                }

                entities.append(Entity(
                    type="money",
                    value=entity_value,
                    raw=raw,
                    span=(match.start(), match.end()),
                    score=0.9,
                ))

        return entities

    def _detect_operator(self, text_lower: str) -> str:
        """Detecta el operador de comparación en el texto."""
        # Primero buscar símbolos directos: > 500, < 1000
        sym_match = OPERATOR_SYMBOLS.search(text_lower)
        if sym_match:
            return sym_match.group(1)

        # Luego buscar palabras: "mayor a 500", "mas de 500"
        for phrase, op in sorted(OPERATOR_WORDS.items(), key=lambda x: -len(x[0])):
            if phrase in text_lower:
                return op

        # Por defecto, igualdad exacta
        return "=="
