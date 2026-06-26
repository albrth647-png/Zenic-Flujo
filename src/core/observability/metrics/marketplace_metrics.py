"""
Metricas de Marketplace — publicaciones, instalaciones, busquedas,
conectores disponibles.

Responsabilidad:
- ``record_marketplace_publish``: contador por connector+status.
- ``record_marketplace_install``: contador por connector+tenant_id.
- ``record_marketplace_search``: contador por has_query.
- ``set_marketplace_connectors_available``: gauge de conectores.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class MarketplaceMetricsMixin:
    """Metricas del marketplace de conectores."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_marketplace_publish(self, connector_name: str, status: str) -> None:
        """
        Registra la publicacion de un conector en el marketplace.

        Args:
            connector_name: Nombre del conector
            status: Estado de la publicacion (success, failed)
        """
        self._metrics.increment_counter(
            "marketplace_connector_publishes_total",
            labels={"connector": connector_name, "status": status},
        )

    def record_marketplace_install(self, connector_name: str, tenant_id: str) -> None:
        """
        Registra la instalacion de un conector.

        Args:
            connector_name: Nombre del conector
            tenant_id: ID del tenant
        """
        self._metrics.increment_counter(
            "marketplace_connector_installs_total",
            labels={"connector": connector_name, "tenant_id": tenant_id},
        )

    def record_marketplace_search(self, query: str = "", results_count: int = 0) -> None:
        """
        Registra una busqueda en el marketplace.

        Args:
            query: Texto de busqueda (truncado a 50 chars)
            results_count: Numero de resultados
        """
        self._metrics.increment_counter(
            "marketplace_searches_total",
            labels={"has_query": "yes" if query else "no"},
        )

    def set_marketplace_connectors_available(self, count: int) -> None:
        """
        Establece el gauge de conectores disponibles.

        Args:
            count: Numero de conectores disponibles
        """
        self._metrics.set_gauge("marketplace_connectors_available", float(count))
