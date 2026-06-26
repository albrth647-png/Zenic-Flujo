"""
Zenic-Flijo API v2 — Router de Tenants
========================================

Endpoints de administracion de multi-tenancy:
- POST   /api/v2/tenants                          — Crear tenant
- GET    /api/v2/tenants/{id}                     — Obtener tenant
- PUT    /api/v2/tenants/{id}                     — Actualizar tenant
- DELETE /api/v2/tenants/{id}                     — Eliminar tenant
- POST   /api/v2/tenants/{id}/suspend             — Suspender tenant
- POST   /api/v2/tenants/{id}/activate            — Activar tenant
- GET    /api/v2/tenants/{id}/users               — Listar usuarios
- POST   /api/v2/tenants/{id}/users               — Agregar usuario
- GET    /api/v2/tenants/{id}/features            — Listar features
- PUT    /api/v2/tenants/{id}/features/{feature}  — Toggle feature

# Audience: External
# Purpose: Multi-tenancy management. API para gestionar tenants, users, roles, permissions.
"""


from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api_v2.auth import require_permission
from src.api_v2.dependencies import get_db, get_tenant_service
from src.core.repositories import UserRepository
from src.api_v2.models import (
    ErrorResponse,
    TenantCreate,
    TenantFeatureToggle,
    TenantResponse,
    TenantUpdate,
    TenantUserCreate,
    TenantUserResponse,
)
from src.core.logging import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/v2/tenants", tags=["Tenants"])


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear tenant",
    description="Crea un nuevo tenant con aprovisionamiento automatico de almacenamiento.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def create_tenant(
    tenant_data: TenantCreate,
    user: dict[str, Any] = Depends(require_permission("settings", "create")),
    tenant_service: Any = Depends(get_tenant_service),
) -> TenantResponse:
    """Crea un nuevo tenant."""
    result = tenant_service.create_tenant(
        name=tenant_data.name,
        slug=tenant_data.slug,
        plan=tenant_data.plan,
        config=tenant_data.config,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error creando tenant"))

    # Obtener datos completos del tenant recien creado
    tenant = tenant_service.get_tenant(result["tenant_id"])
    if not tenant:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Tenant creado pero no encontrado")

    return TenantResponse(**tenant)


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Obtener tenant",
    description="Obtiene la informacion completa de un tenant por su ID.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_tenant(
    tenant_id: str,
    user: dict[str, Any] = Depends(require_permission("settings", "read")),
    tenant_service: Any = Depends(get_tenant_service),
) -> TenantResponse:
    """Obtiene un tenant por su ID."""
    tenant = tenant_service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    return TenantResponse(**tenant)


@router.put(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Actualizar tenant",
    description="Actualiza los datos de un tenant existente.",
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_tenant(
    tenant_id: str,
    tenant_data: TenantUpdate,
    user: dict[str, Any] = Depends(require_permission("settings", "update")),
    tenant_service: Any = Depends(get_tenant_service),
) -> TenantResponse:
    """Actualiza un tenant existente."""
    # Verificar que existe
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    updates = tenant_data.model_dump(exclude_none=True)
    if not updates:
        return TenantResponse(**existing)

    result = tenant_service.update_tenant(tenant_id, updates)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error actualizando tenant"))

    # Obtener datos actualizados
    updated = tenant_service.get_tenant(tenant_id)
    return TenantResponse(**(updated or existing))


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar tenant",
    description="Elimina un tenant y todos sus datos asociados. Operacion irreversible.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_tenant(
    tenant_id: str,
    user: dict[str, Any] = Depends(require_permission("settings", "delete")),
    tenant_service: Any = Depends(get_tenant_service),
) -> None:
    """Elimina un tenant y todos sus datos."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    result = tenant_service.delete_tenant(tenant_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error eliminando tenant"))


@router.post(
    "/{tenant_id}/suspend",
    summary="Suspender tenant",
    description="Suspende un tenant activo. Se conservan los datos pero no se puede acceder.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def suspend_tenant(
    tenant_id: str,
    user: dict[str, Any] = Depends(require_permission("settings", "update")),
    tenant_service: Any = Depends(get_tenant_service),
) -> dict[str, Any]:
    """Suspende un tenant activo."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    result = tenant_service.suspend_tenant(tenant_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error suspendiendo tenant"))

    return {"status": "suspended", "tenant_id": tenant_id}


