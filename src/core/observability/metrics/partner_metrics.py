"""
Metricas de Partnership — registros, revenue share, referencias.

Responsabilidad:
- ``record_partner_registration``: contador por tier+status.
- ``record_partner_revenue_shared``: contador (value=amount) por
  partner_id+currency.
- ``record_partner_referral``: contador por partner_id+status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class PartnerMetricsMixin:
    """Metricas del programa de partners."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_partner_registration(
        self,
        partner_id: str,
        tier: str,
        status: str,
    ) -> None:
        """
        Registra el registro de un nuevo partner.

        Args:
            partner_id: ID del partner
            tier: Nivel del partner (bronze, silver, gold, platinum)
            status: Estado (pending, approved, rejected)
        """
        self._metrics.increment_counter(
            "partnership_registrations_total",
            labels={"tier": tier, "status": status},
        )

    def record_partner_revenue_shared(
        self,
        partner_id: str,
        amount: float,
        currency: str = "USD",
    ) -> None:
        """
        Registra revenue share con un partner.

        Args:
            partner_id: ID del partner
            amount: Monto compartido
            currency: Moneda
        """
        self._metrics.increment_counter(
            "partnership_revenue_shared_total",
            value=amount,
            labels={"partner_id": partner_id, "currency": currency},
        )

    def record_partner_referral(
        self,
        partner_id: str,
        status: str,
    ) -> None:
        """
        Registra una referencia de partner.

        Args:
            partner_id: ID del partner
            status: Estado (converted, pending, expired)
        """
        self._metrics.increment_counter(
            "partnership_referrals_total",
            labels={"partner_id": partner_id, "status": status},
        )
