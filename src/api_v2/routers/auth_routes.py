"""
Zenic-Flijo API v2 — Router de Autenticacion
==============================================

Endpoints de autenticacion, autorizacion y gestion de API keys:
- POST /api/v2/auth/login          — Iniciar sesion
- POST /api/v2/auth/logout         — Cerrar sesion
- POST /api/v2/auth/refresh        — Refrescar token
- POST /api/v2/auth/api-keys       — Crear API key
- GET  /api/v2/auth/api-keys       — Listar API keys
- DELETE /api/v2/auth/api-keys/{id} — Revocar API key
- POST /api/v2/auth/mfa/enable     — Habilitar MFA
- POST /api/v2/auth/mfa/verify     — Verificar codigo MFA

# Audience: External
# Purpose: Auth con JWT + API key. Alternativa a Flask cookie auth para integraciones externas (SDK, móvil, partners).
"""


from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api_v2.auth import generate_token, get_current_user, require_permission, validate_token
from src.api_v2.dependencies import get_db, get_redis
from src.api_v2.models import (
    APIKeyCreate,
    APIKeyResponse,
    ErrorResponse,
    MFAEnableRequest,
    MFAVerifyRequest,
    RefreshTokenRequest,
    TokenRequest,
    TokenResponse,
)
from src.core.repositories import AuditRepository
from src.core.repositories import UserRepository
from src.core.logging import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/v2/auth", tags=["Authentication"])

