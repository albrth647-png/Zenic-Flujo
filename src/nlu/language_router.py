"""
DDE v3 — LanguageRouter (Etapa 3)

Detecta si el texto está en español o inglés por frecuencia de stopwords.
Herencia del BilingualRouter existente con mejoras.
"""
from __future__ import annotations
import re
from src.nlp.bilingual_router import BilingualRouter


class LanguageRouter(BilingualRouter):
    """
    Router de idioma con detección ES/EN determinista.
    
    Extiende el BilingualRouter existente con:
    - Más stopwords en ambos idiomas
    - Normalización NFKD antes de detectar
    """

    EXTRA_SPANISH = [
        r'\b(esto|esta|este|estos|estas|eso|esa|esos|esas|aquel|aquella)\b',
        r'\b(mi|tu|su|nuestro|vuestro|le|les|me|te|se|nos|os)\b',
        r'\b(ya|también|tambien|siempre|nunca|jamas|jamás|quizas|quizás)\b',
        r'\b(muy|mucho|poco|bastante|demasiado|tan|tanto|mas|menos)\b',
    ]

    EXTRA_ENGLISH = [
        r'\b(you|he|she|it|we|they|me|him|her|us|them|my|your|his|its|our|their)\b',
        r'\b(this|that|these|those|here|there|every|all|some|any|no|none)\b',
        r'\b(not|never|always|sometimes|often|usually|already|still|yet|just)\b',
        r'\b(very|much|many|little|few|more|most|less|least|too|enough)\b',
    ]

    def __init__(self):
        super().__init__()
        # Agregar patrones extra a los existentes
        self.SPANISH_MARKERS = list(self.SPANISH_MARKERS) + self.EXTRA_SPANISH
        self.ENGLISH_MARKERS = list(self.ENGLISH_MARKERS) + self.EXTRA_ENGLISH

    def detect(self, text: str) -> str:
        """
        Detecta el idioma del texto.
        
        Usa NFKD normalization antes de contar stopwords.
        Retorna 'es' o 'en'.
        """
        import unicodedata
        text_nfkd = unicodedata.normalize("NFKD", text)
        text_nfkd = text_nfkd.encode("ascii", "ignore").decode("ascii")
        return super().detect(text_nfkd)
