"""
DDE v3 — Normalizer (Etapa 1)

Normaliza texto: NFKD → lowercase → expande números → limpia espacios.
Función pura: misma entrada → misma salida.
"""

from __future__ import annotations

import re
import unicodedata

# Mapa de números escritos en español → dígitos
NUMBERS_ES = {
    "cero": "0",
    "una": "1",
    "uno": "1",
    "un": "1",
    "dos": "2",
    "tres": "3",
    "cuatro": "4",
    "cinco": "5",
    "seis": "6",
    "siete": "7",
    "ocho": "8",
    "nueve": "9",
    "diez": "10",
    "once": "11",
    "doce": "12",
    "trece": "13",
    "catorce": "14",
    "quince": "15",
    "veinte": "20",
    "treinta": "30",
    "cuarenta": "40",
    "cincuenta": "50",
    "sesenta": "60",
    "setenta": "70",
    "ochenta": "80",
    "noventa": "90",
    "cien": "100",
    "quinientos": "500",
    "seiscientos": "600",
    "setecientos": "700",
    "ochocientos": "800",
    "novecientos": "900",
    "mil": "1000",
}

# Mapa de números escritos en inglés → dígitos
NUMBERS_EN = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
}


def normalize(text: str, lang: str = "es") -> str:
    """
    Normaliza un texto aplicando:
    1. NFKD Unicode normalization (quita diacríticos)
    2. lowercase
    3. Expansión de números escritos en palabras
    4. Unificación de espacios
    5. Limpieza de puntuación irrelevante

    Args:
        text: Texto a normalizar
        lang: Idioma ('es' | 'en') para números

    Returns:
        Texto normalizado
    """
    # 1. NFKD: separa diacríticos de letras, luego quita los diacríticos
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # 2. Lowercase
    text = text.lower()

    # 3. Expandir números escritos en palabras
    numbers_map = NUMBERS_ES if lang == "es" else NUMBERS_EN
    words = text.split()
    expanded = []
    for word in words:
        clean = word.strip(".,;:!?\"'()[]{}")
        if clean in numbers_map:
            expanded.append(numbers_map[clean])
        else:
            expanded.append(word)
    text = " ".join(expanded)

    # 4. Quitar puntuación irrelevante (conservar @ . - / para emails, fechas, cron)
    text = re.sub(r"[^a-z0-9@.\-\/\s]", " ", text)

    # 5. Unificar espacios
    text = re.sub(r"\s+", " ", text).strip()

    # 6. Eliminar tokens que son solo puntuación solitaria (.
    #    que no forman parte de palabras como "email.com")
    words = [w for w in text.split() if w not in (".", "-", "/")]
    text = " ".join(words) if words else ""

    return text
