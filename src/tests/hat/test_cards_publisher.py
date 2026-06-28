"""
Tests para F0-D6: agents/cards.py + card_publisher.py + integración con
WebResearcherSpecialist y QueryBuilderWorker.

Cobertura:
- AgentCard: dataclass, to_db_row, to_ovc_metadata, __repr__, frozen
- CardPublisherMixin: publish_card (DB + OVC), idempotencia, helpers
- Integración: WebResearcher.get_card() y QueryBuilder.get_card()
- E2E: publicar 2 cards y verificar resonancia (variable OVC creada)
"""
# ruff: noqa: F821 — Tests en TestIntegrationWebResearcher referencian
# WebResearcherSpecialist y QueryBuilderWorker que fueron eliminados en HAT v2;
# las clases están marcadas con @pytest.mark.skip.

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pytest

from src.hat.agents_legacy.base import AgentConfig

# WebResearcherSpecialist / QueryBuilderWorker were eliminated in HAT v2.
# The integration tests that depended on them (TestIntegrationWebResearcher,
# TestIntegrationQueryBuilder, TestE2EPublishTwoCards) are skipped below.
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level3_specialists.base.card_publisher import CardPublisherMixin
from src.hat.level3_specialists.base.cards import AgentCard
from src.orbital.context import OrbitalContext


@pytest.fixture
def repo():
    return LedgerRepository()


@pytest.fixture
def ctx():
    OrbitalContext._reset()
    return OrbitalContext()


@pytest.fixture(autouse=True)
def cleanup_orbital_context():
    yield
    OrbitalContext._reset()


@pytest.fixture
def unique_agent_id():
    """Genera agent_ids únicos por test para evitar colisiones en DB persistente."""
    ts = datetime.now(UTC).strftime("%H%M%S%f")
    return f"agent_{ts}"


# ─────────────────────────────────────────────────────────
# AgentCard dataclass
# ─────────────────────────────────────────────────────────


class TestAgentCardDataclass:
    def test_agent_card_creation_with_required_fields(self, unique_agent_id):
        card = AgentCard(
            agent_id=unique_agent_id,
            agent_name="Test Agent",
            domain="research",
            tier="worker",
        )
        assert card.agent_id == unique_agent_id
        assert card.agent_name == "Test Agent"
        assert card.domain == "research"
        assert card.tier == "worker"

    def test_agent_card_defaults(self, unique_agent_id):
        """Los campos opcionales deben tener defaults sensatos."""
        card = AgentCard(
            agent_id=unique_agent_id,
            agent_name="Test",
            domain="research",
            tier="worker",
        )
        assert card.capabilities == []
        assert card.cost_per_call == 0.0
        assert card.avg_latency_ms == 0
        assert card.orbital_keywords == []
        assert card.orbital_amplitude == 1.0
        assert card.orbital_velocity == 0.1

    def test_agent_card_is_frozen(self, unique_agent_id):
        """AgentCard debe ser inmutable."""
        from dataclasses import FrozenInstanceError

        card = AgentCard(
            agent_id=unique_agent_id, agent_name="T", domain="r", tier="w",
        )
        with pytest.raises(FrozenInstanceError):
            card.agent_name = "Other"  # type: ignore[misc]

    def test_to_db_row_returns_dict_with_10_columns(self, unique_agent_id):
        card = AgentCard(
            agent_id=unique_agent_id, agent_name="T", domain="r", tier="w",
            capabilities=["a", "b"], orbital_keywords=["k1", "k2"],
            cost_per_call=0.05, avg_latency_ms=100,
            orbital_amplitude=1.5, orbital_velocity=0.2,
        )
        row = card.to_db_row()
        assert isinstance(row, dict)
        assert set(row.keys()) == {
            "agent_id", "agent_name", "domain", "tier",
            "capabilities", "cost_per_call", "avg_latency_ms",
            "orbital_keywords", "orbital_amplitude", "orbital_velocity",
        }
        # capabilities y orbital_keywords deben estar serializados como JSON strings
        assert isinstance(row["capabilities"], str)
        assert json.loads(row["capabilities"]) == ["a", "b"]
        assert isinstance(row["orbital_keywords"], str)
        assert json.loads(row["orbital_keywords"]) == ["k1", "k2"]

    def test_to_ovc_metadata_returns_dict_with_type_marker(self, unique_agent_id):
        card = AgentCard(
            agent_id=unique_agent_id, agent_name="T", domain="r", tier="w",
            capabilities=["a"], orbital_keywords=["k"],
        )
        meta = card.to_ovc_metadata()
        assert meta["type"] == "agent_card"
        assert meta["agent_id"] == unique_agent_id
        assert meta["domain"] == "r"
        assert meta["tier"] == "w"
        assert meta["capabilities"] == ["a"]

    def test_repr_does_not_include_capabilities(self, unique_agent_id):
        """__repr__ debe ser compacto, sin capabilities completas."""
        card = AgentCard(
            agent_id=unique_agent_id, agent_name="T", domain="r", tier="w",
            capabilities=["a"] * 100,  # capabilities largas
            orbital_keywords=["k1", "k2"],
        )
        repr_str = repr(card)
        assert unique_agent_id in repr_str
        assert "research" in repr_str or "r" in repr_str
        # No debe incluir las 100 capabilities
        assert "a, a, a" not in repr_str

    def test_agent_card_with_empty_keywords(self, unique_agent_id):
        """AgentCard válida con 0 keywords (raro pero posible)."""
        card = AgentCard(
            agent_id=unique_agent_id, agent_name="T", domain="r", tier="w",
            orbital_keywords=[],
        )
        assert card.orbital_keywords == []


