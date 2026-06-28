"""Tests Fase 1C — Foso 1: OrbitalResult hashes + persistence + reproducibility.

Cubre:
- OrbitalResult tiene campos input_fingerprint, result_hash, result_signature, previous_hash
- OrbitalEngine.run_tick calcula input_fingerprint y result_hash
- OrbitalPersistence.save_orbital_result persiste con hash + firma + chain
- OrbitalPersistence.get_last_hash_for_execution
- OrbitalPersistence.verify_orbital_execution (recompute + compare)
- Reproducibilidad: mismo input → mismo result_hash (determinismo)
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="foso1_1c_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Cada test usa DB limpia + singletons reset + DB_PATH patcheado."""
    data_dir = tmp_path / "data" / ".workflow_determinista"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "workflow_determinista.db"
    monkeypatch.setenv("WFD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HOME", str(tmp_path))

    from src.core.db import sqlite_manager as sm_mod
    monkeypatch.setattr(sm_mod, "DB_PATH", db_path)
    sm_mod.DatabaseManager._reset()
    from src.core.security.encryption import EncryptionService
    EncryptionService._instance = None  # type: ignore[attr-defined]
    EncryptionService._initialized = False  # type: ignore[attr-defined]
    from src.orbital.context import OrbitalContext
    OrbitalContext._reset()
    yield
    with contextlib.suppress(Exception):
        sm_mod.DatabaseManager._reset()


class TestOrbitalResultHashFields:
    """OrbitalResult debe tener los campos nuevos de Foso 1."""

    def test_orbital_result_has_new_fields(self):
        from src.orbital.models import OrbitalResult

        result = OrbitalResult()
        assert hasattr(result, "input_fingerprint")
        assert hasattr(result, "result_hash")
        assert hasattr(result, "result_signature")
        assert hasattr(result, "previous_hash")
        assert hasattr(result, "workflow_execution_id")
        # Defaults
        assert result.input_fingerprint == ""
        assert result.result_hash == ""
        assert result.result_signature == ""
        assert result.previous_hash == ""
        assert result.workflow_execution_id is None

    def test_to_dict_includes_reproducibility_fields(self):
        """to_dict debe incluir input_fingerprint, previous_hash, workflow_execution_id
        (para que result_hash cubra los metadatos también)."""
        from src.orbital.models import OrbitalResult

        result = OrbitalResult(
            tick=42,
            input_fingerprint="abc123",
            previous_hash="def456",
            workflow_execution_id=99,
        )
        d = result.to_dict()
        assert d["input_fingerprint"] == "abc123"
        assert d["previous_hash"] == "def456"
        assert d["workflow_execution_id"] == 99
        # result_hash y result_signature NO se incluyen (auto-referenciales)
        assert "result_hash" not in d
        assert "result_signature" not in d


class TestOrbitalEngineHashes:
    """OrbitalEngine.run_tick debe calcular input_fingerprint y result_hash."""

    def test_run_tick_populates_input_fingerprint(self):
        from src.orbital.context import OrbitalContext

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_variable(name="v2", theta=0.2, amplitude=1.0, velocity=0.5)

        result = engine.run_tick()
        assert result.input_fingerprint, "input_fingerprint debe estar poblado"
        assert len(result.input_fingerprint) == 64  # SHA-256 hex

    def test_run_tick_populates_result_hash(self):
        from src.orbital.context import OrbitalContext

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_variable(name="v2", theta=0.2, amplitude=1.0, velocity=0.5)

        result = engine.run_tick()
        assert result.result_hash, "result_hash debe estar poblado"
        assert len(result.result_hash) == 64  # SHA-256 hex

    def test_same_input_same_result_hash_deterministic(self):
        """Mismo input → mismo result_hash (garantía de reproducibilidad).

        Configuramos dos contextos idénticos y ejecutamos un tick en cada uno.
        Los result_hash deben ser idénticos (sin retroalimentación aleatoria).
        """
        from src.orbital.context import OrbitalContext

        # Contexto 1
        ctx1 = OrbitalContext()
        engine1 = ctx1.engine
        engine1.create_variable(name="v1", theta=0.5, amplitude=1.0, velocity=0.5)
        engine1.create_variable(name="v2", theta=0.5, amplitude=1.0, velocity=0.5)
        engine1.create_cycle("c", ["v1", "v2"], threshold=0.3)
        result1 = engine1.run_tick()

        # Reset y contexto 2 idéntico
        OrbitalContext._reset()
        ctx2 = OrbitalContext()
        engine2 = ctx2.engine
        engine2.create_variable(name="v1", theta=0.5, amplitude=1.0, velocity=0.5)
        engine2.create_variable(name="v2", theta=0.5, amplitude=1.0, velocity=0.5)
        engine2.create_cycle("c", ["v1", "v2"], threshold=0.3)
        result2 = engine2.run_tick()

        # CRÍTICO: mismo input_fingerprint y mismo result_hash
        assert result1.input_fingerprint == result2.input_fingerprint, (
            "input_fingerprint debe ser idéntico para el mismo input"
        )
        assert result1.result_hash == result2.result_hash, (
            "result_hash debe ser idéntico para el mismo input (determinismo)"
        )

    def test_different_input_different_result_hash(self):
        """Input diferente → result_hash diferente."""
        from src.orbital.context import OrbitalContext

        ctx1 = OrbitalContext()
        engine1 = ctx1.engine
        engine1.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine1.create_variable(name="v2", theta=0.2, amplitude=1.0, velocity=0.5)
        engine1.create_cycle("c", ["v1", "v2"], threshold=0.3)
        result1 = engine1.run_tick()

        OrbitalContext._reset()
        ctx2 = OrbitalContext()
        engine2 = ctx2.engine
        engine2.create_variable(name="v1", theta=0.9, amplitude=1.0, velocity=0.5)  # theta diferente
        engine2.create_variable(name="v2", theta=0.8, amplitude=1.0, velocity=0.5)
        engine2.create_cycle("c", ["v1", "v2"], threshold=0.3)
        result2 = engine2.run_tick()

        assert result1.input_fingerprint != result2.input_fingerprint
        assert result1.result_hash != result2.result_hash


