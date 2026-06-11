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
    ]

    ENGLISH_MARKERS: ClassVar[list[str]] = [
        r"\b(the|a|an|is|are|was|were|have|has|had|do|does|did|will|would|could|should|may|might)\b",
        r"\b(regist|new|client|custom|invoic|invent|stock|email|autom|work|busin)\b",
        r"\b(i|want|need|can|make|create|save|send|receive|search|find|get|set|update|delete)\b",
    ]

    def detect(self, text: str) -> str:
        text_lower = text.lower()
        es_score = 0
        en_score = 0

        for pattern in self.SPANISH_MARKERS:
            es_score += len(re.findall(pattern, text_lower))

        for pattern in self.ENGLISH_MARKERS:
            en_score += len(re.findall(pattern, text_lower))

        return "es" if es_score >= en_score else "en"