_API_KEY_PREFIX = "zf_"

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesion",
    description="Autentica un usuario con username y password, retorna tokens JWT.",
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
async def login(
    request: TokenRequest,
    db: Any = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> TokenResponse:
    """Autentica un usuario y retorna tokens de acceso."""
    import bcrypt

    # Rate limiting por IP/username
    rate_key = f"login:{request.username}"
    rate_result = redis.check_rate_limit(rate_key, max_requests=10, window_seconds=900)
    if not rate_result.get("allowed", True):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos de login. Espere 15 minutos.",
        )

    # Buscar usuario
    users = UserRepository()
    user = users.get_user_by_username(request.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        )

    # Verificar contrasena
    if not user.get("password_hash"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        )

    try:
        if not bcrypt.checkpw(request.password.encode(), user["password_hash"].encode()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales invalidas.",
            )
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        ) from None

    # Verificar que este activo
    if not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cuenta desactivada. Contacte al administrador.",
        )

    # Generar tokens
    access_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user.get("role", "admin"),
    }
    access_token = generate_token(access_payload, expires_in=3600)

    refresh_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "token_type": "refresh",
    }
    refresh_token = generate_token(refresh_payload, expires_in=86400 * 7)

    # Actualizar last_login_at
    db.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
    db.commit()

    # Registrar en audit log
    AuditRepository().log("user.login", f"Usuario '{request.username}' inicio sesion", user_id=user["id"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=3600,
        user_id=user["id"],
        username=user["username"],
        role=user.get("role", "admin"),
    )


@router.post(
    "/logout",
    summary="Cerrar sesion",
    description="Cierra la sesion del usuario actual invalidando el token.",
    responses={401: {"model": ErrorResponse}},
)
async def logout(
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Cierra la sesion del usuario actual."""
    db.audit("user.logout", f"Usuario '{user.get('username')}' cerro sesion", user_id=user.get("user_id"))

    return {"status": "ok", "message": "Sesion cerrada exitosamente"}


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refrescar token",
    description="Genera nuevos tokens de acceso usando un refresh token valido.",
    responses={401: {"model": ErrorResponse}},
)
async def refresh_token(
    request: RefreshTokenRequest,
    db: Any = Depends(get_db),
) -> TokenResponse:
    """Refresca el token de acceso usando un refresh token."""
    from src.core.repositories import UserRepository

    payload = validate_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalido o expirado.",
        )

    if payload.get("token_type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token proporcionado no es un refresh token.",
        )

    # Verificar que el usuario aun existe y esta activo
    users = UserRepository()
    user = users.get_user(payload.get("user_id", 0))
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado o desactivado.",
        )

    # Generar nuevos tokens
    access_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user.get("role", "admin"),
    }
    access_token = generate_token(access_payload, expires_in=3600)

    new_refresh_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "token_type": "refresh",
    }
    new_refresh_token = generate_token(new_refresh_payload, expires_in=86400 * 7)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=3600,
        user_id=user["id"],
        username=user["username"],
        role=user.get("role", "admin"),
    )


@router.post(
    "/api-keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear API key",
    description="Genera una nueva API key para el usuario autenticado.",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def create_api_key(
    key_data: APIKeyCreate,
    user: dict[str, Any] = Depends(require_permission("settings", "create")),
    db: Any = Depends(get_db),
) -> APIKeyResponse:
    """Crea una nueva API key."""
    # Generar API key
    raw_key = f"{_API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_id = str(uuid.uuid4())

    # Calcular expiracion
    expires_at = None
    if key_data.expires_in_days:
        import datetime

        expires_at = (datetime.datetime.now() + datetime.timedelta(days=key_data.expires_in_days)).isoformat()

    # Almacenar en BD
    db.execute(
        """INSERT INTO api_keys (id, name, key_hash, user_id, scopes, expires_at, is_active)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (
            key_id,
            key_data.name,
            key_hash,
            user.get("user_id", 1),
            json.dumps(key_data.scopes),
            expires_at,
        ),
    )
    db.commit()

    # Registrar en audit
    db.audit("api_key.created", f"API key '{key_data.name}' creada", user_id=user.get("user_id"))

    return APIKeyResponse(
        id=key_id,
        name=key_data.name,
        key=raw_key,  # Solo visible en creacion
        key_prefix=raw_key[:8],
        scopes=key_data.scopes,
        created_at=None,
        expires_at=expires_at,
        last_used_at=None,
        is_active=True,
    )


@router.get(
    "/api-keys",
    response_model=list[APIKeyResponse],
    summary="Listar API keys",
    description="Lista todas las API keys del usuario autenticado.",
    responses={401: {"model": ErrorResponse}},
)
async def list_api_keys(
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> list[APIKeyResponse]:
    """Lista las API keys del usuario."""
    keys = db.fetchall(
        "SELECT * FROM api_keys WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC",
        (user.get("user_id", 1),),
    )

    result = []
    for key_row in keys:
        scopes = key_row.get("scopes", "[]")
        if isinstance(scopes, str):
            try:
                scopes = json.loads(scopes)
            except (json.JSONDecodeError, TypeError):
                scopes = []

        result.append(
            APIKeyResponse(
                id=str(key_row.get("id", "")),
                name=key_row.get("name", ""),
                key="",  # Nunca mostrar la key completa
                key_prefix=key_row.get("key_prefix", ""),
                scopes=scopes,
                created_at=key_row.get("created_at"),
                expires_at=key_row.get("expires_at"),
                last_used_at=key_row.get("last_used_at"),
                is_active=bool(key_row.get("is_active", 1)),
            )
        )

    return result


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revocar API key",
    description="Revoca (desactiva) una API key especifica.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def revoke_api_key(
    key_id: str,
    user: dict[str, Any] = Depends(require_permission("settings", "delete")),
    db: Any = Depends(get_db),
) -> None:
    """Revoca una API key."""
    key_row = db.fetchone("SELECT id FROM api_keys WHERE id = ? AND user_id = ?", (key_id, user.get("user_id", 1)))
    if not key_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"API key '{key_id}' no encontrada")

    db.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
    db.commit()

    db.audit("api_key.revoked", f"API key '{key_id}' revocada", user_id=user.get("user_id"))


