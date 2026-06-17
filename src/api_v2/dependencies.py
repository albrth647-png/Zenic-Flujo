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

Todas las dependencias usan singletons existentes del proyecto.
"""

from __future__ import annotations

from typing import Any

from fastapi import Query

from src.api_v2.models import PaginationParams


async def get_db() -> Any:
    """Obtiene la instancia singleton de DatabaseManager.

    Returns:
        DatabaseManager: Instancia de la base de datos SQLite
    """
    from src.data.database_manager import DatabaseManager

    return DatabaseManager()


async def get_redis() -> Any:
    """Obtiene la instancia singleton de RedisService.

    Returns:
        RedisService: Instancia del servicio de Redis
    """
    from src.data.redis_service import RedisService

    return RedisService()


async def get_workflow_engine() -> Any:
    """Obtiene la instancia singleton de WorkflowEngine.

    Returns:
        WorkflowEngine: Instancia del motor de workflows
    """
    from src.workflow.engine import WorkflowEngine

    return WorkflowEngine()


async def get_workflow_repository() -> Any:
    """Obtiene una nueva instancia de WorkflowRepository.

    Returns:
        WorkflowRepository: Instancia del repositorio de workflows
    """
    from src.workflow.repository import WorkflowRepository

    return WorkflowRepository()


async def get_nlu_pipeline() -> Any:
    """Obtiene una nueva instancia del Pipeline NLU.

    Returns:
        Pipeline: Instancia del pipeline de procesamiento de lenguaje natural
    """
    from src.nlu.pipeline import Pipeline

    return Pipeline()


async def get_connector_registry() -> Any:
    """Obtiene la instancia singleton de ConnectorRegistry.

    Returns:
        ConnectorRegistry: Instancia del registro de conectores
    """
    from src.sdk.registry import ConnectorRegistry

    return ConnectorRegistry()


async def get_tenant_service() -> Any:
    """Obtiene la instancia singleton de TenantService.

    Returns:
        TenantService: Instancia del servicio de multi-tenancy
    """
    from src.tenant.service import TenantService

    return TenantService()


async def get_rbac_manager() -> Any:
    """Obtiene la instancia singleton de RBACManager.

    Returns:
        RBACManager: Instancia del gestor de RBAC granular
    """
    from src.security.rbac import RBACManager

    return RBACManager()


async def get_telemetry_service() -> Any:
    """Obtiene la instancia singleton de TelemetryService.

    Returns:
        TelemetryService: Instancia del servicio de telemetria
    """
    from src.observability.telemetry import TelemetryService

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


# ─── Re-exports de auth (BUG-ARCH-03) ────────────────────────────────────
# Algunos routers importan `require_permission` y `get_current_user` desde
# `dependencies`, otros desde `auth`. Para eliminar el drift y hacer ambos
# imports válidos, re-exportamos aquí los símbolos de auth.
# La fuente de verdad sigue siendo src/api_v2/auth.py.
# Esto resuelve el ImportError que impedía cargar api_v2.app.

from src.api_v2.auth import (  # noqa: E402  (import al final es intencional)
    generate_token,
    validate_token,
    get_current_user,
    get_optional_user,
    require_permission,
    get_tenant,
)

__all__ = [
    "get_db",
    "get_redis",
    "get_workflow_engine",
    "get_workflow_repository",
    "get_nlu_pipeline",
    "get_connector_registry",
    "get_tenant_service",
    "get_rbac_manager",
    "get_telemetry_service",
    "get_pagination",
    # Re-exports de auth
    "generate_token",
    "validate_token",
    "get_current_user",
    "get_optional_user",
    "require_permission",
    "get_tenant",
]
