"""
Marketplace — Tienda de Conectores para Zenic-Flijo
====================================================

Modulo que implementa el marketplace de conectores enterprise,
permitiendo publicar, certificar, buscar, instalar y gestionar
conectores de forma centralizada.

Componentes:
    - service: Servicio principal del marketplace
    - certification: Motor de certificacion automatica y manual
    - repository: Almacenamiento y persistencia de conectores
    - models: Modelos Pydantic para datos del marketplace
"""

from __future__ import annotations

from src.marketplace.certification import CertificationEngine, CertificationStatus
from src.marketplace.models import (
    CertificationReport,
    ConnectorCategory,
    ConnectorSearchResult,
    ConnectorVersion,
    InstallationRecord,
    MarketplaceConnector,
    MarketplaceStats,
    ReviewRecord,
)
from src.marketplace.repository import ConnectorRepository
from src.marketplace.service import MarketplaceService
from src.workflow.workflow_templates import get_template, list_templates, template_to_workflow_definition

__all__ = [
    "CertificationEngine",
    "CertificationReport",
    "CertificationStatus",
    "ConnectorCategory",
    "ConnectorRepository",
    "ConnectorSearchResult",
    "ConnectorVersion",
    "InstallationRecord",
    "MarketplaceConnector",
    "MarketplaceService",
    "MarketplaceStats",
    "ReviewRecord",
    "get_template",
    "list_templates",
    "template_to_workflow_definition",
]
