"""
Zenic-Flujo — Tenant Context
=============================

Contexto thread-local para multi-tenancy.
Proporciona funciones para obtener/establecer el tenant_id del hilo actual.
"""

from __future__ import annotations

import types

import threading

# ── Thread-Local Tenant Context ───────────────────────────────

_tenant_context = threading.local()


def get_current_tenant_id() -> str | None:
    """Obtiene el tenant_id del contexto thread-local actual."""
    return getattr(_tenant_context, "tenant_id", None)


def set_current_tenant_id(tenant_id: str | None) -> None:
    """Establece el tenant_id en el contexto thread-local actual."""
    _tenant_context.tenant_id = tenant_id


def clear_tenant_context() -> None:
    """Limpia el contexto de tenant del thread actual."""
    _tenant_context.tenant_id = None


class TenantContext:
    """
    Context manager para establecer temporalmente un tenant en un bloque.

    Uso:
        with TenantContext("tenant-123"):
            # Aqui todo el codigo ve tenant_id = "tenant-123"
            process_request()
        # Aqui se restaura el tenant anterior
    """

    def __init__(self, tenant_id: str | None) -> None:
        self._new_tenant_id = tenant_id
        self._old_tenant_id: str | None = None

    def __enter__(self) -> TenantContext:
        self._old_tenant_id = get_current_tenant_id()
        set_current_tenant_id(self._new_tenant_id)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> None:
        set_current_tenant_id(self._old_tenant_id)
