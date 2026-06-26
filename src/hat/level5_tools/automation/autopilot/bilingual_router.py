"""
Workflow Determinista — BilingualRouter
Detecta si el texto está en español o inglés.

Migrado de src/nlp/bilingual_router.py → src/nlu/bilingual_router.py
"""

from __future__ import annotations

import re
from typing import ClassVar


class BilingualRouter:
    SPANISH_MARKERS: ClassVar[list[str]] = [
        r"\b(hola|que|como|cuando|donde|quien|porque|para|con|sin|muy|mas|pero|es|el|la|los|las|un|una|al|del)\b",
        r"\b(registr|client|nuev|factur|inventari|enví|corre|automatiz|trabaj|negoci)\b",
        r"\b(quiero|necesito|puedo|hacer|tener|crear|guardar|enviar|recibir|buscar)\b",
        # Preposiciones, conjugaciones y artículos españoles adicionales
        r"\b(cuando|llegue|llega|llegan|sea|sean|esté|este|está|están|esté|tenga|tengo|tienes)\b",
        r"\b(de|del|al|por|para|sin|sobre|entre|hasta|desde)\b",
        r"\b(semana|semanal|diario|diaria|mensual|anual|cada|todos|todas)\b",
    ]

    # Marcadores ingleses — excluidas palabras que también son válidas en español
    # en contexto empresarial: stock, email, client, invent, regist ( loanwords)
    ENGLISH_MARKERS: ClassVar[list[str]] = [
        r"\b(the|a|an|is|are|was|were|have|has|had|do|does|did|will|would|could|should|may|might)\b",
        # Solo palabras que NO existen en español empresarial
        r"\b(invoic|custom|autom|work|busin|inventori|every|whenever|trigger|notify|alert)\b",
        # Pronombres y verbos auxiliares típicamente ingleses
        r"\b(i|you|he|she|it|we|they|me|him|her|us|them|my|your|his|its|our|their)\b",
        r"\b(want|need|can|make|create|save|send|receive|search|find|get|set|update|delete)\b",
        r"\b(this|that|these|those|here|there|always|never|sometimes|already|still|yet|just)\b",
    ]

    def detect(self, text: str) -> str:
        text_lower = text.lower()
        es_score = 0
        en_score = 0

        for pattern in self.SPANISH_MARKERS:
            es_score += len(re.findall(pattern, text_lower))

        for pattern in self.ENGLISH_MARKERS:
            en_score += len(re.findall(pattern, text_lower))

        # En caso de empate, favorecer español (producto orientado a LATAM).
        # Antes: "es" if es_score >= en_score else "en" → en empate ganaba "es",
        # pero el LanguageRouter hereda y algunos textos sin marcadores claros
        # iban a "en" porque los loanwords (stock, email) contaban como inglés.
        return "es" if es_score >= en_score else "en"
