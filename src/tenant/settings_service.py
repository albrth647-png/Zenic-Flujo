"""
Sprint 6 (Fase 6) — TenantSettings.
====================================

Extraído de tenant/service.py (BUG-ARCH-02 god class split).
Responsabilidad: gestión de settings y features por tenant.

Thin wrapper que delega en TenantService para compatibilidad total.
"""
from __future__ import annotations

from src.tenant.service import TenantService
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TenantSettings:
    """
    Gestiona settings y features por tenant.
    Delega en TenantService para mantener compatibilidad.
    """

    def __init__(self, tenant_service: TenantService | None = None) -> None:
        self._tenant_service = tenant_service or TenantService()

    # ── Features ──────────────────────────────────────────────

    def set_feature(self, tenant_id: str, feature: str, enabled: bool) -> dict:
        """Habilita o deshabilita una feature para un tenant."""
        return self._tenant_service.set_feature(tenant_id, feature, enabled)

    def check_feature(self, tenant_id: str, feature: str) -> bool:
        """Verifica si una feature está habilitada para el tenant."""
        return self._tenant_service.check_feature(tenant_id, feature)

    def get_features(self, tenant_id: str) -> dict[str, bool]:
        """Retorna todas las features del tenant."""
        return self._tenant_service.get_features(tenant_id)

    # ── Settings ──────────────────────────────────────────────

    def get_setting(self, tenant_id: str, key: str) -> str | None:
        """Obtiene un setting del tenant."""
        return self._tenant_service.get_setting(tenant_id, key)

    def set_setting(self, tenant_id: str, key: str, value: str) -> dict:
        """Establece un setting del tenant."""
        return self._tenant_service.set_setting(tenant_id, key, value)

    def get_all_settings(self, tenant_id: str) -> dict[str, str]:
        """Obtiene todos los settings del tenant."""
        return self._tenant_service._get_tenant_settings(tenant_id)

    # ── Rate limiting ─────────────────────────────────────────

    def check_rate_limit(self, tenant_id: str, action: str = "api") -> dict:
        """Verifica rate limit para el tenant."""
        return self._tenant_service.check_rate_limit(tenant_id, action)
