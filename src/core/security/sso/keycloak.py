"""
SSO — Keycloak Embebido: auto-configuracion como IdP.
"""

from __future__ import annotations

import os

from src.core.db.sqlite_manager import DatabaseManager
from src.core.security.sso.constants import KEYCLOAK_REALM, KEYCLOAK_URL
from src.core.logging import setup_logging

logger = setup_logging(__name__)


def auto_configure_keycloak(db: DatabaseManager) -> dict:
    """Auto-configura Keycloak como IdP si no hay otros proveedores.

    Crea la configuracion del cliente Keycloak para Zenic-Flijo usando
    las variables de entorno WFD_SSO_KEYCLOAK_*.

    Returns:
        dict con status y nombre del proveedor configurado
    """
    if not KEYCLOAK_URL:
        return {"status": "error", "message": "WFD_SSO_KEYCLOAK_URL no configurada"}

    existing = db.fetchone("SELECT COUNT(*) as c FROM sso_providers WHERE enabled = 1")
    if existing and existing["c"] > 0:
        return {"status": "ok", "message": "Ya existen proveedores SSO configurados"}

    realm_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
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

    import json as _json
    config_json = _json.dumps(config, default=str, ensure_ascii=False)
    existing_prov = db.fetchone("SELECT id FROM sso_providers WHERE name = 'keycloak'")
    if existing_prov:
        db.execute(
            "UPDATE sso_providers SET type = 'keycloak', config = ?, updated_at = CURRENT_TIMESTAMP WHERE name = 'keycloak'",
            (config_json,),
        )
    else:
        db.execute(
            "INSERT INTO sso_providers (name, type, config, enabled) VALUES ('keycloak', 'keycloak', ?, 1)",
            (config_json,),
        )
    db.commit()

    logger.info(f"SSO: Keycloak auto-configurado (realm={KEYCLOAK_REALM})")
    return {"status": "ok", "name": "keycloak", "type": "keycloak"}
