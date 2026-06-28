"""Partnership Program — Partner tiers, benefits, and marketplace integration.

Features:
- Multi-tier partner program (Community, Silver, Gold, Platinum)
- Automated tier promotion based on metrics
- Revenue sharing and benefit management
- Partner activity tracking and analytics
- Deep integration with Marketplace connector publishing
"""

from __future__ import annotations

from src.partnership.models import (
    TIER_DEFINITIONS,
    PartnerActivity,
    PartnerActivityType,
    PartnerBenefit,
    PartnerBenefitType,
    PartnerRegistration,
    PartnerStatus,
    PartnerTier,
)
from src.partnership.service import PartnershipService

__all__ = [
    "TIER_DEFINITIONS",
    "PartnerActivity",
    "PartnerActivityType",
    "PartnerBenefit",
    "PartnerBenefitType",
    "PartnerRegistration",
    "PartnerStatus",
    "PartnerTier",
    "PartnershipService",
]
