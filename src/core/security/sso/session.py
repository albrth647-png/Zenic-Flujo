"""
SSO — Session Manager: creacion, validacion, cierre y limpieza de sesiones SSO.
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from datetime import datetime
from typing import Any

from src.core.db.redis_service import RedisService
from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.security.sso.constants import SSO_SESSION_PREFIX, SSO_SESSION_TTL

logger = setup_logging(__name__)


def create_sso_session(db: DatabaseManager, redis: RedisService, provider_name: str, user_id: int,
                       idp_session: str | None = None) -> dict[str, Any]:
    """Crea una sesion SSO en la base de datos y Redis."""
    session_id = str(uuid.uuid4())
    expires_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + SSO_SESSION_TTL))

    db.execute(
        "INSERT INTO sso_sessions (session_id, provider, user_id, idp_session, expires_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, provider_name, user_id, idp_session, expires_at),
    )
    db.commit()

    redis.set_json(
        f"{SSO_SESSION_PREFIX}{session_id}",
        {"provider": provider_name, "user_id": user_id, "idp_session": idp_session},
        ttl=SSO_SESSION_TTL,
    )

    return {"session_id": session_id, "expires_at": expires_at}


def validate_sso_session(db: DatabaseManager, redis: RedisService, session_id: str) -> dict[str, Any] | None:
    """Valida una sesion SSO y retorna la informacion del usuario."""
    cached = redis.get_json(f"{SSO_SESSION_PREFIX}{session_id}")
    if cached:
        return cached

    session_data = db.fetchone(
        "SELECT session_id, provider, user_id, idp_session, expires_at FROM sso_sessions WHERE session_id = ?",
        (session_id,),
    )
    if not session_data:
        return None

    try:
        expires = datetime.fromisoformat(session_data["expires_at"])
        if datetime.now(expires.tzinfo if expires.tzinfo else None) >= expires:
            logout_session(db, redis, session_id)
            return None
    except (ValueError, TypeError):
        pass

    result = {
        "provider": session_data["provider"],
        "user_id": session_data["user_id"],
        "idp_session": session_data.get("idp_session"),
    }
    redis.set_json(f"{SSO_SESSION_PREFIX}{session_id}", result, ttl=SSO_SESSION_TTL)
    return result


def logout_session(db: DatabaseManager, redis: RedisService, session_id: str) -> dict[str, Any]:
    """Invalida una sesion SSO."""
    session_data = redis.get_json(f"{SSO_SESSION_PREFIX}{session_id}")
    redis.delete(f"{SSO_SESSION_PREFIX}{session_id}")
    db.execute("DELETE FROM sso_sessions WHERE session_id = ?", (session_id,))
    db.commit()

    if session_data:
        db.audit("sso.logout", f"Sesion SSO cerrada para usuario {session_data.get('user_id')}",
                 user_id=session_data.get("user_id"))

    logger.info(f"SSO: Sesion {session_id[:8]}... cerrada")
    return {"status": "ok"}


def cleanup_expired_sessions(db: DatabaseManager, redis: RedisService) -> int:
    """Elimina sesiones SSO expiradas de la base de datos."""
    result = db.execute("DELETE FROM sso_sessions WHERE expires_at < datetime('now')")
    db.commit()
    count = result.rowcount
    if count > 0:
        logger.info(f"SSO: {count} sesiones expiradas eliminadas")
    return count


# ── User mapping ─────────────────────────────────────────────

def create_or_link_user(db: DatabaseManager, provider_name: str, external_id: str, user_info: dict[str, Any]) -> dict:
    """Crea un usuario local o vincula un usuario IdP existente."""
    existing_mapping = db.fetchone(
        "SELECT user_id FROM sso_user_mapping WHERE provider_name = ? AND external_id = ?",
        (provider_name, external_id),
    )
    if existing_mapping:
        db.execute(
            "UPDATE sso_user_mapping SET external_attrs = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE provider_name = ? AND external_id = ?",
            (json.dumps(user_info, default=str, ensure_ascii=False), provider_name, external_id),
        )
        db.commit()
        return {"status": "ok", "user_id": existing_mapping["user_id"], "linked": True}

    email = user_info.get("email", "")
    email_verified = user_info.get("email_verified", False)
    local_user_id: int | None = None

    # Fix Sprint 2 bug #20: NO auto-linkar por email sin verificar email_verified.
    # Si un IdP malicioso se configura y retorna el email de una víctima sin
    # verificarlo, el atacante podría tomar control de la cuenta víctima.
    # Solo auto-link si el IdP afirma explícitamente que el email está verificado.
    if email and email_verified:
        existing_user = db.fetchone("SELECT id FROM users WHERE email = ? AND is_active = 1", (email,))
        if existing_user:
            local_user_id = existing_user["id"]
            logger.info(
                f"SSO: Auto-vinculando usuario IdP {external_id} a usuario local "
                f"existente por email verificado"
            )
    elif email and not email_verified:
        # Email presente pero NO verificado por el IdP: NO auto-linkar.
        # Se creará un usuario nuevo (más abajo) en vez de vincular a uno existente.
        logger.warning(
            f"SSO: IdP {provider_name} retornó email {email} sin email_verified=True "
            f"— NO se auto-vinculará a usuario existente (prevención de account takeover)"
        )

    if local_user_id is None:
        username = (
            user_info.get("username") or user_info.get("preferred_username") or email.split("@")[0]
            if email else f"sso_{uuid.uuid4().hex[:8]}"
        )
        display_name = user_info.get("display_name") or user_info.get("name") or username

        existing_username = db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
        if existing_username:
            username = f"{username}_{uuid.uuid4().hex[:4]}"

        import bcrypt
        random_password = secrets.token_urlsafe(32)
        hashed = bcrypt.hashpw(random_password.encode(), bcrypt.gensalt(rounds=12)).decode()

        cursor = db.execute(
            "INSERT INTO users (username, password_hash, role, display_name, email, is_active) "
            "VALUES (?, ?, 'editor', ?, ?, 1)",
            (username, hashed, display_name, email),
        )
        db.commit()
        local_user_id = cursor.lastrowid
        logger.info(f"SSO: Nuevo usuario creado via SSO: {username} (id={local_user_id})")

    db.execute(
        "INSERT INTO sso_user_mapping (provider_name, external_id, user_id, external_attrs) VALUES (?, ?, ?, ?)",
        (provider_name, external_id, local_user_id, json.dumps(user_info, default=str, ensure_ascii=False)),
    )
    db.commit()

    return {"status": "ok", "user_id": local_user_id, "linked": False}


def link_existing_user(db: DatabaseManager, user_id: int, provider_name: str, external_id: str) -> dict[str, Any]:
    """Vincula manualmente un usuario local con una cuenta IdP."""
    existing_user = db.fetchone("SELECT id FROM users WHERE id = ? AND is_active = 1", (user_id,))
    if not existing_user:
        return {"status": "error", "message": f"Usuario {user_id} no encontrado"}

    existing_mapping = db.fetchone(
        "SELECT id FROM sso_user_mapping WHERE provider_name = ? AND external_id = ?",
        (provider_name, external_id),
    )
    if existing_mapping:
        return {"status": "error", "message": "Este usuario IdP ya esta vinculado a otra cuenta"}

    db.execute(
        "INSERT INTO sso_user_mapping (provider_name, external_id, user_id) VALUES (?, ?, ?)",
        (provider_name, external_id, user_id),
    )
    db.commit()

    db.audit("sso.user.linked", f"Usuario {user_id} vinculado con {provider_name}/{external_id}", user_id=user_id)
    return {"status": "ok"}
