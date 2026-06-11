"""
DDE v3 — Tokenizer + Stemmer ligero (Etapa 2)

Tokeniza y lematiza texto usando un stemmer por reglas + diccionario de raíces.
NO usa ML. NO usa NLTK. Puro Python, cero dependencias.

Determinista: misma entrada → mismos tokens siempre.
"""

from __future__ import annotations

from src.nlu.entities.base import Token

# ── Diccionario de raíces (excepciones / irregulares) ──────────
ROOTS_ES: dict[str, str] = {
    "haciendo": "hacer",
    "hace": "hacer",
    "hizo": "hacer",
    "diciendo": "decir",
    "dice": "decir",
    "dijo": "decir",
    "yendo": "ir",
    "va": "ir",
    "fue": "ir",
    "teniendo": "tener",
    "tiene": "tener",
    "tuvo": "tener",
    "poniendo": "poner",
    "pone": "poner",
    "puso": "poner",
    "siendo": "ser",
    "es": "ser",
    "era": "ser",
    "viendo": "ver",
    "ve": "ver",
    "vio": "ver",
    # Verbos con cambios ortográficos (c → z, g → j, etc.)
    "venza": "venc",
    "venzas": "venc",
    "venzo": "venc",
    "vencer": "venc",
    "vencia": "venc",
    "vencio": "venc",
    # Palabras con ñ que NFKD convierte a n + problemas de stemming agresivo
    "cumpleaños": "cumplean",
    "cumpleanos": "cumplean",
    # Participios y conjugaciones que el stemmer por reglas no captura bien
    "vencido": "venc",
    "vencida": "venc",
    "vencidos": "venc",
    "vencidas": "venc",
}

ROOTS_EN: dict[str, str] = {
    "doing": "do",
    "does": "do",
    "did": "do",
    "done": "do",
    "saying": "say",
    "says": "say",
    "said": "say",
    "going": "go",
    "goes": "go",
    "went": "go",
    "gone": "go",
    "making": "make",
    "made": "make",
    "taking": "take",
    "takes": "take",
    "took": "take",
    "taken": "take",
    "having": "have",
    "has": "have",
    "had": "have",
    "buying": "buy",
    "buys": "buy",
    "bought": "buy",
    "sending": "send",
    "sends": "send",
    "sent": "send",
    "writing": "write",
    "writes": "write",
    "wrote": "write",
    "written": "write",
    "creating": "create",
    "creates": "create",
    "created": "create",
    "running": "run",
    "runs": "run",
    "ran": "run",
}


def stem_spanish(word: str) -> str:
    """Stemmer ligero para español por reglas de sufijos."""
    if len(word) <= 3:
        return word

    # Verbos: infinitivo → stem (las keywords de TEMPLATES ya están en forma stemmeada)
    # "registrar" -> "registr", "vender" -> "vend", "recibir" -> "recib"
    if word.endswith("ar"):
        return word[:-2]
    if word.endswith("er"):
        return word[:-2]
    if word.endswith("ir"):
        return word[:-2]

    # Verbos: conjugaciones
    for ending in [
        "ando",
        "iendo",
        "ado",
        "ido",
        "aba",
        "ia",
        "aste",
        "iste",
        "o",
        "amos",
        "imos",
        "ais",
        "is",
        "an",
        "en",
        "as",
        "es",
        "a",
        "e",
    ]:
        if word.endswith(ending):
            stem = word[: -len(ending)]
            if len(stem) >= 2:
                return stem

    # Plurales
    if word.endswith("ces"):  # lápiz → lapices
        return word[:-3] + "z"
    if word.endswith("es"):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]

    # Femenino
    if word.endswith("as"):
        return word[:-2]
    if word.endswith("a"):
        return word[:-1]

    return word


def stem_english(word: str) -> str:
    """Stemmer ligero para inglés (simplified Porter)."""
    if len(word) <= 3:
        return word

    # -ational, -ization (normalizar antes de strip general)
    if word.endswith("ational"):
        return word[:-7] + "ate"
    if word.endswith("ization"):
        return word[:-7] + "ize"

    # -tion, -sion (normalizar nominalizaciones)
    if word.endswith("tion"):
        return word[:-4]
    if word.endswith("sion"):
        return word[:-4]

    # -ment
    if word.endswith("ment"):
        return word[:-4]

    # -ing, -ed, -ly
    for suffix in ["ingly", "edly", "ingly", "edly", "ing", "ed", "ly"]:
        if word.endswith(suffix):
            potential = word[: -len(suffix)]
            if len(potential) >= 2:
                return potential

    # -er, -or, -est (comparativos, agentes)
    for suffix in ["est", "ers", "ors", "er", "or"]:
        if word.endswith(suffix):
            potential = word[: -len(suffix)]
            if len(potential) >= 2:
                return potential

    # -es, -s (plural)
    if word.endswith("es"):
        potential = word[:-2]
        if len(potential) >= 2:
            return potential
    if word.endswith("s"):
        potential = word[:-1]
        if len(potential) >= 2:
            return potential

    return word


def tokenize(text: str, lang: str = "es") -> list[Token]:
    """
    Tokeniza y lematiza un texto normalizado.

    Args:
        text: Texto ya normalizado (minúsculas, sin tildes)
        lang: Idioma ('es' | 'en')

    Returns:
        Lista de Tokens con raw, lemma y posición
    """
    words = text.split()
    roots = ROOTS_ES if lang == "es" else ROOTS_EN
    stemmer = stem_spanish if lang == "es" else stem_english

    tokens = []
    for pos, word in enumerate(words):
        # Limpiar puntuación adherida
        raw = word.strip(".,;:!?\"'()[]{}@")

        if not raw:
            continue

        # Lemmatizar: primero diccionario de raíces, luego stemmer
        lemma = roots.get(raw, stemmer(raw))

        tokens.append(Token(raw=raw, lemma=lemma, pos=pos))

    return tokens
