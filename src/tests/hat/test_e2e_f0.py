"""
Tests E2E de F0 (F0-D8).

Validan el flujo completo HAT-ORBITAL end-to-end:
- Input del usuario → HATRouter.handle() → respuesta con queries
- 5 escenarios distintos cubren: research válido, mensaje ambiguo, mensaje vacío,
  sesión nueva vs recurrente, determinismo.

Estos tests son la aceptación final de F0. Si pasan, F0 está completo.

SKIPPED en HAT v2: este archivo usa el fixture router_with_cards que sembraba
AgentCards con WebResearcherSpecialist/QueryBuilderWorker (stubs eliminados en
M4) y asume los dominios legacy (research/build/operate). El sistema actual
usa operaciones/comunicaciones/datos_auto con specialists reales. La cobertura
equivalente está en src/tests/hat/e2e/test_e2e_hat.py.
"""

from __future__ import annotations

import pytest

# Whole module skipped — see docstring above.
pytestmark = pytest.mark.skip(
    reason="HAT v2: este archivo depende del fixture router_with_cards que "
           "sembraba AgentCards con los stubs WebResearcherSpecialist/"
           "QueryBuilderWorker eliminados en M4. La cobertura equivalente "
           "está en src/tests/hat/e2e/test_e2e_hat.py."
)

from datetime import UTC, datetime  # noqa: E402

from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator  # noqa: E402

# WebResearcherSpecialist / QueryBuilderWorker were eliminated in HAT v2.
# The router_with_cards fixture below is kept for signature compatibility
# only; the module is skipped via pytestmark above.
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
def router_with_cards(repo, ctx, bridge):
    """Router con 2 Agent Cards publicadas (configuración completa de F0).

    SKIPPED en HAT v2: las cards se sembraban con WebResearcherSpecialist y
    QueryBuilderWorker (stubs eliminados en M4). El fixture se mantiene sólo
    para preservar la firma — el módulo entero está saltado vía pytestmark.
    """
    return HATRouter(ledger=repo, ctx=ctx, bridge=bridge)


def _unique_session(prefix: str = "e2e") -> dict[str, str]:
    """Genera user_id + session_id únicos por test."""
    ts = datetime.now(UTC).strftime("%H%M%S%f")
    return {"user_id": f"{prefix}_user_{ts}", "session_id": f"{prefix}_sess_{ts}"}


# ─────────────────────────────────────────────────────────
# Escenario 1: research query válida → respuesta con queries
# ─────────────────────────────────────────────────────────


class TestE2EScenario1ResearchValid:
    """Escenario 1: input 'buscar info de python' → respuesta con queries expandidas."""

    def test_returns_completed_status(self, router_with_cards):
        session = _unique_session("s1")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar info de python",
        )
        assert result["status"] in ("completed", "clarify")

    def test_returns_research_domain(self, router_with_cards):
        session = _unique_session("s1")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar info de python",
        )
        # 'buscar' e 'info' son keywords de research → domain debe ser research
        assert result["domain"] in ("research", "clarify")

    def test_response_mentions_queries(self, router_with_cards):
        session = _unique_session("s1")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar info de python",
        )
        if result["status"] == "completed":
            assert "queries" in result["response"].lower()

    def test_dispatch_id_is_unique(self, router_with_cards):
        """Cada request genera un dispatch_id único."""
        s1 = _unique_session("s1a")
        s2 = _unique_session("s1b")
        r1 = router_with_cards.handle(s1["user_id"], s1["session_id"], "buscar python")
        r2 = router_with_cards.handle(s2["user_id"], s2["session_id"], "buscar python")
        assert r1["dispatch_id"] != r2["dispatch_id"]


# ─────────────────────────────────────────────────────────
# Escenario 2: mensaje ambiguo → clarify o research
# ─────────────────────────────────────────────────────────


class TestE2EScenario2Ambiguous:
    """Escenario 2: input sin keywords claras → clarify o fallback graceful."""

    def test_returns_valid_status(self, router_with_cards):
        session = _unique_session("s2")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "xyz qwerty",
        )
        assert result["status"] in ("completed", "clarify", "failed")

    def test_does_not_crash_on_gibberish(self, router_with_cards):
        """Texto sin sentido no debe crashear el sistema."""
        session = _unique_session("s2")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "asdfgh jklñ 123",
        )
        assert isinstance(result, dict)
        assert "dispatch_id" in result

    def test_response_is_string(self, router_with_cards):
        session = _unique_session("s2")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "xyz",
        )
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0


# ─────────────────────────────────────────────────────────
# Escenario 3: mensaje vacío → graceful handling
# ─────────────────────────────────────────────────────────


