"""
SSO Provider Manager — Gestión de proveedores SSO
===================================================

Extraído de sso.py (configure_provider, get_providers, remove_provider, etc.).
"""

from __future__ import annotations

import json
from typing import Any

from src.core.db.redis_service import RedisService
from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.security.sso.constants import SSO_SESSION_PREFIX

logger = setup_logging(__name__)

VALID_TYPES = {"saml", "oidc", "keycloak"}


def ensure_tables(db: DatabaseManager) -> None:
    """Crea las tablas necesarias para SSO si no existen."""
    conn = db.get_connection()
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
        CREATE INDEX IF NOT EXISTS idx_sso_sessions_user ON sso_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_sso_sessions_expires ON sso_sessions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_sso_user_mapping_provider ON sso_user_mapping(provider_name, external_id);
    """)
    conn.commit()


def configure_provider(db: DatabaseManager, name: str, provider_type: str, config: dict[str, Any]) -> dict:
    """Configura o actualiza un proveedor SSO."""
    if provider_type not in VALID_TYPES:
        return {"status": "error", "message": f"Tipo invalido. Validos: {', '.join(sorted(VALID_TYPES))}"}

    validation = _validate_provider_config(provider_type, config)
    if not validation["valid"]:
        return {"status": "error", "message": validation["message"]}

    config_json = json.dumps(config, default=str, ensure_ascii=False)
    existing = db.fetchone("SELECT id FROM sso_providers WHERE name = ?", (name,))
    if existing:
        db.execute(
            "UPDATE sso_providers SET type = ?, config = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (provider_type, config_json, name),
        )
    else:
        db.execute(
            "INSERT INTO sso_providers (name, type, config, enabled) VALUES (?, ?, ?, 1)",
            (name, provider_type, config_json),
        )
    db.commit()
    logger.info(f"SSO: Proveedor '{name}' {'actualizado' if existing else 'creado'} (tipo={provider_type})")
    db.audit("sso.provider.configured", f"Proveedor '{name}' tipo={provider_type}")
    return {"status": "ok", "name": name, "type": provider_type}


def get_providers(db: DatabaseManager) -> list[dict[str, Any]]:
    """Lista todos los proveedores SSO configurados."""
    rows = db.fetchall(
        "SELECT id, name, type, enabled, created_at, updated_at FROM sso_providers ORDER BY name"
    )
    return [
        {"id": r["id"], "name": r["name"], "type": r["type"], "enabled": bool(r["enabled"]),
         "created_at": r["created_at"], "updated_at": r["updated_at"]}
        for r in rows
    ]


def get_provider(db: DatabaseManager, name: str) -> dict[str, Any] | None:
    """Obtiene un proveedor SSO por nombre."""
    return db.fetchone("SELECT * FROM sso_providers WHERE name = ?", (name,))


def remove_provider(db: DatabaseManager, redis: RedisService, name: str) -> dict[str, Any]:
    """Elimina un proveedor SSO y sus sesiones asociadas."""
    existing = db.fetchone("SELECT id FROM sso_providers WHERE name = ?", (name,))
    if not existing:
        return {"status": "error", "message": f"Proveedor '{name}' no encontrado"}
    sessions = db.fetchall("SELECT session_id FROM sso_sessions WHERE provider = ?", (name,))
    for s in sessions:
        redis.delete(f"{SSO_SESSION_PREFIX}{s['session_id']}")
    db.execute("DELETE FROM sso_user_mapping WHERE provider_name = ?", (name,))
    db.execute("DELETE FROM sso_sessions WHERE provider = ?", (name,))
    db.execute("DELETE FROM sso_providers WHERE name = ?", (name,))
    db.commit()
    db.audit("sso.provider.removed", f"Proveedor '{name}' eliminado")
    logger.info(f"SSO: Proveedor '{name}' eliminado ({len(sessions)} sesiones invalidadas)")
    return {"status": "ok"}


def _validate_provider_config(provider_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Valida la configuración de un proveedor según su tipo."""
    if provider_type == "saml":
        for field in ["entity_id", "acs_url", "idp_sso_url", "idp_entity_id"]:
            if not config.get(field):
                return {"valid": False, "message": f"SAML requiere campo '{field}'"}
    elif provider_type == "oidc":
        for field in ["client_id", "client_secret", "authorization_url", "token_url"]:
            if not config.get(field):
                return {"valid": False, "message": f"OIDC requiere campo '{field}'"}
    elif provider_type == "keycloak":
        for field in ["client_id", "client_secret"]:
            if not config.get(field):
                return {"valid": False, "message": f"Keycloak requiere campo '{field}'"}
    return {"valid": True}
