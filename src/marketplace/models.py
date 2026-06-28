"""
Marketplace — Modelos de datos del marketplace
===============================================

Define los modelos de datos para conectores del marketplace,
versiones, categorias, instalaciones, resenas y reportes
de certificacion.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ConnectorStatus(StrEnum):
    """Estados posibles de un conector en el marketplace."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    CERTIFIED = "certified"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


@dataclass
class ConnectorCategory:
    """Categoria de conector en el marketplace."""

    name: str
    display_name: str = ""
    description: str = ""
    icon: str = "folder"
    parent_category: str | None = None
    connector_count: int = 0
    created_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class ConnectorVersion:
    """Version especifica de un conector en el marketplace."""

    version: str
    changelog: str = ""
    min_platform_version: str = "1.0.0"
    download_url: str = ""
    checksum: str = ""
    size_bytes: int = 0
    released_at: datetime | None = None
    downloads: int = 0

    def __post_init__(self):
        if self.released_at is None:
            self.released_at = datetime.now()


@dataclass
class MarketplaceConnector:
    """Conector publicado en el marketplace."""

    name: str
    display_name: str = ""
    description: str = ""
    category: str = "general"
    icon: str = "plug"
    author: str = ""
    homepage: str = ""
    docs_url: str = ""
    status: ConnectorStatus = ConnectorStatus.DRAFT
    certification_status: str = "pending"
    current_version: str = "1.0.0"
    versions: list[ConnectorVersion] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    auth_types: list[str] = field(default_factory=list)
    installs: int = 0
    rating: float = 0.0
    review_count: int = 0
    featured: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class InstallationRecord:
    """Registro de instalacion de un conector para un tenant."""

    connector_name: str
    tenant_id: str
    id: str = ""
    version: str = "1.0.0"
    status: str = "active"
    config: dict[str, Any] = field(default_factory=dict)
    installed_at: datetime | None = None
    updated_at: datetime | None = None
    uninstalled_at: datetime | None = None

    def __post_init__(self):
        if not self.id:
            self.id = f"inst-{uuid.uuid4().hex[:10]}"
        if self.installed_at is None:
            self.installed_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class ReviewRecord:
    """Resena de un conector en el marketplace."""

    connector_name: str
    tenant_id: str
    rating: int
    id: str = ""
    title: str = ""
    comment: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        if not self.id:
            self.id = f"review-{uuid.uuid4().hex[:10]}"
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class CertificationReport:
    """Reporte de certificacion de un conector."""

    connector_name: str
    version: str
    status: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    score: float = 0.0
    details: str = ""
    reviewed_at: datetime | None = None

    def __post_init__(self):
        if self.reviewed_at is None:
            self.reviewed_at = datetime.now()


@dataclass
class ConnectorSearchResult:
    """Resultado de busqueda de conectores en el marketplace."""

    connectors: list[MarketplaceConnector] = field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    total_pages: int = 0


@dataclass
class MarketplaceStats:
    """Estadisticas generales del marketplace."""

    total_connectors: int = 0
    total_categories: int = 0
    total_installs: int = 0
    certified_connectors: int = 0
    pending_review: int = 0
    top_connectors: list[dict[str, Any]] = field(default_factory=list)
    category_distribution: dict[str, int] = field(default_factory=dict)
    recent_updates: list[dict[str, Any]] = field(default_factory=list)
