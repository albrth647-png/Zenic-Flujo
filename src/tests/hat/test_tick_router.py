"""
Tests para orbital_n0/tick_router.py (F0-D7 sub-features 2, 3, 4).

SKIPPED en HAT v2: este archivo prueba el flujo F0 con los dominios legacy
(research/build/operate) y los stubs WebResearcherSpecialist/QueryBuilderWorker
(eliminados en M4). El sistema actual usa los dominios
operaciones/comunicaciones/datos_auto con specialists reales. La cobertura
equivalente vive en src/tests/hat/e2e/test_e2e_hat.py.
"""

from __future__ import annotations

import pytest

# Whole module skipped — see docstring above.
pytestmark = pytest.mark.skip(
    reason="HAT v2: este archivo depende de los dominios legacy "
           "(research/build/operate) y de los stubs WebResearcherSpecialist/"
           "QueryBuilderWorker eliminados en M4. La cobertura equivalente "
           "está en src/tests/hat/e2e/test_e2e_hat.py."
)

from datetime import UTC, datetime  # noqa: E402

from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator  # noqa: E402

# WebResearcherSpecialist / QueryBuilderWorker were eliminated in HAT v2.
# Tests that referenced them via the router_with_cards fixture are skipped
# at the module level (see pytestmark above).
from src.hat.level1_orchestrator.ledger.ovc_bridge import OVCLedgerBridge  # noqa: E402
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository  # noqa: E402
from src.hat.level1_orchestrator.tick_router import HATRouter  # noqa: E402
from src.orbital.context import OrbitalContext  # noqa: E402


@pytest.fixture
def repo():
    return LedgerRepository()


@pytest.fixture
def ctx():
    OrbitalContext._reset()
    return OrbitalContext()


@pytest.fixture
def bridge(repo, ctx):
    return OVCLedgerBridge(repo=repo, ctx=ctx)


@pytest.fixture(autouse=True)
def cleanup():
    """Reset singletons entre tests."""
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()
    yield
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()


@pytest.fixture
def session():
    ts = datetime.now(UTC).strftime("%H%M%S%f")
    return {"user_id": f"router_user_{ts}", "session_id": f"router_sess_{ts}"}


@pytest.fixture
def router_with_cards(repo, ctx, bridge):
    """Router con 2 Agent Cards publicadas (web_researcher + query_builder).

    SKIPPED en HAT v2: las cards se sembraban con WebResearcherSpecialist y
    QueryBuilderWorker (stubs eliminados en M4). El fixture se mantiene sólo
    para preservar la firma — el módulo entero está saltado vía pytestmark.
    """
    return HATRouter(ledger=repo, ctx=ctx, bridge=bridge)


# ─────────────────────────────────────────────────────────
# HATRouter.__init__
# ─────────────────────────────────────────────────────────


class TestHATRouterInit:
    def test_init_with_defaults_uses_singletons(self):
        router = HATRouter()
        assert isinstance(router._ledger, LedgerRepository)
        assert router._ctx is OrbitalContext()
        assert isinstance(router._bridge, OVCLedgerBridge)
        assert "research" in router._supervisors

    def test_init_with_explicit_dependencies(self, repo, ctx, bridge):
        router = HATRouter(ledger=repo, ctx=ctx, bridge=bridge)
        assert router._ledger is repo
        assert router._ctx is ctx
        assert router._bridge is bridge

    def test_init_has_research_supervisor(self, repo, ctx, bridge):
        router = HATRouter(ledger=repo, ctx=ctx, bridge=bridge)
        assert "research" in router._supervisors
        # NOTE: ResearchSupervisor was eliminated in HAT v2 — the new
        # tick_router uses operaciones/comunicaciones/datos_auto supervisors.
        # The whole module is skipped via pytestmark; this body never runs.


# ─────────────────────────────────────────────────────────
# handle() — flujo E2E
# ─────────────────────────────────────────────────────────