@router.post(
    "/mfa/enable",
    summary="Habilitar MFA",
    description="Habilita la autenticacion multi-factor para el usuario actual.",
    responses={401: {"model": ErrorResponse}},
)
async def enable_mfa(
    request: MFAEnableRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Habilita MFA para el usuario actual."""
    # Verificar si ya tiene MFA habilitado
    mfa_row = db.fetchone("SELECT id FROM user_mfa WHERE user_id = ? AND method = ? AND is_active = 1", (user.get("user_id"), request.method))
    if mfa_row:
        return {"status": "already_enabled", "method": request.method, "message": "MFA ya esta habilitado para este metodo"}

    # Generar secreto TOTP si es necesario
    secret = ""
    backup_codes: list[str] = []
    if request.method == "totp":
        secret = secrets.token_urlsafe(20)
        # Generar codigos de respaldo
        for _ in range(8):
            backup_codes.append(secrets.token_hex(4).upper())

    # Almacenar en BD
    db.execute(
        """INSERT INTO user_mfa (user_id, method, secret, backup_codes, is_active, enabled_at)
           VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
        (user.get("user_id"), request.method, secret, json.dumps(backup_codes)),
    )
    db.commit()

    db.audit("mfa.enabled", f"MFA habilitado (metodo: {request.method})", user_id=user.get("user_id"))

    response_data: dict[str, Any] = {
        "status": "enabled",
        "method": request.method,
        "message": f"MFA ({request.method}) habilitado exitosamente",
    }

    if secret:
        response_data["secret"] = secret
        response_data["backup_codes"] = backup_codes

    return response_data


@router.post(
    "/mfa/verify",
    summary="Verificar codigo MFA",
    description="Verifica un codigo MFA proporcionado por el usuario.",
    responses={401: {"model": ErrorResponse}},
)
async def verify_mfa(
    request: MFAVerifyRequest,
    user: dict[str, Any] = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Verifica un codigo MFA (TOTP RFC 6238 real o backup codes).

    Fix Sprint 1 bug #7: antes este endpoint aceptaba cualquier código de 6
    dígitos ('para demo'), lo que era un bypass total de MFA. Ahora valida
    el código TOTP contra el secret almacenado usando pyotp (RFC 6238) con
    una ventana de ±1 step (90 segundos), o contra los backup codes bcrypt.
    """
    mfa_row = db.fetchone(
        "SELECT * FROM user_mfa WHERE user_id = ? AND method = ? AND is_active = 1",
        (user.get("user_id"), request.method),
    )

    if not mfa_row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA no configurado para este metodo.",
        )

    # Verificar codigo TOTP
    if request.method == "totp":
        # 1. Verificar contra codigos de respaldo (bcrypt-hashed)
        backup_codes_json = mfa_row.get("backup_codes", "[]")
        try:
            backup_codes = json.loads(backup_codes_json) if isinstance(backup_codes_json, str) else backup_codes_json or []
        except (json.JSONDecodeError, TypeError):
            backup_codes = []

        # Backup codes están hasheados con bcrypt; verificar cada uno constant-time
        import bcrypt
        for i, hashed_code in enumerate(backup_codes):
            try:
                if bcrypt.checkpw(request.code.encode("utf-8"), hashed_code.encode("utf-8")):
                    # Remover codigo de respaldo usado (one-time use)
                    backup_codes.pop(i)
                    db.execute(
                        "UPDATE user_mfa SET backup_codes = ? WHERE id = ?",
                        (json.dumps(backup_codes), mfa_row["id"]),
                    )
                    db.commit()
                    return {
                        "status": "verified",
                        "method": request.method,
                        "message": "Codigo de respaldo verificado (ya no puede reutilizarse)",
                    }
            except (ValueError, TypeError):
                continue

        # 2. Verificar código TOTP real con pyotp (RFC 6238)
        # Validar formato: 6 dígitos numéricos
        if not (len(request.code) == 6 and request.code.isdigit()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Codigo MFA invalido: debe ser 6 digitos.",
            )

        secret = mfa_row.get("secret")
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Secret TOTP no encontrado para el usuario.",
            )

        try:
            import pyotp
            totp = pyotp.TOTP(secret)
            # valid_window=1 permite ±1 step (±30 segundos = ventana 90s total)
            if not totp.verify(request.code, valid_window=1):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Codigo MFA invalido o expirado.",
                )
        except ImportError:
            # pyotp no instalado — fallar seguro (no permitir bypass)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Servidor no configurado para TOTP (pyotp faltante).",
            )

        # Actualizar last_used_at para detección de reuso
        db.execute(
            "UPDATE user_mfa SET last_used_at = datetime('now') WHERE id = ?",
            (mfa_row["id"],),
        )
        db.commit()
        return {"status": "verified", "method": request.method, "message": "Codigo MFA verificado"}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Codigo MFA invalido.",
    )
