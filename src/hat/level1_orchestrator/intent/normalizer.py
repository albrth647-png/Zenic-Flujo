"""
HAT-ORBITAL Nivel 1 — Intent Normalizer.

Normaliza texto del usuario para hashing determinista y comparaciones.

Extraído de intent_hasher.py en M2.1 (single responsibility):
- hasher.py: cálculo de sha256 determinista.
- normalizer.py: normalización de texto (lowercase, acentos, puntuación, espacios).

Implementado en F0-D7, extraído en M2.1.
"""

from __future__ import annotations

import re

from src.core.logging import setup_logging

logger = setup_logging(__name__)

# Regex para normalizar: lowercase, sin acentos, sin puntuación extraña.
_ACCENT_MAP = {
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
    "ñ": "n", "ü": "u",
}
_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9 ]")


def normalize_intent(text: str) -> str:
    """Normaliza texto del usuario para hashing determinista.

    Pasos:
    1. lowercase
    2. strip
    3. reemplazar acentos (á→a, é→e, ...)
    4. colapsar espacios múltiples
    5. eliminar puntuación (mantener solo alfanum + espacio)

    Args:
        text: Texto crudo del usuario.

    Returns:
        Texto normalizado listo para hashing. Vacío si el input es inválido.
    """
    if not isinstance(text, str):
        logger.warning("normalize_intent called with non-string: %s", type(text).__name__)
        return ""
    original_len = len(text)
    lowered = text.lower().strip()
    # Reemplazar acentos
    for accented, plain in _ACCENT_MAP.items():
        lowered = lowered.replace(accented, plain)
    # Eliminar puntuación
    lowered = _NON_ALNUM_SPACE.sub(" ", lowered)
    # Colapsar espacios
    result = " ".join(lowered.split())
    logger.debug("normalize_intent: %d chars -> %d chars", original_len, len(result))
    return result
