"""Tests para FactsManager — capa de negocio sobre LedgerRepository.

Cubre:
- Validación de confidence (clamp [0, 1], TypeError en bool/no-numérico).
- Promoción de hypothesis a fact (forzar confidence=1.0, theta=0).
- Atajos de active_domain (set/get/clear, defensivo ante tipos inválidos).
- Delegación al repositorio (no toca SQL directo).

Usa una base SQLite en tmpdir, aislada por test vía fixture.
"""
from __future__ import annotations

import contextlib
import math
from pathlib import Path

import pytest

from src.hat.level1_orchestrator.ledger.facts_manager import (
    ACTIVE_DOMAIN_FACT_KEY,
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    FACT_THETA,
    HYPOTHESIS_THETA,
    FactsManager,
)
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Ruta a una DB SQLite temporal aislada por test."""
    return tmp_path / "test_hats.db"


@pytest.fixture
def repo(tmp_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> LedgerRepository:
    """LedgerRepository con DatabaseManager apuntando a tmp_db_path.

    Resetea el singleton ``DatabaseManager`` y parchea ``DB_PATH`` para que
    cada test tenga su propia SQLite temporal, sin compartir estado.
    """
    import src.core.db.sqlite_manager as sm_module
    from src.core.db.sqlite_manager import DatabaseManager

    # Guardar estado original para restaurar al final.
    original_instance = DatabaseManager._instance
    original_db_path = sm_module.DB_PATH

    # Reset del singleton y parchear DB_PATH antes de instanciar.
    DatabaseManager._instance = None
    monkeypatch.setattr(sm_module, "DB_PATH", tmp_db_path)

    # Forzar nueva instancia — ahora apunta a tmp_db_path.
    db = DatabaseManager()
    # Sanity check: el path interno debe ser el temporal.
    assert db._db_path == tmp_db_path

    yield LedgerRepository()

    # Cleanup: cerrar conexión y restaurar el singleton original.
    with contextlib.suppress(Exception):
        db.close_connection()
    DatabaseManager._instance = original_instance
    monkeypatch.setattr(sm_module, "DB_PATH", original_db_path)


@pytest.fixture
def manager(repo: LedgerRepository) -> FactsManager:
    """FactsManager con repo inyectado."""
    return FactsManager(repo=repo)


# ── Tests de validación de confidence ──────────────────────────────────


class TestConfidenceValidation:
    """Validación del rango y tipo de confidence."""

    def test_confidence_in_range_passes_through(
        self, manager: FactsManager,
    ) -> None:
        """Confidence en [0, 1] se acepta sin cambios."""
        row_id = manager.upsert_fact(
            "u1", "s1", "k1", "v1", confidence=0.5,
        )
        assert row_id > 0
        fact = manager.get_fact("u1", "s1", "k1")
        assert fact is not None
        assert fact["confidence"] == 0.5

    def test_confidence_above_max_clamped_to_one(
        self, manager: FactsManager,
    ) -> None:
        """Confidence > 1.0 se clamp a 1.0."""
        manager.upsert_fact("u1", "s1", "k1", "v1", confidence=2.5)
        fact = manager.get_fact("u1", "s1", "k1")
        assert fact is not None
        assert fact["confidence"] == CONFIDENCE_MAX

    def test_confidence_below_min_clamped_to_zero(
        self, manager: FactsManager,
    ) -> None:
        """Confidence < 0 se clamp a 0.0."""
        manager.upsert_fact("u1", "s1", "k1", "v1", confidence=-0.3)
        fact = manager.get_fact("u1", "s1", "k1")
        assert fact is not None
        assert fact["confidence"] == CONFIDENCE_MIN

    def test_confidence_bool_raises_type_error(
        self, manager: FactsManager,
    ) -> None:
        """bool no es confidence válido (subclase de int pero erróneo)."""
        with pytest.raises(TypeError, match="confidence debe ser numérico"):
            manager.upsert_fact("u1", "s1", "k1", "v1", confidence=True)

    def test_confidence_string_raises_type_error(
        self, manager: FactsManager,
    ) -> None:
        """String NO es confidence válido."""
        with pytest.raises(TypeError, match="confidence debe ser numérico"):
            manager.upsert_fact("u1", "s1", "k1", "v1", confidence="0.5")

    def test_confidence_none_raises_type_error(
        self, manager: FactsManager,
    ) -> None:
        """None NO es confidence válido."""
        with pytest.raises(TypeError, match="confidence debe ser numérico"):
            manager.upsert_fact("u1", "s1", "k1", "v1", confidence=None)  # type: ignore[arg-type]


# ── Tests de Facts CRUD (delegación al repo) ───────────────────────────


class TestFactsCRUD:
    """CRUD básico de Facts vía FactsManager."""

    def test_upsert_creates_new_fact(self, manager: FactsManager) -> None:
        """upsert_fact inserta un Fact nuevo."""
        manager.upsert_fact("u1", "s1", "color", "azul")
        fact = manager.get_fact("u1", "s1", "color")
        assert fact is not None
        assert fact["fact_value"] == "azul"
        assert fact["confidence"] == 1.0
        assert fact["orbital_theta"] == FACT_THETA

    def test_upsert_updates_existing_fact(self, manager: FactsManager) -> None:
        """upsert_fact actualiza un Fact existente (UNIQUE constraint)."""
        manager.upsert_fact("u1", "s1", "color", "azul")
        manager.upsert_fact("u1", "s1", "color", "rojo")
        fact = manager.get_fact("u1", "s1", "color")
        assert fact is not None
        assert fact["fact_value"] == "rojo"

    def test_get_fact_returns_none_if_missing(
        self, manager: FactsManager,
    ) -> None:
        """get_fact retorna None si el Fact no existe."""
        assert manager.get_fact("u1", "s1", "inexistente") is None

    def test_get_facts_returns_all_sorted_by_key(
        self, manager: FactsManager,
    ) -> None:
        """get_facts retorna todos los Facts ordenados por fact_key."""
        manager.upsert_fact("u1", "s1", "zeta", "1")
        manager.upsert_fact("u1", "s1", "alpha", "2")
        manager.upsert_fact("u1", "s1", "mid", "3")
        facts = manager.get_facts("u1", "s1")
        keys = [f["fact_key"] for f in facts]
        assert keys == ["alpha", "mid", "zeta"]

    def test_get_facts_isolates_by_session(
        self, manager: FactsManager,
    ) -> None:
        """Los Facts de una sesión no aparecen en otra."""
        manager.upsert_fact("u1", "s1", "k1", "v1")
        manager.upsert_fact("u1", "s2", "k2", "v2")
        s1_facts = manager.get_facts("u1", "s1")
        s2_facts = manager.get_facts("u1", "s2")
        assert len(s1_facts) == 1
        assert len(s2_facts) == 1
        assert s1_facts[0]["fact_key"] == "k1"
        assert s2_facts[0]["fact_key"] == "k2"

    def test_delete_fact_returns_true_when_deleted(
        self, manager: FactsManager,
    ) -> None:
        """delete_fact retorna True si eliminó, False si no existía."""
        manager.upsert_fact("u1", "s1", "k1", "v1")
        assert manager.delete_fact("u1", "s1", "k1") is True
        assert manager.delete_fact("u1", "s1", "k1") is False


# ── Tests de Hypotheses ────────────────────────────────────────────────


class TestHypotheses:
    """Manejo de Hypotheses y promoción a Facts."""

    def test_upsert_hypothesis_default_theta_is_pi_over_4(
        self, manager: FactsManager,
    ) -> None:
        """Una hypothesis nueva tiene θ = π/4 por defecto."""
        manager.upsert_hypothesis("u1", "s1", "h1", "maybe")
        hyp = manager.get_hypothesis("u1", "s1", "h1")
        assert hyp is not None
        assert math.isclose(hyp["orbital_theta"], HYPOTHESIS_THETA, abs_tol=1e-6)

    def test_upsert_hypothesis_clamps_confidence_below_one(
        self, manager: FactsManager,
    ) -> None:
        """Una hypothesis NO puede tener confidence=1.0 (debe verificarse)."""
        manager.upsert_hypothesis("u1", "s1", "h1", "maybe", confidence=1.0)
        hyp = manager.get_hypothesis("u1", "s1", "h1")
        assert hyp is not None
        assert hyp["confidence"] < 1.0
        assert hyp["confidence"] == 0.99

    def test_verify_hypothesis_without_promotion(
        self, manager: FactsManager,
    ) -> None:
        """verify_hypothesis marca verified=1 sin copiar a Facts."""
        manager.upsert_hypothesis("u1", "s1", "h1", "maybe")
        result = manager.verify_hypothesis(
            "u1", "s1", "h1", promote_to_fact=False,
        )
        assert result is True
        hyp = manager.get_hypothesis("u1", "s1", "h1")
        assert hyp is not None
        assert hyp["verified"] is True
        # No debe existir como Fact
        assert manager.get_fact("u1", "s1", "h1") is None

    def test_verify_hypothesis_with_promotion_creates_fact(
        self, manager: FactsManager,
    ) -> None:
        """verify_hypothesis con promote_to_fact=True copia a Facts."""
        manager.upsert_hypothesis("u1", "s1", "h1", "maybe", confidence=0.6)
        assert manager.verify_hypothesis("u1", "s1", "h1", promote_to_fact=True) is True
        # Debe existir como Fact con confidence=1.0 y theta=0
        fact = manager.get_fact("u1", "s1", "h1")
        assert fact is not None
        assert fact["fact_value"] == "maybe"
        assert fact["confidence"] == 1.0
        assert fact["orbital_theta"] == FACT_THETA

    def test_verify_nonexistent_hypothesis_returns_false(
        self, manager: FactsManager,
    ) -> None:
        """verify_hypothesis retorna False si la hypothesis no existe."""
        assert manager.verify_hypothesis("u1", "s1", "inexistente") is False

    def test_get_hypotheses_only_unverified(
        self, manager: FactsManager,
    ) -> None:
        """get_hypotheses(only_unverified=True) filtra las verificadas."""
        manager.upsert_hypothesis("u1", "s1", "h1", "a")
        manager.upsert_hypothesis("u1", "s1", "h2", "b")
        manager.verify_hypothesis("u1", "s1", "h1")
        unverified = manager.get_hypotheses("u1", "s1", only_unverified=True)
        assert len(unverified) == 1
        assert unverified[0]["hypothesis_key"] == "h2"


# ── Tests de active_domain (atajos del HATRouter) ──────────────────────


class TestActiveDomain:
    """Atajos para el dominio activo de la sesión."""

    def test_set_active_domain_persists_fact(
        self, manager: FactsManager,
    ) -> None:
        """set_active_domain crea un Fact con clave 'active_domain'."""
        manager.set_active_domain("u1", "s1", "operaciones")
        fact = manager.get_fact("u1", "s1", ACTIVE_DOMAIN_FACT_KEY)
        assert fact is not None
        assert fact["fact_value"] == "operaciones"
        assert fact["confidence"] == 1.0

    def test_get_active_domain_returns_string_when_set(
        self, manager: FactsManager,
    ) -> None:
        """get_active_domain retorna el string del dominio activo."""
        manager.set_active_domain("u1", "s1", "comunicaciones")
        assert manager.get_active_domain("u1", "s1") == "comunicaciones"

    def test_get_active_domain_returns_none_when_missing(
        self, manager: FactsManager,
    ) -> None:
        """get_active_domain retorna None si no hay Fact."""
        assert manager.get_active_domain("u1", "s1") is None

    def test_get_active_domain_returns_none_for_non_string_value(
        self, manager: FactsManager,
    ) -> None:
        """get_active_domain es defensivo: si el valor no es string, retorna None."""
        # Insertar un Fact con valor no-string (simular corrupción).
        manager.upsert_fact("u1", "s1", ACTIVE_DOMAIN_FACT_KEY, 12345)
        assert manager.get_active_domain("u1", "s1") is None

    def test_clear_active_domain_returns_true_when_existed(
        self, manager: FactsManager,
    ) -> None:
        """clear_active_domain elimina el Fact y retorna True."""
        manager.set_active_domain("u1", "s1", "datos_auto")
        assert manager.clear_active_domain("u1", "s1") is True
        assert manager.get_active_domain("u1", "s1") is None

    def test_clear_active_domain_returns_false_when_missing(
        self, manager: FactsManager,
    ) -> None:
        """clear_active_domain retorna False si el Fact no existía."""
        assert manager.clear_active_domain("u1", "s1") is False

    def test_set_active_domain_overwrites_previous(
        self, manager: FactsManager,
    ) -> None:
        """set_active_domain actualiza el dominio (UNIQUE constraint)."""
        manager.set_active_domain("u1", "s1", "operaciones")
        manager.set_active_domain("u1", "s1", "comunicaciones")
        assert manager.get_active_domain("u1", "s1") == "comunicaciones"
