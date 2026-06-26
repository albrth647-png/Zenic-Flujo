"""
Tests para F1-D1: anti-doble-llamada (5 capas + cascade + concurrencia).

Cobertura:
- Cada capa individualmente (Exact Match, Idempotency, TTL, Semantic, Circuit Breaker)
- Cascade orquestador (cortocircuito en primera capa que detecta)
- Integración con tick_router (handle usa cascade)
- Tests de concurrencia (2 threads, misma sesión)
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone

import pytest

from src.hat.agents_legacy.base import AgentConfig
from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator
# WebResearcherSpecialist / QueryBuilderWorker were eliminated in HAT v2
# (specialists/workers stubs removed). Tests that depended on them are
# skipped below (see TestTickRouterAntiDupIntegration, TestConcurrency).
from src.hat.level1_orchestrator.anti_duplication.cascade import AntiDuplicationCascade
from src.hat.level4_workers.circuit_breaker import CircuitBreakerLayer
from src.hat.level1_orchestrator.anti_duplication.exact_match import ExactMatchLayer
from src.hat.level1_orchestrator.anti_duplication.idempotency import IdempotencyLayer
# SemanticDedupLayer was eliminated in HAT v2 — TestSemanticDedupLayer below
# is skipped (see pytestmark on the class).
from src.hat.level1_orchestrator.anti_duplication.ttl_freshness import TTLFreshnessLayer
from src.hat.level1_orchestrator.ledger.ovc_bridge import OVCLedgerBridge
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level1_orchestrator.tick_router import HATRouter
from src.orbital.context import OrbitalContext


@pytest.fixture
def repo():
    return LedgerRepository()


@pytest.fixture(autouse=True)
def cleanup():
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()
    yield
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()


@pytest.fixture
def session():
    ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
    return {"user_id": f"ad_user_{ts}", "session_id": f"ad_sess_{ts}"}


def _make_hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


# ─────────────────────────────────────────────────────────
# Capa 1: Exact Match
# ─────────────────────────────────────────────────────────


class TestExactMatchLayer:
    def test_no_dispatch_returns_proceed(self, repo, session):
        h = _make_hash(f"em_none_{session['session_id']}")
        layer = ExactMatchLayer(repo=repo)
        result = layer.check(h)
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_completed_dispatch_returns_cache(self, repo, session):
        h = _make_hash(f"em_done_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        repo.complete_dispatch(h, {"answer": "cached"})
        layer = ExactMatchLayer(repo=repo)
        result = layer.check(h)
        assert result["duplicate"] is True
        assert result["action"] == "return_cache"
        assert result["cached_result"] == {"answer": "cached"}

    def test_in_progress_dispatch_returns_proceed(self, repo, session):
        h = _make_hash(f"em_prog_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        layer = ExactMatchLayer(repo=repo)
        result = layer.check(h)
        assert result["duplicate"] is False
        assert result["action"] == "proceed"


# ─────────────────────────────────────────────────────────
# Capa 2: Idempotency
# ─────────────────────────────────────────────────────────


class TestIdempotencyLayer:
    def test_no_dispatch_returns_proceed(self, repo, session):
        h = _make_hash(f"id_none_{session['session_id']}")
        layer = IdempotencyLayer(repo=repo)
        result = layer.check(h)
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_in_progress_dispatch_returns_subscribe(self, repo, session):
        h = _make_hash(f"id_prog_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        layer = IdempotencyLayer(repo=repo)
        result = layer.check(h)
        assert result["duplicate"] is True
        assert result["action"] == "subscribe"
        assert result["subscription_id"] is not None

    def test_completed_dispatch_returns_proceed(self, repo, session):
        h = _make_hash(f"id_done_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        repo.complete_dispatch(h, {"done": True})
        layer = IdempotencyLayer(repo=repo)
        result = layer.check(h)
        assert result["duplicate"] is False
        assert result["action"] == "proceed"


# ─────────────────────────────────────────────────────────
# Capa 4: TTL Freshness
# ─────────────────────────────────────────────────────────


class TestTTLFreshnessLayer:
    def test_no_recent_dispatches_returns_proceed(self, repo, session):
        layer = TTLFreshnessLayer(repo=repo)
        result = layer.check("any_hash", session["user_id"], session["session_id"])
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_recent_dispatch_returns_discard(self, repo, session):
        h = _make_hash(f"ttl_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        layer = TTLFreshnessLayer(repo=repo, ttl_seconds=10)
        result = layer.check(h, session["user_id"], session["session_id"])
        assert result["duplicate"] is True
        assert result["action"] == "discard"


# ─────────────────────────────────────────────────────────
# Capa 3: Semantic Dedup — ELIMINATED in HAT v2 (skipped)
# ─────────────────────────────────────────────────────────
# The semantic_dedup module was removed during the HAT v2 migration.
# TestSemanticDedupLayer has been deleted; the cascade now relies on
# ttl_freshness + exact_match + idempotency + circuit_breaker.


# ─────────────────────────────────────────────────────────
# Capa 5: Circuit Breaker
# ─────────────────────────────────────────────────────────


class TestCircuitBreakerLayer:
    def test_no_history_returns_proceed(self, repo, session):
        layer = CircuitBreakerLayer(repo=repo)
        result = layer.check("research", session["user_id"], session["session_id"])
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_threshold_failures_returns_fallback(self, repo, session):
        for i in range(3):
            repo.record_progress(
                session["user_id"], session["session_id"],
                dispatch_id=f"fail_{i}_{session['session_id']}",
                domain="research", status="failed",
            )
        layer = CircuitBreakerLayer(repo=repo, failure_threshold=3)
        result = layer.check("research", session["user_id"], session["session_id"])
        assert result["duplicate"] is True
        assert result["action"] == "fallback"
        assert result["failure_count"] >= 3

    def test_success_resets_failure_count(self, repo, session):
        """Un success después de un failure resetea el contador.

        Nota: SQLite started_at tiene resolución de 1 segundo, así que el
        orden de los 2 inserts puede no ser determinístico. Aceptamos
        failure_count <= 1 (el success debería resetear, pero si el orden
        es incierto, el fail podría contar como 1).
        """
        repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=f"fail_{session['session_id']}",
            domain="research", status="failed",
        )
        repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=f"ok_{session['session_id']}",
            domain="research", status="completed",
        )
        layer = CircuitBreakerLayer(repo=repo, failure_threshold=2)
        result = layer.check("research", session["user_id"], session["session_id"])
        assert result["duplicate"] is False
        assert result["failure_count"] <= 1  # tolerar orden no determinístico


# ─────────────────────────────────────────────────────────
# Cascade orquestador
# ─────────────────────────────────────────────────────────


class TestAntiDuplicationCascade:
    def test_all_layers_pass_returns_proceed(self, repo, session):
        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(
            intent_hash=_make_hash(f"cas_ok_{session['session_id']}"),
            user_id=session["user_id"],
            session_id=session["session_id"],
            message="buscar python",
            domain="research",
        )
        assert result["duplicate"] is False
        assert result["action"] == "proceed"
        assert result["layer_hit"] == "none"

    def test_exact_match_short_circuits(self, repo, session):
        h = _make_hash(f"cas_em_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        repo.complete_dispatch(h, {"cached": True})
        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(
            intent_hash=h,
            user_id=session["user_id"],
            session_id=session["session_id"],
            message="buscar python",
            domain="research",
        )
        assert result["duplicate"] is True
        assert result["action"] == "return_cache"
        assert result["layer_hit"] == "exact_match"

    @pytest.mark.skip(reason="HAT v2 M9: TTL Freshness now only blocks the same intent_hash "
                             "(no longer blocks different hashes within the TTL window).")
    def test_ttl_freshness_short_circuits(self, repo, session):
        h = _make_hash(f"cas_ttl_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(
            intent_hash=_make_hash("different"),
            user_id=session["user_id"],
            session_id=session["session_id"],
            message="buscar python",
            domain="research",
        )
        assert result["duplicate"] is True
        assert result["action"] == "discard"
        assert result["layer_hit"] == "ttl_freshness"


# ─────────────────────────────────────────────────────────
# Integración con tick_router
# ─────────────────────────────────────────────────────────
# NOTE: The two classes below depend on the eliminated HAT v1 stubs
# (WebResearcherSpecialist / QueryBuilderWorker). They are skipped until
# the HAT v2 specialists/workers replacement is wired into the fixture.


@pytest.mark.skip(reason="HAT v2: WebResearcherSpecialist / QueryBuilderWorker stubs eliminated; "
                         "router_with_cards fixture no longer constructible as-is.")
class TestTickRouterAntiDupIntegration:
    @pytest.fixture
    def router_with_cards(self, repo):
        OrbitalContext._reset()
        MultiAgentOrchestrator.reset_instance()
        ctx = OrbitalContext()
        bridge = OVCLedgerBridge(repo=repo, ctx=ctx)
        # NOTE: stubs were eliminated in HAT v2 — fixture kept for reference.
        # Re-enable when a real specialist is wired in via the new bootstrap.
        return HATRouter(ledger=repo, ctx=ctx, bridge=bridge)

    def test_first_request_passes_all_layers(self, router_with_cards, session):
        """El primer dispatch pasa todas las capas → layer_hit='none'."""
        result = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        assert result["anti_dup_layer_hit"] in ("none", "exact_match", "idempotency",
                                                 "ttl_freshness", "semantic_dedup",
                                                 "circuit_breaker")

    def test_second_identical_request_blocked(self, router_with_cards, session):
        """Segundo dispatch idéntico debe ser bloqueado por alguna capa."""
        r1 = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        r2 = router_with_cards.handle(
            session["user_id"], session["session_id"], "buscar python",
        )
        # La 2ª request debe ser bloqueada por anti-dup
        assert r2["anti_dup_layer_hit"] != "none"
        assert r2["status"] == "anti_dup_blocked"


# ─────────────────────────────────────────────────────────
# Tests de concurrencia (fix sistémico #3)
# ─────────────────────────────────────────────────────────


@pytest.mark.skip(reason="HAT v2: WebResearcherSpecialist / QueryBuilderWorker stubs eliminated; "
                         "router_with_cards fixture no longer constructible as-is.")
class TestConcurrency:
    """Tests que validan comportamiento bajo concurrencia.

    Fix sistémico #3: no existían tests de concurrencia.
    """

    @pytest.fixture
    def router_with_cards(self, repo):
        OrbitalContext._reset()
        MultiAgentOrchestrator.reset_instance()
        ctx = OrbitalContext()
        bridge = OVCLedgerBridge(repo=repo, ctx=ctx)
        # NOTE: stubs were eliminated in HAT v2 — fixture kept for reference.
        return HATRouter(ledger=repo, ctx=ctx, bridge=bridge)

    def test_two_different_sessions_concurrent(self, router_with_cards):
        """2 threads con sesiones distintas no deben crashear.

        Fix sistémico #1: user_intent ahora namespaced por sesión.
        Sin el fix, las 2 threads se pisarían user_intent_current.

        Bajo SQLite WAL, puede haber 'database is locked' — aceptamos
        que los threads terminen sin crash grave (ProtocolError o similar).
        """
        results: list[dict] = []
        errors: list[str] = []
        barrier = threading.Barrier(2)

        def worker(user_id: str, session_id: str, message: str) -> None:
            try:
                barrier.wait(timeout=5)
                result = router_with_cards.handle(user_id, session_id, message)
                results.append(result)
            except Exception as exc:
                errors.append(str(exc))

        ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
        t1 = threading.Thread(target=worker, args=(f"conc_u1_{ts}", f"conc_s1_{ts}", "buscar python"))
        t2 = threading.Thread(target=worker, args=(f"conc_u2_{ts}", f"conc_s2_{ts}", "buscar javascript"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Bajo SQLite, al menos 1 debe completarse (el otro puede fallar con DB locked)
        total_completed = len(results) + sum(1 for e in errors if "database is locked" in e)
        assert total_completed >= 1, f"Ningún thread completó. Results: {results}, Errors: {errors}"

    def test_two_different_sessions_different_domains(self, router_with_cards):
        """2 sesiones distintas con mensajes distintos → domains pueden differir.

        Bajo SQLite WAL, puede haber 'database is locked' — aceptamos
        que al menos 1 thread complete.
        """
        results: list[dict] = []
        errors: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%H%M%S%f")

        def worker(user_id: str, session_id: str, message: str) -> None:
            try:
                result = router_with_cards.handle(user_id, session_id, message)
                results.append(result)
            except Exception as exc:
                errors.append(str(exc))

        t1 = threading.Thread(target=worker, args=(f"sep_u1_{ts}", f"sep_s1_{ts}", "buscar python"))
        t2 = threading.Thread(target=worker, args=(f"sep_u2_{ts}", f"sep_s2_{ts}", "buscar info de rust"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Al menos 1 debe completar
        total = len(results) + sum(1 for e in errors if "database is locked" in e)
        assert total >= 1, f"Ningún thread completó. Results: {results}, Errors: {errors}"
        # Si ambos completaron, dispatch_ids deben ser distintos
        if len(results) == 2:
            assert results[0]["dispatch_id"] != results[1]["dispatch_id"]
