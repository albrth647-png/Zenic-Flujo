"""Tests para OVCLedgerBridge — sincronización OVC ↔ Ledger.

Cubre:
- load_session: carga Facts y Hypotheses como variables OVC.
- persist_session: snapshot del OVC → SQLite.
- Namespacing: variables con prefijo hat_<session>__.
- Idempotencia: load_session no duplica variables.
- Casos edge: sesión sin facts ni hypotheses.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.hat.level1_orchestrator.ledger.ovc_bridge import (
    FACT_GROUP,
    FACT_THETA,
    FACT_VELOCITY,
    HYPOTHESIS_GROUP,
    HYPOTHESIS_THETA,
    HYPOTHESIS_VELOCITY,
    SESSION_VAR_PREFIX,
    OVCLedgerBridge,
)
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.orbital.context import OrbitalContext


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_orbital_context() -> None:
    """Reset del singleton OrbitalContext antes de cada test."""
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Ruta a DB SQLite temporal."""
    return tmp_path / "test_hats.db"


@pytest.fixture
def repo(tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> LedgerRepository:
    """LedgerRepository con DB temporal."""
    import src.core.db.sqlite_manager as sm_module
    from src.core.db.sqlite_manager import DatabaseManager

    original_instance = DatabaseManager._instance
    original_db_path = sm_module.DB_PATH

    DatabaseManager._instance = None
    monkeypatch.setattr(sm_module, "DB_PATH", tmp_db_path)

    db = DatabaseManager()

    yield LedgerRepository()

    try:
        db.close_connection()
    except Exception:
        pass
    DatabaseManager._instance = original_instance
    monkeypatch.setattr(sm_module, "DB_PATH", original_db_path)


@pytest.fixture
def ctx() -> OrbitalContext:
    """OrbitalContext fresco."""
    return OrbitalContext()


@pytest.fixture
def bridge(repo: LedgerRepository, ctx: OrbitalContext) -> OVCLedgerBridge:
    """OVCLedgerBridge con repo y ctx inyectados."""
    return OVCLedgerBridge(repo=repo, ctx=ctx)


# ── Tests de constantes ────────────────────────────────────────────────


class TestConstants:
    """Constantes exportadas del módulo."""

    def test_fact_theta_is_zero(self) -> None:
        """FACT_THETA es 0.0 (alta confianza, no orbita)."""
        assert FACT_THETA == 0.0

    def test_hypothesis_theta_is_pi_over_4(self) -> None:
        """HYPOTHESIS_THETA es π/4 (confianza media)."""
        assert math.isclose(HYPOTHESIS_THETA, math.pi / 4.0, abs_tol=1e-9)

    def test_fact_velocity_is_zero(self) -> None:
        """FACT_VELOCITY es 0.0 (facts no orbitan)."""
        assert FACT_VELOCITY == 0.0

    def test_hypothesis_velocity_is_small(self) -> None:
        """HYPOTHESIS_VELOCITY es 0.05 (drift lento)."""
        assert HYPOTHESIS_VELOCITY == 0.05

    def test_session_var_prefix(self) -> None:
        """SESSION_VAR_PREFIX es 'hat_'."""
        assert SESSION_VAR_PREFIX == "hat_"


# ── Tests de load_session ──────────────────────────────────────────────


class TestLoadSession:
    """Carga de Facts y Hypotheses al OVC."""

    def test_load_session_empty_returns_zero_counts(
        self, bridge: OVCLedgerBridge,
    ) -> None:
        """Sesión sin facts ni hypotheses → counts en 0."""
        counts = bridge.load_session("u1", "s1")
        assert counts["facts"] == 0
        assert counts["hypotheses"] == 0
        assert counts["plan_steps"] == 0
        assert counts["cards"] == 0

    def test_load_session_loads_facts_as_ovc_vars(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository, ctx: OrbitalContext,
    ) -> None:
        """Los Facts se cargan como variables OVC con prefijo hat_<sess>__."""
        repo.upsert_fact("u1", "s1", "color", "azul")
        bridge.load_session("u1", "s1")
        # Debe existir una variable OVC con el prefijo correcto
        fact_vars = [
            v for v in ctx.ovc.get_all_variables().values()
            if v.metadata.get("type") == "fact"
        ]
        assert len(fact_vars) == 1
        assert fact_vars[0].metadata["key"] == "color"
        assert fact_vars[0].metadata["value"] == "azul"

    def test_load_session_loads_hypotheses_as_ovc_vars(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository, ctx: OrbitalContext,
    ) -> None:
        """Las Hypotheses no verificadas se cargan al OVC."""
        repo.upsert_hypothesis("u1", "s1", "h1", "maybe")
        bridge.load_session("u1", "s1")
        hyp_vars = [
            v for v in ctx.ovc.get_all_variables().values()
            if v.metadata.get("type") == "hypothesis"
        ]
        assert len(hyp_vars) == 1
        assert hyp_vars[0].metadata["key"] == "h1"

    def test_load_session_skips_verified_hypotheses(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository, ctx: OrbitalContext,
    ) -> None:
        """Las Hypotheses verificadas NO se cargan."""
        repo.upsert_hypothesis("u1", "s1", "h1", "maybe")
        repo.verify_hypothesis("u1", "s1", "h1")
        bridge.load_session("u1", "s1")
        hyp_vars = [
            v for v in ctx.ovc.get_all_variables().values()
            if v.metadata.get("type") == "hypothesis"
        ]
        assert len(hyp_vars) == 0

    def test_load_session_is_idempotent(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository, ctx: OrbitalContext,
    ) -> None:
        """load_session dos veces no duplica variables."""
        repo.upsert_fact("u1", "s1", "k1", "v1")
        bridge.load_session("u1", "s1")
        bridge.load_session("u1", "s1")
        fact_vars = [
            v for v in ctx.ovc.get_all_variables().values()
            if v.metadata.get("type") == "fact"
        ]
        assert len(fact_vars) == 1


# ── Tests de persist_session ───────────────────────────────────────────


class TestPersistSession:
    """Snapshot del OVC → SQLite."""

    def test_persist_session_empty_returns_zero(self, bridge: OVCLedgerBridge) -> None:
        """Sesión sin variables OVC → 0 facts y 0 hypotheses persistidos."""
        counts = bridge.persist_session("u1", "s1")
        assert counts["facts_persisted"] == 0
        assert counts["hypotheses_persisted"] == 0

    def test_persist_session_saves_facts(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository,
    ) -> None:
        """persist_session guarda los Facts al Ledger."""
        # Cargar una sesión con un fact
        repo.upsert_fact("u1", "s1", "color", "azul")
        bridge.load_session("u1", "s1")
        # Modificar el valor del fact en el OVC (simular mutación)
        # No podemos mutar directamente metadata, así que solo persistimos
        counts = bridge.persist_session("u1", "s1")
        assert counts["facts_persisted"] >= 1
        # El fact debe existir en el repo
        fact = repo.get_fact("u1", "s1", "color")
        assert fact is not None

    def test_persist_session_isolates_by_session_prefix(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository, ctx: OrbitalContext,
    ) -> None:
        """persist_session solo guarda variables con el prefijo de la sesión."""
        # Crear una variable OVC SIN el prefijo de sesión (simula otra sesión)
        ctx.ovc.create_variable(
            name="other_session__fact_k1",
            theta=0.0, amplitude=1.0, velocity=0.0,
            orbit_group="hat_facts",
            metadata={"type": "fact", "key": "k1", "value": "other", "confidence": 1.0},
        )
        # Persistir sesión s1 (no debe tocar la variable de otra sesión)
        counts = bridge.persist_session("u1", "s1")
        assert counts["facts_persisted"] == 0


# ── Tests de namespacing ───────────────────────────────────────────────


class TestNamespacing:
    """Namespacing por session_id."""

    def test_two_sessions_have_isolated_vars(
        self, bridge: OVCLedgerBridge, repo: LedgerRepository, ctx: OrbitalContext,
    ) -> None:
        """Dos sesiones distintas tienen variables OVC distintas."""
        repo.upsert_fact("u1", "s1", "k1", "v1")
        repo.upsert_fact("u1", "s2", "k1", "v2")

        bridge.load_session("u1", "s1")
        vars_s1 = [n for n in ctx.ovc.get_all_variables() if "s1" in n]
        assert len(vars_s1) >= 1

        bridge.load_session("u1", "s2")
        vars_s2 = [n for n in ctx.ovc.get_all_variables() if "s2" in n]
        assert len(vars_s2) >= 1

        # Las variables de s1 y s2 son distintas
        assert set(vars_s1) != set(vars_s2)

    def test_session_prefix_format(self, bridge: OVCLedgerBridge) -> None:
        """El prefijo tiene formato 'hat_<sanitized_session_id>__'."""
        # Acceder al método estático _make_session_prefix
        prefix = OVCLedgerBridge._make_session_prefix("s1")
        assert prefix == "hat_s1__"
        # Sanitización de caracteres especiales
        prefix_special = OVCLedgerBridge._make_session_prefix("s-1/test")
        assert prefix_special == "hat_s_1_test__"
