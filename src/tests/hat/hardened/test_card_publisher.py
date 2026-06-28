"""Tests para CardPublisherMixin — publicación de AgentCards en OVC.

Cubre:
- get_card() raise NotImplementedError en base.
- publish_card() inyecta card en OVC.
- _deterministic_theta genera θ determinista desde keywords.
- Idempotencia: publicar dos veces no duplica.
- make_card_var_name genera nombre canónico.
"""
from __future__ import annotations

import hashlib
import math

import pytest

from src.hat.level3_specialists.base.card_publisher import CardPublisherMixin
from src.hat.level3_specialists.base.cards import AgentCard
from src.orbital.context import OrbitalContext

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_orbital_context() -> None:
    """Reset del singleton OrbitalContext antes de cada test."""
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def ctx() -> OrbitalContext:
    """OrbitalContext fresco."""
    return OrbitalContext()


# ── Helper: publisher concreto para tests ──────────────────────────────


class _FakePublisher(CardPublisherMixin):
    """Publisher concreto para tests."""

    def __init__(self, card: AgentCard) -> None:
        self._card = card

    def get_card(self) -> AgentCard:
        return self._card


@pytest.fixture
def sample_card() -> AgentCard:
    """AgentCard de prueba."""
    return AgentCard(
        agent_id="test_agent",
        agent_name="Test Agent",
        domain="test",
        tier="specialist",
        capabilities=["action_a"],
        orbital_keywords=["test", "agent"],
        orbital_amplitude=1.5,
        orbital_velocity=0.05,
    )


@pytest.fixture
def publisher(sample_card: AgentCard) -> _FakePublisher:
    """_FakePublisher con sample_card."""
    return _FakePublisher(card=sample_card)


# ── Tests de get_card (base) ───────────────────────────────────────────


class TestGetCard:
    """get_card() en la base class."""

    def test_base_get_card_raises_not_implemented(self) -> None:
        """CardPublisherMixin.get_card() raise NotImplementedError."""
        mixin = CardPublisherMixin()
        with pytest.raises(NotImplementedError, match="get_card"):
            mixin.get_card()


# ── Tests de publish_card ──────────────────────────────────────────────


class TestPublishCard:
    """Publicación de AgentCard en OVC."""

    def test_publish_card_injects_variable_into_ovc(
        self, publisher: _FakePublisher, sample_card: AgentCard,
    ) -> None:
        """publish_card() crea una variable OVC para la card."""
        publisher.publish_card()
        ctx = OrbitalContext()
        var = ctx.ovc.get_variable("card_test_agent")
        assert var is not None
        assert var.metadata["type"] == "agent_card"
        assert var.metadata["agent_id"] == "test_agent"

    def test_publish_card_returns_the_card(
        self, publisher: _FakePublisher, sample_card: AgentCard,
    ) -> None:
        """publish_card() retorna la AgentCard publicada."""
        result = publisher.publish_card()
        assert result is sample_card

    def test_publish_card_sets_amplitude_from_card(
        self, publisher: _FakePublisher, sample_card: AgentCard,
    ) -> None:
        """La variable OVC tiene la amplitude de la card."""
        publisher.publish_card()
        ctx = OrbitalContext()
        var = ctx.ovc.get_variable("card_test_agent")
        assert var is not None
        assert var.amplitude == sample_card.orbital_amplitude

    def test_publish_card_sets_velocity_from_card(
        self, publisher: _FakePublisher, sample_card: AgentCard,
    ) -> None:
        """La variable OVC tiene la velocity de la card."""
        publisher.publish_card()
        ctx = OrbitalContext()
        var = ctx.ovc.get_variable("card_test_agent")
        assert var is not None
        assert var.velocity == sample_card.orbital_velocity

    def test_publish_card_sets_orbit_group(
        self, publisher: _FakePublisher,
    ) -> None:
        """La variable OVC tiene orbit_group='hat_cards_<domain>'."""
        publisher.publish_card()
        ctx = OrbitalContext()
        var = ctx.ovc.get_variable("card_test_agent")
        assert var is not None
        assert var.orbit_group == "hat_cards_test"

    def test_publish_card_is_idempotent(
        self, publisher: _FakePublisher,
    ) -> None:
        """Publicar dos veces no crea duplicados (ValueError se suprime)."""
        publisher.publish_card()
        # Segunda publicación no debe lanzar
        publisher.publish_card()
        ctx = OrbitalContext()
        # Solo debe haber una variable card_test_agent
        var = ctx.ovc.get_variable("card_test_agent")
        assert var is not None


# ── Tests de _deterministic_theta ──────────────────────────────────────


class TestDeterministicTheta:
    """Generación de θ determinista desde keywords."""

    def test_same_keywords_produce_same_theta(self) -> None:
        """Las mismas keywords producen la misma θ."""
        theta1 = CardPublisherMixin._deterministic_theta(["a", "b"])
        theta2 = CardPublisherMixin._deterministic_theta(["a", "b"])
        assert theta1 == theta2

    def test_different_keywords_produce_different_theta(self) -> None:
        """Keywords distintas producen θ distinta."""
        theta1 = CardPublisherMixin._deterministic_theta(["a", "b"])
        theta2 = CardPublisherMixin._deterministic_theta(["c", "d"])
        assert theta1 != theta2

    def test_theta_in_range_0_to_2pi(self) -> None:
        """θ está en [0, 2π)."""
        for keywords in [[], ["a"], ["a", "b"], ["x", "y", "z"]]:
            theta = CardPublisherMixin._deterministic_theta(keywords)
            assert 0.0 <= theta < 2 * math.pi

    def test_empty_keywords_produce_valid_theta(self) -> None:
        """Keywords vacío produce θ válida (no crashea)."""
        theta = CardPublisherMixin._deterministic_theta([])
        assert 0.0 <= theta < 2 * math.pi

    def test_theta_matches_md5_hash_formula(self) -> None:
        """θ coincide con la fórmula: md5(keywords)[:8] % 10000 / 10000 * 2π."""
        keywords = ["test", "agent"]
        joined = "|".join(keywords)
        hash_val = int(hashlib.md5(joined.encode(), usedforsecurity=False).hexdigest()[:8], 16)
        expected_theta = (hash_val % 10000) / 10000.0 * (2 * math.pi)
        actual_theta = CardPublisherMixin._deterministic_theta(keywords)
        assert math.isclose(actual_theta, expected_theta, abs_tol=1e-9)


# ── Tests de make_card_var_name ────────────────────────────────────────


class TestMakeCardVarName:
    """Generación de nombre canónico de variable OVC."""

    def test_var_name_format(self) -> None:
        """El nombre tiene formato 'card_<agent_id>'."""
        name = CardPublisherMixin.make_card_var_name("crm")
        assert name == "card_crm"

    def test_var_name_with_complex_id(self) -> None:
        """Agent ID con guiones bajos."""
        name = CardPublisherMixin.make_card_var_name("notification_specialist")
        assert name == "card_notification_specialist"

    def test_var_name_with_empty_id(self) -> None:
        """Agent ID vacío."""
        name = CardPublisherMixin.make_card_var_name("")
        assert name == "card_"