class TestHATRouterHandle:
    def test_handle_returns_well_formed_response(self, router_with_cards, session):
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "busca info de python",
        )
        # Verificar campos obligatorios
        assert "dispatch_id" in result
        assert "domain" in result
        assert "response" in result
        assert "orbital_resonance" in result
        assert "anti_dup_layer_hit" in result
        assert "duration_ms" in result
        assert "status" in result
        # dispatch_id debe tener formato esperado
        assert result["dispatch_id"].startswith("disp_")
        # domain debe ser uno de los válidos o clarify
        assert result["domain"] in ("research", "build", "operate", "clarify")

    def test_handle_research_query_returns_queries(self, router_with_cards, session):
        """Para una query de research, debe retornar queries expandidas."""
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar info de python",
        )
        assert result["status"] in ("completed", "clarify")
        if result["status"] == "completed":
            # La respuesta debe mencionar queries
            assert "queries" in result["response"].lower() or "query" in result["response"].lower()

    def test_handle_persists_dispatch_to_ledger(self, router_with_cards, repo, session):
        """handle() debe registrar el dispatch en hat_dispatch_registry."""
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        # Buscar el dispatch por dispatch_id en progress
        progress = repo.get_progress(session["user_id"], session["session_id"])
        matching = [p for p in progress if p["dispatch_id"] == result["dispatch_id"]]
        assert len(matching) == 1

    def test_handle_with_empty_message(self, router_with_cards, session):
        """Mensaje vacío debe handled gracefully (no crash)."""
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "",
        )
        assert "status" in result
        assert result["status"] in ("completed", "clarify", "failed")

    def test_handle_is_deterministic_for_same_input(self, router_with_cards, session):
        """Mismo input → mismo domain (determinismo del ruteo orbital).

        Nota: tras F1-D1, la 2ª request puede ser bloqueada por anti-dup cascade
        (TTL Freshness o Exact Match). Validamos que domain es igual, pero status
        puede differir (completed vs anti_dup_blocked).
        """
        r1 = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        r2 = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        # Domain debe ser igual (determinismo del ruteo orbital)
        assert r1["domain"] == r2["domain"]

    def test_handle_duration_ms_positive(self, router_with_cards, session):
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        assert result["duration_ms"] >= 0


# ─────────────────────────────────────────────────────────
# _route_by_orbital
# ─────────────────────────────────────────────────────────


class TestRouteByOrbital:
    def test_returns_empty_list_when_no_cards(self, repo, ctx, bridge):
        """Sin Agent Cards publicadas, _route_by_orbital retorna []."""
        router = HATRouter(ledger=repo, ctx=ctx, bridge=bridge)
        top3 = router._route_by_orbital("buscar python")
        assert top3 == []

    def test_returns_top3_when_cards_exist(self, router_with_cards):
        """Con Agent Cards publicadas, retorna top-3 dominios con resonancia."""
        top3 = router_with_cards._route_by_orbital("buscar info de python")
        # Debe haber al menos 1 dominio (research)
        assert len(top3) >= 1
        # Todos los dominios deben ser válidos
        for domain, resonance in top3:
            assert domain in ("research", "build", "operate")
            assert 0.0 <= resonance <= 1.0

    def test_top3_sorted_descending_by_resonance(self, router_with_cards):
        top3 = router_with_cards._route_by_orbital("buscar python")
        if len(top3) >= 2:
            assert top3[0][1] >= top3[1][1]
            if len(top3) >= 3:
                assert top3[1][1] >= top3[2][1]

    def test_collect_cards_by_domain_groups_correctly(self, router_with_cards):
        """_collect_cards_by_domain debe agrupar cards por dominio."""
        cards = router_with_cards._collect_cards_by_domain()
        # En F0 solo tenemos research, pero la estructura debe ser correcta
        assert "research" in cards
        # Las cards de research deben ser >= 1
        assert len(cards["research"]) >= 1


# ─────────────────────────────────────────────────────────
# _disambiguate
# ─────────────────────────────────────────────────────────


class TestDisambiguate:
    def test_returns_clarify_when_top3_empty(self, repo, ctx, bridge):
        router = HATRouter(ledger=repo, ctx=ctx, bridge=bridge)
        result = router._disambiguate([], "test", None)
        assert result == "clarify"

    def test_returns_clear_winner_when_diff_above_threshold(self, router_with_cards):
        """Diferencia > 0.15 → top1 gana sin FSM."""
        top3 = [("research", 0.9), ("build", 0.4), ("operate", 0.1)]
        result = router_with_cards._disambiguate(top3, "buscar", None)
        assert result == "research"

    def test_uses_fsm_when_diff_below_threshold(self, router_with_cards):
        """Diferencia < 0.15 → FSM decide basándose en keywords."""
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        # "buscar" es keyword de research → research gana
        result = router_with_cards._disambiguate(top3, "buscar info", None)
        assert result == "research"

    def test_fsm_returns_clarify_when_no_keyword_match(self, router_with_cards):
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        # "xyz" no es keyword de ningún dominio en top2 → clarify
        result = router_with_cards._disambiguate(top3, "xyz", None)
        assert result == "clarify"


