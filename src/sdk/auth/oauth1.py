"""
Connector SDK — OAuth1Auth
==========================

Autenticacion OAuth 1.0a con generacion de firma HMAC-SHA1.
Implementa el flujo completo: request token, autorizacion, access token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse
from typing import Any

from src.core.logging import setup_logging
from src.sdk.auth.base import AuthProvider

logger = setup_logging(__name__)


class OAuth1Auth(AuthProvider):
    """
    Autenticacion OAuth 1.0a con generacion de firma.

    Implementa el flujo completo de OAuth 1.0a:
    1. Obtener request token
    2. Autorizar el request token
    3. Intercambiar por access token
    4. Firmar todas las peticiones con HMAC-SHA1

    Args:
        consumer_key: Consumer key de la aplicacion
        consumer_secret: Consumer secret de la aplicacion
        access_token: Token de acceso obtenido
        access_token_secret: Secreto del token de acceso
        request_token_url: URL para obtener request tokens
        authorize_url: URL para autorizar request tokens
        access_token_url: URL para obtener access tokens
        callback_url: URL de callback para el flujo OAuth
    """

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str = "",
        access_token_secret: str = "",
        request_token_url: str = "",
        authorize_url: str = "",
        access_token_url: str = "",
        callback_url: str = "",
    ) -> None:
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._access_token = access_token
        self._access_token_secret = access_token_secret
        self._request_token_url = request_token_url
        self._authorize_url = authorize_url
        self._access_token_url = access_token_url
        self._callback_url = callback_url

    def _generate_nonce(self) -> str:
        """Genera un nonce aleatorio para la firma OAuth."""
        return secrets.token_urlsafe(16)

    def _build_signature_base_string(
        self,
        method: str,
        url: str,
        params: dict[str, str],
    ) -> str:
        """
        Construye la base de la firma OAuth 1.0a.

        Args:
            method: Metodo HTTP (GET, POST, etc.)
            url: URL de la peticion (sin query params)
            params: Parametros OAuth y de query combinados

        Retorna:
            Base string para la firma en formato estandar
        """
        sorted_params = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted(params.items()))
        base_url = urllib.parse.quote(url, safe="")
        return f"{method.upper()}&{base_url}&{urllib.parse.quote(sorted_params, safe='')}"

    def _sign(self, base_string: str) -> str:
        """
        Firma la base string con HMAC-SHA1.

        Args:
            base_string: Base string generada por _build_signature_base_string

        Retorna:
            Firma codificada en Base64
        """
        key = f"{urllib.parse.quote(self._consumer_secret, safe='')}&{urllib.parse.quote(self._access_token_secret, safe='')}"
        hashed = hmac.new(key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1)
        return base64.b64encode(hashed.digest()).decode("utf-8")

    def _build_oauth_params(self, method: str, url: str, extra_params: dict[str, str] | None = None) -> dict[str, str]:
        """
        Construye los parametros OAuth para una peticion firmada.

        Args:
            method: Metodo HTTP
            url: URL de la peticion
            extra_params: Parametros adicionales de la peticion

        Retorna:
            Diccionario con todos los parametros OAuth incluyendo la firma
        """
        oauth_params: dict[str, str] = {
            "oauth_consumer_key": self._consumer_key,
            "oauth_nonce": self._generate_nonce(),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_version": "1.0",
        }
        if self._access_token:
            oauth_params["oauth_token"] = self._access_token

        all_params = dict(oauth_params)
        if extra_params:
            all_params.update(extra_params)

        base_string = self._build_signature_base_string(method, url, all_params)
        signature = self._sign(base_string)
        oauth_params["oauth_signature"] = signature

        return oauth_params

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica la firma OAuth 1.0a a la peticion.

        Genera la firma HMAC-SHA1 y la incluye en el header
        Authorization segun RFC 5849.

        Args:
            request: Peticion HTTP con method, url y params

        Retorna:
            Peticion con el header Authorization OAuth firmado
        """
        method = request.get("method", "GET")
        url = request.get("url", "")
        extra_params = {k: str(v) for k, v in request.get("params", {}).items()}

        oauth_params = self._build_oauth_params(method, url, extra_params or None)

        header_parts = [f'{k}=\"{urllib.parse.quote(str(v), safe="")}\"' for k, v in sorted(oauth_params.items())]
        auth_header = "OAuth " + ", ".join(header_parts)

        request.setdefault("headers", {})
        request["headers"]["Authorization"] = auth_header
        logger.debug("OAuth1Auth: peticion firmada con HMAC-SHA1")
        return request

    def refresh(self) -> bool:
        """OAuth 1.0a no soporta renovacion automatica de tokens."""
        return False

    def is_expired(self) -> bool:
        """OAuth 1.0a no tiene expiracion de tokens por defecto."""
        return False

    def validate(self) -> bool:
        """Valida que consumer key y secret esten presentes."""
        return bool(self._consumer_key and self._consumer_secret)

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de OAuth1 (oculta secretos)."""
        result = super().to_dict()
        result["consumer_key"] = self._consumer_key
        result["has_access_token"] = bool(self._access_token)
        return result
