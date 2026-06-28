"""
Zenic-Flijo API v2 — Autenticacion y Autorizacion
===================================================

Sistema de autenticacion y autorizacion para la API v2:
- APIKeyAuth: Valida X-API-Key contra la base de datos
- BearerTokenAuth: Valida tokens JWT/Bearer
- get_current_user: Retorna el usuario autenticado
- require_permission: Verifica permisos RBAC granulares
- get_tenant: Resuelve el tenant desde la solicitud
- Rate limiting por API key usando RedisService

Integra con el sistema RBAC existente en src.security.rbac.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from src.core.repositories import AuditRepository
from src.core.db import DatabaseManager
from src.core.db import RedisService
from src.core.repositories import SettingsRepository
from src.core.repositories import UserRepository
from src.core.security.rbac import RBACManager
from src.tenant.service import TenantService
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# ── Constantes ─────────────────────────────────────────────────

_API_KEY_PREFIX = "zf_"
_JWT_SECRET_ENV = "WFD_API_V2_JWT_SECRET"
# Mínimo de caracteres para considerar el secreto aceptable.
# 64 chars base64 ≈ 384 bits de entropía (suficiente para HMAC-SHA256).
_JWT_SECRET_MIN_LEN = 64
_RATE_LIMIT_WINDOW = 60  # segundos
_RATE_LIMIT_MAX_REQUESTS = 100  # requests por ventana

# ── Security Schemes ───────────────────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


# ── Token Helpers ──────────────────────────────────────────────

# Cache del secret en modo dev para que generate_token/validate_token usen
# el mismo valor dentro de una sesión. En producción el secret viene de env
# var y el cache es estable.
_CACHED_DEV_SECRET: str | None = None


def _get_jwt_secret() -> str:
    """Obtiene el secreto JWT desde la variable de entorno.

    CRÍTICO: No hay default. La app DEBE configurar WFD_API_V2_JWT_SECRET
    con un valor aleatorio de al menos 64 caracteres. En producción, si no
    está configurado o es demasiado corto, se lanza RuntimeError para evitar
    arrancar con un secreto débil o inexistente (que permitiría a cualquier
    atacante con acceso al código forjar tokens JWT).

    En desarrollo (WFD_PRODUCTION != "true"), si no está configurado se
    genera uno aleatorio por sesión (cacheado para que generate_token y
    validate_token usen el mismo valor) y se emite un warning.
    """
    global _CACHED_DEV_SECRET

    secret = os.environ.get(_JWT_SECRET_ENV, "")
    production = os.environ.get("WFD_PRODUCTION", "false").lower() == "true"

    if secret and len(secret) >= _JWT_SECRET_MIN_LEN:
        # Secret válido configurado vía env var — usarlo siempre (sin cachear
        # porque podría cambiar en runtime en tests).
        return secret

    if production:
        raise RuntimeError(
            "SEGURIDAD CRÍTICA: WFD_API_V2_JWT_SECRET no configurado o demasiado corto "
            f"(mínimo {_JWT_SECRET_MIN_LEN} caracteres). Genere uno nuevo con, por ejemplo:  "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"  "
            "y configúrelo en su entorno antes de desplegar."
        )

    # Modo desarrollo: usar el secret cacheado si existe (estabilidad
    # dentro de la sesión). Si no, generar uno nuevo y cachearlo.
    if _CACHED_DEV_SECRET is not None:
        return _CACHED_DEV_SECRET

    if not secret:
        import secrets as _secrets
        import warnings
        _CACHED_DEV_SECRET = _secrets.token_urlsafe(48)
        warnings.warn(
            "WFD_API_V2_JWT_SECRET no configurado. Se generó un secreto aleatorio "
            "efímero para esta sesión. NO use esto en producción. Configure la "
            "variable de entorno WFD_API_V2_JWT_SECRET con un valor aleatorio de "
            f"al menos {_JWT_SECRET_MIN_LEN} caracteres.",
            stacklevel=2,
        )
        return _CACHED_DEV_SECRET

    # Secret configurado pero demasiado corto — advertir pero permitir en dev.
    import warnings
    warnings.warn(
        f"WFD_API_V2_JWT_SECRET tiene {len(secret)} caracteres; se recomiendan "
        f"al menos {_JWT_SECRET_MIN_LEN}. Considere rotarlo por uno más largo.",
        stacklevel=2,
    )
    return secret


def generate_token(payload: dict[str, Any], expires_in: int = 3600) -> str:
    """Genera un token JWT simplificado ( HMAC-based ).

    Args:
        payload: Datos a incluir en el token
        expires_in: Tiempo de vida en segundos (default: 1 hora)

    Returns:
        Token como string codificado en base64
    """
    import base64

    token_data = {
        "payload": payload,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
        "jti": str(uuid.uuid4()),
    }
    token_json = json.dumps(token_data, sort_keys=True, default=str)
    token_b64 = base64.urlsafe_b64encode(token_json.encode()).decode()

    # Firma HMAC-SHA256
    signature = hmac.new(_get_jwt_secret().encode(), token_b64.encode(), hashlib.sha256).hexdigest()

    return f"{token_b64}.{signature}"


def validate_token(token: str) -> dict[str, Any] | None:
    """Valida un token JWT simplificado (HMAC-based).

    Args:
        token: Token a validar

    Returns:
        Payload del token si es valido, None si es invalido o expirado
    """
    import base64

    parts = token.split(".")
    if len(parts) != 2:
        return None

    token_b64, signature = parts

    # Verificar firma
    expected_sig = hmac.new(_get_jwt_secret().encode(), token_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return None

    try:
        token_json = base64.urlsafe_b64decode(token_b64.encode()).decode()
        token_data = json.loads(token_json)
    except (ValueError, json.JSONDecodeError):
        return None

    # Verificar expiracion
    if token_data.get("exp", 0) < int(time.time()):
        return None

    return token_data.get("payload")


# ── API Key Authentication ─────────────────────────────────────


class APIKeyAuth:
    """Dependencia que valida la API key del header X-API-Key."""

    def __init__(self) -> None:
        self._db = DatabaseManager()
        self._redis = RedisService()
        self._users = UserRepository(self._db)
        self._settings = SettingsRepository(self._db)
        self._audit = AuditRepository(self._db)

    async def __call__(self, request: Request, api_key: str = Security(api_key_header)) -> dict[str, Any]:
        """Valida la API key contra la base de datos y aplica rate limiting.

        Args:
            request: Solicitud HTTP
            api_key: API key del header X-API-Key

        Returns:
            Dict con datos de la API key validada

        Raises:
            HTTPException: Si la API key es invalida, expirada o rate limited
        """
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key requerida. Envie el header X-API-Key.",
            )

        # Verificar formato
        if not api_key.startswith(_API_KEY_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Formato de API key invalido.",
            )

        # Buscar en cache Redis primero
        cache_key = f"api_key:{api_key[:8]}:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"
        cached = self._redis.get_json(cache_key)
        if cached:
            # Verificar expiracion desde cache
            if cached.get("expires_at") and time.time() > cached["expires_at"]:
                self._redis.delete(cache_key)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key expirada.",
                )
            self._check_rate_limit(api_key, cached)
            return cached

        # Buscar en base de datos
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = self._db.fetchone("SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1", (key_hash,))

        if not key_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key invalida o revocada.",
            )

        # Verificar expiracion
        if key_data.get("expires_at"):
            from datetime import datetime

            try:
                exp = datetime.fromisoformat(str(key_data["expires_at"]))
                if exp.timestamp() < time.time():
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API key expirada.",
                    )
            except (ValueError, TypeError):
                pass

        # Construir datos de la API key
        key_info = {
            "id": key_data["id"],
            "name": key_data.get("name", ""),
            "user_id": key_data.get("user_id"),
            "tenant_id": key_data.get("tenant_id"),
            "scopes": json.loads(key_data.get("scopes", "[]")),
            "expires_at": None,
        }
        if key_data.get("expires_at"):
            try:
                from datetime import datetime

                key_info["expires_at"] = datetime.fromisoformat(str(key_data["expires_at"])).timestamp()
            except (ValueError, TypeError):
                pass

        # Cachear en Redis (5 minutos)
        self._redis.set_json(cache_key, key_info, ttl=300)

        # Actualizar last_used_at
        self._db.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (key_data["id"],))
        self._db.commit()

        # Rate limiting
        self._check_rate_limit(api_key, key_info)

        return key_info

    def _check_rate_limit(self, api_key: str, key_info: dict[str, Any]) -> None:
        """Verifica el rate limit para la API key.

        Args:
            api_key: API key completa (para el identificador de rate limit)
            key_info: Informacion de la API key

        Raises:
            HTTPException: Si se excede el rate limit
        """
        rate_key = f"api_v2:{api_key[:8]}"
        result = self._redis.check_rate_limit(rate_key, _RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW)
        if not result.get("allowed", True):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit excedido. Intentelo de nuevo en {_RATE_LIMIT_WINDOW} segundos.",
                headers={"Retry-After": str(result.get("reset_at", _RATE_LIMIT_WINDOW))},
            )


# ── Bearer Token Authentication ────────────────────────────────


class BearerTokenAuth:
    """Dependencia que valida tokens Bearer JWT."""

    async def __call__(
        self, credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
    ) -> dict[str, Any] | None:
        """Valida el token Bearer JWT.

        Args:
            credentials: Credenciales del header Authorization

        Returns:
            Payload del token si es valido

        Raises:
            HTTPException: Si el token es invalido o expirado
        """
        if not credentials:
            return None

        payload = validate_token(credentials.credentials)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalido o expirado.",
            )

        return payload


# ── Combined Auth Dependencies ─────────────────────────────────

_api_key_auth = APIKeyAuth()
_bearer_auth = BearerTokenAuth()


async def get_current_user(
    request: Request,
    api_key_info: dict[str, Any] | None = Depends(_api_key_auth.__call__),
    bearer_payload: dict[str, Any] | None = Depends(_bearer_auth.__call__),
) -> dict[str, Any]:
    """Obtiene el usuario autenticado desde API key o Bearer token.

    Intenta primero API key, luego Bearer token. Al menos uno debe ser valido.

    Args:
        request: Solicitud HTTP
        api_key_info: Datos de la API key (inyectado por APIKeyAuth)
        bearer_payload: Payload del Bearer token (inyectado por BearerTokenAuth)

    Returns:
        Dict con datos del usuario autenticado

    Raises:
        HTTPException: Si no se proporciona ninguna credencial valida
    """
    # Intentar API key primero
    if api_key_info and api_key_info.get("user_id"):
        users = UserRepository()
        user = users.get_user(api_key_info["user_id"])
        if user and user.get("is_active"):
            return {
                "user_id": user["id"],
                "username": user.get("username", ""),
                "role": user.get("role", "viewer"),
                "tenant_id": api_key_info.get("tenant_id"),
                "scopes": api_key_info.get("scopes", []),
                "auth_method": "api_key",
            }

    # Intentar Bearer token
    if bearer_payload:
        return {
            "user_id": bearer_payload.get("user_id", 0),
            "username": bearer_payload.get("username", ""),
            "role": bearer_payload.get("role", "viewer"),
            "tenant_id": bearer_payload.get("tenant_id"),
            "scopes": bearer_payload.get("scopes", []),
            "auth_method": "bearer",
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticacion requerida. Proporcione X-API-Key o Authorization: Bearer <token>.",
    )


async def get_optional_user(
    request: Request,
    api_key_info: dict[str, Any] | None = None,
    bearer_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Obtiene el usuario autenticado de forma opcional (no lanza error si no hay credenciales).

    Args:
        request: Solicitud HTTP
        api_key_info: Datos de la API key (opcional)
        bearer_payload: Payload del Bearer token (opcional)

    Returns:
        Dict con datos del usuario o None si no hay credenciales
    """
    try:
        return await get_current_user(request, api_key_info, bearer_payload)
    except HTTPException:
        return None


