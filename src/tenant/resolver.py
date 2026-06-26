"""
Sprint 6 (Fase 6) — TenantResolver.
===================================

Extraído de tenant/service.py (BUG-ARCH-02 god class split).
Responsabilidad: resolución de tenant desde request (header, session,
subdomain, custom domain).

Esta clase es un thin wrapper que delega en el TenantService singleton
para mantener compatibilidad total. Los servicios nuevos pueden usarla
directamente sin depender del god class completo.
"""
from __future__ import annotations

from typing import Any

from src.tenant.service import TenantService
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TenantResolver:
    """
    Resuelve el tenant desde una request Flask/FastAPI.
    Orden de resolución: X-Tenant-ID header → session → subdomain → custom domain.
    """

    def __init__(self, tenant_service: TenantService | None = None) -> None:
        self._tenant_service = tenant_service or TenantService()

    def resolve_from_request(self, request: Any) -> dict | None:
        """
        Resuelve el tenant desde una request.
        Delega en TenantService.resolve_tenant().
        """
        return self._tenant_service.resolve_tenant(request)

    def resolve_from_header(self, headers: dict[str, str]) -> dict | None:
        """Resuelve por header X-Tenant-ID."""
        tenant_id = headers.get("X-Tenant-ID") or headers.get("x-tenant-id")
        if not tenant_id:
            return None
        return self._tenant_service.get_tenant(tenant_id)

    def resolve_from_subdomain(self, host: str) -> dict | None:
        """
        Resuelve por subdomain.
        Ej: acme.app.zenic-flijo.com → busca tenant con slug 'acme'.
        """
        if not host or "." not in host:
            return None
        # Tomar la primera parte del host como slug potencial
        parts = host.split(".")
        if len(parts) < 3:
            return None
        slug = parts[0]
        if slug in ("www", "app", "api", "admin"):
            return None
        return self._tenant_service.get_tenant_by_slug(slug)
