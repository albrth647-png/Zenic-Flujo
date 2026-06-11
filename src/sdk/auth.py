"""
Connector SDK — Sistema de Autenticacion
==========================================

Provee un sistema extensible de autenticacion para conectores,
soportando multiples mecanismos de auth:

- APIKeyAuth: API key via header o query param
- BasicAuth: usuario/contrasena
- OAuth2Auth: Authorization Code Flow con token refresh
- OAuth1Auth: OAuth 1.0a con generacion de firma
- MTLSAuth: mTLS con certificado de cliente
- CustomAuth: Headers/tokens personalizados

Todos los proveedores implementan la interfaz AuthProvider con:
- apply_auth(request): Aplica credenciales a una peticion
- refresh(): Renueva las credenciales si es posible
- is_expired(): Verifica si las credenciales expiraron
- validate(): Valida que las credenciales sean correctas
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class AuthProvider(ABC):
    """
    Clase base abstracta para proveedores de autenticacion.

    Define la interfaz comun que todos los proveedores de auth
    deben implementar. Cada proveedor maneja un tipo especifico
    de autenticacion y sabe como aplicar sus credenciales a
    una peticion HTTP.
    """

    @abstractmethod
    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica las credenciales de autenticacion a una peticion.

        Modifica la peticion (headers, params, etc.) para incluir
        las credenciales apropiadas segun el tipo de autenticacion.

        Args:
            request: Diccionario con la peticion HTTP (debe tener al menos 'headers' y 'params')

        Retorna:
            Peticion modificada con las credenciales aplicadas
        """

    @abstractmethod
    def refresh(self) -> bool:
        """
        Renueva las credenciales de autenticacion.

        Implementa la logica de renovacion de credenciales
        cuando sea soportada (ej: OAuth2 token refresh).

        Retorna:
            True si la renovacion fue exitosa, False en caso contrario
        """

    @abstractmethod
    def is_expired(self) -> bool:
        """
        Verifica si las credenciales han expirado.

        Retorna:
            True si las credenciales expiraron o no son validas
        """

    @abstractmethod
    def validate(self) -> bool:
        """
        Valida que las credenciales sean correctas y esten completas.

        Verifica que todos los campos requeridos esten presentes
        y tengan valores validos. No verifica contra el servicio externo.

        Retorna:
            True si las credenciales son validas localmente
        """

    def get_auth_type(self) -> str:
        """
        Retorna el tipo de autenticacion como string.

        Retorna:
            Nombre del tipo de autenticacion (ej: 'api_key', 'basic', 'oauth2')
        """
        return self.__class__.__name__.replace("Auth", "").lower()

    def to_dict(self) -> dict[str, Any]:
        """
        Serializa la configuracion de auth a diccionario (sin secretos).

        Retorna:
            Diccionario con la configuracion de auth, excluyendo valores sensibles
        """
        return {
            "auth_type": self.get_auth_type(),
            "expired": self.is_expired(),
            "valid": self.validate(),
        }


class APIKeyAuth(AuthProvider):
    """
    Autenticacion mediante API key via header o query parameter.

    Soporta dos modos de envio:
    - header: La API key se envia como header HTTP (default: 'X-API-Key')
    - query: La API key se envia como parametro de query (default: 'api_key')

    Args:
        api_key: Valor de la API key
        header_name: Nombre del header para enviar la key (default: 'X-API-Key')
        query_name: Nombre del param de query (default: 'api_key')
        location: Donde enviar la key: 'header', 'query', o 'both'
    """

    def __init__(
        self,
        api_key: str,
        header_name: str = "X-API-Key",
        query_name: str = "api_key",
        location: str = "header",
    ) -> None:
        self._api_key = api_key
        self._header_name = header_name
        self._query_name = query_name
        self._location = location

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica la API key a la peticion segun la ubicacion configurada.

        Args:
            request: Peticion HTTP con headers y params

        Retorna:
            Peticion con la API key aplicada
        """
        request.setdefault("headers", {})
        request.setdefault("params", {})

        if self._location in ("header", "both"):
            request["headers"][self._header_name] = self._api_key
        if self._location in ("query", "both"):
            request["params"][self._query_name] = self._api_key

        logger.debug(f"APIKeyAuth: key aplicada via {self._location}")
        return request

    def refresh(self) -> bool:
        """Las API keys estaticas no soportan renovacion automatica."""
        logger.debug("APIKeyAuth: renovacion no soportada para API keys estaticas")
        return False

    def is_expired(self) -> bool:
        """Las API keys estaticas no expiran (se asume validas hasta revocacion)."""
        return False

    def validate(self) -> bool:
        """Valida que la API key no este vacia."""
        return bool(self._api_key and self._api_key.strip())

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de API key (oculta el valor real)."""
        result = super().to_dict()
        result["header_name"] = self._header_name
        result["query_name"] = self._query_name
        result["location"] = self._location
        result["api_key_masked"] = f"{'*' * 8}{self._api_key[-4:]}" if len(self._api_key) > 4 else "****"
        return result


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

        header_parts = [f'{k}="{urllib.parse.quote(str(v), safe="")}"' for k, v in sorted(oauth_params.items())]
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


