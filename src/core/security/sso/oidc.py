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

from src.core.db.sqlite_manager import DatabaseManager
from src.core.db.redis_service import RedisService
from src.core.security.sso.constants import OIDC_STATE_PREFIX, SSO_BASE_URL
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class OIDCHandler:
    """Maneja operaciones OIDC: login, callback, token exchange y validacion."""

    def __init__(self, db: DatabaseManager, redis: RedisService):
        self._db = db
        self._redis = redis

    def initiate_login(self, config: dict, provider_name: str) -> dict:
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

    def handle_callback(self, config: dict, code: str, state: str) -> dict:
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

        id_token_claims: dict = {}
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

    def _exchange_code(self, config: dict, code: str, state_data: dict) -> dict:
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

    def _validate_id_token(self, id_token: str, config: dict) -> dict:
        """Valida un ID token JWT y extrae los claims.

        Fix Sprint 2 bug #23: antes solo decodificaba el payload sin validar
        la firma, lo que permitía forgery de ID tokens. Ahora valida la firma
        usando PyJWT (o python-jose) contra las JWKS del IdP.
        Si la firma es inválida, retorna {} (rechazo silencioso con log).
        """
        try:
            # ── Validación de firma digital (fix bug #23) ─────────────
            # Detectar qué librería JWT está disponible (una sola vez, con cache).
            if not hasattr(self, "_jwt_lib"):
                self._jwt_lib = self._detect_jwt_lib()

            if self._jwt_lib is None:
                logger.error(
                    "SSO OIDC: Ni PyJWT ni python-jose instalados — no se puede "
                    "validar firma de ID token. Rechazando por seguridad. "
                    "Instala con: pip install PyJWT cryptography"
                )
                return {}

            # Obtener JWKS del IdP (con cache)
            jwks_uri = config.get("jwks_uri") or self._discover_jwks_uri(config)
            if not jwks_uri:
                logger.error(
                    "SSO OIDC: jwks_uri no configurado — no se puede validar "
                    "firma de ID token. Configura 'jwks_uri' o 'discovery_url'."
                )
                return {}

            jwks = self._fetch_jwks(jwks_uri)
            if not jwks:
                logger.error("SSO OIDC: No se pudieron obtener JWKS del IdP")
                return {}

            # Decodificar header para obtener kid
            parts = id_token.split(".")
            if len(parts) != 3:
                logger.warning("SSO OIDC: ID token malformado (no es JWT)")
                return {}

            header_b64 = parts[0]
            padding = 4 - len(header_b64) % 4
            if padding != 4:
                header_b64 += "=" * padding
            header = json.loads(base64.urlsafe_b64decode(header_b64))
            kid = header.get("kid")

            # Buscar la clave correcta en JWKS
            signing_key = None
            for key in jwks.get("keys", []):
                if kid is None or key.get("kid") == kid:
                    signing_key = key
                    break

            if not signing_key:
                logger.error(f"SSO OIDC: Clave con kid={kid} no encontrada en JWKS")
                return {}

            # Validar firma + decodificar claims
            expected_audience = config.get("client_id", "")
            expected_issuer = config.get("issuer", "")

            if self._jwt_lib == "pyjwt":
                # PyJWT: importar y validar
                import jwt
                from jwt.algorithms import RSAAlgorithm
                public_key = RSAAlgorithm.from_jwk(json.dumps(signing_key))
                claims = jwt.decode(
                    id_token,
                    key=public_key,
                    algorithms=["RS256"],
                    audience=expected_audience or None,
                    issuer=expected_issuer or None,
                )
            else:
                # python-jose fallback
                from jose import jwt
                claims = jwt.decode(
                    id_token,
                    key=json.dumps(signing_key),
                    algorithms=["RS256"],
                    audience=expected_audience or None,
                    issuer=expected_issuer or None,
                    options={"verify_signature": True},
                )

            logger.debug(f"SSO OIDC: ID token validado y firma verificada (sub={claims.get('sub', 'N/A')})")
            return claims

        except Exception as e:
            logger.error(f"SSO OIDC: Error validando/firmando ID token: {e}")
            return {}

    def _discover_jwks_uri(self, config: dict) -> str | None:
        """Descubre jwks_uri vía OpenID Connect discovery document."""
        discovery_url = config.get("discovery_url")
        if not discovery_url:
            return None
        try:
            import urllib.request
            req = urllib.request.Request(discovery_url)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            return doc.get("jwks_uri")
        except Exception as e:
            logger.error(f"SSO OIDC: Error en discovery: {e}")
            return None

    @staticmethod
    def _detect_jwt_lib() -> str | None:
        """Detecta qué librería JWT está disponible: 'pyjwt', 'jose', o None."""
        # Usar importlib.util.find_spec para evitar imports completos
        # (más rápido y no ensucia el namespace del módulo).
        import importlib.util
        if importlib.util.find_spec("jwt") is not None:
            return "pyjwt"
        if importlib.util.find_spec("jose") is not None:
            return "jose"
        return None

    def _fetch_jwks(self, jwks_uri: str) -> dict | None:
        """Fetch JWKS del IdP (con cache simple en memoria)."""
        # Cache simple en atributo de instancia (TTL implícito por proceso)
        if not hasattr(self, "_jwks_cache"):
            self._jwks_cache: dict[str, dict] = {}
        if jwks_uri in self._jwks_cache:
            return self._jwks_cache[jwks_uri]

        try:
            import urllib.request
            req = urllib.request.Request(jwks_uri)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=10) as resp:
                jwks = json.loads(resp.read().decode("utf-8"))
            self._jwks_cache[jwks_uri] = jwks
            return jwks
        except Exception as e:
            logger.error(f"SSO OIDC: Error obteniendo JWKS: {e}")
            return None

    def _fetch_userinfo(self, config: dict, access_token: str) -> dict | None:
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
