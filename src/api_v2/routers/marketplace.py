"""
Zenic-Flijo API v2 — Router de Marketplace
============================================

Endpoints de busqueda e instalacion de conectores del marketplace:
- GET    /api/v2/marketplace/connectors               — Buscar/listar conectores
- GET    /api/v2/marketplace/connectors/{name}        — Detalles de conector
- POST   /api/v2/marketplace/connectors/{name}/install — Instalar conector
- DELETE /api/v2/marketplace/connectors/{name}        — Desinstalar conector
- POST   /api/v2/marketplace/publish                  — Publicar conector
- GET    /api/v2/marketplace/categories               — Listar categorias
- GET    /api/v2/marketplace/stats                    — Estadisticas del marketplace
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.api_v2.auth import get_current_user, require_permission
from src.api_v2.dependencies import get_connector_registry, get_db
from src.api_v2.models import (
    ConnectorPublishRequest,
    ConnectorSearchRequest,
    ConnectorSearchResponse,
    ConnectorSearchResult,
    ErrorResponse,
    MarketplaceCategory,
    MarketplaceStats,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/v2/marketplace", tags=["Marketplace"])

# Categorias predefinidas del marketplace
_MARKETPLACE_CATEGORIES: list[dict[str, Any]] = [
    {"name": "messaging", "icon": "message-circle", "description": "Plataformas de mensajeria"},
    {"name": "crm", "icon": "users", "description": "Gestion de relaciones con clientes"},
    {"name": "storage", "icon": "hard-drive", "description": "Almacenamiento y archivos"},
    {"name": "finance", "icon": "credit-card", "description": "Pagos y facturacion"},
    {"name": "communication", "icon": "mail", "description": "Email y comunicaciones"},
    {"name": "ai", "icon": "brain", "description": "Inteligencia artificial y ML"},
    {"name": "database", "icon": "database", "description": "Bases de datos"},
    {"name": "monitoring", "icon": "activity", "description": "Monitoreo y observabilidad"},
    {"name": "productivity", "icon": "zap", "description": "Productividad y oficina"},
    {"name": "social", "icon": "share-2", "description": "Redes sociales"},
    {"name": "devops", "icon": "git-branch", "description": "DevOps y CI/CD"},
    {"name": "general", "icon": "plug", "description": "Conectores generales"},
]


@router.get(
    "/connectors",
    response_model=ConnectorSearchResponse,
    summary="Buscar conectores en el marketplace",
    description="Busca y lista conectores del marketplace con paginacion, filtros y ordenamiento.",
    responses={401: {"model": ErrorResponse}},
)
async def search_connectors(
    search_params: ConnectorSearchRequest = Depends(),
    user: dict[str, Any] = Depends(get_current_user),
    registry: Any = Depends(get_connector_registry),
    db: Any = Depends(get_db),
) -> ConnectorSearchResponse:
    """Busca conectores en el marketplace."""
    # Obtener todos los conectores registrados
    all_connectors = registry.list_all()

    # Filtrar por query si se proporciona
    if search_params.query:
        query_lower = search_params.query.lower()
        all_connectors = [
            c for c in all_connectors
            if query_lower in c.get("name", "").lower()
            or query_lower in c.get("description", "").lower()
            or query_lower in c.get("category", "").lower()
        ]

    # Filtrar por categoria
    if search_params.category:
        all_connectors = [
            c for c in all_connectors if c.get("category", "general") == search_params.category
        ]

    # Ordenar
    reverse = search_params.sort_order == "desc"
    sort_key = search_params.sort_by
    if sort_key in ("name", "category", "author"):
        all_connectors.sort(key=lambda c: c.get(sort_key, ""), reverse=reverse)
    elif sort_key == "downloads":
        all_connectors.sort(key=lambda c: c.get("downloads", 0), reverse=True)
    elif sort_key == "rating":
        all_connectors.sort(key=lambda c: c.get("rating", 0.0), reverse=True)

    # Obtener conectores instalados
    installed_configs = db.fetchall("SELECT connector_name FROM connector_configs")
    installed_names = {row["connector_name"] for row in installed_configs}

    # Paginar
    total = len(all_connectors)
    total_pages = math.ceil(total / search_params.page_size) if total > 0 else 0
    start = (search_params.page - 1) * search_params.page_size
    end = start + search_params.page_size
    page_items = all_connectors[start:end]

    results = [
        ConnectorSearchResult(
            name=c.get("name", ""),
            version=c.get("version", "1.0.0"),
            description=c.get("description", ""),
            category=c.get("category", "general"),
            icon=c.get("icon", "plug"),
            author=c.get("author", ""),
            downloads=c.get("downloads", 0),
            rating=c.get("rating", 0.0),
            installed=c.get("name", "") in installed_names,
        )
        for c in page_items
    ]

    return ConnectorSearchResponse(
        items=results,
        total=total,
        page=search_params.page,
        page_size=search_params.page_size,
        total_pages=total_pages,
    )


@router.get(
    "/connectors/{name}",
    summary="Detalles de conector del marketplace",
    description="Obtiene los detalles completos de un conector en el marketplace.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def get_marketplace_connector(
    name: str,
    user: dict[str, Any] = Depends(get_current_user),
    registry: Any = Depends(get_connector_registry),
) -> dict[str, Any]:
    """Obtiene los detalles de un conector del marketplace."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado en el marketplace")

    metadata = registry.get_metadata(name) or {}
    metadata["name"] = name
    cls = registry.get(name)
    if cls:
        metadata["class_name"] = cls.__name__
        metadata["module"] = cls.__module__

    # Agregar datos de marketplace simulados
    metadata.setdefault("downloads", 0)
    metadata.setdefault("rating", 0.0)
    metadata.setdefault("reviews", [])
    metadata.setdefault("changelog", [])
    metadata.setdefault("documentation_url", "")
    metadata.setdefault("repository_url", "")

    return metadata


