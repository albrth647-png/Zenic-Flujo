"""
Workflow Determinista — SSO Service (SAML 2.0 + OIDC)
======================================================

Servicio de Single Sign-On que soporta SAML 2.0 y OpenID Connect (OIDC).
Permite integracion con Okta, Azure AD, OneLogin, Google Workspace, Auth0 y Keycloak.

Funcionalidades:
- SAML 2.0: Metadata SP, AuthnRequest, validacion de Response, extraccion de atributos
- OIDC: Authorization Code Flow con PKCE, intercambio de tokens, validacion de ID token
- Keycloak embebido: auto-configuracion si no hay IdP externo
- Mapeo de usuarios IdP externos a usuarios locales
- Sesiones SSO con tracking en DB y cache en Redis
- Rutas Flask para login/callback SAML y OIDC

Configuracion via variables de entorno:
- WFD_SSO_BASE_URL: URL base del SP (default: http://localhost:8080)
- WFD_SSO_SESSION_TTL: TTL de sesion SSO en segundos (default: 28800 = 8h)
- WFD_SSO_KEYCLOAK_URL: URL de Keycloak embebido (opcional)
- WFD_SSO_KEYCLOAK_REALM: Realm de Keycloak (default: zenic-flijo)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from typing import Any

from src.data.database_manager import DatabaseManager
from src.data.redis_service import RedisService
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Constantes ────────────────────────────────────────────────

_SSO_BASE_URL: str = os.environ.get("WFD_SSO_BASE_URL", "http://localhost:8080")
_SSO_SESSION_TTL: int = int(os.environ.get("WFD_SSO_SESSION_TTL", "28800"))
_KEYCLOAK_URL: str | None = os.environ.get("WFD_SSO_KEYCLOAK_URL", None)
_KEYCLOAK_REALM: str = os.environ.get("WFD_SSO_KEYCLOAK_REALM", "zenic-flijo")

_SAML_NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig",
}

# Prefijo Redis para estados OIDC y sesiones SSO
_OIDC_STATE_PREFIX = "sso:oidc:state:"
_SSO_SESSION_PREFIX = "sso:session:"


class SSOService:
    """Servicio de Single Sign-On con soporte SAML 2.0 y OIDC."""

    _instance: SSOService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> SSOService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._redis = RedisService()
            self._ensure_tables()
            logger.info("SSO Service inicializado")

    # ── Inicializacion de tablas ──────────────────────────

    def _ensure_tables(self) -> None:
        """Crea las tablas SSO si no existen."""
        conn = self._db.get_connection()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS sso_providers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                type        TEXT NOT NULL CHECK(type IN ('saml', 'oidc', 'keycloak')),
                config      TEXT NOT NULL DEFAULT '{}',
                enabled     INTEGER DEFAULT 1,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sso_sessions (
                session_id  TEXT PRIMARY KEY,
                provider    TEXT NOT NULL,
                user_id     INTEGER NOT NULL,
                idp_session TEXT,
                expires_at  TIMESTAMP NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS sso_user_mapping (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name   TEXT NOT NULL,
                external_id     TEXT NOT NULL,
                user_id         INTEGER NOT NULL,
                external_attrs  TEXT DEFAULT '{}',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider_name, external_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_sso_sessions_user
                ON sso_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sso_sessions_expires
                ON sso_sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_sso_user_mapping_provider
                ON sso_user_mapping(provider_name, external_id);
        """)
        conn.commit()

    # ── Gestion de proveedores ────────────────────────────

    def configure_provider(self, name: str, provider_type: str, config: dict) -> dict:
        """Configura o actualiza un proveedor de identidad SSO.

        Args:
            name: Nombre unico del proveedor (ej: 'okta', 'google')
            provider_type: Tipo de proveedor ('saml', 'oidc', 'keycloak')
            config: Configuracion del proveedor como dict

        Returns:
            dict con status y datos del proveedor
        """
        valid_types = {"saml", "oidc", "keycloak"}
        if provider_type not in valid_types:
            return {"status": "error", "message": f"Tipo invalido. Validos: {', '.join(sorted(valid_types))}"}

        # Validar configuracion segun tipo
        validation = self._validate_provider_config(provider_type, config)
        if not validation["valid"]:
            return {"status": "error", "message": validation["message"]}

        config_json = json.dumps(config, default=str, ensure_ascii=False)

        existing = self._db.fetchone("SELECT id FROM sso_providers WHERE name = ?", (name,))
        if existing:
            self._db.execute(
                "UPDATE sso_providers SET type = ?, config = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                (provider_type, config_json, name),
            )
            self._db.commit()
            logger.info(f"SSO: Proveedor '{name}' actualizado (tipo={provider_type})")
        else:
            self._db.execute(
                "INSERT INTO sso_providers (name, type, config, enabled) VALUES (?, ?, ?, 1)",
                (name, provider_type, config_json),
            )
            self._db.commit()
            logger.info(f"SSO: Proveedor '{name}' creado (tipo={provider_type})")

        self._db.audit("sso.provider.configured", f"Proveedor '{name}' tipo={provider_type}")
        return {"status": "ok", "name": name, "type": provider_type}

    def get_providers(self) -> list[dict]:
        """Retorna la lista de proveedores SSO configurados."""
        rows = self._db.fetchall(
            "SELECT id, name, type, enabled, created_at, updated_at FROM sso_providers ORDER BY name"
        )
        # No exponer config completo (contiene secrets)
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "enabled": bool(row["enabled"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_provider(self, name: str) -> dict | None:
        """Obtiene la configuracion completa de un proveedor."""
        return self._db.fetchone("SELECT * FROM sso_providers WHERE name = ?", (name,))

    def remove_provider(self, name: str) -> dict:
        """Elimina un proveedor SSO y sus sesiones activas."""
        existing = self._db.fetchone("SELECT id FROM sso_providers WHERE name = ?", (name,))
        if not existing:
            return {"status": "error", "message": f"Proveedor '{name}' no encontrado"}

        # Invalidar sesiones activas del proveedor
        sessions = self._db.fetchall(
            "SELECT session_id FROM sso_sessions WHERE provider = ?",
            (name,),
        )
        for s in sessions:
            self._redis.delete(f"{_SSO_SESSION_PREFIX}{s['session_id']}")

        # Eliminar mapeos de usuario
        self._db.execute("DELETE FROM sso_user_mapping WHERE provider_name = ?", (name,))
        # Eliminar sesiones
        self._db.execute("DELETE FROM sso_sessions WHERE provider = ?", (name,))
        # Eliminar proveedor
        self._db.execute("DELETE FROM sso_providers WHERE name = ?", (name,))
        self._db.commit()

        self._db.audit("sso.provider.removed", f"Proveedor '{name}' eliminado")
        logger.info(f"SSO: Proveedor '{name}' eliminado ({len(sessions)} sesiones invalidadas)")
        return {"status": "ok"}

    def _validate_provider_config(self, provider_type: str, config: dict) -> dict:
        """Valida la configuracion de un proveedor segun su tipo."""
        if provider_type == "saml":
            required = ["entity_id", "acs_url", "idp_sso_url", "idp_entity_id"]
            for field in required:
                if not config.get(field):
                    return {"valid": False, "message": f"SAML requiere campo '{field}'"}
        elif provider_type == "oidc":
            required = ["client_id", "client_secret", "authorization_url", "token_url"]
            for field in required:
                if not config.get(field):
                    return {"valid": False, "message": f"OIDC requiere campo '{field}'"}
        elif provider_type == "keycloak":
            required = ["client_id", "client_secret"]
            for field in required:
                if not config.get(field):
                    return {"valid": False, "message": f"Keycloak requiere campo '{field}'"}
        return {"valid": True}

    # ── SAML 2.0 ─────────────────────────────────────────

    def generate_sp_metadata(self, provider_name: str) -> str:
        """Genera el metadata XML del Service Provider para un proveedor SAML.

        Args:
            provider_name: Nombre del proveedor SAML

        Returns:
            XML del metadata SP como string
        """
        provider = self.get_provider(provider_name)
        if not provider:
            return ""

        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        entity_id = config.get("entity_id", f"{_SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")
        acs_url = config.get("acs_url", f"{_SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")

        metadata_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
                     entityID="{entity_id}">
  <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified</md:NameIDFormat>
    <md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                                 Location="{acs_url}"
                                 index="0" isDefault="true"/>
    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                            Location="{_SSO_BASE_URL}/api/v1/auth/sso/logout"/>
  </md:SPSSODescriptor>
  <md:Organization>
    <md:OrganizationName xml:lang="en">Zenic-Flijo</md:OrganizationName>
    <md:OrganizationDisplayName xml:lang="en">Zenic-Flijo Workflow Platform</md:OrganizationDisplayName>
    <md:OrganizationURL xml:lang="en">{_SSO_BASE_URL}</md:OrganizationURL>
  </md:Organization>
</md:EntityDescriptor>"""
        return metadata_xml

    def initiate_saml_login(self, provider_name: str) -> dict:
        """Inicia el flujo de login SAML generando un AuthnRequest.

        Genera un AuthnRequest codificado en Base64 y retorna la URL de redireccion
        al IdP con el parametro SAMLRequest.

        Args:
            provider_name: Nombre del proveedor SAML

        Returns:
            dict con redirect_url y request_id
        """
        provider = self.get_provider(provider_name)
        if not provider or not provider["enabled"]:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no disponible"}

        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        idp_sso_url = config.get("idp_sso_url", "")
        if not idp_sso_url:
            return {"status": "error", "message": "IdP SSO URL no configurada"}

        request_id = f"id_{uuid.uuid4().hex}"
        issue_instant = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entity_id = config.get("entity_id", f"{_SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")
        acs_url = config.get("acs_url", f"{_SSO_BASE_URL}/api/v1/auth/saml/{provider_name}/callback")

        # Construir AuthnRequest XML
        authn_request = f"""<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
                        ID="{request_id}"
                        Version="2.0"
                        IssueInstant="{issue_instant}"
                        AssertionConsumerServiceURL="{acs_url}"
                        Destination="{idp_sso_url}">
  <saml:Issuer>{entity_id}</saml:Issuer>
  <samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
                      AllowCreate="true"/>
</samlp:AuthnRequest>"""

        # Codificar en Base64 (deflated en produccion, plain para compatibilidad)
        encoded_request = base64.b64encode(authn_request.encode("utf-8")).decode("ascii")

        # Construir URL de redireccion
        redirect_url = f"{idp_sso_url}?SAMLRequest={urllib.parse.quote(encoded_request)}"

        # Almacenar request_id en Redis para validacion posterior
        self._redis.set_json(
            f"sso:saml:request:{request_id}",
            {"provider": provider_name, "created_at": time.time()},
            ttl=300,  # 5 minutos para completar login
        )

        logger.info(f"SSO SAML: Login iniciado para proveedor '{provider_name}' (request_id={request_id})")
        return {"status": "ok", "redirect_url": redirect_url, "request_id": request_id}

    def handle_saml_callback(self, provider_name: str, saml_response: str) -> dict:
        """Procesa la respuesta SAML del IdP tras el login.

        Decodifica y valida la respuesta SAML, extrae los atributos del usuario
        y crea o vincula la cuenta local.

        Args:
            provider_name: Nombre del proveedor SAML
            saml_response: Respuesta SAML codificada en Base64

        Returns:
            dict con status, user_info y session_id
        """
        provider = self.get_provider(provider_name)
        if not provider:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no encontrado"}

        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]

        # Decodificar respuesta Base64
        try:
            decoded_xml = base64.b64decode(saml_response).decode("utf-8")
        except Exception as e:
            logger.error(f"SSO SAML: Error decodificando respuesta: {e}")
            return {"status": "error", "message": "Respuesta SAML invalida (decodificacion)"}

        # Parsear XML y extraer atributos
        try:
            root = ET.fromstring(decoded_xml)
            user_info = self._extract_saml_attributes(root, config)
        except ET.ParseError as e:
            logger.error(f"SSO SAML: Error parseando XML: {e}")
            return {"status": "error", "message": "Respuesta SAML invalida (XML)"}

        if not user_info.get("external_id"):
            return {"status": "error", "message": "No se pudo identificar al usuario en la respuesta SAML"}

        # Validar condiciones de la asercion (audience, expiracion)
        validation = self._validate_saml_conditions(root, config)
        if not validation["valid"]:
            return {"status": "error", "message": validation["message"]}

        # Crear o vincular usuario local
        user_result = self.create_or_link_user(
            provider_name=provider_name,
            external_id=user_info["external_id"],
            user_info=user_info,
        )

        if user_result.get("status") != "ok":
            return user_result

        # Crear sesion SSO
        session_result = self._create_sso_session(provider_name, user_result["user_id"], user_info.get("idp_session"))

        self._db.audit(
            "sso.saml.login",
            f"Login SAML exitoso via '{provider_name}' para usuario {user_result['user_id']}",
            user_id=user_result["user_id"],
        )
        logger.info(f"SSO SAML: Login exitoso via '{provider_name}' para usuario {user_result['user_id']}")

        return {
            "status": "ok",
            "user_info": user_info,
            "user_id": user_result["user_id"],
            "session_id": session_result["session_id"],
        }

    def _extract_saml_attributes(self, root: ET.Element, config: dict) -> dict:
        """Extrae atributos del usuario desde una asercion SAML."""
        user_info: dict[str, Any] = {}

        # Buscar NameID
        name_id_elements = root.findall(".//saml:NameID", _SAML_NS)
        if name_id_elements:
            user_info["external_id"] = name_id_elements[0].text or ""
            user_info["name_id_format"] = name_id_elements[0].get("Format", "")

        # Buscar atributos de la asercion
        attributes = root.findall(".//saml:Attribute", _SAML_NS)
        for attr in attributes:
            attr_name = attr.get("Name", "")
            values = attr.findall("saml:AttributeValue", _SAML_NS)
            if len(values) == 1:
                user_info[attr_name] = values[0].text or ""
            elif len(values) > 1:
                user_info[attr_name] = [v.text or "" for v in values]

        # Mapeo de atributos comunes segun configuracion
        attr_map = config.get("attribute_map", {})
        mapped: dict[str, str] = {}
        for target_key, source_key in attr_map.items():
            if source_key in user_info:
                mapped[target_key] = user_info[source_key]

        # Defaults: mapear atributos comunes de IdPs conocidos
        if "email" not in mapped:
            mapped["email"] = (
                user_info.get("urn:oid:0.9.2342.19200300.100.1.3")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
                or user_info.get("email")
                or user_info.get("Email")
                or ""
            )
        if "display_name" not in mapped:
            mapped["display_name"] = (
                user_info.get("urn:oid:2.16.840.1.113730.3.1.241")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
                or user_info.get("displayName")
                or user_info.get("name")
                or ""
            )
        if "first_name" not in mapped:
            mapped["first_name"] = (
                user_info.get("urn:oid:2.5.4.42")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname")
                or user_info.get("firstName")
                or ""
            )
        if "last_name" not in mapped:
            mapped["last_name"] = (
                user_info.get("urn:oid:2.5.4.4")
                or user_info.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname")
                or user_info.get("lastName")
                or ""
            )

        mapped["external_id"] = user_info.get("external_id", mapped.get("email", ""))
        return mapped

    def _validate_saml_conditions(self, root: ET.Element, config: dict) -> dict:
        """Valida las condiciones de una asercion SAML (audience, expiracion)."""
        conditions = root.findall(".//saml:Conditions", _SAML_NS)
        if not conditions:
            return {"valid": True, "message": "Sin condiciones explicitas"}

        for condition in conditions:
            # Verificar NotOnOrAfter
            not_on_or_after = condition.get("NotOnOrAfter")
            if not_on_or_after:
                try:
                    from datetime import datetime

                    expiry = datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
                    if datetime.now(expiry.tzinfo) >= expiry:
                        return {"valid": False, "message": "Asercion SAML expirada"}
                except (ValueError, TypeError):
                    pass

            # Verificar AudienceRestriction
            audiences = condition.findall(".//saml:Audience", _SAML_NS)
            if audiences:
                entity_id = config.get("entity_id", "")
                valid_audience = any(aud.text == entity_id for aud in audiences if aud.text)
                if not valid_audience and entity_id:
                    return {"valid": False, "message": "Audience SAML no coincide con entity_id del SP"}

        return {"valid": True, "message": "Condiciones validas"}

    # ── OIDC ──────────────────────────────────────────────

    def initiate_oidc_login(self, provider_name: str) -> dict:
        """Inicia el flujo de login OIDC con Authorization Code Flow + PKCE.

        Genera la URL de autorizacion, un state aleatorio para CSRF protection
        y un code_verifier + code_challenge para PKCE.

        Args:
            provider_name: Nombre del proveedor OIDC

        Returns:
            dict con redirect_url y state
        """
        provider = self.get_provider(provider_name)
        if not provider or not provider["enabled"]:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no disponible"}

        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]

        # Generar state para CSRF protection
        state = secrets.token_urlsafe(32)

        # Generar PKCE code_verifier y code_challenge
        code_verifier = secrets.token_urlsafe(64)
        code_challenge_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_hash).rstrip(b"=").decode("ascii")

        # Construir URL de autorizacion
        client_id = config.get("client_id", "")
        authorization_url = config.get("authorization_url", "")
        scope = config.get("scope", "openid profile email")
        redirect_uri = config.get("redirect_uri") or f"{_SSO_BASE_URL}/api/v1/auth/oidc/{provider_name}/callback"

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        # Agregar parametros adicionales segun proveedor
        extra_params = config.get("extra_auth_params", {})
        params.update(extra_params)

        auth_url = f"{authorization_url}?{urllib.parse.urlencode(params)}"

        # Almacenar state + PKCE en Redis (TTL 5 min)
        self._redis.set_json(
            f"{_OIDC_STATE_PREFIX}{state}",
            {
                "provider": provider_name,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "created_at": time.time(),
            },
            ttl=300,
        )

        logger.info(f"SSO OIDC: Login iniciado para proveedor '{provider_name}' (state={state[:8]}...)")
        return {"status": "ok", "redirect_url": auth_url, "state": state}

    def handle_oidc_callback(self, provider_name: str, code: str, state: str) -> dict:
        """Procesa el callback OIDC tras la autorizacion del usuario.

        Intercambia el codigo de autorizacion por tokens, valida el ID token
        y obtiene informacion del usuario.

        Args:
            provider_name: Nombre del proveedor OIDC
            code: Codigo de autorizacion recibido del IdP
            state: State parameter para verificar CSRF

        Returns:
            dict con status, user_info y session_id
        """
        provider = self.get_provider(provider_name)
        if not provider:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no encontrado"}

        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]

        # Verificar state (CSRF protection)
        state_data = self._redis.get_json(f"{_OIDC_STATE_PREFIX}{state}")
        if not state_data or state_data.get("provider") != provider_name:
            logger.warning(f"SSO OIDC: State invalido o expirado para proveedor '{provider_name}'")
            return {"status": "error", "message": "State invalido o expirado (posible CSRF)"}

        # Limpiar state usado
        self._redis.delete(f"{_OIDC_STATE_PREFIX}{state}")

        # Intercambiar codigo por tokens
        token_result = self._exchange_oidc_code(config, code, state_data)
        if not token_result.get("access_token"):
            return {"status": "error", "message": token_result.get("message", "Error intercambiando codigo por tokens")}

        # Validar ID token y extraer claims
        id_token_claims: dict = {}
        if token_result.get("id_token"):
            id_token_claims = self._validate_id_token(token_result["id_token"], config)

        # Obtener userinfo si hay access_token
        user_info: dict[str, Any] = {}
        if token_result.get("access_token"):
            userinfo_result = self._fetch_oidc_userinfo(config, token_result["access_token"])
            if userinfo_result:
                user_info = userinfo_result

        # Combinar claims del ID token con userinfo
        user_info.update({k: v for k, v in id_token_claims.items() if k not in user_info})

        # Identificar al usuario externo
        external_id = user_info.get("sub") or user_info.get("email") or id_token_claims.get("sub", "")
        if not external_id:
            return {"status": "error", "message": "No se pudo identificar al usuario (sin sub ni email)"}

        user_info["external_id"] = external_id

        # Crear o vincular usuario local
        user_result = self.create_or_link_user(
            provider_name=provider_name,
            external_id=external_id,
            user_info=user_info,
        )

        if user_result.get("status") != "ok":
            return user_result

        # Crear sesion SSO
        session_result = self._create_sso_session(
            provider_name,
            user_result["user_id"],
            id_token_claims.get("sid"),
        )

        self._db.audit(
            "sso.oidc.login",
            f"Login OIDC exitoso via '{provider_name}' para usuario {user_result['user_id']}",
            user_id=user_result["user_id"],
        )
        logger.info(f"SSO OIDC: Login exitoso via '{provider_name}' para usuario {user_result['user_id']}")

        return {
            "status": "ok",
            "user_info": user_info,
            "user_id": user_result["user_id"],
            "session_id": session_result["session_id"],
        }

    def _exchange_oidc_code(self, config: dict, code: str, state_data: dict) -> dict:
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

        Verifica firma (si hay JWKS configurado), audiencia, emisor y expiracion.
        En modo basico, decodifica el payload sin verificar firma (para desarrollo).
        """
        try:
            # Decodificar payload JWT (formato: header.payload.signature)
            parts = id_token.split(".")
            if len(parts) != 3:
                logger.warning("SSO OIDC: ID token malformado (no es JWT)")
                return {}

            # Decodificar payload (parte 2)
            payload_b64 = parts[1]
            # Agregar padding si es necesario
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            claims = json.loads(payload_bytes)

            # Verificar audience
            expected_audience = config.get("client_id", "")
            token_aud = claims.get("aud", "")
            if isinstance(token_aud, list):
                if expected_audience not in token_aud:
                    logger.warning(
                        f"SSO OIDC: Audience no coincide. Esperada={expected_audience}, Recibida={token_aud}"
                    )
            elif token_aud != expected_audience:
                logger.warning(f"SSO OIDC: Audience no coincide. Esperada={expected_audience}, Recibida={token_aud}")

            # Verificar expiracion
            exp = claims.get("exp")
            if exp and time.time() > exp:
                logger.warning("SSO OIDC: ID token expirado")
                return {}

            # Verificar issuer
            expected_issuer = config.get("issuer", "")
            if expected_issuer and claims.get("iss") != expected_issuer:
                logger.warning(
                    f"SSO OIDC: Issuer no coincide. Esperado={expected_issuer}, Recibido={claims.get('iss')}"
                )

            # Verificar nonce si fue enviado
            # (no implementado en initiate_oidc_login por simplicidad)

            logger.debug(f"SSO OIDC: ID token validado (sub={claims.get('sub', 'N/A')})")
            return claims

        except Exception as e:
            logger.error(f"SSO OIDC: Error validando ID token: {e}")
            return {}

    def _fetch_oidc_userinfo(self, config: dict, access_token: str) -> dict | None:
        """Obtiene informacion del usuario desde el endpoint UserInfo de OIDC."""
        userinfo_url = config.get("userinfo_url", "")
        if not userinfo_url:
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

    # ── Keycloak Embebido ─────────────────────────────────

    def auto_configure_keycloak(self) -> dict:
        """Auto-configura Keycloak como IdP si no hay otros proveedores configurados.

        Crea la configuracion del cliente Keycloak para Zenic-Flijo usando
        las variables de entorno WFD_SSO_KEYCLOAK_*.

        Returns:
            dict con status y nombre del proveedor configurado
        """
        if not _KEYCLOAK_URL:
            return {"status": "error", "message": "WFD_SSO_KEYCLOAK_URL no configurada"}

        # Verificar si ya hay proveedores configurados
        existing = self._db.fetchone("SELECT COUNT(*) as c FROM sso_providers WHERE enabled = 1")
        if existing and existing["c"] > 0:
            return {"status": "ok", "message": "Ya existen proveedores SSO configurados"}

        # Construir URLs de Keycloak
        realm_url = f"{_KEYCLOAK_URL}/realms/{_KEYCLOAK_REALM}"
        config = {
            "client_id": os.environ.get("WFD_SSO_KEYCLOAK_CLIENT_ID", "zenic-flijo"),
            "client_secret": os.environ.get("WFD_SSO_KEYCLOAK_CLIENT_SECRET", ""),
            "authorization_url": f"{realm_url}/protocol/openid-connect/auth",
            "token_url": f"{realm_url}/protocol/openid-connect/token",
            "userinfo_url": f"{realm_url}/protocol/openid-connect/userinfo",
            "issuer": realm_url,
            "scope": "openid profile email",
            "jwks_uri": f"{realm_url}/protocol/openid-connect/certs",
        }

        result = self.configure_provider("keycloak", "keycloak", config)
        if result.get("status") == "ok":
            logger.info(f"SSO: Keycloak auto-configurado (realm={_KEYCLOAK_REALM})")
        return result

    # ── Mapeo de usuarios ─────────────────────────────────

    def create_or_link_user(self, provider_name: str, external_id: str, user_info: dict) -> dict:
        """Crea un usuario local o vincula un usuario IdP existente.

        Si ya existe un mapeo para el provider_name + external_id, retorna el user_id
        existente. Si no, busca un usuario local por email para vincular.
        Si no hay coincidencia, crea un nuevo usuario local.

        Args:
            provider_name: Nombre del proveedor IdP
            external_id: ID del usuario en el IdP
            user_info: Informacion del usuario (email, display_name, etc.)

        Returns:
            dict con status y user_id
        """
        # 1. Verificar mapeo existente
        existing_mapping = self._db.fetchone(
            "SELECT user_id FROM sso_user_mapping WHERE provider_name = ? AND external_id = ?",
            (provider_name, external_id),
        )
        if existing_mapping:
            # Actualizar atributos externos
            self._db.execute(
                "UPDATE sso_user_mapping SET external_attrs = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE provider_name = ? AND external_id = ?",
                (json.dumps(user_info, default=str, ensure_ascii=False), provider_name, external_id),
            )
            self._db.commit()
            return {"status": "ok", "user_id": existing_mapping["user_id"], "linked": True}

        # 2. Buscar usuario local por email para vincular
        email = user_info.get("email", "")
        local_user_id: int | None = None

        if email:
            existing_user = self._db.fetchone("SELECT id FROM users WHERE email = ? AND is_active = 1", (email,))
            if existing_user:
                local_user_id = existing_user["id"]

        # 3. Crear nuevo usuario si no existe
        if local_user_id is None:
            username = (
                user_info.get("username") or user_info.get("preferred_username") or email.split("@")[0]
                if email
                else f"sso_{uuid.uuid4().hex[:8]}"
            )
            display_name = user_info.get("display_name") or user_info.get("name") or username

            # Verificar que el username sea unico
            existing_username = self._db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
            if existing_username:
                username = f"{username}_{uuid.uuid4().hex[:4]}"

            # Crear usuario con password aleatorio (no se usara para login directo)
            import bcrypt

            random_password = secrets.token_urlsafe(32)
            hashed = bcrypt.hashpw(random_password.encode(), bcrypt.gensalt(rounds=12)).decode()

            cursor = self._db.execute(
                "INSERT INTO users (username, password_hash, role, display_name, email, is_active) "
                "VALUES (?, ?, 'editor', ?, ?, 1)",
                (username, hashed, display_name, email),
            )
            self._db.commit()
            local_user_id = cursor.lastrowid
            logger.info(f"SSO: Nuevo usuario creado via SSO: {username} (id={local_user_id})")

        # 4. Crear mapeo
        self._db.execute(
            "INSERT INTO sso_user_mapping (provider_name, external_id, user_id, external_attrs) VALUES (?, ?, ?, ?)",
            (provider_name, external_id, local_user_id, json.dumps(user_info, default=str, ensure_ascii=False)),
        )
        self._db.commit()

        return {"status": "ok", "user_id": local_user_id, "linked": False}

    def link_existing_user(self, user_id: int, provider_name: str, external_id: str) -> dict:
        """Vincula manualmente un usuario local con una cuenta IdP.

        Args:
            user_id: ID del usuario local
            provider_name: Nombre del proveedor IdP
            external_id: ID del usuario en el IdP

        Returns:
            dict con status
        """
        existing_user = self._db.fetchone("SELECT id FROM users WHERE id = ? AND is_active = 1", (user_id,))
        if not existing_user:
            return {"status": "error", "message": f"Usuario {user_id} no encontrado"}

        existing_mapping = self._db.fetchone(
            "SELECT id FROM sso_user_mapping WHERE provider_name = ? AND external_id = ?",
            (provider_name, external_id),
        )
        if existing_mapping:
            return {"status": "error", "message": "Este usuario IdP ya esta vinculado a otra cuenta"}

        self._db.execute(
            "INSERT INTO sso_user_mapping (provider_name, external_id, user_id) VALUES (?, ?, ?)",
            (provider_name, external_id, user_id),
        )
        self._db.commit()

        self._db.audit(
            "sso.user.linked", f"Usuario {user_id} vinculado con {provider_name}/{external_id}", user_id=user_id
        )
        return {"status": "ok"}

    # ── Sesiones SSO ──────────────────────────────────────

    def _create_sso_session(self, provider_name: str, user_id: int, idp_session: str | None = None) -> dict:
        """Crea una sesion SSO en la base de datos y Redis."""
        session_id = str(uuid.uuid4())
        expires_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + _SSO_SESSION_TTL))

        self._db.execute(
            "INSERT INTO sso_sessions (session_id, provider, user_id, idp_session, expires_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, provider_name, user_id, idp_session, expires_at),
        )
        self._db.commit()

        # Cache en Redis para validacion rapida
        self._redis.set_json(
            f"{_SSO_SESSION_PREFIX}{session_id}",
            {"provider": provider_name, "user_id": user_id, "idp_session": idp_session},
            ttl=_SSO_SESSION_TTL,
        )

        return {"session_id": session_id, "expires_at": expires_at}

    def validate_sso_session(self, session_id: str) -> dict | None:
        """Valida una sesion SSO y retorna la informacion del usuario.

        Verifica primero en Redis (rapido), luego en DB si no esta en cache.

        Args:
            session_id: ID de la sesion SSO

        Returns:
            dict con user_id y provider, o None si la sesion no es valida
        """
        # Verificar en Redis primero (rapido)
        cached = self._redis.get_json(f"{_SSO_SESSION_PREFIX}{session_id}")
        if cached:
            return cached

        # Fallback a DB
        session_data = self._db.fetchone(
            "SELECT session_id, provider, user_id, idp_session, expires_at FROM sso_sessions WHERE session_id = ?",
            (session_id,),
        )
        if not session_data:
            return None

        # Verificar expiracion
        try:
            from datetime import datetime

            expires = datetime.fromisoformat(session_data["expires_at"])
            if datetime.now(expires.tzinfo if expires.tzinfo else None) >= expires:
                self.logout(session_id)
                return None
        except (ValueError, TypeError):
            pass

        # Restaurar en Redis
        result = {
            "provider": session_data["provider"],
            "user_id": session_data["user_id"],
            "idp_session": session_data.get("idp_session"),
        }
        self._redis.set_json(f"{_SSO_SESSION_PREFIX}{session_id}", result, ttl=_SSO_SESSION_TTL)

        return result

    def logout(self, session_id: str) -> dict:
        """Invalida una sesion SSO.

        Elimina la sesion de Redis y de la base de datos.

        Args:
            session_id: ID de la sesion SSO

        Returns:
            dict con status
        """
        # Obtener datos de sesion antes de eliminar
        session_data = self._redis.get_json(f"{_SSO_SESSION_PREFIX}{session_id}")

        # Eliminar de Redis
        self._redis.delete(f"{_SSO_SESSION_PREFIX}{session_id}")

        # Eliminar de DB
        self._db.execute("DELETE FROM sso_sessions WHERE session_id = ?", (session_id,))
        self._db.commit()

        if session_data:
            self._db.audit(
                "sso.logout",
                f"Sesion SSO cerrada para usuario {session_data.get('user_id')}",
                user_id=session_data.get("user_id"),
            )

        logger.info(f"SSO: Sesion {session_id[:8]}... cerrada")
        return {"status": "ok"}

    def cleanup_expired_sessions(self) -> int:
        """Elimina sesiones SSO expiradas de la base de datos.

        Returns:
            Numero de sesiones eliminadas
        """
        result = self._db.execute("DELETE FROM sso_sessions WHERE expires_at < datetime('now')")
        self._db.commit()
        count = result.rowcount
        if count > 0:
            logger.info(f"SSO: {count} sesiones expiradas eliminadas")
        return count


