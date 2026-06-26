"""
Metricas de Tenant — operaciones y tenants activos.

Responsabilidad:
- ``record_tenant_operation``: contador por operation+status.
- ``set_tenant_active_count``: gauge de tenants activos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class TenantMetricsMixin:
    """Metricas de multi-tenancy."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_tenant_operation(self, tenant_id: str, operation: str, status: str) -> None:
        """
        Registra una operacion de tenant.

        Args:
            tenant_id: ID del tenant
            operation: Tipo de operacion (create, update, delete, suspend)
            status: Estado (success, failed)
        """
        self._metrics.increment_counter(
            "tenant_operations_total",
            labels={"operation": operation, "status": status},
        )

    def set_tenant_active_count(self, count: int) -> None:
        """
        Establece el gauge de tenants activos.

        Args:
            count: Numero de tenants activos
        """
        self._metrics.set_gauge("tenant_active_count", float(count))