# ─────────────────────────────────────────────────────────
# CardPublisherMixin
# ─────────────────────────────────────────────────────────


class TestCardPublisherMixin:
    def test_mixin_get_card_raises_not_implemented(self):
        """Si una subclase no implementa get_card(), debe dar NotImplementedError."""
        # Crear una clase que herede BaseAgent + CardPublisherMixin sin implementar get_card
        from src.hat.agents_legacy.base import BaseAgent

        class IncompleteAgent(BaseAgent, CardPublisherMixin):
            def think(self, observation):
                return None

            def act(self, decision):
                return None

        agent = IncompleteAgent(AgentConfig(name="incomplete"))
        with pytest.raises(NotImplementedError, match="get_card"):
            agent.get_card()

    @pytest.mark.skip(reason="HAT v2: LedgerRepository.get_agent_card was removed; "
                             "agent cards are now persisted via level3 specialist bootstrap.")
    def test_publish_card_persists_to_db(self, repo, ctx, unique_agent_id):
        """publish_card debe crear una fila en hat_agent_cards."""
        from src.hat.agents_legacy.base import BaseAgent

        class TestAgent(BaseAgent, CardPublisherMixin):
            def think(self, observation):
                return None

            def act(self, decision):
                return None

            def get_card(self):
                return AgentCard(
                    agent_id=unique_agent_id, agent_name="Test Agent",
                    domain="research", tier="worker",
                    capabilities=["test"], orbital_keywords=["test_kw"],
                )

        agent = TestAgent(AgentConfig(name="test_agent"))
        agent.publish_card(repo=repo, ctx=ctx)

        # Verificar en DB
        db_card = repo.get_agent_card(unique_agent_id)
        assert db_card is not None
        assert db_card["agent_name"] == "Test Agent"
        assert db_card["domain"] == "research"
        assert db_card["capabilities"] == ["test"]

    def test_publish_card_injects_ovc_variable(self, repo, ctx, unique_agent_id):
        """publish_card debe crear una variable OVC con el nombre canónico."""
        from src.hat.agents_legacy.base import BaseAgent

        class TestAgent(BaseAgent, CardPublisherMixin):
            def think(self, observation):
                return None

            def act(self, decision):
                return None

            def get_card(self):
                return AgentCard(
                    agent_id=unique_agent_id, agent_name="T",
                    domain="research", tier="worker",
                    orbital_keywords=["buscar", "info"],
                    orbital_amplitude=1.3,
                )

        agent = TestAgent(AgentConfig(name="t"))
        agent.publish_card(repo=repo, ctx=ctx)

        var_name = CardPublisherMixin.make_card_var_name(unique_agent_id)
        var = ctx.ovc.get_variable(var_name)
        assert var is not None
        assert var.amplitude == 1.3
        assert var.orbit_group == "hat_cards_research"
        assert var.metadata["type"] == "agent_card"
        assert var.metadata["agent_id"] == unique_agent_id

    def test_publish_card_is_idempotent(self, repo, ctx, unique_agent_id):
        """Publicar 2 veces la misma card no duplica variables OVC."""
        from src.hat.agents_legacy.base import BaseAgent

        class TestAgent(BaseAgent, CardPublisherMixin):
            def think(self, observation):
                return None

            def act(self, decision):
                return None

            def get_card(self):
                return AgentCard(
                    agent_id=unique_agent_id, agent_name="T",
                    domain="research", tier="worker",
                    orbital_keywords=["test"],
                )

        agent = TestAgent(AgentConfig(name="t"))
        agent.publish_card(repo=repo, ctx=ctx)
        agent.publish_card(repo=repo, ctx=ctx)  # segunda vez

        var_name = CardPublisherMixin.make_card_var_name(unique_agent_id)
        # La variable OVC no debe duplicarse (create_variable lanza ValueError si existe)
        # y el segundo publish_card debe skip silenciosamente.
        all_vars = ctx.ovc.get_all_variables()
        matching = [n for n in all_vars if n == var_name]
        assert len(matching) == 1

    def test_publish_card_returns_the_card(self, repo, ctx, unique_agent_id):
        """publish_card retorna la AgentCard publicada (no None)."""
        from src.hat.agents_legacy.base import BaseAgent

        class TestAgent(BaseAgent, CardPublisherMixin):
            def think(self, observation):
                return None

            def act(self, decision):
                return None

            def get_card(self):
                return AgentCard(
                    agent_id=unique_agent_id, agent_name="T",
                    domain="build", tier="specialist",
                )

        agent = TestAgent(AgentConfig(name="t"))
        result = agent.publish_card(repo=repo, ctx=ctx)
        assert isinstance(result, AgentCard)
        assert result.agent_id == unique_agent_id
        assert result.domain == "build"
        assert result.tier == "specialist"

    def test_deterministic_theta_is_deterministic(self):
        """La misma lista de keywords siempre produce la misma θ."""
        theta1 = CardPublisherMixin._deterministic_theta(["buscar", "info"])
        theta2 = CardPublisherMixin._deterministic_theta(["buscar", "info"])
        assert theta1 == theta2

    def test_deterministic_theta_in_range_0_to_2pi(self):
        theta = CardPublisherMixin._deterministic_theta(["test"])
        assert 0.0 <= theta < 2 * math.pi

    def test_deterministic_theta_empty_keywords(self):
        """Lista vacía debe dar una θ válida."""
        theta = CardPublisherMixin._deterministic_theta([])
        assert 0.0 <= theta < 2 * math.pi

    def test_make_card_var_name_format(self):
        """El nombre canónico de variable OVC debe ser 'card_<agent_id>'."""
        assert CardPublisherMixin.make_card_var_name("my_agent") == "card_my_agent"


