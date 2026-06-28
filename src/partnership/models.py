"""Partnership Program — Partner models, tiers, and benefits."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class PartnerTier(StrEnum):
    """Partner program tiers."""
    COMMUNITY = "community"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class PartnerStatus(StrEnum):
    """Partner account lifecycle status."""
    APPLICANT = "applicant"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class PartnerBenefitType(StrEnum):
    """Types of benefits available to partners."""
    REVENUE_SHARE = "revenue_share"
    FREE_CONNECTORS = "free_connectors"
    PRIORITY_SUPPORT = "priority_support"
    WHITE_LABEL = "white_label"
    CO_MARKETING = "co_marketing"
    EARLY_ACCESS = "early_access"
    DEDICATED_ENGINEER = "dedicated_engineer"
    TRAINING_CREDITS = "training_credits"
    CUSTOM_INTEGRATIONS = "custom_integrations"


class PartnerActivityType(StrEnum):
    """Types of partner activities tracked for compliance."""
    CONNECTOR_PUBLISHED = "connector_published"
    CONNECTOR_INSTALLED = "connector_installed"
    REFERRAL = "referral"
    TICKET_CREATED = "ticket_created"
    TICKET_RESOLVED = "ticket_resolved"
    TRAINING_COMPLETED = "training_completed"
    REVIEW_SUBMITTED = "review_submitted"


@dataclass
class PartnerRegistration:
    """Partner account registration."""

    company_name: str
    contact_name: str
    contact_email: str
    partner_id: str = ""
    tier: PartnerTier = PartnerTier.COMMUNITY
    status: PartnerStatus = PartnerStatus.APPLICANT
    website: str = ""
    description: str = ""
    country: str = ""
    tax_id: str = ""
    api_key: str = ""
    connector_count: int = 0
    total_installs: int = 0
    revenue_share_pct: float = 0.0
    rating: float = 0.0
    joined_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        if self.joined_at is None:
            self.joined_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class PartnerBenefit:
    """A benefit granted to a partner based on tier."""

    partner_id: str
    benefit_type: PartnerBenefitType
    benefit_id: str = ""
    description: str = ""
    value: str = ""
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    active: bool = True

    def __post_init__(self):
        if not self.benefit_id:
            self.benefit_id = f"benefit-{uuid.uuid4().hex[:10]}"
        if self.granted_at is None:
            self.granted_at = datetime.now()


@dataclass
class PartnerActivity:
    """A tracked partner activity for compliance and rewards."""

    partner_id: str
    activity_type: PartnerActivityType
    activity_id: str = ""
    description: str = ""
    metadata: dict[str, Any] | None = None
    performed_at: datetime | None = None

    def __post_init__(self):
        if not self.activity_id:
            self.activity_id = f"activity-{uuid.uuid4().hex[:10]}"
        if self.metadata is None:
            self.metadata = {}
        if self.performed_at is None:
            self.performed_at = datetime.now()


# ── Tier Definition ────────────────────────────────────

TIER_DEFINITIONS: dict[PartnerTier, dict[str, Any]] = {
    PartnerTier.COMMUNITY: {
        "name": "Community",
        "description": "Open to all developers. Publish open-source connectors.",
        "min_connectors": 0,
        "min_installs": 0,
        "min_rating": 0.0,
        "revenue_share_pct": 0.0,
        "benefits": [
            PartnerBenefitType.FREE_CONNECTORS,
            PartnerBenefitType.CO_MARKETING,
        ],
    },
    PartnerTier.SILVER: {
        "name": "Silver",
        "description": "For professional connector publishers. Revenue share enabled.",
        "min_connectors": 3,
        "min_installs": 100,
        "min_rating": 3.5,
        "revenue_share_pct": 30.0,
        "benefits": [
            PartnerBenefitType.FREE_CONNECTORS,
            PartnerBenefitType.REVENUE_SHARE,
            PartnerBenefitType.PRIORITY_SUPPORT,
            PartnerBenefitType.CO_MARKETING,
            PartnerBenefitType.EARLY_ACCESS,
        ],
    },
    PartnerTier.GOLD: {
        "name": "Gold",
        "description": "Strategic partners with premium support and co-marketing.",
        "min_connectors": 10,
        "min_installs": 1000,
        "min_rating": 4.0,
        "revenue_share_pct": 50.0,
        "benefits": [
            PartnerBenefitType.FREE_CONNECTORS,
            PartnerBenefitType.REVENUE_SHARE,
            PartnerBenefitType.PRIORITY_SUPPORT,
            PartnerBenefitType.WHITE_LABEL,
            PartnerBenefitType.CO_MARKETING,
            PartnerBenefitType.EARLY_ACCESS,
            PartnerBenefitType.TRAINING_CREDITS,
            PartnerBenefitType.CUSTOM_INTEGRATIONS,
        ],
    },
    PartnerTier.PLATINUM: {
        "name": "Platinum",
        "description": "Exclusive enterprise partners. Full strategic alliance.",
        "min_connectors": 20,
        "min_installs": 10000,
        "min_rating": 4.5,
        "revenue_share_pct": 70.0,
        "benefits": [
            PartnerBenefitType.FREE_CONNECTORS,
            PartnerBenefitType.REVENUE_SHARE,
            PartnerBenefitType.PRIORITY_SUPPORT,
            PartnerBenefitType.WHITE_LABEL,
            PartnerBenefitType.CO_MARKETING,
            PartnerBenefitType.EARLY_ACCESS,
            PartnerBenefitType.DEDICATED_ENGINEER,
            PartnerBenefitType.TRAINING_CREDITS,
            PartnerBenefitType.CUSTOM_INTEGRATIONS,
        ],
    },
}
