"""
Connector SDK — CustomAuth
==========================

Autenticacion personalizada con headers y tokens arbitrarios.
Permite configurar cualquier combinacion de headers y parametros
de query para autenticacion no estandar.
"""

from __future__ import annotations

import time
from typing import Any

from src.sdk.auth.base import AuthProvider
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class CustomAuth(AuthProvider):
    """
    Autenticacion personalizada con headers y tokens arbitrarios.

    Permite configurar cualquier combinacion de headers y
    parametros de query para autenticacion no estandar.

    Args:
        headers: Diccionario de headers personalizados para autenticacion
        query_params: Diccionario de query params para autenticacion
        token: Token de autenticacion generico
        token_prefix: Prefijo para el token en el header Authorization (ej: 'Token', 'JWT')
        expires_at: Timestamp de expiracion opcional
    """

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
        token: str = "",
        token_prefix: str = "Bearer",
        expires_at: float | None = None,
    ) -> None:
        self._headers = headers or {}
        self._query_params = query_params or {}
        self._token = token
        self._token_prefix = token_prefix
        self._expires_at = expires_at

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica headers personalizados y token a la peticion.

        Si se configuro un token, lo agrega al header Authorization
        con el prefijo configurado. Ademas agrega todos los headers
        y query params personalizados.

        Args:
            request: Peticion HTTP

        Retorna:
            Peticion con los headers y params personalizados aplicados
        """
        request.setdefault("headers", {})
        request.setdefault("params", {})

        if self._token:
            request["headers"]["Authorization"] = f"{self._token_prefix} {self._token}"

        request["headers"].update(self._headers)
        request["params"].update(self._query_params)

        logger.debug("CustomAuth: headers y parametros personalizados aplicados")
        return request

    def refresh(self) -> bool:
        """CustomAuth no soporta renovacion automatica por defecto."""
        return False

    def is_expired(self) -> bool:
        """
        Verifica si las credenciales personalizado han expirado.

        Retorna:
            True si se configuro expires_at y ya paso
        """
        if self._expires_at is None:
            return False
        return time.time() >= self._expires_at

    def validate(self) -> bool:
        """
        Valida que al menos un metodo de auth personalizado este configurado.

        Retorna:
            True si hay headers, query params o token configurado
        """
        return bool(self._headers or self._query_params or self._token)

    def add_header(self, name: str, value: str) -> None:
        """
        Agrega un header personalizado.

        Args:
            name: Nombre del header
            value: Valor del header
        """
        self._headers[name] = value

    def add_query_param(self, name: str, value: str) -> None:
        """
        Agrega un parametro de query personalizado.

        Args:
            name: Nombre del parametro
            value: Valor del parametro
        """
        self._query_params[name] = value

    def set_token(self, token: str, prefix: str = "Bearer", expires_at: float | None = None) -> None:
        """
        Establece un token de autenticacion generico.

        Args:
            token: Valor del token
            prefix: Prefijo para el header Authorization
            expires_at: Timestamp de expiracion opcional
        """
        self._token = token
        self._token_prefix = prefix
        self._expires_at = expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de CustomAuth (oculta valores sensibles)."""
        result = super().to_dict()
        result["custom_headers"] = list(self._headers.keys())
        result["custom_query_params"] = list(self._query_params.keys())
        result["has_token"] = bool(self._token)
        result["token_prefix"] = self._token_prefix
        result["expires_at"] = self._expires_at
        return result
