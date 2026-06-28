"""
Zenic-Flijo i18n — Sistema de Internacionalización (Fase 4)

Soporte multilingüe para la plataforma:
- es: Español (idioma por defecto)
- en: Inglés
- pt-BR: Portugués brasileño

Uso:
    from src.i18n import t, set_language, get_available_languages

    set_language("pt-BR")
    msg = t("workflow.created", name="Invoice Workflow")
    # → "Workflow 'Invoice Workflow' criado com sucesso"
"""

from __future__ import annotations

from typing import Any

from src.i18n.locales.en import MESSAGES as EN_MESSAGES
from src.i18n.locales.es import MESSAGES as ES_MESSAGES
from src.i18n.locales.pt_br import MESSAGES as PT_BR_MESSAGES

# Registry of available locales
_LOCALES: dict[str, dict[str, str]] = {
    "es": ES_MESSAGES,
    "en": EN_MESSAGES,
    "pt-BR": PT_BR_MESSAGES,
}

# Supported language codes
_SUPPORTED_LANGUAGES: list[str] = ["es", "en", "pt-BR"]

# Default language (Spanish)
_DEFAULT_LANG: str = "es"

# Current active language
_current_lang: str = _DEFAULT_LANG


def set_language(lang: str) -> None:
    """Establece el idioma activo.

    Args:
        lang: Código de idioma ('es', 'en', 'pt-BR')

    Raises:
        ValueError: Si el idioma no está soportado
    """
    global _current_lang
    if lang not in _SUPPORTED_LANGUAGES:
        valid = ", ".join(_SUPPORTED_LANGUAGES)
        raise ValueError(f"Idioma '{lang}' no soportado. Idiomas: {valid}")
    _current_lang = lang


def get_current_language() -> str:
    """Retorna el código del idioma activo."""
    return _current_lang


def get_available_languages() -> list[dict[str, str]]:
    """Retorna lista de idiomas disponibles con sus nombres nativos."""
    return [
        {"code": "es", "name": "Español", "native": "Español"},
        {"code": "en", "name": "English", "native": "English"},
        {"code": "pt-BR", "name": "Português (Brasil)", "native": "Português (Brasil)"},
    ]


# legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Traduce una clave al idioma especificado.

    Args:
        key: Clave de traducción (ej: 'workflow.created')
        lang: Código de idioma (usa el idioma activo si None)
        **kwargs: Variables para formatear el mensaje

    Returns:
        Texto traducido con las variables interpoladas

    Examples:
        >>> t("workflow.created", name="Mi Workflow")
        "Workflow 'Mi Workflow' creado exitosamente"

        >>> t("workflow.created", lang="pt-BR", name="Meu Workflow")
        "Workflow 'Meu Workflow' criado com sucesso"
    """
    locale_code = lang or _current_lang

    # Try exact match first
    messages = _LOCALES.get(locale_code)

    # Fallback: try base language (e.g., "pt-BR" -> "pt")
    if messages is None and "-" in locale_code:
        base = locale_code.split("-")[0]
        messages = _LOCALES.get(base)

    # Last fallback: default language (es)
    if messages is None:
        messages = _LOCALES.get(_DEFAULT_LANG)

    template = messages.get(key, _LOCALES[_DEFAULT_LANG].get(key, key)) if messages else key

    # Interpolate variables if provided
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template

    return template


# legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
def translate(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Alias para t()."""
    return t(key, lang, **kwargs)


def has_key(key: str, lang: str | None = None) -> bool:
    """Verifica si una clave de traducción existe en un idioma."""
    locale_code = lang or _current_lang
    messages = _LOCALES.get(locale_code, _LOCALES.get(_DEFAULT_LANG, {}))
    return key in messages


def get_all_keys(lang: str | None = None) -> list[str]:
    """Retorna todas las claves de traducción disponibles."""
    locale_code = lang or _current_lang
    messages = _LOCALES.get(locale_code, _LOCALES.get(_DEFAULT_LANG, {}))
    return sorted(messages.keys())


__all__ = [
    "_SUPPORTED_LANGUAGES",
    "get_all_keys",
    "get_available_languages",
    "get_current_language",
    "has_key",
    "set_language",
    "t",
    "translate",
]
