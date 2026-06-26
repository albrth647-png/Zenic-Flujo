"""src.core.utils.ids — Generadores de identificadores.

Funciones para generar IDs unicos y tokens criptograficamente seguros.
Split de ``src/utils/helpers.py`` (M1.4).
"""

from __future__ import annotations

import secrets
import uuid


def generate_id() -> str:
    """Genera un ID único alfanumérico de 8 caracteres."""
    return uuid.uuid4().hex[:8]


def generate_secure_token(length: int = 32) -> str:
    """Genera un token criptográficamente seguro usando secrets module."""
    return secrets.token_hex(length // 2)


__all__ = ["generate_id", "generate_secure_token"]