# ─────────────────────────────────────────────────────────
# Integración: WebResearcher + QueryBuilder
# ─────────────────────────────────────────────────────────
# NOTE: The three classes below depend on the eliminated HAT v1 stubs
# (WebResearcherSpecialist / QueryBuilderWorker). They are skipped until
# equivalent seed logic is wired through the new level3/level4 specialists.


@pytest.mark.skip(reason="HAT v2: WebResearcherSpecialist stub eliminated.")
class TestIntegrationWebResearcher:
    def test_web_researcher_has_get_card(self):
        specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.agent_id == "web_researcher"
        assert card.domain == "research"
        assert card.tier == "specialist"
        # Specialist debe tener mayor amplitud que worker
        assert card.orbital_amplitude == 1.5
        assert len(card.orbital_keywords) > 0

    def test_web_researcher_publish_card_e2e(self, repo, ctx):
        specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
        specialist.publish_card(repo=repo, ctx=ctx)

        # Verificar DB
        db_card = repo.get_agent_card("web_researcher")
        assert db_card is not None
        assert db_card["agent_name"] == "Web Researcher"
        assert "web_search" in db_card["capabilities"]

        # Verificar OVC
        var = ctx.ovc.get_variable("card_web_researcher")
        assert var is not None
        assert var.amplitude == 1.5
        assert var.orbit_group == "hat_cards_research"


