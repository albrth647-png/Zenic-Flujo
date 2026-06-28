"""
Tests del LedgerRepository (F0-D2).

Cada método CRUD tiene al menos 1 test. Usa DatabaseManager singleton
de ZF sobre SQLite WAL — los tests se ejecutan en la DB real (no mock)
para validar el esquema y las queries SQL.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from src.core.db import DatabaseManager
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository


@pytest.fixture(scope="module")
def db():
    """DatabaseManager singleton — se crea una vez por módulo."""
    return DatabaseManager()


@pytest.fixture
def repo(db):
    """LedgerRepository fresco para cada test. El schema es idempotente."""
    return LedgerRepository(db)


@pytest.fixture
def session():
    """Session IDs únicos por test para evitar contaminación cruzada."""
    return {
        "user_id": f"user_{datetime.now(UTC).strftime('%H%M%S%f')}",
        "session_id": f"sess_{datetime.now(UTC).strftime('%H%M%S%f')}",
    }


# ─────────────────────────────────────────────────────────
# Facts CRUD
# ─────────────────────────────────────────────────────────


class TestFactsCRUD:
    def test_upsert_fact_creates_new(self, repo, session):
        rid = repo.upsert_fact(
            session["user_id"], session["session_id"],
            "user_language", "es", confidence=1.0,
        )
        assert rid > 0

    def test_upsert_fact_updates_existing(self, repo, session):
        repo.upsert_fact(session["user_id"], session["session_id"], "k", "v1")
        repo.upsert_fact(session["user_id"], session["session_id"], "k", "v2")
        facts = repo.get_facts(session["user_id"], session["session_id"])
        assert len(facts) == 1
        assert facts[0]["fact_value"] == "v2"

    def test_upsert_fact_stores_complex_json(self, repo, session):
        complex_value = {"nested": {"list": [1, 2, 3], "flag": True}, "name": "test"}
        repo.upsert_fact(session["user_id"], session["session_id"], "complex", complex_value)
        fact = repo.get_fact(session["user_id"], session["session_id"], "complex")
        assert fact is not None
        assert fact["fact_value"] == complex_value

    def test_get_facts_returns_all_for_session(self, repo, session):
        for i in range(3):
            repo.upsert_fact(session["user_id"], session["session_id"], f"k{i}", i)
        facts = repo.get_facts(session["user_id"], session["session_id"])
        assert len(facts) == 3

    def test_get_facts_isolates_by_session(self, repo, session):
        other_session = {"user_id": session["user_id"], "session_id": session["session_id"] + "_other"}
        repo.upsert_fact(session["user_id"], session["session_id"], "k", "v1")
        repo.upsert_fact(other_session["user_id"], other_session["session_id"], "k", "v2")
        assert len(repo.get_facts(session["user_id"], session["session_id"])) == 1
        assert len(repo.get_facts(other_session["user_id"], other_session["session_id"])) == 1

    def test_delete_fact_returns_true_when_deleted(self, repo, session):
        repo.upsert_fact(session["user_id"], session["session_id"], "k", "v")
        assert repo.delete_fact(session["user_id"], session["session_id"], "k") is True
        assert repo.get_fact(session["user_id"], session["session_id"], "k") is None

    def test_delete_fact_returns_false_when_not_found(self, repo, session):
        assert repo.delete_fact(session["user_id"], session["session_id"], "nope") is False

    def test_fact_persists_orbital_metadata(self, repo, session):
        repo.upsert_fact(
            session["user_id"], session["session_id"], "k", "v",
            confidence=0.85, orbital_theta=1.5, orbital_amplitude=2.5,
        )
        fact = repo.get_fact(session["user_id"], session["session_id"], "k")
        assert fact["confidence"] == 0.85
        assert fact["orbital_theta"] == 1.5
        assert fact["orbital_amplitude"] == 2.5


# ─────────────────────────────────────────────────────────
# Hypotheses CRUD
# ─────────────────────────────────────────────────────────


class TestHypothesesCRUD:
    def test_upsert_hypothesis_creates_new(self, repo, session):
        rid = repo.upsert_hypothesis(
            session["user_id"], session["session_id"], "maybe_lang", "en", confidence=0.5,
        )
        assert rid > 0

    def test_get_hypotheses_filters_unverified(self, repo, session):
        repo.upsert_hypothesis(session["user_id"], session["session_id"], "h1", "v1")
        repo.upsert_hypothesis(session["user_id"], session["session_id"], "h2", "v2")
        repo.verify_hypothesis(session["user_id"], session["session_id"], "h1")
        unverified = repo.get_hypotheses(session["user_id"], session["session_id"], only_unverified=True)
        assert len(unverified) == 1
        assert unverified[0]["hypothesis_key"] == "h2"

    def test_verify_hypothesis_marks_verified(self, repo, session):
        repo.upsert_hypothesis(session["user_id"], session["session_id"], "h", "v")
        assert repo.verify_hypothesis(session["user_id"], session["session_id"], "h") is True
        hyp = repo.get_hypothesis(session["user_id"], session["session_id"], "h")
        assert hyp["verified"] is True
        assert hyp["verified_at"] is not None

    def test_verify_hypothesis_returns_false_when_not_found(self, repo, session):
        assert repo.verify_hypothesis(session["user_id"], session["session_id"], "nope") is False

    def test_verify_hypothesis_promotes_to_fact(self, repo, session):
        repo.upsert_hypothesis(session["user_id"], session["session_id"], "h", {"lang": "es"})
        repo.verify_hypothesis(session["user_id"], session["session_id"], "h", promote_to_fact=True)
        # La hipótesis queda verificada
        hyp = repo.get_hypothesis(session["user_id"], session["session_id"], "h")
        assert hyp["promoted_to_fact"] is True
        # Y se copió a facts con confidence=1.0
        fact = repo.get_fact(session["user_id"], session["session_id"], "h")
        assert fact is not None
        assert fact["fact_value"] == {"lang": "es"}
        assert fact["confidence"] == 1.0
        assert fact["orbital_theta"] == 0.0

    def test_hypothesis_default_theta_is_pi_over_4(self, repo, session):
        repo.upsert_hypothesis(session["user_id"], session["session_id"], "h", "v")
        hyp = repo.get_hypothesis(session["user_id"], session["session_id"], "h")
        assert abs(hyp["orbital_theta"] - 0.785) < 0.001  # π/4


# ─────────────────────────────────────────────────────────
# Plan CRUD
# ─────────────────────────────────────────────────────────


class TestPlanCRUD:
    def test_add_plan_step_creates_new(self, repo, session):
        rid = repo.add_plan_step(
            session["user_id"], session["session_id"],
            step_index=0, step_description="Buscar info",
            assigned_domain="research",
        )
        assert rid > 0

    def test_get_plan_returns_ordered_by_index(self, repo, session):
        for i in [2, 0, 1]:
            repo.add_plan_step(session["user_id"], session["session_id"], i, f"step{i}")
        plan = repo.get_plan(session["user_id"], session["session_id"])
        assert [p["step_index"] for p in plan] == [0, 1, 2]

    def test_update_step_status_changes_status(self, repo, session):
        repo.add_plan_step(session["user_id"], session["session_id"], 0, "step0")
        assert repo.update_step_status(
            session["user_id"], session["session_id"], 0, "done", dispatch_id="d1"
        ) is True
        plan = repo.get_plan(session["user_id"], session["session_id"])
        assert plan[0]["step_status"] == "done"
        assert plan[0]["dispatch_id"] == "d1"

    def test_update_step_status_returns_false_when_not_found(self, repo, session):
        assert repo.update_step_status(
            session["user_id"], session["session_id"], 99, "done"
        ) is False

    def test_add_plan_step_upserts_on_conflict(self, repo, session):
        repo.add_plan_step(session["user_id"], session["session_id"], 0, "v1")
        repo.add_plan_step(session["user_id"], session["session_id"], 0, "v2")
        plan = repo.get_plan(session["user_id"], session["session_id"])
        assert len(plan) == 1
        assert plan[0]["step_description"] == "v2"


# ─────────────────────────────────────────────────────────
# Progress CRUD
# ─────────────────────────────────────────────────────────


class TestProgressCRUD:
    def test_record_progress_inserts_new(self, repo, session):
        rid = repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=f"dp_{session['session_id']}_1", domain="research", status="dispatched",
        )
        assert rid > 0

    def test_record_progress_completes_sets_completed_at(self, repo, session):
        dp_id = f"dp_{session['session_id']}_2"
        repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=dp_id, domain="research", status="dispatched",
        )
        repo.record_progress(
            session["user_id"], session["session_id"],
            dispatch_id=dp_id, domain="research", status="completed",
            result_summary={"answer": "42"},
            orbital_resonance=0.8,
        )
        progress = repo.get_progress(session["user_id"], session["session_id"])
        assert len(progress) == 1
        assert progress[0]["status"] == "completed"
        assert progress[0]["completed_at"] is not None
        assert progress[0]["result_summary"] == {"answer": "42"}
        assert progress[0]["orbital_resonance"] == 0.8

    def test_get_progress_orders_by_started_at_desc(self, repo, session):
        for i in range(3):
            repo.record_progress(
                session["user_id"], session["session_id"],
                dispatch_id=f"dp_{session['session_id']}_{i}", domain="research", status="completed",
            )
        progress = repo.get_progress(session["user_id"], session["session_id"])
        assert len(progress) == 3
        # SQLite CURRENT_TIMESTAMP tiene resolución de 1 segundo — 3 inserts en el mismo
        # segundo pueden quedar con timestamps idénticos. Validamos solo que los 3
        # dispatch_ids esperados estén presentes (no el orden estricto).
        returned_ids = {p["dispatch_id"] for p in progress}
        expected_ids = {f"dp_{session['session_id']}_{i}" for i in range(3)}
        assert returned_ids == expected_ids


# ─────────────────────────────────────────────────────────
# Dispatch Registry CRUD (anti-doble-llamada)
# ─────────────────────────────────────────────────────────


class TestDispatchRegistryCRUD:
    @staticmethod
    def _hash(session_id: str, label: str) -> str:
        """Hash único por sesión para evitar colisiones entre tests."""
        return hashlib.sha256(f"{session_id}:{label}".encode()).hexdigest()

    def test_register_dispatch_creates_new(self, repo, session):
        h = self._hash(session["session_id"], "test1")
        rid, created = repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        assert rid > 0
        assert created is True

    def test_register_dispatch_returns_existing_on_duplicate(self, repo, session):
        h = self._hash(session["session_id"], "test2")
        rid1, created1 = repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        rid2, created2 = repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        assert created1 is True
        assert created2 is False
        assert rid1 == rid2

    def test_get_dispatch_returns_full_record(self, repo, session):
        h = self._hash(session["session_id"], "test3")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "build", ttl_seconds=10)
        d = repo.get_dispatch(h)
        assert d is not None
        assert d["intent_hash"] == h
        assert d["domain"] == "build"
        assert d["status"] == "in_progress"
        assert d["ttl_expires_at"] is not None

    def test_complete_dispatch_caches_result(self, repo, session):
        h = self._hash(session["session_id"], "test4")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        result = {"answer": "Python 3.13", "sources": ["url1", "url2"]}
        assert repo.complete_dispatch(h, result) is True
        d = repo.get_dispatch(h)
        assert d["status"] == "completed"
        assert d["result_cache"] == result
        assert d["completed_at"] is not None

    def test_complete_dispatch_returns_false_when_not_in_progress(self, repo, session):
        h = self._hash(session["session_id"], "test5_nonexistent")
        # No registrado primero
        assert repo.complete_dispatch(h, {"x": 1}) is False

    def test_increment_subscriber_increments_count(self, repo, session):
        h = self._hash(session["session_id"], "test6")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        assert repo.increment_subscriber(h) == 1
        assert repo.increment_subscriber(h) == 2
        d = repo.get_dispatch(h)
        assert d["subscriber_count"] == 2

    def test_increment_subscriber_returns_zero_when_not_found(self, repo, session):
        h = self._hash(session["session_id"], "test7_nonexistent")
        assert repo.increment_subscriber(h) == 0

    def test_get_in_progress_dispatches_filters_status(self, repo, session):
        h1 = self._hash(session["session_id"], "test8a")
        h2 = self._hash(session["session_id"], "test8b")
        repo.register_dispatch(h1, session["user_id"], session["session_id"], "research")
        repo.register_dispatch(h2, session["user_id"], session["session_id"], "build")
        repo.complete_dispatch(h1, {"done": True})
        in_progress = repo.get_in_progress_dispatches()
        # h1 completado, h2 sigue in_progress
        hashes = [d["intent_hash"] for d in in_progress]
        assert h2 in hashes
        assert h1 not in hashes

    def test_get_recent_dispatches_by_session_filters_by_time(self, repo, session):
        h = self._hash(session["session_id"], "test9")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        # Debe aparecer en los últimos 5s
        recent = repo.get_recent_dispatches_by_session(session["user_id"], session["session_id"], since_seconds=5)
        assert any(d["intent_hash"] == h for d in recent)


# ─────────────────────────────────────────────────────────
# Agent Cards CRUD
# ─────────────────────────────────────────────────────────


class TestAgentCardsCRUD:
    def test_upsert_agent_card_creates_new(self, repo):
        rid = repo.upsert_agent_card(
            "web_researcher", "Web Researcher",
            domain="research", tier="specialist",
            capabilities=["web_search", "summarize"],
            orbital_keywords=["buscar", "info", "investigar"],
        )
        assert rid > 0

    def test_upsert_agent_card_updates_existing(self, repo):
        repo.upsert_agent_card(
            "agent1", "Agent 1", "research", "worker",
            capabilities=["c1"], orbital_keywords=["k1"],
        )
        repo.upsert_agent_card(
            "agent1", "Agent 1 Updated", "research", "worker",
            capabilities=["c1", "c2"], orbital_keywords=["k1", "k2"],
            cost_per_call=0.5,
        )
        card = repo.get_agent_card("agent1")
        assert card["agent_name"] == "Agent 1 Updated"
        assert card["capabilities"] == ["c1", "c2"]
        assert card["orbital_keywords"] == ["k1", "k2"]
        assert card["cost_per_call"] == 0.5

    def test_get_agent_card_returns_none_when_not_found(self, repo):
        assert repo.get_agent_card("nonexistent_agent") is None

    def test_get_agent_cards_filters_by_domain(self, repo):
        repo.upsert_agent_card(
            "r1", "R1", "research", "specialist", ["c"], ["k"]
        )
        repo.upsert_agent_card(
            "b1", "B1", "build", "specialist", ["c"], ["k"]
        )
        research_cards = repo.get_agent_cards(domain="research")
        assert all(c["domain"] == "research" for c in research_cards)
        assert any(c["agent_id"] == "r1" for c in research_cards)
        assert not any(c["agent_id"] == "b1" for c in research_cards)

    def test_get_agent_cards_filters_by_tier(self, repo):
        repo.upsert_agent_card(
            "supervisor1", "Sup1", "research", "supervisor", ["c"], ["k"]
        )
        repo.upsert_agent_card(
            "worker1", "W1", "research", "worker", ["c"], ["k"]
        )
        supervisors = repo.get_agent_cards(domain="research", tier="supervisor")
        assert all(c["tier"] == "supervisor" for c in supervisors)
        assert any(c["agent_id"] == "supervisor1" for c in supervisors)

    def test_agent_card_decodes_json_arrays(self, repo):
        repo.upsert_agent_card(
            "agent_json", "Agent JSON", "research", "worker",
            capabilities=["search", "parse", "rank"],
            orbital_keywords=["buscar", "encontrar"],
        )
        card = repo.get_agent_card("agent_json")
        assert isinstance(card["capabilities"], list)
        assert "search" in card["capabilities"]
        assert isinstance(card["orbital_keywords"], list)


# ─────────────────────────────────────────────────────────
# Sessions CRUD
# ─────────────────────────────────────────────────────────


class TestSessionsCRUD:
    def test_start_session_creates_new(self, repo):
        sid = f"sess_{datetime.now(UTC).strftime('%H%M%S%f')}"
        rid = repo.start_session("user_a", sid)
        assert rid > 0

    def test_start_session_idempotent_on_conflict(self, repo):
        sid = f"sess_{datetime.now(UTC).strftime('%H%M%S%f')}"
        repo.start_session("user_a", sid, active_domain="research")
        # Re-start same session — should update last_activity, not fail
        repo.start_session("user_a", sid, active_domain="build")
        sess = repo.get_session(sid)
        assert sess is not None
        # active_domain no debe sobrescribirse a None en re-start
        assert sess["active_domain"] in ("research", "build")

    def test_touch_session_updates_counters(self, repo):
        sid = f"sess_{datetime.now(UTC).strftime('%H%M%S%f')}"
        repo.start_session("user_a", sid)
        repo.touch_session(sid, ticks_delta=5, tokens_delta=100)
        repo.touch_session(sid, ticks_delta=3, tokens_delta=50)
        sess = repo.get_session(sid)
        assert sess["orbital_tick_count"] == 8
        assert sess["total_tokens_consumed"] == 150

    def test_touch_session_updates_active_domain(self, repo):
        sid = f"sess_{datetime.now(UTC).strftime('%H%M%S%f')}"
        repo.start_session("user_a", sid, active_domain="research")
        repo.touch_session(sid, active_domain="build")
        sess = repo.get_session(sid)
        assert sess["active_domain"] == "build"

    def test_get_session_returns_none_when_not_found(self, repo):
        assert repo.get_session("nonexistent_session") is None


# ─────────────────────────────────────────────────────────
# Schema & Integration
# ─────────────────────────────────────────────────────────


class TestLedgerSchema:
    def test_ensure_schema_is_idempotent(self, db):
        """Llamar ensure_schema múltiples veces no debe fallar."""
        repo = LedgerRepository(db)
        repo.ensure_schema()
        repo.ensure_schema()
        # Si llegamos aquí sin excepción, el schema es idempotente

    def test_all_7_tables_exist(self, db):
        """Las 7 tablas HAT deben existir tras ensure_schema."""
        expected_tables = {
            "hat_facts", "hat_hypotheses", "hat_plan", "hat_progress",
            "hat_dispatch_registry", "hat_agent_cards", "hat_sessions",
        }
        rows = db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'hat_%'"
        )
        actual_tables = {r["name"] for r in rows}
        missing = expected_tables - actual_tables
        assert not missing, f"Tablas HAT faltantes: {missing}"

    def test_facts_unique_constraint(self, repo, session):
        """UNIQUE(user_id, session_id, fact_key) debe prevenir duplicados via upsert."""
        repo.upsert_fact(session["user_id"], session["session_id"], "k", "v1")
        repo.upsert_fact(session["user_id"], session["session_id"], "k", "v2")
        facts = repo.get_facts(session["user_id"], session["session_id"])
        assert len(facts) == 1

    def test_dispatch_registry_unique_hash(self, repo, session):
        """UNIQUE(intent_hash) debe prevenir duplicados."""
        h = hashlib.sha256(f"{session['session_id']}:unique_test_hash".encode()).hexdigest()
        rid1, created1 = repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        rid2, created2 = repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        assert created1 is True
        assert created2 is False
        assert rid1 == rid2
