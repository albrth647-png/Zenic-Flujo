"""
Zenic-Flujo — Tenant Middleware
================================

Middleware Flask que resuelve el tenant antes de cada request.
Inyecta g.tenant_id y g.tenant para uso downstream.
"""

from __future__ import annotations

from typing import Any

from src.tenant.context import clear_tenant_context, set_current_tenant_id
from src.tenant.service import TenantService
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# Rutas que no requieren resolucion de tenant
PUBLIC_PATH_PREFIXES = (
    "/api/auth/",
    "/api/v1/auth/",
    "/api/v2/health",
    "/api/v2/info",
    "/api/v2/docs",
    "/api/v2/redoc",
    "/login",
    "/static",
    "/app",
    "/health",
)

PUBLIC_PATHS = ("/", "/login", "/register")


class TenantMiddleware:
    """
    Middleware Flask que resuelve el tenant antes de cada request.

    Inyecta g.tenant_id y g.tenant para uso downstream.
    Retorna 404 para dominios de tenant desconocidos en rutas API.
    """

    def __init__(self, app: Any = None) -> None:
        self._tenant_service = TenantService()
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        """Registra el middleware en la aplicacion Flask."""
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        logger.info("TenantMiddleware registrado en la aplicacion Flask")

    def _is_public_path(self, path: str) -> bool:
        """Verifica si una ruta es publica (no requiere tenant)."""
        return path in PUBLIC_PATHS or any(
            path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES
        )

    def _before_request(self) -> Any | None:
        """Resuelve el tenant antes de cada request."""
        from flask import g, request

        # Skip para rutas publicas
        if self._is_public_path(request.path):
            return None

        tenant = self._tenant_service.resolve_tenant(request)

        if tenant:
            g.tenant_id = tenant["id"]
            g.tenant = tenant
            set_current_tenant_id(tenant["id"])

            # Almacenar en sesion para requests futuros
            try:
                from flask import session

                session["tenant_id"] = tenant["id"]
            except RuntimeError:
                pass
        else:
            # Si no se puede resolver el tenant y es ruta API, retornar 404
            if request.path.startswith("/api/") or request.path.startswith("/api/v2/"):
                from flask import jsonify

                return jsonify({"error": "Tenant no encontrado", "code": "TENANT_NOT_FOUND"}), 404

            # Para paginas web, continuar sin tenant (modo single-tenant)
            g.tenant_id = None
            g.tenant = None

        return None

    def _after_request(self, response: Any) -> Any:
        """Limpia el contexto de tenant despues de cada request."""
        clear_tenant_context()
        return response
