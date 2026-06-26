"""Tests para LedgerRepository — CRUD sobre las 3 tablas HAT del Ledger.

Cubre:
- hat_facts: upsert, get, get_all, delete (UNIQUE constraint, JSON encode/decode).
- hat_hypotheses: upsert, get, get_all (only_unverified), verify (con/sin promote).
- hat_progress: record, get_progress, register_dispatch, get_dispatch, complete_dispatch.
- _decode_dispatch alias de compatibilidad (result_cache → result_summary).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.hat.level1_orchestrator.ledger.repository import LedgerRepository


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Ruta a DB SQLite temporal."""
    return tmp_path / "test_hats.db"


@pytest.fixture
def repo(tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> LedgerRepository:
    """LedgerRepository con DatabaseManager apuntando a DB temporal."""
    import src.core.db.sqlite_manager as sm_module
    from src.core.db.sqlite_manager import DatabaseManager

    original_instance = DatabaseManager._instance
    original_db_path = sm_module.DB_PATH

    DatabaseManager._instance = None
    monkeypatch.setattr(sm_module, "DB_PATH", tmp_db_path)

    db = DatabaseManager()
    assert db._db_path == tmp_db_path

    yield LedgerRepository()

    try:
        db.close_connection()
    except Exception:
        pass
    DatabaseManager._instance = original_instance
    monkeypatch.setattr(sm_module, "DB_PATH", original_db_path)


# ── Tests de hat_facts ─────────────────────────────────────────────────


class TestFacts:
    """CRUD sobre hat_facts."""

    def test_upsert_creates_new_fact(self, repo: LedgerRepository) -> None:
        """upsert_fact inserta un Fact nuevo."""
        row_id = repo.upsert_fact("u1", "s1", "color", "azul")
        assert row_id > 0
        fact = repo.get_fact("u1", "s1", "color")
        assert fact is not None
        assert fact["fact_value"] == "azul"
        assert fact["confidence"] == 1.0
        assert fact["orbital_theta"] == 0.0

    def test_upsert_updates_existing_fact(self, repo: LedgerRepository) -> None:
        """upsert_fact actualiza un Fact existente (UNIQUE constraint)."""
        repo.upsert_fact("u1", "s1", "color", "azul")
        repo.upsert_fact("u1", "s1", "color", "rojo")
        fact = repo.get_fact("u1", "s1", "color")
        assert fact is not None
        assert fact["fact_value"] == "rojo"

    def test_get_fact_returns_none_if_missing(self, repo: LedgerRepository) -> None:
        """get_fact retorna None si no existe."""
        assert repo.get_fact("u1", "s1", "inexistente") is None

    def test_get_facts_returns_all_sorted(self, repo: LedgerRepository) -> None:
        """get_facts retorna todos los facts ordenados por fact_key."""
        repo.upsert_fact("u1", "s1", "zeta", "1")
        repo.upsert_fact("u1", "s1", "alpha", "2")
        facts = repo.get_facts("u1", "s1")
        keys = [f["fact_key"] for f in facts]
        assert keys == ["alpha", "zeta"]

    def test_get_facts_isolates_by_session(self, repo: LedgerRepository) -> None:
        """Facts de una sesión no aparecen en otra."""
        repo.upsert_fact("u1", "s1", "k1", "v1")
        repo.upsert_fact("u1", "s2", "k2", "v2")
        assert len(repo.get_facts("u1", "s1")) == 1
        assert len(repo.get_facts("u1", "s2")) == 1

    def test_delete_fact_returns_true_when_deleted(self, repo: LedgerRepository) -> None:
        """delete_fact retorna True si eliminó."""
        repo.upsert_fact("u1", "s1", "k1", "v1")
        assert repo.delete_fact("u1", "s1", "k1") is True
        assert repo.delete_fact("u1", "s1", "k1") is False

    def test_fact_value_json_encoded(self, repo: LedgerRepository) -> None:
        """fact_value se serializa como JSON."""
        repo.upsert_fact("u1", "s1", "data", {"nested": [1, 2, 3]})
        fact = repo.get_fact("u1", "s1", "data")
        assert fact is not None
        assert fact["fact_value"] == {"nested": [1, 2, 3]}


# ── Tests de hat_hypotheses ────────────────────────────────────────────


class TestHypotheses:
    """CRUD sobre hat_hypotheses."""

    def test_upsert_creates_new_hypothesis(self, repo: LedgerRepository) -> None:
        """upsert_hypothesis inserta una Hypothesis nueva."""
        repo.upsert_hypothesis("u1", "s1", "h1", "maybe")
        hyp = repo.get_hypothesis("u1", "s1", "h1")
        assert hyp is not None
        assert hyp["hypothesis_value"] == "maybe"
        assert hyp["verified"] is False
        assert hyp["promoted_to_fact"] is False

    def test_verify_hypothesis_without_promotion(self, repo: LedgerRepository) -> None:
        """verify_hypothesis marca verified=1 sin copiar a Facts."""
        repo.upsert_hypothesis("u1", "s1", "h1", "maybe")
        result = repo.verify_hypothesis("u1", "s1", "h1", promote_to_fact=False)
        assert result is True
        hyp = repo.get_hypothesis("u1", "s1", "h1")
        assert hyp is not None
        assert hyp["verified"] is True
        # No debe existir como Fact
        assert repo.get_fact("u1", "s1", "h1") is None

    def test_verify_hypothesis_with_promotion_creates_fact(
        self, repo: LedgerRepository,
    ) -> None:
        """verify_hypothesis con promote_to_fact=True copia a Facts."""
        repo.upsert_hypothesis("u1", "s1", "h1", "maybe", confidence=0.6)
        result = repo.verify_hypothesis("u1", "s1", "h1", promote_to_fact=True)
        assert result is True
        fact = repo.get_fact("u1", "s1", "h1")
        assert fact is not None
        assert fact["fact_value"] == "maybe"
        assert fact["confidence"] == 1.0
        assert fact["orbital_theta"] == 0.0

    def test_verify_nonexistent_returns_false(self, repo: LedgerRepository) -> None:
        """verify_hypothesis retorna False si no existe."""
        assert repo.verify_hypothesis("u1", "s1", "inexistente") is False

    def test_get_hypotheses_only_unverified(self, repo: LedgerRepository) -> None:
        """get_hypotheses(only_unverified=True) filtra verificadas."""
        repo.upsert_hypothesis("u1", "s1", "h1", "a")
        repo.upsert_hypothesis("u1", "s1", "h2", "b")
        repo.verify_hypothesis("u1", "s1", "h1")
        unverified = repo.get_hypotheses("u1", "s1", only_unverified=True)
        assert len(unverified) == 1
        assert unverified[0]["hypothesis_key"] == "h2"

    def test_hypothesis_default_theta_is_pi_over_4(self, repo: LedgerRepository) -> None:
        """Una hypothesis nueva tiene θ ≈ π/4 (0.785 en schema)."""
        repo.upsert_hypothesis("u1", "s1", "h1", "maybe")
        hyp = repo.get_hypothesis("u1", "s1", "h1")
        assert hyp is not None
        assert abs(hyp["orbital_theta"] - 0.785) < 1e-3


# ── Tests de hat_progress ──────────────────────────────────────────────


class TestProgress:
    """CRUD sobre hat_progress (reemplaza hat_dispatch_registry)."""

    def test_record_progress_creates_entry(self, repo: LedgerRepository) -> None:
        """record_progress inserta un dispatch nuevo."""
        row_id = repo.record_progress(
            user_id="u1", session_id="s1", dispatch_id="d1",
            domain="operaciones", status="dispatched",
        )
        assert row_id > 0

    def test_get_progress_returns_history(self, repo: LedgerRepository) -> None:
        """get_progress retorna historial ordenado por created_at desc."""
        repo.record_progress("u1", "s1", "d1", "operaciones", "completed")
        repo.record_progress("u1", "s1", "d2", "comunicaciones", "completed")
        progress = repo.get_progress("u1", "s1")
        assert len(progress) == 2

    def test_register_dispatch_creates_entry(self, repo: LedgerRepository) -> None:
        """register_dispatch inserta con status='dispatched'."""
        row_id, created = repo.register_dispatch(
            intent_hash="hash123", user_id="u1", session_id="s1",
            domain="operaciones",
        )
        assert created is True
        assert row_id > 0

    def test_register_dispatch_duplicate_returns_false(
        self, repo: LedgerRepository,
    ) -> None:
        """Segundo register_dispatch con mismo hash retorna created=False."""
        repo.register_dispatch("h1", "u1", "s1", "operaciones")
        _, created = repo.register_dispatch("h1", "u1", "s1", "operaciones")
        assert created is False

    def test_get_dispatch_by_hash(self, repo: LedgerRepository) -> None:
        """get_dispatch retorna el dispatch por intent_hash."""
        repo.register_dispatch("h1", "u1", "s1", "operaciones")
        dispatch = repo.get_dispatch("h1")
        assert dispatch is not None
        assert dispatch["domain"] == "operaciones"
        assert dispatch["status"] == "dispatched"

    def test_get_dispatch_returns_none_if_missing(self, repo: LedgerRepository) -> None:
        """get_dispatch retorna None si no existe."""
        assert repo.get_dispatch("inexistente") is None

    def test_complete_dispatch_updates_status(self, repo: LedgerRepository) -> None:
        """complete_dispatch marca como completed y guarda result."""
        repo.register_dispatch("h1", "u1", "s1", "operaciones")
        result = repo.complete_dispatch("h1", {"output": "done"}, status="completed")
        assert result is True
        dispatch = repo.get_dispatch("h1")
        assert dispatch is not None
        assert dispatch["status"] == "completed"
        assert dispatch["result_cache"] == {"output": "done"}

    def test_increment_subscriber(self, repo: LedgerRepository) -> None:
        """increment_subscriber aumenta el contador."""
        repo.register_dispatch("h1", "u1", "s1", "operaciones")
        count1 = repo.increment_subscriber("h1")
        count2 = repo.increment_subscriber("h1")
        assert count1 == 1
        assert count2 == 2

    def test_get_recent_dispatches_by_hash(self, repo: LedgerRepository) -> None:
        """get_recent_dispatches_by_hash filtra por hash y tiempo."""
        repo.register_dispatch("h1", "u1", "s1", "operaciones")
        recent = repo.get_recent_dispatches_by_hash("h1", since_seconds=60)
        assert len(recent) >= 1
        # Hash diferente no debe aparecer
        recent_other = repo.get_recent_dispatches_by_hash("h2", since_seconds=60)
        assert len(recent_other) == 0

    def test_decode_dispatch_has_result_cache_alias(self, repo: LedgerRepository) -> None:
        """_decode_dispatch añade alias 'result_cache' apuntando a result_summary."""
        repo.register_dispatch("h1", "u1", "s1", "operaciones")
        repo.complete_dispatch("h1", {"data": "test"}, status="completed")
        dispatch = repo.get_dispatch("h1")
        assert dispatch is not None
        assert "result_cache" in dispatch
        assert dispatch["result_cache"] == dispatch["result_summary"]