@pytest.mark.skip(reason="HAT v2: QueryBuilderWorker stub eliminated.")
class TestIntegrationQueryBuilder:
    def test_query_builder_has_get_card(self):
        worker = QueryBuilderWorker(AgentConfig(name="qb"))
        card = worker.get_card()
        assert isinstance(card, AgentCard)
        assert card.agent_id == "query_builder"
        assert card.domain == "research"
        assert card.tier == "worker"
        # Worker debe tener menor amplitud que specialist
        assert card.orbital_amplitude == 0.8
        assert len(card.orbital_keywords) > 0

    def test_query_builder_publish_card_e2e(self, repo, ctx):
        worker = QueryBuilderWorker(AgentConfig(name="qb"))
        worker.publish_card(repo=repo, ctx=ctx)

        # Verificar DB
        db_card = repo.get_agent_card("query_builder")
        assert db_card is not None
        assert db_card["agent_name"] == "Query Builder"

        # Verificar OVC
        var = ctx.ovc.get_variable("card_query_builder")
        assert var is not None
        assert var.amplitude == 0.8
        assert var.orbit_group == "hat_cards_research"


# ─────────────────────────────────────────────────────────
# E2E: publicar 2 cards y verificar estado
# ─────────────────────────────────────────────────────────


@pytest.mark.skip(reason="HAT v2: WebResearcherSpecialist / QueryBuilderWorker stubs eliminated.")
class TestE2EPublishTwoCards:
    def test_publish_two_cards_creates_two_ovc_variables(self, repo, ctx):
        """Publicar WebResearcher + QueryBuilder debe crear 2 variables OVC."""
        specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
        worker = QueryBuilderWorker(AgentConfig(name="qb"))

        specialist.publish_card(repo=repo, ctx=ctx)
        worker.publish_card(repo=repo, ctx=ctx)

        all_vars = ctx.ovc.get_all_variables()
        card_vars = [n for n in all_vars if n.startswith("card_")]
        # Al menos nuestras 2 cards (puede haber más de tests previos en singleton)
        assert "card_web_researcher" in card_vars
        assert "card_query_builder" in card_vars

    def test_two_cards_have_different_theta(self, repo, ctx):
        """Cada card debe tener θ distinta (derivada de keywords distintas)."""
        specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
        worker = QueryBuilderWorker(AgentConfig(name="qb"))

        specialist.publish_card(repo=repo, ctx=ctx)
        worker.publish_card(repo=repo, ctx=ctx)

        var_specialist = ctx.ovc.get_variable("card_web_researcher")
        var_worker = ctx.ovc.get_variable("card_query_builder")
        assert var_specialist.theta != var_worker.theta

    def test_two_cards_in_same_orbit_group(self, repo, ctx):
        """Ambas cards del dominio research deben estar en el mismo orbit_group."""
        specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
        worker = QueryBuilderWorker(AgentConfig(name="qb"))

        specialist.publish_card(repo=repo, ctx=ctx)
        worker.publish_card(repo=repo, ctx=ctx)

        var_specialist = ctx.ovc.get_variable("card_web_researcher")
        var_worker = ctx.ovc.get_variable("card_query_builder")
        assert var_specialist.orbit_group == var_worker.orbit_group == "hat_cards_research"

    def test_publish_cards_via_supervisor_initialization(self, repo, ctx):
        """Simula el flujo real: ResearchSupervisor inicializa → publica cards.

        Aunque ResearchSupervisor no publica cards automáticamente en F0
        (lo hará tick_router en F0-D7), verificamos que un caller externo
        puede publicar ambas cards y el sistema queda en estado coherente.
        """
        # Simular inicialización del dominio Research
        specialist = WebResearcherSpecialist(AgentConfig(name="web_researcher"))
        specialist.publish_card(repo=repo, ctx=ctx)

        worker = QueryBuilderWorker(AgentConfig(name="query_builder"))
        worker.publish_card(repo=repo, ctx=ctx)

        # Verificar que ambas están en DB
        cards = repo.get_agent_cards(domain="research")
        agent_ids = {c["agent_id"] for c in cards}
        assert "web_researcher" in agent_ids
        assert "query_builder" in agent_ids

        # Verificar que ambas están en OVC
        assert ctx.ovc.get_variable("card_web_researcher") is not None
        assert ctx.ovc.get_variable("card_query_builder") is not None