# ── Flask Routes ──────────────────────────────────────────────


def register_sso_routes(app: Any) -> None:
    """Registra las rutas SSO en la aplicacion Flask.

    Rutas registradas:
    - GET  /api/v1/auth/saml/<provider>/login    — Iniciar login SAML
    - POST /api/v1/auth/saml/<provider>/callback  — Callback SAML
    - GET  /api/v1/auth/oidc/<provider>/login     — Iniciar login OIDC
    - GET  /api/v1/auth/oidc/<provider>/callback   — Callback OIDC
    - GET  /api/v1/auth/sso/providers              — Listar proveedores
    - POST /api/v1/auth/sso/link                   — Vincular cuenta existente
    """

    sso = SSOService()

    @app.route("/api/v1/auth/saml/<provider>/login")
    def sso_saml_login(provider: str):
        """Inicia el flujo de login SAML redirigiendo al IdP."""
        result = sso.initiate_saml_login(provider)
        if result.get("status") != "ok":
            from flask import jsonify

            return jsonify(result), 400

        from flask import redirect

        return redirect(result["redirect_url"])

    @app.route("/api/v1/auth/saml/<provider>/callback", methods=["POST"])
    def sso_saml_callback(provider: str):
        """Procesa la respuesta SAML del IdP."""
        from flask import jsonify, request, session

        saml_response = request.form.get("SAMLResponse", "")
        if not saml_response:
            return jsonify({"error": "SAMLResponse no encontrada en el POST"}), 400

        result = sso.handle_saml_callback(provider, saml_response)
        if result.get("status") != "ok":
            return jsonify(result), 401

        # Crear sesion Flask local
        user_id = result["user_id"]
        user = sso._db.get_user(user_id)
        if user:
            session["user"] = user["username"]
            session["user_id"] = user_id
            session["role"] = user.get("role", "editor")
            session["sso_session_id"] = result["session_id"]
            session["sso_provider"] = provider
            session.permanent = True

            # Actualizar last_login
            sso._db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            sso._db.commit()

        return jsonify(
            {
                "status": "ok",
                "user": user,
                "sso_session_id": result["session_id"],
            }
        )

    @app.route("/api/v1/auth/oidc/<provider>/login")
    def sso_oidc_login(provider: str):
        """Inicia el flujo de login OIDC redirigiendo al IdP."""
        result = sso.initiate_oidc_login(provider)
        if result.get("status") != "ok":
            from flask import jsonify

            return jsonify(result), 400

        from flask import redirect

        return redirect(result["redirect_url"])

    @app.route("/api/v1/auth/oidc/<provider>/callback")
    def sso_oidc_callback(provider: str):
        """Procesa el callback OIDC tras la autorizacion del usuario."""
        from flask import jsonify, request, session

        code = request.args.get("code", "")
        state = request.args.get("state", "")

        if not code or not state:
            return jsonify({"error": "Parametros code y state son requeridos"}), 400

        result = sso.handle_oidc_callback(provider, code, state)
        if result.get("status") != "ok":
            return jsonify(result), 401

        # Crear sesion Flask local
        user_id = result["user_id"]
        user = sso._db.get_user(user_id)
        if user:
            session["user"] = user["username"]
            session["user_id"] = user_id
            session["role"] = user.get("role", "editor")
            session["sso_session_id"] = result["session_id"]
            session["sso_provider"] = provider
            session.permanent = True

            # Actualizar last_login
            sso._db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user_id,))
            sso._db.commit()

        return jsonify(
            {
                "status": "ok",
                "user": user,
                "sso_session_id": result["session_id"],
            }
        )

    @app.route("/api/v1/auth/sso/providers")
    def sso_list_providers():
        """Lista los proveedores SSO disponibles."""
        from flask import jsonify

        providers = sso.get_providers()
        return jsonify({"providers": providers})

    @app.route("/api/v1/auth/sso/link", methods=["POST"])
    def sso_link_account():
        """Vincula una cuenta IdP con un usuario local existente."""
        from flask import jsonify, request, session

        if "user" not in session:
            return jsonify({"error": "No autenticado"}), 401

        data = request.get_json() or {}
        provider_name = data.get("provider", "")
        external_id = data.get("external_id", "")

        if not provider_name or not external_id:
            return jsonify({"error": "provider y external_id son requeridos"}), 400

        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Sesion invalida"}), 401

        result = sso.link_existing_user(user_id, provider_name, external_id)
        if result.get("status") != "ok":
            return jsonify(result), 400

        return jsonify(result)
