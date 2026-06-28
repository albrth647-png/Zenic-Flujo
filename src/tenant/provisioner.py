"""
Sprint 6 (Fase 6) — TenantProvisioner.
=======================================

Extraído de tenant/service.py (BUG-ARCH-02 god class split).
Responsabilidad: creación y aprovisionamiento de tenants (DB schema/DB).

Thin wrapper que delega en TenantService para compatibilidad total.
"""
from __future__ import annotations

from src.core.logging import setup_logging
from src.tenant.service import TenantService
from typing import Any

logger = setup_logging(__name__)


class TenantProvisioner:
    """
    Crea y aprovisiona tenants.
    Delega en TenantService para mantener compatibilidad.
    """

    def __init__(self, tenant_service: TenantService | None = None) -> None:
        self._tenant_service = tenant_service or TenantService()

    def create_tenant(
        self,
        name: str,
        slug: str,
        plan: str = "free",
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Crea un nuevo tenant con su storage aprovisionado.
        Delega en TenantService.create_tenant() que internamente:
        1. Genera UUID
        2. Aprovisiona storage (schema o DB según plan)
        3. Habilita features del plan
        4. Cachea en Redis
        """
        return self._tenant_service.create_tenant(name, slug, plan, config)

    def get_tenant_db(self, tenant_id: str):
        """Obtiene la conexión DB específica del tenant."""
        return self._tenant_service.get_tenant_db(tenant_id)

    def suspend_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Suspende un tenant (no borra datos)."""
        return self._tenant_service.suspend_tenant(tenant_id)

    def activate_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Reactiva un tenant suspendido."""
        return self._tenant_service.activate_tenant(tenant_id)

    def delete_tenant(self, tenant_id: str) -> dict[str, Any]:
        """Elimina un tenant y limpia recursos asociados."""
        return self._tenant_service.delete_tenant(tenant_id)
