"""
Marketplace — Modelos Pydantic para datos del marketplace
=========================================================

Define los modelos de datos para conectores del marketplace,
versiones, categorias, instalaciones, resenas y reportes
de certificacion.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorStatus(str, Enum):
    """Estados posibles de un conector en el marketplace."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    CERTIFIED = "certified"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class ConnectorCategory(BaseModel):
    """Categoria de conector en el marketplace."""

    name: str = Field(description="Nombre unico de la categoria")
    display_name: str = Field(default="", description="Nombre para mostrar")
    description: str = Field(default="", description="Descripcion de la categoria")
    icon: str = Field(default="folder", description="Icono de la categoria")
    parent_category: str | None = Field(default=None, description="Categoria padre")
    connector_count: int = Field(default=0, description="Numero de conectores en la categoria")
    created_at: datetime = Field(default_factory=datetime.now, description="Fecha de creacion")


class ConnectorVersion(BaseModel):
    """Version especifica de un conector en el marketplace."""

    version: str = Field(description="Version semver del conector")
    changelog: str = Field(default="", description="Registro de cambios")
    min_platform_version: str = Field(default="1.0.0", description="Version minima de la plataforma")
    download_url: str = Field(default="", description="URL de descarga del paquete")
    checksum: str = Field(default="", description="Checksum SHA-256 del paquete")
    size_bytes: int = Field(default=0, description="Tamano del paquete en bytes")
    released_at: datetime = Field(default_factory=datetime.now, description="Fecha de lanzamiento")
    downloads: int = Field(default=0, description="Numero de descargas")


class MarketplaceConnector(BaseModel):
    """Conector publicado en el marketplace."""

    name: str = Field(description="Nombre unico del conector")
    display_name: str = Field(default="", description="Nombre para mostrar")
    description: str = Field(default="", description="Descripcion del conector")
    category: str = Field(default="general", description="Categoria del conector")
    icon: str = Field(default="plug", description="Icono del conector")
    author: str = Field(default="", description="Autor del conector")
    homepage: str = Field(default="", description="URL del sitio web")
    docs_url: str = Field(default="", description="URL de la documentacion")
    status: ConnectorStatus = Field(default=ConnectorStatus.DRAFT, description="Estado del conector")
    certification_status: str = Field(default="pending", description="Estado de certificacion")
    current_version: str = Field(default="1.0.0", description="Version actual")
    versions: list[ConnectorVersion] = Field(default_factory=list, description="Historial de versiones")
    tags: list[str] = Field(default_factory=list, description="Etiquetas de clasificacion")
    actions: list[str] = Field(default_factory=list, description="Acciones disponibles")
    auth_types: list[str] = Field(default_factory=list, description="Tipos de autenticacion soportados")
    installs: int = Field(default=0, description="Numero total de instalaciones")
    rating: float = Field(default=0.0, description="Calificacion promedio (0-5)")
    review_count: int = Field(default=0, description="Numero de resenas")
    featured: bool = Field(default=False, description="Si es un conector destacado")
    created_at: datetime = Field(default_factory=datetime.now, description="Fecha de creacion")
    updated_at: datetime = Field(default_factory=datetime.now, description="Fecha de actualizacion")


class InstallationRecord(BaseModel):
    """Registro de instalacion de un conector para un tenant."""

    id: str = Field(default="", description="ID unico de la instalacion")
    connector_name: str = Field(description="Nombre del conector instalado")
    tenant_id: str = Field(description="ID del tenant")
    version: str = Field(default="1.0.0", description="Version instalada")
    status: str = Field(default="active", description="Estado de la instalacion")
    config: dict[str, Any] = Field(default_factory=dict, description="Configuracion del conector")
    installed_at: datetime = Field(default_factory=datetime.now, description="Fecha de instalacion")
    updated_at: datetime = Field(default_factory=datetime.now, description="Fecha de actualizacion")
    uninstalled_at: datetime | None = Field(default=None, description="Fecha de desinstalacion")


class ReviewRecord(BaseModel):
    """Resena de un conector en el marketplace."""

    id: str = Field(default="", description="ID unico de la resena")
    connector_name: str = Field(description="Nombre del conector resenado")
    tenant_id: str = Field(description="ID del tenant que hizo la resena")
    rating: int = Field(ge=1, le=5, description="Calificacion de 1 a 5 estrellas")
    title: str = Field(default="", description="Titulo de la resena")
    comment: str = Field(default="", description="Comentario de la resena")
    created_at: datetime = Field(default_factory=datetime.now, description="Fecha de la resena")
    updated_at: datetime = Field(default_factory=datetime.now, description="Fecha de actualizacion")


class CertificationReport(BaseModel):
    """Reporte de certificacion de un conector."""

    connector_name: str = Field(description="Nombre del conector evaluado")
    version: str = Field(description="Version evaluada")
    status: str = Field(description="Estado de certificacion")
    checks: list[dict[str, Any]] = Field(default_factory=list, description="Lista de verificaciones realizadas")
    passed: int = Field(default=0, description="Numero de verificaciones aprobadas")
    failed: int = Field(default=0, description="Numero de verificaciones fallidas")
    warnings: int = Field(default=0, description="Numero de advertencias")
    score: float = Field(default=0.0, description="Puntuacion general (0-100)")
    details: str = Field(default="", description="Detalles adicionales")
    reviewed_at: datetime = Field(default_factory=datetime.now, description="Fecha de revision")


class ConnectorSearchResult(BaseModel):
    """Resultado de busqueda de conectores en el marketplace."""

    connectors: list[MarketplaceConnector] = Field(default_factory=list, description="Conectores encontrados")
    total: int = Field(default=0, description="Total de resultados")
    page: int = Field(default=1, description="Pagina actual")
    per_page: int = Field(default=20, description="Resultados por pagina")
    total_pages: int = Field(default=0, description="Total de paginas")


class MarketplaceStats(BaseModel):
    """Estadisticas generales del marketplace."""

    total_connectors: int = Field(default=0, description="Total de conectores")
    total_categories: int = Field(default=0, description="Total de categorias")
    total_installs: int = Field(default=0, description="Total de instalaciones")
    certified_connectors: int = Field(default=0, description="Conectores certificados")
    pending_review: int = Field(default=0, description="Conectores pendientes de revision")
    top_connectors: list[dict[str, Any]] = Field(default_factory=list, description="Conectores mas populares")
    category_distribution: dict[str, int] = Field(default_factory=dict, description="Distribucion por categoria")
    recent_updates: list[dict[str, Any]] = Field(default_factory=list, description="Actualizaciones recientes")
