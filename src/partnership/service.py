"""Partnership Program — Service layer for partner management."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from typing import Any

from src.marketplace.repository import ConnectorRepository
from src.partnership.models import (
    TIER_DEFINITIONS,
    PartnerActivityType,
    PartnerBenefitType,
    PartnerRegistration,
    PartnerStatus,
    PartnerTier,
)
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class PartnershipService:
    """Service for managing partner accounts, tiers, and benefits.

    Integrates with:
    - ConnectorRepository: tracks partner connector metrics
    - MarketplaceService: partner connector publishing
    """

    _instance: PartnershipService | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = None) -> None:
        if db_path is None:
            from src.core.config import PARTNERS_DB_PATH
            db_path = str(PARTNERS_DB_PATH)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._repo = ConnectorRepository()
        self._init_db()

    @classmethod
    def get_instance(cls, **kwargs: Any) -> PartnershipService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS partners (
                partner_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                contact_name TEXT NOT NULL,
                contact_email TEXT NOT NULL UNIQUE,
                website TEXT DEFAULT '',
                description TEXT DEFAULT '',
                country TEXT DEFAULT '',
                tax_id TEXT DEFAULT '',
                tier TEXT NOT NULL DEFAULT 'community',
                status TEXT NOT NULL DEFAULT 'applicant',
                api_key TEXT DEFAULT '',
                connector_count INTEGER DEFAULT 0,
                total_installs INTEGER DEFAULT 0,
                revenue_share_pct REAL DEFAULT 0.0,
                rating REAL DEFAULT 0.0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS partner_benefits (
                benefit_id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL,
                benefit_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                value TEXT DEFAULT '',
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                active INTEGER DEFAULT 1,
                FOREIGN KEY (partner_id) REFERENCES partners(partner_id)
            );
            CREATE TABLE IF NOT EXISTS partner_activities (
                activity_id TEXT PRIMARY KEY,
                partner_id TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                description TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (partner_id) REFERENCES partners(partner_id)
            );
            CREATE INDEX IF NOT EXISTS idx_partner_tier ON partners(tier);
            CREATE INDEX IF NOT EXISTS idx_partner_status ON partners(status);
            CREATE INDEX IF NOT EXISTS idx_partner_benefits ON partner_benefits(partner_id);
            CREATE INDEX IF NOT EXISTS idx_partner_activities ON partner_activities(partner_id);
        """)
        self._conn.commit()
        logger.info("PartnershipService: Database initialized")

    # ── Partner Registration ───────────────────────────────

    def register(self, registration: PartnerRegistration) -> dict[str, Any]:
        """Register a new partner."""
        existing = self._conn.execute(
            "SELECT partner_id FROM partners WHERE contact_email = ?", (registration.contact_email,)
        ).fetchone()
        if existing:
            return {"success": False, "error": "A partner with this email already exists"}

        partner_id = f"partner-{uuid.uuid4().hex[:10]}"
        api_key = f"zp_{uuid.uuid4().hex}{uuid.uuid4().hex[:16]}"

        tier_info = TIER_DEFINITIONS.get(registration.tier, TIER_DEFINITIONS[PartnerTier.COMMUNITY])

        self._conn.execute(
            """INSERT INTO partners
               (partner_id, company_name, contact_name, contact_email, website,
                description, country, tax_id, tier, status, api_key,
                revenue_share_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (partner_id, registration.company_name, registration.contact_name,
             registration.contact_email, registration.website,
             registration.description, registration.country, registration.tax_id,
             registration.tier.value, PartnerStatus.APPLICANT.value, api_key,
             tier_info["revenue_share_pct"]),
        )
        self._conn.commit()

        # Auto-create tier benefits
        for benefit_type in tier_info["benefits"]:
            self._create_benefit(partner_id, benefit_type)

        self._log_activity(partner_id, PartnerActivityType.REFERRAL, "Partner registered")

        logger.info(f"Partnership: New partner '{registration.company_name}' registered ({partner_id})")
        return {
            "success": True,
            "partner_id": partner_id,
            "api_key": api_key,
            "tier": registration.tier.value,
        }

    def approve(self, partner_id: str) -> bool:
        """Approve a partner application and activate the account."""
        cursor = self._conn.execute(
            "UPDATE partners SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE partner_id = ? AND status = ?",
            (PartnerStatus.ACTIVE.value, partner_id, PartnerStatus.APPLICANT.value),
        )
        if cursor.rowcount == 0:
            return False
        self._conn.commit()
        self._log_activity(partner_id, PartnerActivityType.REFERRAL, "Partner application approved")
        logger.info(f"Partnership: Partner '{partner_id}' approved")
        return True

    def get_partner(self, partner_id: str) -> dict[str, Any] | None:
        """Get partner details."""
        row = self._conn.execute(
            "SELECT * FROM partners WHERE partner_id = ?", (partner_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_partner_by_email(self, email: str) -> dict[str, Any] | None:
        """Find partner by email."""
        row = self._conn.execute(
            "SELECT * FROM partners WHERE contact_email = ?", (email,)
        ).fetchone()
        return dict(row) if row else None

    def list_partners(
        self,
        tier: PartnerTier | None = None,
        status: PartnerStatus | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """List partners with optional filters."""
        query = "SELECT * FROM partners WHERE 1=1"
        params: list[Any] = []

        if tier:
            query += " AND tier = ?"
            params.append(tier.value)
        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY updated_at DESC"

        # Count total (construct separate count query to avoid fragile string replacement)
        count_params = []
        count_query = "SELECT COUNT(*) as total FROM partners WHERE 1=1"
        if tier:
            count_query += " AND tier = ?"
            count_params.append(tier.value)
        if status:
            count_query += " AND status = ?"
            count_params.append(status.value)
        count_row = self._conn.execute(count_query, count_params).fetchone()
        total = count_row["total"] if count_row else 0

        # Paginate
        offset = (page - 1) * per_page
        query += " LIMIT ? OFFSET ?"
        params.extend([per_page, offset])

        rows = self._conn.execute(query, params).fetchall()
        partners = [dict(r) for r in rows]

        return {
            "partners": partners,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }

    # ── Tier Management ────────────────────────────────────

    def promote(self, partner_id: str, new_tier: PartnerTier) -> dict[str, Any]:
        """Promote a partner to a higher tier."""
        partner = self.get_partner(partner_id)
        if not partner:
            return {"success": False, "error": "Partner not found"}

        current_tier = PartnerTier(partner["tier"])
        tier_order = list(PartnerTier)
        if tier_order.index(new_tier) <= tier_order.index(current_tier):
            return {"success": False, "error": "New tier must be higher than current tier"}

        tier_info = TIER_DEFINITIONS[new_tier]

        # Check requirements
        if partner["connector_count"] < tier_info["min_connectors"]:
            return {
                "success": False,
                "error": f"Minimum {tier_info['min_connectors']} connectors required (has {partner['connector_count']})",
            }
        if partner["total_installs"] < tier_info["min_installs"]:
            return {
                "success": False,
                "error": f"Minimum {tier_info['min_installs']} installs required (has {partner['total_installs']})",
            }
        if partner["rating"] < tier_info["min_rating"]:
            return {
                "success": False,
                "error": f"Minimum rating {tier_info['min_rating']} required (has {partner['rating']})",
            }

        self._conn.execute(
            "UPDATE partners SET tier = ?, revenue_share_pct = ?, updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
            (new_tier.value, tier_info["revenue_share_pct"], partner_id),
        )
        self._conn.commit()

        # Grant new-tier benefits
        existing_benefits = self._conn.execute(
            "SELECT benefit_type FROM partner_benefits WHERE partner_id = ?", (partner_id,)
        ).fetchall()
        existing_types = {r["benefit_type"] for r in existing_benefits}

        for benefit_type in tier_info["benefits"]:
            if benefit_type.value not in existing_types:
                self._create_benefit(partner_id, benefit_type)

        self._log_activity(partner_id, PartnerActivityType.REFERRAL, f"Promoted to {new_tier.value}")
        logger.info(f"Partnership: Partner '{partner_id}' promoted to {new_tier.value}")
        return {"success": True, "new_tier": new_tier.value}

    def auto_promote(self, partner_id: str) -> dict[str, Any]:
        """Automatically promote partner if they meet next tier requirements."""
        partner = self.get_partner(partner_id)
        if not partner:
            return {"success": False, "error": "Partner not found"}

        current_tier = PartnerTier(partner["tier"])
        tier_order = list(PartnerTier)
        current_idx = tier_order.index(current_tier)

        # Check each higher tier
        for next_idx in range(current_idx + 1, len(tier_order)):
            next_tier = tier_order[next_idx]
            tier_info = TIER_DEFINITIONS[next_tier]

            if (partner["connector_count"] >= tier_info["min_connectors"]
                    and partner["total_installs"] >= tier_info["min_installs"]
                    and partner["rating"] >= tier_info["min_rating"]):
                return self.promote(partner_id, next_tier)

        return {"success": True, "message": "No promotion available at this time"}

    def get_tier_requirements(self, tier: PartnerTier | None = None) -> dict[str, Any]:
        """Get tier definition requirements."""
        if tier:
            return {tier.value: TIER_DEFINITIONS[tier]}
        return {t.value: TIER_DEFINITIONS[t] for t in PartnerTier}

    # ── Benefits Management ────────────────────────────────

    def _create_benefit(
        self,
        partner_id: str,
        benefit_type: PartnerBenefitType,
        description: str = "",
        value: str = "",
    ) -> str:
        benefit_id = f"benefit-{uuid.uuid4().hex[:10]}"
        self._conn.execute(
            """INSERT INTO partner_benefits
               (benefit_id, partner_id, benefit_type, description, value)
               VALUES (?, ?, ?, ?, ?)""",
            (benefit_id, partner_id, benefit_type.value, description, value),
        )
        self._conn.commit()
        return benefit_id

    def revoke_benefit(self, benefit_id: str) -> bool:
        """Revoke a benefit from a partner."""
        cursor = self._conn.execute(
            "UPDATE partner_benefits SET active = 0 WHERE benefit_id = ?", (benefit_id,)
        )
        return cursor.rowcount > 0

    def get_partner_benefits(self, partner_id: str) -> list[dict[str, Any]]:
        """List all benefits for a partner."""
        rows = self._conn.execute(
            "SELECT * FROM partner_benefits WHERE partner_id = ? ORDER BY granted_at DESC",
            (partner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Activity Tracking ──────────────────────────────────

    def _log_activity(
        self,
        partner_id: str,
        activity_type: PartnerActivityType,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        activity_id = f"activity-{uuid.uuid4().hex[:10]}"
        self._conn.execute(
            """INSERT INTO partner_activities
               (activity_id, partner_id, activity_type, description, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (activity_id, partner_id, activity_type.value, description,
             json.dumps(metadata or {})),
        )
        self._conn.commit()
        return activity_id

    def track_activity(self, partner_id: str, activity_type: PartnerActivityType, description: str = "", metadata: dict[str, Any] | None = None) -> str:
        """Track a partner activity (public API)."""
        activity_id = self._log_activity(partner_id, activity_type, description, metadata)

        # Update partner metrics
        if activity_type == PartnerActivityType.CONNECTOR_PUBLISHED:
            self._conn.execute(
                "UPDATE partners SET connector_count = connector_count + 1, updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                (partner_id,),
            )
        elif activity_type == PartnerActivityType.CONNECTOR_INSTALLED:
            self._conn.execute(
                "UPDATE partners SET total_installs = total_installs + 1, updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                (partner_id,),
            )

        self._conn.commit()
        return activity_id

    def get_activities(self, partner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get activity history for a partner."""
        rows = self._conn.execute(
            "SELECT * FROM partner_activities WHERE partner_id = ? ORDER BY performed_at DESC LIMIT ?",
            (partner_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Analytics ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get partnership program statistics."""
        total = self._conn.execute("SELECT COUNT(*) as c FROM partners").fetchone()
        by_tier: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for row in self._conn.execute("SELECT tier, COUNT(*) as c FROM partners GROUP BY tier").fetchall():
            by_tier[row["tier"]] = row["c"]
        for row in self._conn.execute("SELECT status, COUNT(*) as c FROM partners GROUP BY status").fetchall():
            by_status[row["status"]] = row["c"]

        return {
            "total_partners": total["c"] if total else 0,
            "by_tier": by_tier,
            "by_status": by_status,
            "total_connectors_published": self._conn.execute(
                "SELECT SUM(connector_count) as s FROM partners"
            ).fetchone()["s"] or 0,
            "total_installs": self._conn.execute(
                "SELECT SUM(total_installs) as s FROM partners"
            ).fetchone()["s"] or 0,
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None