def require_permission(resource: str, action: str):
    """Crea una dependencia que verifica permisos RBAC granulares.

    Fix Sprint 5 BUG-ARCH-03: usa `has_permission` del módulo compartido
    `security.auth_shared` para evitar drift con Flask.

    Args:
        resource: Recurso a verificar (workflow, connector, tool, etc.)
        action: Accion a verificar (create, read, update, delete, execute, etc.)

    Returns:
        Dependencia FastAPI que verifica el permiso

    Usage:
        @router.post("/", dependencies=[Depends(require_permission("workflow", "create"))])
    """
    from src.core.security.auth_shared import has_permission

    async def _check_permission(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        """Verifica si el usuario tiene el permiso especificado.

        Args:
            user: Usuario autenticado (inyectado por get_current_user)

        Returns:
            Datos del usuario si tiene permiso

        Raises:
            HTTPException: Si el usuario no tiene el permiso requerido
        """
        user_id = user.get("user_id", 0)
        user_role = user.get("role", "viewer")
        scopes = set(user.get("scopes", []) or [])

        # Usar función compartida has_permission (fix BUG-ARCH-03)
        if has_permission(user_role, scopes, resource, action):
            return user

        # Fallback a RBACManager para permisos granulares en DB
        rbac = RBACManager()
        if rbac.check_permission(user_id, resource, action):
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permiso denegado: {resource}:{action}. "
            f"Contacte al administrador para obtener acceso.",
        )

    return _check_permission


async def get_tenant(request: Request, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any] | None:
    """Resuelve el tenant desde la solicitud y el usuario autenticado.

    Orden de resolucion:
    1. Header X-Tenant-ID (para API directa)
    2. Tenant ID del usuario autenticado (si viene de API key)
    3. Subdominio (tenant.zenic-flijo.com)
    4. Ningun tenant (modo sin multi-tenancy)

    Args:
        request: Solicitud HTTP
        user: Usuario autenticado

    Returns:
        Dict con datos del tenant o None

    Raises:
        HTTPException: Si el tenant especificado no existe o esta inactivo
    """
    tenant_service = TenantService()

    # 1. Header X-Tenant-ID
    tenant_id = request.headers.get("X-Tenant-ID", "")
    if tenant_id:
        tenant = tenant_service.get_tenant(tenant_id)
        if tenant and tenant.get("status") == "active":
            return tenant
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' no encontrado o inactivo.",
        )

    # 2. Tenant ID del usuario
    user_tenant_id = user.get("tenant_id")
    if user_tenant_id:
        tenant = tenant_service.get_tenant(user_tenant_id)
        if tenant and tenant.get("status") == "active":
            return tenant

    # 3. Sin tenant (modo sin multi-tenancy)
    return None