# ─────────────────────────────────────────────────────────
# _dispatch_to_supervisor
# ─────────────────────────────────────────────────────────


class TestDispatchToSupervisor:
    def test_dispatch_to_research_executes_supervisor(self, router_with_cards, session):
        """Despachar a research → ResearchSupervisor.handle() retorna resultado."""
        subtask = {
            "dispatch_id": "test_disp",
            "user_id": session["user_id"],
            "session_id": session["session_id"],
            "params": {"query": "buscar python"},
        }
        result = router_with_cards._dispatch_to_supervisor("research", subtask)
        assert "status" in result
        assert result["status"] in ("completed", "failed")
        if result["status"] == "completed":
            assert "specialists_used" in result

    def test_dispatch_to_unknown_domain_returns_failed(self, router_with_cards):
        """Dominio sin supervisor → status failed con error claro."""
        subtask = {"dispatch_id": "test", "params": {}}
        result = router_with_cards._dispatch_to_supervisor("unknown_domain", subtask)
        assert result["status"] == "failed"
        assert "no supervisor" in result["error"]

    def test_dispatch_to_build_works_in_f2(self, router_with_cards, session):
        """En F2, build tiene BuildSupervisor → debe funcionar."""
        subtask = {
            "dispatch_id": f"build_test_{session['session_id']}",
            "user_id": session["user_id"],
            "session_id": session["session_id"],
            "params": {"query": "crear función"},
        }
        result_b = router_with_cards._dispatch_to_supervisor("build", subtask)
        assert result_b["status"] in ("completed", "failed")


# ─────────────────────────────────────────────────────────
# _build_clarify_response + _synthesize_response
# ─────────────────────────────────────────────────────────


class TestClarifyAndSynthesize:
    def test_build_clarify_response_returns_clarify_status(self, router_with_cards):
        result = router_with_cards._build_clarify_response("test message")
        assert result["status"] == "clarify"
        assert "clarify_message" in result["result"]
        assert "test message" in result["result"]["clarify_message"]

    def test_synthesize_response_includes_all_fields(self, router_with_cards):
        supervisor_result = {
            "status": "completed",
            "result": {"queries": ["q1", "q2"]},
            "specialists_used": ["web_researcher"],
            "duration_ms": 100,
        }
        response = router_with_cards._synthesize_response(
            "disp_123", "research", supervisor_result, 0.75, 500, "none",
        )
        assert response["dispatch_id"] == "disp_123"
        assert response["domain"] == "research"
        assert response["orbital_resonance"] == 0.75
        assert response["duration_ms"] == 500
        assert response["anti_dup_layer_hit"] == "none"
        assert response["status"] == "completed"
        assert "queries" in response["response"].lower()

    def test_synthesize_response_handles_clarify_status(self, router_with_cards):
        supervisor_result = {
            "status": "clarify",
            "result": {"clarify_message": "Need more info"},
            "specialists_used": [],
            "duration_ms": 0,
        }
        response = router_with_cards._synthesize_response(
            "disp_x", "clarify", supervisor_result, 0.0, 10,
        )
        assert response["status"] == "clarify"
        assert response["response"] == "Need more info"

    def test_synthesize_response_handles_failed_status(self, router_with_cards):
        supervisor_result = {
            "status": "failed",
            "result": {"error": "timeout"},
            "specialists_used": [],
            "duration_ms": 0,
        }
        response = router_with_cards._synthesize_response(
            "disp_y", "research", supervisor_result, 0.0, 100,
        )
        assert response["status"] == "failed"
        assert "timeout" in response["response"]


# ─────────────────────────────────────────────────────────
# _get_active_domain
# ─────────────────────────────────────────────────────────


class TestGetActiveDomain:
    def test_returns_none_when_no_fact(self, router_with_cards, session):
        result = router_with_cards._get_active_domain(
            session["user_id"], session["session_id"],
        )
        assert result is None

    def test_returns_domain_string_when_fact_exists(self, router_with_cards, repo, session):
        repo.upsert_fact(
            session["user_id"], session["session_id"],
            "active_domain", "research",
        )
        result = router_with_cards._get_active_domain(
            session["user_id"], session["session_id"],
        )
        assert result == "research"

    def test_returns_none_when_fact_value_not_string(self, router_with_cards, repo, session):
        repo.upsert_fact(
            session["user_id"], session["session_id"],
            "active_domain", 123,
        )
        result = router_with_cards._get_active_domain(
            session["user_id"], session["session_id"],
        )
        assert result is None