class MTLSAuth(AuthProvider):
    """
    Autenticacion mTLS (Mutual TLS) con certificado de cliente.

    Configura la peticion para usar un certificado de cliente
    y clave privada para autenticacion mutua TLS.

    Args:
        cert_path: Ruta al certificado de cliente (PEM)
        key_path: Ruta a la clave privada del cliente (PEM)
        ca_path: Ruta al certificado CA para verificar el servidor (PEM)
        cert_password: Password para la clave privada (opcional)
    """

    def __init__(
        self,
        cert_path: str,
        key_path: str,
        ca_path: str | None = None,
        cert_password: str | None = None,
    ) -> None:
        self._cert_path = cert_path
        self._key_path = key_path
        self._ca_path = ca_path
        self._cert_password = cert_password

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica la configuracion mTLS a la peticion.

        Agrega los certificados de cliente y CA a la peticion
        para que el transporte HTTP los use durante el handshake TLS.

        Args:
            request: Peticion HTTP

        Retorna:
            Peticion con la configuracion de certificados TLS aplicada
        """
        cert_tuple: tuple[str, str] | tuple[str, str, str] = (self._cert_path, self._key_path)
        if self._cert_password:
            cert_tuple = (self._cert_path, self._key_path, self._cert_password)

        request["cert"] = cert_tuple
        if self._ca_path:
            request["verify"] = self._ca_path

        logger.debug("MTLSAuth: certificados de cliente configurados para mTLS")
        return request

    def refresh(self) -> bool:
        """Los certificados mTLS no soportan renovacion automatica."""
        return False

    def is_expired(self) -> bool:
        """
        Verifica si el certificado de cliente ha expirado.

        Lee el certificado PEM y verifica la fecha de expiracion.

        Retorna:
            True si el certificado expiro
        """
        try:
            from cryptography import x509

            with open(self._cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            from datetime import UTC, datetime

            return cert.not_valid_after_utc < datetime.now(UTC)
        except ImportError:
            logger.debug("MTLSAuth: cryptography no instalado, no se puede verificar expiracion")
            return False
        except FileNotFoundError:
            logger.warning(f"MTLSAuth: certificado no encontrado en {self._cert_path}")
            return True
        except Exception as e:
            logger.warning(f"MTLSAuth: error verificando expiracion del certificado: {e}")
            return False

    def validate(self) -> bool:
        """
        Valida que los archivos de certificado y clave existan.

        Retorna:
            True si ambos archivos existen
        """
        import os

        cert_exists = os.path.isfile(self._cert_path)
        key_exists = os.path.isfile(self._key_path)
        if not cert_exists:
            logger.warning(f"MTLSAuth: certificado no encontrado: {self._cert_path}")
        if not key_exists:
            logger.warning(f"MTLSAuth: clave privada no encontrada: {self._key_path}")
        return cert_exists and key_exists

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de mTLS (oculta el password)."""
        result = super().to_dict()
        result["cert_path"] = self._cert_path
        result["key_path"] = self._key_path
        result["ca_path"] = self._ca_path
        result["has_password"] = bool(self._cert_password)
        return result


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