class TestOrbitalPersistence:
    """OrbitalPersistence debe guardar OrbitalResult con hash + firma."""

    def test_save_orbital_result_returns_metadata(self):
        from src.orbital.context import OrbitalContext
        from src.orbital.orbital_persistence import OrbitalPersistence

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_variable(name="v2", theta=0.2, amplitude=1.0, velocity=0.5)
        engine.create_cycle("c", ["v1", "v2"], threshold=0.3)
        result = engine.run_tick()

        persistence = OrbitalPersistence()
        info = persistence.save_orbital_result(
            result=result,
            workflow_execution_id=1,  # No existe en DB pero FK no se valida
            tenant_id="default",
            previous_hash="",
        )
        assert info["orbital_execution_id"]
        assert info["result_hash"] == result.result_hash
        assert info["previous_hash"] == ""

    def test_save_two_results_chains_via_previous_hash(self):
        """El segundo save debe usar el result_hash del primero como previous_hash."""
        from src.orbital.context import OrbitalContext
        from src.orbital.orbital_persistence import OrbitalPersistence

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_variable(name="v2", theta=0.2, amplitude=1.0, velocity=0.5)
        engine.create_cycle("c", ["v1", "v2"], threshold=0.3)

        persistence = OrbitalPersistence()

        # Primer tick
        r1 = engine.run_tick()
        info1 = persistence.save_orbital_result(
            result=r1, workflow_execution_id=1, previous_hash="",
        )

        # Segundo tick
        r2 = engine.run_tick()
        # Lookup del último hash del workflow_execution
        prev_hash = persistence.get_last_hash_for_execution(1)
        info2 = persistence.save_orbital_result(
            result=r2, workflow_execution_id=1, previous_hash=prev_hash,
        )

        assert prev_hash == info1["result_hash"]
        assert info2["previous_hash"] == info1["result_hash"]
        assert info2["result_hash"] != info1["result_hash"]  # diferentes ticks

    def test_load_orbital_execution(self):
        from src.orbital.context import OrbitalContext
        from src.orbital.orbital_persistence import OrbitalPersistence

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_cycle("c", ["v1"], threshold=0.3)
        result = engine.run_tick()

        persistence = OrbitalPersistence()
        persistence.save_orbital_result(
            result=result, workflow_execution_id=42, previous_hash="",
        )

        loaded = persistence.load_orbital_execution(42)
        assert loaded is not None
        assert loaded["workflow_execution_id"] == 42
        assert loaded["result_hash"] == result.result_hash
        assert loaded["input_fingerprint"] == result.input_fingerprint
        assert loaded["tick"] == result.tick

    def test_verify_orbital_execution_hash_matches(self):
        """verify_orbital_execution recalcula hash y compara con stored."""
        from src.orbital.context import OrbitalContext
        from src.orbital.orbital_persistence import OrbitalPersistence

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_cycle("c", ["v1"], threshold=0.3)
        result = engine.run_tick()

        persistence = OrbitalPersistence()
        persistence.save_orbital_result(
            result=result, workflow_execution_id=1, previous_hash="",
        )

        verification = persistence.verify_orbital_execution(1)
        assert verification["hash_matches"] is True

    def test_verify_detects_tampering(self):
        """Si modificamos final_state, verification debe detectar mismatch."""
        from src.orbital.context import OrbitalContext
        from src.orbital.orbital_persistence import OrbitalPersistence

        ctx = OrbitalContext()
        engine = ctx.engine
        engine.create_variable(name="v1", theta=0.1, amplitude=1.0, velocity=0.5)
        engine.create_cycle("c", ["v1"], threshold=0.3)
        result = engine.run_tick()

        persistence = OrbitalPersistence()
        persistence.save_orbital_result(
            result=result, workflow_execution_id=1, previous_hash="",
        )

        # Tamper: modificar final_state
        from src.core.db.sqlite_manager import DatabaseManager
        db = DatabaseManager()
        db.execute(
            "UPDATE orbital_executions SET final_state = 'tampered' "
            "WHERE workflow_execution_id = 1"
        )
        db.commit()

        verification = persistence.verify_orbital_execution(1)
        assert verification["hash_matches"] is False
        assert verification["valid"] is False
