"""
Connector SDK — BasicAuth
=========================

Autenticacion basica HTTP (username/password).
Codifica las credenciales en Base64 segun RFC 7617.
"""

from __future__ import annotations

import base64
from typing import Any

from src.core.logging import setup_logging
from src.sdk.auth.base import AuthProvider

logger = setup_logging(__name__)


class BasicAuth(AuthProvider):
    """
    Autenticacion basica HTTP (username/password).

    Codifica las credenciales en Base64 segun RFC 7617
    y las envia en el header Authorization.

    Args:
        username: Nombre de usuario
        password: Contrasena
    """

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica credenciales Basic Auth al header Authorization.

        Codifica username:password en Base64 y lo establece
        como header Authorization: Basic <encoded>.

        Args:
            request: Peticion HTTP

        Retorna:
            Peticion con el header Authorization aplicado
        """
        request.setdefault("headers", {})
        credentials = f"{self._username}:{self._password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        request["headers"]["Authorization"] = f"Basic {encoded}"
        logger.debug("BasicAuth: credenciales aplicadas al header Authorization")
        return request

    def refresh(self) -> bool:
        """Basic Auth no soporta renovacion automatica de credenciales."""
        return False

    def is_expired(self) -> bool:
        """Basic Auth no expira (las credenciales son validas hasta cambio)."""
        return False

    def validate(self) -> bool:
        """Valida que username y password no esten vacios."""
        return bool(self._username.strip() and self._password.strip())

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de Basic Auth (oculta la contrasena)."""
        result = super().to_dict()
        result["username"] = self._username
        result["password_masked"] = "*" * len(self._password) if self._password else ""
        return result
