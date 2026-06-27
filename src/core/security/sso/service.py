"""
Workflow Determinista — SSO Service (SAML 2.0 + OIDC)
======================================================

Servicio de Single Sign-On que soporta SAML 2.0 y OpenID Connect (OIDC).

NOTA: Entry point delgado. La implementacion de cada dominio (SAML, OIDC,
Keycloak, Sesiones, Proveedores) se encuentra en src/security/sso/ subpackage.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from src.core.db.redis_service import RedisService
from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.security.sso.keycloak import auto_configure_keycloak
from src.core.security.sso.oidc import OIDCHandler
from src.core.security.sso.provider_manager import (
    configure_provider,
    ensure_tables,
    get_provider,
    get_providers,
    remove_provider,
)
from src.core.security.sso.routes import register_sso_routes
from src.core.security.sso.saml import SAMLHandler
from src.core.security.sso.session import (
    cleanup_expired_sessions,
    create_or_link_user,
    create_sso_session,
    link_existing_user,
    logout_session,
    validate_sso_session,
)

logger = setup_logging(__name__)


class SSOService:
    """Servicio de Single Sign-On con soporte SAML 2.0 y OIDC.

    Orquestador delgado que delega a:
    - provider_manager.py: configure_provider, get_providers, remove_provider
    - saml.py: SAMLHandler (login, callback, metadata)
    - oidc.py: OIDCHandler (login, callback)
    - session.py: create/validate/logout sessions
    - mapping.py: user mapping
    - keycloak.py: auto-configure
    - routes.py: Flask routes
    """

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
            ensure_tables(self._db)
            self._saml = SAMLHandler(self._db, self._redis)
            self._oidc = OIDCHandler(self._db, self._redis)
            logger.info("SSO Service inicializado")

    # ── Gestion de proveedores ────────────────────────────

    def configure_provider(self, name: str, provider_type: str, config: dict[str, Any]) -> dict:
        return configure_provider(self._db, name, provider_type, config)

    def get_providers(self) -> list[dict[str, Any]]:
        return get_providers(self._db)

    def get_provider(self, name: str) -> dict[str, Any] | None:
        return get_provider(self._db, name)

    def remove_provider(self, name: str) -> dict[str, Any]:
        return remove_provider(self._db, self._redis, name)

    # ── SAML 2.0 ─────────────────────────────────────────

    def generate_sp_metadata(self, provider_name: str) -> str:
        provider = self.get_provider(provider_name)
        if not provider:
            return ""
        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        return self._saml.generate_sp_metadata(config, provider_name)

    def initiate_saml_login(self, provider_name: str) -> dict[str, Any]:
        provider = self.get_provider(provider_name)
        if not provider or not provider["enabled"]:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no disponible"}
        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        return self._saml.initiate_login(config, provider_name)

    def handle_saml_callback(self, provider_name: str, saml_response: str) -> dict[str, Any]:
        provider = self.get_provider(provider_name)
        if not provider:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no encontrado"}
        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        result = self._saml.handle_callback(config, saml_response)
        if result.get("status") != "ok":
            return result

        user_info = result["user_info"]
        user_result = create_or_link_user(self._db, provider_name, user_info["external_id"], user_info)
        if user_result.get("status") != "ok":
            return user_result

        session_result = create_sso_session(self._db, self._redis, provider_name, user_result["user_id"])
        self._db.audit("sso.saml.login",
                       f"Login SAML exitoso via '{provider_name}' para usuario {user_result['user_id']}",
                       user_id=user_result["user_id"])
        logger.info(f"SSO SAML: Login exitoso via '{provider_name}' para usuario {user_result['user_id']}")
        return {"status": "ok", "user_info": user_info, "user_id": user_result["user_id"],
                "session_id": session_result["session_id"]}

    # ── OIDC ──────────────────────────────────────────────

    def initiate_oidc_login(self, provider_name: str) -> dict[str, Any]:
        provider = self.get_provider(provider_name)
        if not provider or not provider["enabled"]:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no disponible"}
        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        return self._oidc.initiate_login(config, provider_name)

    def handle_oidc_callback(self, provider_name: str, code: str, state: str) -> dict[str, Any]:
        provider = self.get_provider(provider_name)
        if not provider:
            return {"status": "error", "message": f"Proveedor '{provider_name}' no encontrado"}
        config = json.loads(provider["config"]) if isinstance(provider["config"], str) else provider["config"]
        config["_provider_name"] = provider_name

        result = self._oidc.handle_callback(config, code, state)
        if result.get("status") != "ok":
            return result

        user_info = result["user_info"]
        user_result = create_or_link_user(self._db, provider_name, user_info["external_id"], user_info)
        if user_result.get("status") != "ok":
            return user_result

        session_result = create_sso_session(self._db, self._redis, provider_name, user_result["user_id"],
                                             result.get("idp_session"))
        self._db.audit("sso.oidc.login",
                       f"Login OIDC exitoso via '{provider_name}' para usuario {user_result['user_id']}",
                       user_id=user_result["user_id"])
        logger.info(f"SSO OIDC: Login exitoso via '{provider_name}' para usuario {user_result['user_id']}")
        return {"status": "ok", "user_info": user_info, "user_id": user_result["user_id"],
                "session_id": session_result["session_id"]}

    # ── Keycloak Embebido ─────────────────────────────────

    def auto_configure_keycloak(self) -> dict[str, Any]:
        return auto_configure_keycloak(self._db)

    # ── Mapeo de usuarios ─────────────────────────────────

    def create_or_link_user(self, provider_name: str, external_id: str, user_info: dict[str, Any]) -> dict:
        return create_or_link_user(self._db, provider_name, external_id, user_info)

    def link_existing_user(self, user_id: int, provider_name: str, external_id: str) -> dict[str, Any]:
        return link_existing_user(self._db, user_id, provider_name, external_id)

    # ── Sesiones SSO ──────────────────────────────────────

    def validate_sso_session(self, session_id: str) -> dict[str, Any] | None:
        return validate_sso_session(self._db, self._redis, session_id)

    def logout(self, session_id: str) -> dict[str, Any]:
        return logout_session(self._db, self._redis, session_id)

    def cleanup_expired_sessions(self) -> int:
        return cleanup_expired_sessions(self._db, self._redis)

    # ── Routes ────────────────────────────────────────────

    def register_routes(self, app) -> None:
        """Registra las rutas SSO Flask. Conveniencia sobre register_sso_routes()."""
        register_sso_routes(app, self._db)
