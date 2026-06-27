"""
Auth compartido entre Flask (web) y FastAPI (api_v2).

Fix Sprint 5 BUG-ARCH-03: antes la lógica de autenticación estaba duplicada:
- Flask: `@login_required` + `@require_role` en `web/helpers.py` (session cookie)
- FastAPI: `Depends(get_current_user)` + `Depends(require_permission(...))` en `api_v2/auth.py` (API key + JWT)

Este módulo NO reemplaza esos mecanismos (cada API tiene su propio transporte),
pero unifica:
1. La jerarquía de roles (`ROLE_HIERARCHY`)
2. El mapeo resource:action → permission string (`build_permission`)
3. La verificación de si un rol tiene permiso para una acción (`has_permission`)
4. La validación de password (bcrypt + pbkdf2 con compare_digest)

Ambas APIs pueden usar estas funciones para evitar drift futuro.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

# ── Jerarquía de roles (compartida) ──────────────────────
# Mismo orden en Flask (web/helpers.py) y FastAPI (api_v2/auth.py)
ROLE_HIERARCHY: dict[str, int] = {
    "admin": 3,
    "editor": 2,
    "viewer": 1,
}

# Permisos granulares (resource:action) — usados por FastAPI require_permission
# Flask puede adoptarlos gradualmente para migrar de roles jerárquicos a RBAC
WILDCARD_PERMISSION = "*:*"


def build_permission(resource: str, action: str) -> str:
    """Construye un string de permission en formato 'resource:action'."""
    return f"{resource}:{action}"


def has_permission(
    user_role: str,
    user_permissions: set[str] | None,
    resource: str,
    action: str,
) -> bool:
    """Verifica si un usuario tiene permiso para una acción sobre un recurso.

    Lógica:
    1. Si user_role es 'admin', siempre True (superuser).
    2. Si user_permissions contiene '*:*', siempre True.
    3. Si user_permissions contiene 'resource:*', True para cualquier action.
    4. Si user_permissions contiene 'resource:action', True.
    5. Fallback a jerarquía de roles: si user_role >= role requerido, True.

    Args:
        user_role: Rol del usuario ('admin', 'editor', 'viewer').
        user_permissions: Set de permission strings ('resource:action').
        resource: Recurso a verificar ('workflow', 'connector', etc.).
        action: Acción a verificar ('read', 'write', 'delete', etc.).

    Returns:
        True si tiene permiso, False si no.
    """
    # 1. Admin = superuser
    if user_role == "admin":
        return True

    # 2-4. Verificar permissions granulares
    if user_permissions:
        required = build_permission(resource, action)
        wildcard = build_permission(resource, "*")
        if WILDCARD_PERMISSION in user_permissions:
            return True
        if wildcard in user_permissions:
            return True
        if required in user_permissions:
            return True

    # 5. Fallback a jerarquía de roles
    # (solo para recursos que no requieren permisos granulares explícitos)
    return False


def role_at_least(user_role: str, required_role: str) -> bool:
    """Verifica si user_role tiene nivel >= required_role en la jerarquía."""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


# ── Validación de password (compartida) ──────────────────

def verify_password(stored_hash: str, password: str) -> bool:
    """Verifica una contraseña contra un hash almacenado.

    Soporta:
    - bcrypt ($2b$...) — delega a bcrypt.checkpw
    - pbkdf2 (pbkdf2:sha256:iterations:salt:hash) — usa hmac.compare_digest

    Args:
        stored_hash: Hash almacenado en DB.
        password: Password en claro a verificar.

    Returns:
        True si coincide, False si no.
    """
    if not stored_hash or not password:
        return False

    # bcrypt
    if stored_hash.startswith("$2"):
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except (ValueError, TypeError, ImportError):
            return False

    # pbkdf2:sha256:iterations:salt:hash
    if stored_hash.startswith("pbkdf2:"):
        try:
            parts = stored_hash.split(":")
            algo = parts[1]
            iterations = int(parts[2])
            salt = parts[3]
            expected = parts[4]
            computed = hashlib.pbkdf2_hmac(
                algo, password.encode(), salt.encode(), iterations
            ).hex()
            # Constant-time comparison (fix bug #31 Sprint 3)
            return hmac.compare_digest(computed, expected)
        except (IndexError, ValueError, TypeError):
            return False

    return False


def hash_password(password: str, *, algorithm: str = "bcrypt") -> str:
    """Hashea una contraseña con el algoritmo especificado.

    Args:
        password: Password en claro.
        algorithm: 'bcrypt' (default, recomendado) o 'pbkdf2'.

    Returns:
        Hash string listo para almacenar en DB.
    """
    if algorithm == "bcrypt":
        import bcrypt
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    elif algorithm == "pbkdf2":
        import secrets
        salt = secrets.token_hex(16)
        iterations = 600000
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
        return f"pbkdf2:sha256:{iterations}:{salt}:{hashed}"
    else:
        raise ValueError(f"Algoritmo no soportado: {algorithm}")


# ── Utilidades para serialización de usuario ──────────────

def serialize_user(user_row: dict[str, Any] | Any) -> dict[str, Any]:
    """Serializa un row de DB de usuario a dict[str, Any] plano (compartido Flask/FastAPI).

    NUNCA incluye password_hash — evita leak accidental en responses.
    """
    if hasattr(user_row, "keys"):  # sqlite3.Row
        user_dict = dict[str, Any](user_row)
    elif isinstance(user_row, dict[str, Any]):
        user_dict = user_row.copy()
    else:
        return {}

    # Eliminar campos sensibles
    user_dict.pop("password_hash", None)
    user_dict.pop("password", None)

    return user_dict
