"""
Zenic-Flijo API v2 — Dependencias FastAPI Compartidas
======================================================

Dependencias reutilizables por todos los routers de la API v2:
- get_db: Sesion de base de datos (DatabaseManager)
- get_redis: Servicio de Redis (RedisService)
- get_workflow_engine: Motor de workflows (WorkflowEngine)
- get_nlu_pipeline: Pipeline NLU (Pipeline)
- get_connector_registry: Registro de conectores (ConnectorRegistry)
- get_tenant_service: Servicio de tenants (TenantService)
- get_pagination: Parametros de paginacion desde query params
- verify_tenant_ownership: Verifica que un usuario pertenece a un tenant
- require_tenant_access: Dependency que valida X-Tenant-ID contra user_tenants

Todas las dependencias usan singletons existentes del proyecto.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Query, Request, status

from src.api_v2.models import PaginationParams

# TYPE_CHECKING: imports solo para type checkers (mypy/pyright).
# No se ejecutan en runtime, evitando imports circulares.
if TYPE_CHECKING:
    from src.core.db import DatabaseManager
    from src.core.db import RedisService
    from src.core.observability.telemetry import TelemetryService
    from src.core.security.rbac import RBACManager
    from src.nlu.pipeline import Pipeline
    from src.sdk.registry import ConnectorRegistry
    from src.tenant.service import TenantService
    from src.workflow.engine import WorkflowEngine
    from src.workflow.repository import WorkflowRepository


async def get_db() -> DatabaseManager:
    """Obtiene la instancia singleton de DatabaseManager.

    Returns:
        DatabaseManager: Instancia de la base de datos SQLite
    """
    from src.core.db import DatabaseManager

    return DatabaseManager()


async def get_redis() -> RedisService:
    """Obtiene la instancia singleton de RedisService.

    Returns:
        RedisService: Instancia del servicio de Redis
    """
    from src.core.db import RedisService

    return RedisService()


async def get_workflow_engine() -> WorkflowEngine:
    """Obtiene la instancia singleton de WorkflowEngine.

    Returns:
        WorkflowEngine: Instancia del motor de workflows
    """
    from src.workflow.engine import WorkflowEngine

    return WorkflowEngine()


async def get_workflow_repository() -> WorkflowRepository:
    """Obtiene una nueva instancia de WorkflowRepository.

    Returns:
        WorkflowRepository: Instancia del repositorio de workflows
    """
    from src.workflow.repository import WorkflowRepository

    return WorkflowRepository()


async def get_nlu_pipeline() -> Pipeline:
    """Obtiene una nueva instancia del Pipeline NLU.

    Returns:
        Pipeline: Instancia del pipeline de procesamiento de lenguaje natural
    """
    from src.nlu.pipeline import Pipeline

    return Pipeline()


async def get_connector_registry() -> ConnectorRegistry:
    """Obtiene la instancia singleton de ConnectorRegistry.

    Returns:
        ConnectorRegistry: Instancia del registro de conectores
    """
    from src.sdk.registry import ConnectorRegistry

    return ConnectorRegistry()


async def get_tenant_service() -> TenantService:
    """Obtiene la instancia singleton de TenantService.

    Returns:
        TenantService: Instancia del servicio de multi-tenancy
    """
    from src.tenant.service import TenantService

    return TenantService()


async def get_rbac_manager() -> RBACManager:
    """Obtiene la instancia singleton de RBACManager.

    Returns:
        RBACManager: Instancia del gestor de RBAC granular
    """
    from src.core.security.rbac import RBACManager

    return RBACManager()


async def get_telemetry_service() -> TelemetryService:
    """Obtiene la instancia singleton de TelemetryService.

    Returns:
        TelemetryService: Instancia del servicio de telemetria
    """
    from src.core.observability.telemetry import TelemetryService

    return TelemetryService()


def get_pagination(
    page: int = Query(default=1, ge=1, description="Numero de pagina"),
    page_size: int = Query(default=20, ge=1, le=100, description="Elementos por pagina"),
) -> PaginationParams:
    """Extrae parametros de paginacion desde query params.

    Args:
        page: Numero de pagina (default: 1)
        page_size: Elementos por pagina (default: 20, max: 100)

    Returns:
        PaginationParams: Parametros de paginacion validados
    """
    return PaginationParams(page=page, page_size=page_size)


# ─── Bug TENANT-03: X-Tenant-ID bypass ─────────────────────────────────
# Cualquier usuario autenticado podia pasar X-Tenant-ID: <otro_tenant>
# en el header y acceder a datos ajenos sin verificacion de ownership.
# verify_tenant_ownership() valida contra la tabla user_tenants que el
# usuario pertenece al tenant solicitado. require_tenant_access() es la
# dependencia FastAPI que se usa en routers que acepten X-Tenant-ID.


def verify_tenant_ownership(user: dict[str, Any], tenant_id: str) -> bool:
    """Verifica que el usuario pertenece al tenant solicitado.

    Fuente de verdad: tabla ``user_tenants`` en SQLite (clave compuesta
    ``(user_id, tenant_id)``). Si el usuario no tiene asignado el tenant,
    retorna False y el caller debe denegar el acceso con 403.

    Args:
        user: Dict con al menos ``user_id`` (devuelto por get_current_user).
        tenant_id: ID del tenant que se quiere acceder (del header X-Tenant-ID).

    Returns:
        True si el usuario pertenece al tenant, False en caso contrario.
    """
    if not tenant_id:
        return False

    user_id = user.get("user_id") if isinstance(user, dict) else None
    if not user_id:
        return False

    # Lazy import para romper circular: sqlite_manager <-> repositorios.
    from src.core.db import DatabaseManager

    db = DatabaseManager()
    row = db.fetchone(
        "SELECT 1 AS ok FROM user_tenants WHERE user_id = ? AND tenant_id = ? LIMIT 1",
        (user_id, tenant_id),
    )
    return bool(row)


async def require_tenant_access(
    request: Request,
    user: dict[str, Any] = Depends(lambda: None),
) -> dict[str, Any]:
    """Dependencia FastAPI que valida el acceso del usuario al tenant del header.

    Lee ``X-Tenant-ID`` del header, valida que el usuario autenticado
    pertenezca a ese tenant (vía ``verify_tenant_ownership`` contra
    ``user_tenants``) y retorna el contexto con ``tenant_id`` validado.

    Debe combinarse con ``get_current_user`` para autenticar al usuario.
    Uso tipico::

        @router.get("/workflows")
        async def list_workflows(
            ctx: dict = Depends(require_tenant_access),
        ):
            tenant_id = ctx["tenant_id"]
            ...

    Args:
        request: Solicitud HTTP (para leer el header X-Tenant-ID).
        user: Usuario autenticado (Depends(get_current_user)).

    Returns:
        Dict con ``user`` y ``tenant_id`` validado.

    Raises:
        HTTPException 401: Si no hay usuario autenticado.
        HTTPException 400: Si falta el header X-Tenant-ID.
        HTTPException 403: Si el usuario no pertenece al tenant.
    """
    # Import diferido para evitar ciclo con auth.py (que importa dependencies).
    from src.api_v2.auth import get_current_user

    if user is None:
        user = await get_current_user(request, None, None)

    if not user or not user.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacion requerida para acceder a recursos de tenant.",
        )

    tenant_id = (request.headers.get("X-Tenant-ID") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header X-Tenant-ID requerido para este recurso.",
        )

    if not verify_tenant_ownership(user, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para acceder al tenant solicitado.",
        )

    return {"user": user, "tenant_id": tenant_id}


# ─── Re-exports de auth (BUG-ARCH-03) ────────────────────────────────────
# Algunos routers importan `require_permission` y `get_current_user` desde
# `dependencies`, otros desde `auth`. Para eliminar el drift y hacer ambos
# imports válidos, re-exportamos aquí los símbolos de auth.
# La fuente de verdad sigue siendo src/api_v2/auth.py.
# Esto resuelve el ImportError que impedía cargar api_v2.app.

from src.api_v2.auth import (
    generate_token,
    validate_token,
    get_current_user,
    get_optional_user,
    require_permission,
    get_tenant,
)

__all__ = [
    "generate_token",
    "get_connector_registry",
    "get_current_user",
    "get_db",
    "get_nlu_pipeline",
    "get_optional_user",
    "get_pagination",
    "get_rbac_manager",
    "get_redis",
    "get_telemetry_service",
    "get_tenant",
    "get_tenant_service",
    "get_workflow_engine",
    "get_workflow_repository",
    # Bug TENANT-03 — X-Tenant-ID bypass
    "require_permission",
    "require_tenant_access",
    "validate_token",
    "verify_tenant_ownership",
]