class TestE2EScenario3Empty:
    """Escenario 3: mensaje vacío o solo espacios → no crash."""

    def test_empty_message_handled(self, router_with_cards):
        session = _unique_session("s3")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "",
        )
        assert result["status"] in ("completed", "clarify", "failed")

    def test_whitespace_only_handled(self, router_with_cards):
        session = _unique_session("s3")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "    ",
        )
        assert result["status"] in ("completed", "clarify", "failed")

    def test_returns_well_formed_dict_even_on_empty(self, router_with_cards):
        session = _unique_session("s3")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "",
        )
        assert "dispatch_id" in result
        assert "domain" in result
        assert "response" in result
        assert "duration_ms" in result


# ─────────────────────────────────────────────────────────
# Escenario 4: sesión recurrente → persistencia Ledger
# ─────────────────────────────────────────────────────────


class TestE2EScenario4SessionRecurrence:
    """Escenario 4: 2 requests en la misma sesión → Ledger persiste ambos dispatches."""

    def test_two_dispatches_persisted(self, router_with_cards, repo):
        """Tras F1-D1, la 2ª request puede ser bloqueada por anti-dup cascade.

        Usamos 2 mensajes distintos para evitar TTL Freshness.
        Solo la 1ª request se persiste si la 2ª es bloqueada.
        """
        session = _unique_session("s4")
        r1 = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar javascript",
        )
        progress = repo.get_progress(session["user_id"], session["session_id"])
        dispatch_ids = {p["dispatch_id"] for p in progress}
        # Al menos la 1ª debe estar persistida
        assert r1["dispatch_id"] in dispatch_ids

    def test_session_started_in_ledger(self, router_with_cards, repo):
        """La sesión debe quedar registrada en hat_sessions (vía load_session)."""
        session = _unique_session("s4")
        router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        # La sesión debe tener al menos 1 dispatch
        progress = repo.get_progress(session["user_id"], session["session_id"])
        assert len(progress) >= 1


# ─────────────────────────────────────────────────────────
# Escenario 5: determinismo
# ─────────────────────────────────────────────────────────


class TestE2EScenario5Determinism:
    """Escenario 5: mismo input → mismo domain y status (determinismo ORBITAL)."""

    def test_same_input_same_domain(self, router_with_cards):
        s1 = _unique_session("s5a")
        s2 = _unique_session("s5b")
        r1 = router_with_cards.handle(s1["user_id"], s1["session_id"], "buscar python")
        r2 = router_with_cards.handle(s2["user_id"], s2["session_id"], "buscar python")
        assert r1["domain"] == r2["domain"]

    def test_same_input_same_status(self, router_with_cards):
        s1 = _unique_session("s5a")
        s2 = _unique_session("s5b")
        r1 = router_with_cards.handle(s1["user_id"], s1["session_id"], "buscar python")
        r2 = router_with_cards.handle(s2["user_id"], s2["session_id"], "buscar python")
        assert r1["status"] == r2["status"]

    def test_intent_hash_deterministic(self, router_with_cards):
        """El intent_hash subyacente debe ser determinista."""
        from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash

        h1 = compute_intent_hash("u", "s", "buscar python")
        h2 = compute_intent_hash("u", "s", "buscar python")
        assert h1 == h2


# ─────────────────────────────────────────────────────────
# Aceptación final F0
# ─────────────────────────────────────────────────────────


class TestF0Acceptance:
    """Tests de aceptación final de F0. Si pasan, F0 está completo."""

    def test_complete_pipeline_e2e(self, router_with_cards):
        """Pipeline completo: input → hash → load_session → route → dispatch → persist → synthesize."""
        session = _unique_session("accept")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar info de python",
        )
        # Verificar todos los campos del contrato HATResponse
        required_fields = [
            "dispatch_id", "domain", "response", "orbital_resonance",
            "anti_dup_layer_hit", "duration_ms", "facts_updated", "status",
        ]
        for field in required_fields:
            assert field in result, f"Falta campo {field!r} en respuesta HAT"

    def test_response_time_under_2_seconds(self, router_with_cards):
        """DoD F0 #8: latencia p50 < 300ms (aquí validamos < 2000ms como smoke test)."""
        session = _unique_session("perf")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        # 2000ms es un umbral generoso; el benchmark formal mide p50/p99 real
        assert result["duration_ms"] < 2000, (
            f"Latencia {result['duration_ms']}ms > 2000ms — posible problema de performance"
        )

    def test_anti_dup_layer_hit_documented(self, router_with_cards):
        """La respuesta debe indicar qué capa anti-doble se activó.

        Tras F1-D1, el primer dispatch pasa todas las capas → layer_hit='none'.
        Un segundo dispatch idéntico activaría TTL Freshness o Exact Match.
        """
        session = _unique_session("antidup")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        # El primer dispatch pasa todas las capas → 'none'
        assert result["anti_dup_layer_hit"] in ("none", "exact_match", "idempotency",
                                                  "ttl_freshness", "semantic_dedup",
                                                  "circuit_breaker")

    def test_orbital_resonance_in_range(self, router_with_cards):
        """orbital_resonance debe estar en [0, 1]."""
        session = _unique_session("resonance")
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        assert 0.0 <= result["orbital_resonance"] <= 1.0
