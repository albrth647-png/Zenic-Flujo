"""src.core.utils.text — Manipulacion de strings.

Split de ``src/utils/helpers.py`` (M1.4).
"""

from __future__ import annotations


def truncate(text: str, max_length: int = 100) -> str:
    """Trunca texto a max_length caracteres."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


__all__ = ["truncate"]
