"""
Connector SDK — OAuth2Auth
==========================

Autenticacion OAuth 2.0 Authorization Code Flow con token refresh.
Soporta el flujo completo: autorizacion, intercambio de codigo,
y renovacion automatica de tokens.
"""

from __future__ import annotations

import secrets
import time
import urllib.parse
from typing import Any

from src.sdk.auth.base import AuthProvider
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class OAuth2Auth(AuthProvider):
    """
    Autenticacion OAuth 2.0 Authorization Code Flow con token refresh.

    Soporta el flujo completo de OAuth2:
    1. Redirigir al usuario a la URL de autorizacion
    2. Intercambiar el codigo de autorizacion por tokens
    3. Usar el access token en las peticiones
    4. Renovar automaticamente con el refresh token cuando expira

    Args:
        client_id: ID del cliente OAuth2
        client_secret: Secreto del cliente OAuth2
        token_url: URL del endpoint de token
        authorize_url: URL del endpoint de autorizacion
        access_token: Token de acceso actual
        refresh_token: Token de renovacion
        scopes: Lista de scopes solicitados
        expires_at: Timestamp de expiracion del access token
        redirect_uri: URI de redireccion para el flujo de autorizacion
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        authorize_url: str = "",
        access_token: str = "",
        refresh_token: str = "",
        scopes: list[str] | None = None,
        expires_at: float | None = None,
        redirect_uri: str = "",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._authorize_url = authorize_url
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._scopes = scopes or []
        self._expires_at = expires_at
        self._redirect_uri = redirect_uri
        self._token_type = "Bearer"

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica el access token OAuth2 al header Authorization.

        Verifica si el token expiro y lo renueva automaticamente
        antes de aplicar si es posible.

        Args:
            request: Peticion HTTP

        Retorna:
            Peticion con el header Authorization Bearer aplicado
        """
        if self.is_expired() and self._refresh_token:
            refreshed = self.refresh()
            if not refreshed:
                logger.warning("OAuth2Auth: token expirado y no se pudo renovar")

        request.setdefault("headers", {})
        request["headers"]["Authorization"] = f"{self._token_type} {self._access_token}"
        logger.debug("OAuth2Auth: Bearer token aplicado")
        return request

    def refresh(self) -> bool:
        """
        Renueva el access token usando el refresh token.

        Realiza una peticion POST al token_url con el grant_type
        refresh_token y actualiza los tokens en memoria.

        Retorna:
            True si la renovacion fue exitosa, False en caso contrario
        """
        if not self._refresh_token:
            logger.warning("OAuth2Auth: no hay refresh token disponible")
            return False

        try:
            import requests

            response = requests.post(
                self._token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            self._access_token = token_data.get("access_token", self._access_token)
            if "refresh_token" in token_data:
                self._refresh_token = token_data["refresh_token"]
            if "expires_in" in token_data:
                self._expires_at = time.time() + token_data["expires_in"]
            if "token_type" in token_data:
                self._token_type = token_data["token_type"]

            logger.info("OAuth2Auth: token renovado exitosamente")
            return True
        except Exception as e:
            logger.error(f"OAuth2Auth: error renovando token: {e}")
            return False

    def is_expired(self) -> bool:
        """
        Verifica si el access token ha expirado.

        Incluye un buffer de 60 segundos para evitar usar tokens
        que esten a punto de expirar.

        Retorna:
            True si el token expiro o no se establecio fecha de expiracion
        """
        if self._expires_at is None:
            return not bool(self._access_token)
        return time.time() >= (self._expires_at - 60)

    def validate(self) -> bool:
        """Valida que los campos obligatorios de OAuth2 esten presentes."""
        return bool(self._client_id and self._client_secret and self._token_url)

    def get_authorize_url(self, state: str | None = None) -> str:
        """
        Genera la URL de autorizacion para el flujo OAuth2.

        Args:
            state: Estado para prevenir CSRF attacks (se genera uno si no se provee)

        Retorna:
            URL completa de autorizacion con query parameters
        """
        if not self._authorize_url:
            raise ValueError("authorize_url no configurado")
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "scope": " ".join(self._scopes),
            "state": state or secrets.token_urlsafe(32),
        }
        return f"{self._authorize_url}?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> bool:
        """
        Intercambia un codigo de autorizacion por tokens.

        Args:
            code: Codigo de autorizacion recibido del callback

        Retorna:
            True si el intercambio fue exitoso
        """
        try:
            import requests

            response = requests.post(
                self._token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": self._redirect_uri,
                },
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()

            self._access_token = token_data.get("access_token", "")
            self._refresh_token = token_data.get("refresh_token", "")
            if "expires_in" in token_data:
                self._expires_at = time.time() + token_data["expires_in"]
            if "token_type" in token_data:
                self._token_type = token_data["token_type"]

            logger.info("OAuth2Auth: codigo de autorizacion intercambiado exitosamente")
            return True
        except Exception as e:
            logger.error(f"OAuth2Auth: error intercambiando codigo: {e}")
            return False

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de OAuth2 (oculta secretos)."""
        result = super().to_dict()
        result["client_id"] = self._client_id
        result["token_url"] = self._token_url
        result["scopes"] = self._scopes
        result["has_refresh_token"] = bool(self._refresh_token)
        result["expires_at"] = self._expires_at
        return result
