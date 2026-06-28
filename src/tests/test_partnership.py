"""Partnership Program — Tests for partner registration, tiers, benefits, and activity tracking."""

from __future__ import annotations

import pytest

from src.partnership.models import (
    TIER_DEFINITIONS,
    PartnerActivityType,
    PartnerRegistration,
    PartnerStatus,
    PartnerTier,
)
from src.partnership.service import PartnershipService


@pytest.fixture
def partnership(tmp_path):
    """PartnershipService with temp database."""
    db_path = str(tmp_path / "test_partners.db")
    service = PartnershipService(db_path)
    yield service
    PartnershipService.reset_instance()


class TestPartnerRegistration:
    """Tests for partner registration flow."""

    def test_register_community(self, partnership):
        reg = PartnerRegistration(
            company_name="Dev Shop",
            contact_name="John Doe",
            contact_email="john@devshop.com",
            country="BR",
        )
        result = partnership.register(reg)
        assert result["success"] is True
        assert result["tier"] == "community"
        assert result["api_key"].startswith("zp_")

    def test_register_silver(self, partnership):
        reg = PartnerRegistration(
            company_name="Big Corp",
            contact_name="Jane CEO",
            contact_email="jane@bigcorp.com",
            tier=PartnerTier.SILVER,
        )
        result = partnership.register(reg)
        assert result["success"] is True
        assert result["tier"] == "silver"

    def test_register_duplicate_email(self, partnership):
        reg = PartnerRegistration(
            company_name="Test",
            contact_name="Test",
            contact_email="dup@test.com",
        )
        partnership.register(reg)

        result = partnership.register(reg)
        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_approve_partner(self, partnership):
        reg = PartnerRegistration(
            company_name="Approved Co",
            contact_name="Alice",
            contact_email="alice@approved.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]

        assert partnership.approve(pid) is True
        partner = partnership.get_partner(pid)
        assert partner["status"] == PartnerStatus.ACTIVE.value

    def test_approve_nonexistent(self, partnership):
        assert partnership.approve("nonexistent") is False

    def test_get_partner_by_email(self, partnership):
        reg = PartnerRegistration(
            company_name="Find Me",
            contact_name="Bob",
            contact_email="bob@findme.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]

        found = partnership.get_partner_by_email("bob@findme.com")
        assert found is not None
        assert found["partner_id"] == pid

    def test_list_partners(self, partnership):
        for i in range(3):
            reg = PartnerRegistration(
                company_name=f"Company {i}",
                contact_name=f"Owner {i}",
                contact_email=f"c{i}@test.com",
            )
            partnership.register(reg)

        result = partnership.list_partners()
        assert result["total"] == 3
        assert len(result["partners"]) == 3


class TestTierManagement:
    """Tests for partner tier promotion and requirements."""

    def test_promote_too_low_tier_fails(self, partnership):
        reg = PartnerRegistration(
            company_name="Low Tier",
            contact_name="Test",
            contact_email="low@test.com",
            tier=PartnerTier.SILVER,
        )
        result = partnership.register(reg)
        pid = result["partner_id"]
        partnership.approve(pid)

        # Cannot promote to same or lower tier
        assert partnership.promote(pid, PartnerTier.COMMUNITY)["success"] is False
        assert partnership.promote(pid, PartnerTier.SILVER)["success"] is False

    def test_promote_fails_requirements(self, partnership):
        reg = PartnerRegistration(
            company_name="Small",
            contact_name="Test",
            contact_email="small@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]
        partnership.approve(pid)

        # Community → Gold requires 10 connectors, but partner has 0
        assert partnership.promote(pid, PartnerTier.GOLD)["success"] is False

    def test_promote_success(self, partnership):
        reg = PartnerRegistration(
            company_name="Full Stack",
            contact_name="Test",
            contact_email="full@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]
        partnership.approve(pid)

        # Manually set metrics to meet Gold requirements
        partnership._conn.execute(
            "UPDATE partners SET connector_count = 10, total_installs = 1000, rating = 4.0 WHERE partner_id = ?",
            (pid,),
        )
        partnership._conn.commit()

        result = partnership.promote(pid, PartnerTier.GOLD)
        assert result["success"] is True
        assert result["new_tier"] == "gold"

        partner = partnership.get_partner(pid)
        assert partner["tier"] == "gold"
        assert partner["revenue_share_pct"] == 50.0  # Gold revenue share

    def test_auto_promote(self, partnership):
        reg = PartnerRegistration(
            company_name="Auto Promo",
            contact_name="Test",
            contact_email="auto@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]
        partnership.approve(pid)

        # Set metrics to meet Silver requirements
        partnership._conn.execute(
            "UPDATE partners SET connector_count = 5, total_installs = 200, rating = 3.8 WHERE partner_id = ?",
            (pid,),
        )
        partnership._conn.commit()

        result = partnership.auto_promote(pid)
        assert result["success"] is True
        partner = partnership.get_partner(pid)
        assert partner["tier"] == "silver"

    def test_get_tier_requirements_all(self, partnership):
        reqs = partnership.get_tier_requirements()
        assert len(reqs) == 4  # 4 tiers
        assert "community" in reqs
        assert "platinum" in reqs

    def test_get_tier_requirements_single(self, partnership):
        req = partnership.get_tier_requirements(PartnerTier.GOLD)
        assert "gold" in req
        assert req["gold"]["min_connectors"] == 10
        assert req["gold"]["revenue_share_pct"] == 50.0


class TestBenefits:
    """Tests for partner benefits management."""

    def test_tier_benefits_auto_created(self, partnership):
        reg = PartnerRegistration(
            company_name="Benefits Test",
            contact_name="Test",
            contact_email="benefits@test.com",
            tier=PartnerTier.PLATINUM,
        )
        result = partnership.register(reg)
        pid = result["partner_id"]

        benefits = partnership.get_partner_benefits(pid)
        assert len(benefits) == len(TIER_DEFINITIONS[PartnerTier.PLATINUM]["benefits"])

    def test_revoke_benefit(self, partnership):
        reg = PartnerRegistration(
            company_name="Revoke Test",
            contact_name="Test",
            contact_email="revoke@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]

        benefits = partnership.get_partner_benefits(pid)
        assert len(benefits) > 0
        benefit_id = benefits[0]["benefit_id"]

        assert partnership.revoke_benefit(benefit_id) is True


class TestActivityTracking:
    """Tests for partner activity tracking and metrics updates."""

    def test_track_activity(self, partnership):
        reg = PartnerRegistration(
            company_name="Active Partner",
            contact_name="Test",
            contact_email="active@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]
        partnership.approve(pid)

        activity_id = partnership.track_activity(
            pid, PartnerActivityType.CONNECTOR_PUBLISHED,
            description="Published connector v1.0",
        )
        assert activity_id is not None

        activities = partnership.get_activities(pid)
        assert len(activities) == 3  # 1 registration + 1 approval + 1 publish
        descriptions = [a["description"] for a in activities]
        assert "Published connector v1.0" in descriptions

    def test_activity_updates_metrics(self, partnership):
        reg = PartnerRegistration(
            company_name="Metric Test",
            contact_name="Test",
            contact_email="metric@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]
        partnership.approve(pid)

        partner_before = partnership.get_partner(pid)
        assert partner_before["connector_count"] == 0

        partnership.track_activity(pid, PartnerActivityType.CONNECTOR_PUBLISHED)

        partner_after = partnership.get_partner(pid)
        assert partner_after["connector_count"] == 1

    def test_track_install_increments(self, partnership):
        reg = PartnerRegistration(
            company_name="Install Test",
            contact_name="Test",
            contact_email="install@test.com",
        )
        result = partnership.register(reg)
        pid = result["partner_id"]

        partnership.track_activity(pid, PartnerActivityType.CONNECTOR_INSTALLED)
        partner = partnership.get_partner(pid)
        assert partner["total_installs"] == 1


class TestAnalytics:
    """Tests for partnership program statistics."""

    def test_get_stats_empty(self, partnership):
        stats = partnership.get_stats()
        assert stats["total_partners"] == 0

    def test_get_stats_with_data(self, partnership):
        for i in range(3):
            reg = PartnerRegistration(
                company_name=f"Stats {i}",
                contact_name="Tester",
                contact_email=f"s{i}@test.com",
            )
            partnership.register(reg)

        stats = partnership.get_stats()
        assert stats["total_partners"] == 3
        assert stats["by_tier"]["community"] == 3


class TestTierDefinitions:
    """Tests for tier definition structures."""

    def test_all_tiers_have_definitions(self):
        for tier in PartnerTier:
            assert tier.value in TIER_DEFINITIONS
            definition = TIER_DEFINITIONS[tier]
            assert "min_connectors" in definition
            assert "min_installs" in definition
            assert "min_rating" in definition
            assert "revenue_share_pct" in definition
            assert "benefits" in definition

    def test_tier_benefits_cumulative(self):
        """Higher tiers should have at least as many benefits as lower tiers."""
        tiers = list(PartnerTier)
        for i in range(len(tiers) - 1):
            lower = TIER_DEFINITIONS[tiers[i]]
            higher = TIER_DEFINITIONS[tiers[i + 1]]
            # Higher tier should have >= benefits (superset)
            assert len(higher["benefits"]) >= len(lower["benefits"])

    def test_tier_requirements_increase(self):
        """Higher tiers should have increasing requirements."""
        for key in ["min_connectors", "min_installs", "min_rating", "revenue_share_pct"]:
            values = [TIER_DEFINITIONS[t][key] for t in PartnerTier]
            assert values == sorted(values), f"{key} should be non-decreasing"


class TestSingleton:
    """Tests for PartnershipService singleton."""

    def test_singleton(self):
        m1 = PartnershipService.get_instance()
        m2 = PartnershipService.get_instance()
        assert m1 is m2
        PartnershipService.reset_instance()

    def test_reset(self):
        PartnershipService.reset_instance()
        m1 = PartnershipService.get_instance()
        PartnershipService.reset_instance()
        m2 = PartnershipService.get_instance()
        assert m1 is not m2
