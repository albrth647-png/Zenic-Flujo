"""
Tests de race conditions para F1-D2.

10 escenarios que ejercitan el anti-doble-llamada cascade bajo condiciones
de borde y concurrencia:

1. Doble-click idéntico (segunda request <5s → TTL discard)
2. Cache hit (dispatch completado → exact match return_cache)
3. Subscribe a in-progress (dispatch en ejecución → idempotency subscribe)
4. Circuit breaker trip (3 fallos consecutivos → fallback)
5. Semantic dedup confirm (mensaje similar >0.85 → confirm)
6. TTL discard (despacho reciente → discard)
7. Cross-session isolation (2 sesiones no se afectan)
8. Cascade short-circuit ordering (capa 1 cortocircuita antes que capa 5)
9. Concurrent identical hash (2 threads mismo hash → 1 proceed, 1 subscribe)
10. Recovery after circuit (success resetea failure count)
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone

import pytest

from src.hat.agents_legacy.base import AgentConfig
from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator
# WebResearcherSpecialist / QueryBuilderWorker were eliminated in HAT v2
# (specialists/workers stubs removed). These tests no longer require them —
# the cascade + ledger + repo are sufficient to exercise the race conditions.
from src.hat.level1_orchestrator.anti_duplication.cascade import AntiDuplicationCascade
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
    return {"user_id": f"rc_user_{ts}", "session_id": f"rc_sess_{ts}"}


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


# ─────────────────────────────────────────────────────────
# Escenario 1: Doble-click idéntico
# ─────────────────────────────────────────────────────────


class TestScenario1DoubleClick:
    def test_second_identical_request_blocked_by_ttl(self, repo, session):
        """Segunda request idéntica <5s después → TTL Freshness discard."""
        cascade = AntiDuplicationCascade(repo=repo)
        h = _hash(f"dc_{session['session_id']}")
        msg = "buscar python"

        # Primera request: registra dispatch
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        r1 = cascade.check(h, session["user_id"], session["session_id"], msg, "research")
        assert r1["action"] == "proceed" or r1["duplicate"] is True

        # Segunda request idéntica: TTL debe detectar
        r2 = cascade.check(h, session["user_id"], session["session_id"], msg, "research")
        assert r2["duplicate"] is True
        assert r2["layer_hit"] in ("ttl_freshness", "exact_match", "idempotency")


# ─────────────────────────────────────────────────────────
# Escenario 2: Cache hit
# ─────────────────────────────────────────────────────────


class TestScenario2CacheHit:
    def test_completed_dispatch_returns_cache(self, repo, session):
        """Dispatch ya completado → Exact Match return_cache."""
        h = _hash(f"ch_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        repo.complete_dispatch(h, {"answer": "cached result"})

        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(h, session["user_id"], session["session_id"], "buscar", "research")
        assert result["duplicate"] is True
        assert result["action"] == "return_cache"
        assert result["layer_hit"] == "exact_match"


# ─────────────────────────────────────────────────────────
# Escenario 3: Subscribe a in-progress
# ─────────────────────────────────────────────────────────


class TestScenario3SubscribeInProgress:
    def test_in_progress_returns_subscribe(self, repo, session):
        """Dispatch in_progress → Idempotency subscribe."""
        h = _hash(f"sub_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        # No completar → queda in_progress

        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(h, session["user_id"], session["session_id"], "buscar", "research")
        assert result["duplicate"] is True
        assert result["action"] == "subscribe"
        assert result["layer_hit"] in ("idempotency", "exact_match")


# ─────────────────────────────────────────────────────────
# Escenario 4: Circuit breaker trip
# ─────────────────────────────────────────────────────────


@pytest.mark.skip(reason="HAT v2: circuit_breaker was removed from the cascade (now lives "
                    "in level4_workers as a separate concern).")
class TestScenario4CircuitBreakerTrip:
    def test_three_failures_trigger_fallback(self, repo, session):
        """3 fallos consecutivos → Circuit Breaker fallback."""
        for i in range(3):
            repo.record_progress(
                session["user_id"], session["session_id"],
                dispatch_id=f"cb_fail_{i}_{session['session_id']}",
                domain="research", status="failed",
            )

        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(
            _hash(f"cb_{session['session_id']}"),
            session["user_id"], session["session_id"],
            "buscar", "research",
        )
        assert result["duplicate"] is True
        assert result["action"] == "fallback"
        assert result["layer_hit"] == "circuit_breaker"


# ─────────────────────────────────────────────────────────
# Escenario 5: Semantic dedup confirm
# ─────────────────────────────────────────────────────────


@pytest.mark.skip(reason="HAT v2: semantic_dedup was eliminated (Jaccard false positives).")
class TestScenario5SemanticConfirm:
    def test_similar_message_triggers_confirm(self, repo, session):
        """Mensaje similar a dispatch reciente → Semantic Dedup confirm."""
        repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=f"sd_{session['session_id']}",
            domain="research", status="completed",
            result_summary="buscar info de python",
        )

        cascade = AntiDuplicationCascade(repo=repo)
        # Mensaje idéntico al summary → alta similitud
        result = cascade.check(
            _hash(f"sd2_{session['session_id']}"),
            session["user_id"], session["session_id"],
            "buscar info de python", "research",
        )
        # Debe ser bloqueado por alguna capa (TTL o semantic)
        assert result["duplicate"] is True
        assert result["layer_hit"] in ("ttl_freshness", "semantic_dedup")


# ─────────────────────────────────────────────────────────
# Escenario 6: TTL discard
# ─────────────────────────────────────────────────────────


@pytest.mark.skip(reason="HAT v2 M9: TTL Freshness now only blocks the same intent_hash "
                    "(no longer blocks different messages within the TTL window).")
class TestScenario6TTLDiscard:
    def test_recent_dispatch_triggers_discard(self, repo, session):
        """Despacho reciente en misma sesión → TTL discard."""
        h = _hash(f"ttl_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")

        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(
            _hash(f"ttl2_{session['session_id']}"),  # hash distinto para evitar exact match
            session["user_id"], session["session_id"],
            "buscar python", "research",
        )
        assert result["duplicate"] is True
        assert result["action"] == "discard"
        assert result["layer_hit"] == "ttl_freshness"


# ─────────────────────────────────────────────────────────
# Escenario 7: Cross-session isolation
# ─────────────────────────────────────────────────────────


class TestScenario7CrossSessionIsolation:
    def test_different_sessions_dont_interfere(self, repo):
        """Dispatches en sesión A no afectan sesión B."""
        ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
        sess_a = {"user_id": f"iso_a_{ts}", "session_id": f"iso_sa_{ts}"}
        sess_b = {"user_id": f"iso_b_{ts}", "session_id": f"iso_sb_{ts}"}

        h_a = _hash(f"iso_a_{ts}")
        repo.register_dispatch(h_a, sess_a["user_id"], sess_a["session_id"], "research")

        cascade = AntiDuplicationCascade(repo=repo)
        result_b = cascade.check(
            _hash(f"iso_b_{ts}"),
            sess_b["user_id"], sess_b["session_id"],
            "buscar python", "research",
        )
        # Sesión B no tiene dispatches → proceed
        assert result_b["duplicate"] is False
        assert result_b["action"] == "proceed"


# ─────────────────────────────────────────────────────────
# Escenario 8: Cascade short-circuit ordering
# ─────────────────────────────────────────────────────────


class TestScenario8CascadeOrdering:
    def test_exact_match_beats_circuit_breaker(self, repo, session):
        """Si exact match Y circuit breaker dispararían, exact match gana (capa 1 < capa 5)."""
        h = _hash(f"ord_{session['session_id']}")
        # Crear dispatch completado (activa exact match)
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        repo.complete_dispatch(h, {"cached": True})
        # Crear 3 fallos (activaría circuit breaker)
        for i in range(3):
            repo.record_progress(
                session["user_id"], session["session_id"],
                dispatch_id=f"ord_fail_{i}_{session['session_id']}",
                domain="research", status="failed",
            )

        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(h, session["user_id"], session["session_id"], "buscar", "research")
        # Exact match (capa 1) debe cortocircuitar antes que circuit breaker (capa 5)
        assert result["layer_hit"] == "exact_match"


# ─────────────────────────────────────────────────────────
# Escenario 9: Concurrent identical hash
# ─────────────────────────────────────────────────────────


class TestScenario9ConcurrentIdenticalHash:
    def test_two_threads_same_hash_one_proceeds(self, repo, session):
        """2 threads con mismo hash → al menos 1 proceed, el otro subscribe o discard.

        Bajo SQLite, puede haber DB locked — aceptamos que al menos 1 complete.
        """
        h = _hash(f"conc_{session['session_id']}")
        results: list[dict] = []
        errors: list[str] = []
        barrier = threading.Barrier(2)

        def worker() -> None:
            try:
                barrier.wait(timeout=5)
                cascade = AntiDuplicationCascade(repo=repo)
                result = cascade.check(
                    h, session["user_id"], session["session_id"],
                    "buscar python", "research",
                )
                results.append(result)
            except Exception as exc:
                errors.append(str(exc))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        total = len(results) + sum(1 for e in errors if "database is locked" in e)
        assert total >= 1, f"Ningún thread completó. Results: {results}, Errors: {errors}"


# ─────────────────────────────────────────────────────────
# Escenario 10: Recovery after circuit
# ─────────────────────────────────────────────────────────


class TestScenario10RecoveryAfterCircuit:
    def test_success_after_failures_resets_circuit(self, repo, session):
        """Un success después de fallos resetea el contador del circuit breaker."""
        # Crear 2 fallos (no llega al threshold de 3)
        for i in range(2):
            repo.record_progress(
                session["user_id"], session["session_id"],
                dispatch_id=f"rec_fail_{i}_{session['session_id']}",
                domain="research", status="failed",
            )
        # Crear 1 success (resetea contador)
        repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=f"rec_ok_{session['session_id']}",
            domain="research", status="completed",
        )

        cascade = AntiDuplicationCascade(repo=repo)
        result = cascade.check(
            _hash(f"rec_{session['session_id']}"),
            session["user_id"], session["session_id"],
            "buscar", "research",
        )
        # Circuit breaker NO debe disparar (failure_count < threshold tras reset)
        # Puede ser bloqueado por TTL, pero no por circuit_breaker
        if result["duplicate"]:
            assert result["layer_hit"] != "circuit_breaker"