@router.post(
    "/{tenant_id}/activate",
    summary="Activar tenant",
    description="Reactiva un tenant suspendido.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def activate_tenant(
    tenant_id: str,
    user: dict[str, Any] = Depends(require_permission("settings", "update")),
    tenant_service: Any = Depends(get_tenant_service),
) -> dict[str, Any]:
    """Reactiva un tenant suspendido."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    result = tenant_service.activate_tenant(tenant_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error activando tenant"))

    return {"status": "active", "tenant_id": tenant_id}


@router.get(
    "/{tenant_id}/users",
    response_model=list[TenantUserResponse],
    summary="Listar usuarios de tenant",
    description="Lista los usuarios asociados a un tenant.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def list_tenant_users(
    tenant_id: str,
    user: dict[str, Any] = Depends(require_permission("user", "read")),
    tenant_service: Any = Depends(get_tenant_service),
    db: Any = Depends(get_db),
) -> list[TenantUserResponse]:
    """Lista los usuarios de un tenant."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    # Listar usuarios del tenant (usando BD del tenant)
    users_repo = UserRepository()
    users = users_repo.list_users()

    return [
        TenantUserResponse(
            id=u["id"],
            username=u.get("username", ""),
            role=u.get("role", "admin"),
            display_name=u.get("display_name", ""),
            email=u.get("email", ""),
            is_active=u.get("is_active", 1),
            created_at=u.get("created_at"),
        )
        for u in users
    ]


@router.post(
    "/{tenant_id}/users",
    response_model=TenantUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar usuario a tenant",
    description="Crea un nuevo usuario y lo asocia al tenant.",
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def add_tenant_user(
    tenant_id: str,
    user_data: TenantUserCreate,
    user: dict[str, Any] = Depends(require_permission("user", "create")),
    tenant_service: Any = Depends(get_tenant_service),
    db: Any = Depends(get_db),
) -> TenantUserResponse:
    """Crea un nuevo usuario y lo asocia al tenant."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    try:
        users_repo = UserRepository()
        created_user = users_repo.create_user(
            username=user_data.username,
            password=user_data.password,
            role=user_data.role,
            display_name=user_data.display_name,
            email=user_data.email,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error creando usuario: {e}") from e

    return TenantUserResponse(
        id=created_user["id"],
        username=created_user.get("username", ""),
        role=created_user.get("role", "admin"),
        display_name=created_user.get("display_name", ""),
        email=created_user.get("email", ""),
        is_active=created_user.get("is_active", 1),
        created_at=created_user.get("created_at"),
    )


@router.get(
    "/{tenant_id}/features",
    summary="Listar features de tenant",
    description="Lista las features (feature flags) de un tenant.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def list_tenant_features(
    tenant_id: str,
    user: dict[str, Any] = Depends(require_permission("settings", "read")),
    tenant_service: Any = Depends(get_tenant_service),
) -> dict[str, Any]:
    """Lista las features de un tenant."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    features = existing.get("features", {})

    return {
        "tenant_id": tenant_id,
        "features": [{"name": name, "enabled": enabled} for name, enabled in features.items()],
        "total": len(features),
    }


@router.put(
    "/{tenant_id}/features/{feature}",
    summary="Toggle feature de tenant",
    description="Habilita o deshabilita una feature especifica de un tenant.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def toggle_tenant_feature(
    tenant_id: str,
    feature: str,
    toggle_data: TenantFeatureToggle,
    user: dict[str, Any] = Depends(require_permission("settings", "update")),
    tenant_service: Any = Depends(get_tenant_service),
) -> dict[str, Any]:
    """Habilita o deshabilita una feature de un tenant."""
    existing = tenant_service.get_tenant(tenant_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant '{tenant_id}' no encontrado")

    result = tenant_service.set_feature(tenant_id, feature, toggle_data.enabled)
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Error toggling feature"))

    return {
        "tenant_id": tenant_id,
        "feature": feature,
        "enabled": toggle_data.enabled,
    }