@router.post(
    "/connectors/{name}/install",
    summary="Instalar conector del marketplace",
    description="Instala un conector del marketplace en la instancia actual.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def install_connector(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "create")),
    registry: Any = Depends(get_connector_registry),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Instala un conector del marketplace."""
    if not registry.exists(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conector '{name}' no encontrado en el marketplace")

    # Verificar si ya esta instalado
    existing = db.fetchone("SELECT id FROM connector_configs WHERE connector_name = ?", (name,))
    if existing:
        return {"status": "already_installed", "connector": name, "message": "El conector ya esta instalado"}

    # Crear configuracion vacia para marcar como instalado
    db.execute(
        "INSERT INTO connector_configs (connector_name, config, user_id) VALUES (?, ?, ?)",
        (name, '{"auth_type": "none", "credentials": {}, "config": {}}', user.get("user_id", 1)),
    )
    db.commit()

    return {"status": "installed", "connector": name, "message": f"Conector '{name}' instalado exitosamente"}


@router.delete(
    "/connectors/{name}",
    summary="Desinstalar conector del marketplace",
    description="Desinstala un conector previamente instalado.",
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def uninstall_connector(
    name: str,
    user: dict[str, Any] = Depends(require_permission("connector", "delete")),
    db: Any = Depends(get_db),
    registry: Any = Depends(get_connector_registry),
) -> dict[str, Any]:
    """Desinstala un conector del marketplace."""
    existing = db.fetchone("SELECT id FROM connector_configs WHERE connector_name = ?", (name,))
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conector '{name}' no esta instalado",
        )

    # Eliminar configuracion
    db.execute("DELETE FROM connector_configs WHERE connector_name = ?", (name,))
    db.commit()

    # Opcionalmente remover del registro
    registry.unregister(name)

    return {"status": "uninstalled", "connector": name, "message": f"Conector '{name}' desinstalado"}


@router.post(
    "/publish",
    summary="Publicar conector al marketplace",
    description="Publica un conector registrado en el marketplace para que otros puedan instalarlo.",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def publish_connector(
    publish_data: ConnectorPublishRequest,
    user: dict[str, Any] = Depends(require_permission("connector", "create")),
    registry: Any = Depends(get_connector_registry),
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    """Publica un conector al marketplace."""
    if not registry.exists(publish_data.connector_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conector '{publish_data.connector_name}' no encontrado en el registro",
        )

    metadata = registry.get_metadata(publish_data.connector_name) or {}

    # Registrar publicacion en BD
    import json

    db.execute(
        """INSERT OR REPLACE INTO marketplace_published
           (connector_name, version, visibility, changelog, publisher_id, metadata, published_at)
           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            publish_data.connector_name,
            publish_data.version,
            publish_data.visibility,
            publish_data.changelog,
            user.get("user_id", 1),
            json.dumps(metadata, default=str),
        ),
    )
    db.commit()

    return {
        "status": "published",
        "connector": publish_data.connector_name,
        "version": publish_data.version,
        "visibility": publish_data.visibility,
    }


@router.get(
    "/categories",
    response_model=list[MarketplaceCategory],
    summary="Listar categorias del marketplace",
    description="Lista todas las categorias disponibles en el marketplace.",
    responses={401: {"model": ErrorResponse}},
)
async def list_categories(
    user: dict[str, Any] = Depends(get_current_user),
    registry: Any = Depends(get_connector_registry),
) -> list[MarketplaceCategory]:
    """Lista las categorias del marketplace."""
    # Contar conectores por categoria
    all_connectors = registry.list_all()
    category_counts: dict[str, int] = {}
    for connector in all_connectors:
        cat = connector.get("category", "general")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    categories = []
    for cat_data in _MARKETPLACE_CATEGORIES:
        name = cat_data["name"]
        categories.append(
            MarketplaceCategory(
                name=name,
                count=category_counts.get(name, 0),
                icon=cat_data.get("icon", "folder"),
            )
        )

    return categories


@router.get(
    "/stats",
    response_model=MarketplaceStats,
    summary="Estadisticas del marketplace",
    description="Obtiene estadisticas generales del marketplace.",
    responses={401: {"model": ErrorResponse}},
)
async def marketplace_stats(
    user: dict[str, Any] = Depends(get_current_user),
    registry: Any = Depends(get_connector_registry),
) -> MarketplaceStats:
    """Obtiene estadisticas del marketplace."""
    all_connectors = registry.list_all()
    categories = set()

    featured = []
    for connector in all_connectors[:5]:
        featured.append(connector.get("name", ""))
        categories.add(connector.get("category", "general"))

    return MarketplaceStats(
        total_connectors=len(all_connectors),
        total_downloads=sum(c.get("downloads", 0) for c in all_connectors),
        total_categories=len(categories),
        featured_connectors=featured,
    )
