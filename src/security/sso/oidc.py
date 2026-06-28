"""
SSO — OIDC Handler: Authorization Code Flow con PKCE, token exchange, ID token validation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from typing import Any

from src.data.database_manager import DatabaseManager
from src.data.redis_service import RedisService
from src.security.sso.constants import OIDC_STATE_PREFIX, SSO_BASE_URL
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OIDCHandler:
    """Maneja operaciones OIDC: login, callback, token exchange y validacion."""

    def __init__(self, db: DatabaseManager, redis: RedisService):
        self._db = db
        self._redis = redis

    def initiate_login(self, config: dict[str, Any], provider_name: str) -> dict[str, Any]:
        """Inicia el flujo de login OIDC con Authorization Code Flow + PKCE."""
        state = secrets.token_urlsafe(32)

        code_verifier = secrets.token_urlsafe(64)
        code_challenge_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_hash).rstrip(b"=").decode("ascii")

        client_id = config.get("client_id", "")
        authorization_url = config.get("authorization_url", "")
        scope = config.get("scope", "openid profile email")
        redirect_uri = config.get("redirect_uri") or f"{SSO_BASE_URL}/api/v1/auth/oidc/{provider_name}/callback"

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        extra_params = config.get("extra_auth_params", {})
        params.update(extra_params)

        auth_url = f"{authorization_url}?{urllib.parse.urlencode(params)}"

        self._redis.set_json(
            f"{OIDC_STATE_PREFIX}{state}",
            {"provider": provider_name, "code_verifier": code_verifier, "redirect_uri": redirect_uri,
             "created_at": time.time()},
            ttl=300,
        )

        logger.info(f"SSO OIDC: Login iniciado para proveedor '{provider_name}' (state={state[:8]}...)")
        return {"status": "ok", "redirect_url": auth_url, "state": state}

    def handle_callback(self, config: dict[str, Any], code: str, state: str) -> dict[str, Any]:
        """Procesa el callback OIDC tras la autorizacion del usuario."""
        provider_name = config.get("_provider_name", "")
        state_data = self._redis.get_json(f"{OIDC_STATE_PREFIX}{state}")
        if not state_data or state_data.get("provider") != provider_name:
            logger.warning(f"SSO OIDC: State invalido o expirado para proveedor '{provider_name}'")
            return {"status": "error", "message": "State invalido o expirado (posible CSRF)"}

        self._redis.delete(f"{OIDC_STATE_PREFIX}{state}")

        token_result = self._exchange_code(config, code, state_data)
        if not token_result.get("access_token"):
            return {"status": "error", "message": token_result.get("message", "Error intercambiando codigo por tokens")}

        id_token_claims: dict[str, Any] = {}
        if token_result.get("id_token"):
            id_token_claims = self._validate_id_token(token_result["id_token"], config)

        user_info: dict[str, Any] = {}
        if token_result.get("access_token"):
            userinfo_result = self._fetch_userinfo(config, token_result["access_token"])
            if userinfo_result:
                user_info = userinfo_result

        user_info.update({k: v for k, v in id_token_claims.items() if k not in user_info})

        external_id = user_info.get("sub") or user_info.get("email") or id_token_claims.get("sub", "")
        if not external_id:
            return {"status": "error", "message": "No se pudo identificar al usuario (sin sub ni email)"}

        user_info["external_id"] = external_id

        return {
            "status": "ok",
            "user_info": user_info,
            "idp_session": id_token_claims.get("sid"),
        }

    def _exchange_code(self, config: dict[str, Any], code: str, state_data: dict[str, Any]) -> dict[str, Any]:
        """Intercambia el codigo de autorizacion OIDC por tokens."""
        token_url = config.get("token_url", "")
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        redirect_uri = state_data.get("redirect_uri", "")
        code_verifier = state_data.get("code_verifier", "")

        if not token_url:
            return {"message": "token_url no configurada"}

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": code_verifier,
        }

        # Validate token_url to prevent SSRF
        if not self._is_safe_url(token_url):
            logger.error(f"SSO OIDC: URL no segura rechazada: {token_url}")
            return {"message": "URL de token no segura"}

        try:
            import urllib.request
            data = urllib.parse.urlencode(payload).encode("utf-8")
            req = urllib.request.Request(token_url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
            logger.debug("SSO OIDC: Tokens recibidos correctamente")
            return response_data
        except Exception as e:
            logger.error(f"SSO OIDC: Error intercambiando codigo: {e}")
            return {"message": f"Error en token exchange: {e}"}

    def _validate_id_token(self, id_token: str, config: dict[str, Any]) -> dict[str, Any]:
        """Valida un ID token JWT y extrae los claims."""
        try:
            parts = id_token.split(".")
            if len(parts) != 3:
                logger.warning("SSO OIDC: ID token malformado (no es JWT)")
                return {}

            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            claims = json.loads(payload_bytes)

            expected_audience = config.get("client_id", "")
            token_aud = claims.get("aud", "")
            if isinstance(token_aud, list):
                if expected_audience not in token_aud:
                    logger.warning(f"SSO OIDC: Audience no coincide. Esperada={expected_audience}, Recibida={token_aud}")
            elif token_aud != expected_audience:
                logger.warning(f"SSO OIDC: Audience no coincide. Esperada={expected_audience}, Recibida={token_aud}")

            exp = claims.get("exp")
            if exp and time.time() > exp:
                logger.warning("SSO OIDC: ID token expirado")
                return {}

            expected_issuer = config.get("issuer", "")
            if expected_issuer and claims.get("iss") != expected_issuer:
                logger.warning(f"SSO OIDC: Issuer no coincide. Esperado={expected_issuer}, Recibido={claims.get('iss')}")

            logger.debug(f"SSO OIDC: ID token validado (sub={claims.get('sub', 'N/A')})")
            return claims
        except Exception as e:
            logger.error(f"SSO OIDC: Error validando ID token: {e}")
            return {}

    def _fetch_userinfo(self, config: dict[str, Any], access_token: str) -> dict[str, Any] | None:
        """Obtiene informacion del usuario desde el endpoint UserInfo de OIDC."""
        userinfo_url = config.get("userinfo_url", "")
        if not userinfo_url:
            return None

        # Validate userinfo_url to prevent SSRF
        if not self._is_safe_url(userinfo_url):
            logger.error(f"SSO OIDC: UserInfo URL no segura rechazada: {userinfo_url}")
            return None

        try:
            import urllib.request
            req = urllib.request.Request(userinfo_url)
            req.add_header("Authorization", f"Bearer {access_token}")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"SSO OIDC: Error obteniendo userinfo: {e}")
            return None

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Valida que una URL sea segura para prevenir SSRF.

        Reglas de validacion:
        - Solo permite esquema HTTPS (no HTTP, file, ftp, etc.)
        - Bloquea IPs privadas/locales (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16)
        - Bloquea localhost y variantes
        - Permite solo dominios publicos validos
        """
        import ipaddress
        import re
        import urllib.parse

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return False

        # Solo permitir HTTPS
        if parsed.scheme.lower() != "https":
            return False

        # Obtener hostname (sin puerto)
        hostname = parsed.hostname or ""
        if not hostname:
            return False

        # Bloquear localhost y variantes
        if hostname.lower() in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}:
            return False

        # Bloquear IPs privadas
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return False
        except ValueError:
            # No es una IP, es un hostname - validar formato
            if not re.match(r"^[a-zA-Z0-9.-]+$", hostname):
                return False
            # Bloquear dominios que parezcan internos
            if hostname.endswith((".local", ".internal", ".corp", ".lan")):
                return False

        return True
