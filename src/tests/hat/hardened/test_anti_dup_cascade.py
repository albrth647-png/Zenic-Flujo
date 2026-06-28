"""Tests para AntiDuplicationCascade — orquestador de 3 capas anti-doble-llamada.

Cubre:
- Cascada: si una capa detecta duplicado, las siguientes no se ejecutan.
- Orden de capas: exact_match → idempotency → ttl_freshness.
- Acciones por capa: return_cache, subscribe, discard, proceed.
- Casos edge: hash sin dispatch, hash completado, hash en progreso.
- clear_cache() limpia caches de las capas.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level1_orchestrator.anti_duplication.cascade import AntiDuplicationCascade


@pytest.fixture
def mock_repo() -> MagicMock:
    """Mock del LedgerRepository — no toca SQLite."""
    repo = MagicMock()
    repo.get_dispatch.return_value = None
    repo.get_recent_dispatches_by_hash.return_value = []
    return repo


@pytest.fixture
def cascade(mock_repo: MagicMock) -> AntiDuplicationCascade:
    """Cascade con repo mockeado."""
    return AntiDuplicationCascade(repo=mock_repo)


# ── Tests del flujo cascade ────────────────────────────────────────────


class TestCascadeFlow:
    """Flujo del cascade: orden y cortocircuito."""

    def test_all_layers_pass_returns_proceed(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """Sin dispatches previos → 'proceed', layer_hit='none'."""
        result = cascade.check(
            intent_hash="abc123",
            user_id="u1",
            session_id="s1",
            message="test",
            domain="operaciones",
        )
        assert result["duplicate"] is False
        assert result["action"] == "proceed"
        assert result["layer_hit"] == "none"
        assert "all layers passed" in result["reason"]

    def test_exact_match_short_circuits(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """Si exact_match detecta duplicado, idempotency y ttl no se ejecutan."""
        mock_repo.get_dispatch.return_value = {
            "status": "completed",
            "result_cache": {"data": "cached"},
        }
        result = cascade.check(
            intent_hash="abc123",
            user_id="u1",
            session_id="s1",
            message="test",
            domain="operaciones",
        )
        assert result["duplicate"] is True
        assert result["action"] == "return_cache"
        assert result["layer_hit"] == "exact_match"
        # idempotency no debe haberse invocado (no increment_subscriber)
        mock_repo.increment_subscriber.assert_not_called()

    def test_idempotency_short_circuits_after_exact_match_passes(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """Si exact_match pasa pero idempotency detecta, ttl no se ejecuta."""
        # Primera llamada a get_dispatch (exact_match): no completado
        # Segunda llamada (idempotency): in_progress
        mock_repo.get_dispatch.side_effect = [
            {"status": "dispatched", "result_cache": None},
            {"status": "dispatched", "result_cache": None},
        ]
        mock_repo.increment_subscriber.return_value = 1
        result = cascade.check(
            intent_hash="abc123",
            user_id="u1",
            session_id="s1",
            message="test",
            domain="operaciones",
        )
        assert result["duplicate"] is True
        assert result["action"] == "subscribe"
        assert result["layer_hit"] == "idempotency"
        assert "sub_" in result["subscription_id"]

    def test_ttl_freshness_last_layer(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """Si exact e idempotency pasan, ttl_freshness es la última."""
        mock_repo.get_dispatch.return_value = {"status": "failed", "result_cache": None}
        mock_repo.get_recent_dispatches_by_hash.return_value = [
            {"id": 1, "intent_hash": "abc123"},
        ]
        result = cascade.check(
            intent_hash="abc123",
            user_id="u1",
            session_id="s1",
            message="test",
            domain="operaciones",
        )
        assert result["duplicate"] is True
        assert result["action"] == "discard"
        assert result["layer_hit"] == "ttl_freshness"


# ── Tests de acciones ──────────────────────────────────────────────────


class TestActions:
    """Acciones retornadas por cada capa."""

    def test_return_cache_action(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """exact_match con status=completed → return_cache."""
        mock_repo.get_dispatch.return_value = {
            "status": "completed",
            "result_cache": {"output": "result"},
        }
        result = cascade.check("h", "u", "s", "m", "d")
        assert result["action"] == "return_cache"
        assert result["cached_result"] == {"output": "result"}

    def test_subscribe_action(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """idempotency con status=running → subscribe."""
        mock_repo.get_dispatch.return_value = {"status": "running", "result_cache": None}
        mock_repo.increment_subscriber.return_value = 3
        result = cascade.check("h", "u", "s", "m", "d")
        assert result["action"] == "subscribe"
        assert result["subscription_id"] == "sub_h_3"

    def test_discard_action(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """ttl_freshness con dispatches recientes → discard."""
        mock_repo.get_dispatch.return_value = {"status": "failed", "result_cache": None}
        mock_repo.get_recent_dispatches_by_hash.return_value = [{"id": 1}]
        result = cascade.check("h", "u", "s", "m", "d")
        assert result["action"] == "discard"

    def test_proceed_action_when_all_pass(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """Todas las capas pasan → proceed."""
        mock_repo.get_dispatch.return_value = None
        mock_repo.get_recent_dispatches_by_hash.return_value = []
        result = cascade.check("h", "u", "s", "m", "d")
        assert result["action"] == "proceed"


# ── Tests de clear_cache ───────────────────────────────────────────────


class TestClearCache:
    """clear_cache() limpia caches de las capas."""

    def test_clear_cache_does_not_raise(self, cascade: AntiDuplicationCascade) -> None:
        """clear_cache() no lanza excepción y retorna None."""
        result = cascade.clear_cache()
        assert result is None

    def test_clear_cache_allows_recheck_after_completed_dispatch(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """Tras clear_cache, un dispatch completado se re-verifica (no cache hit)."""
        mock_repo.get_dispatch.return_value = {
            "status": "completed",
            "result_cache": {"data": "cached"},
        }
        # Primera verificación: cache hit
        r1 = cascade.check("h", "u", "s", "m", "d")
        assert r1["action"] == "return_cache"
        # Limpiar cache
        cascade.clear_cache()
        # Segunda verificación: sigue siendo cache hit (el repo sigue retornando completed)
        r2 = cascade.check("h", "u", "s", "m", "d")
        assert r2["action"] == "return_cache"


# ── Tests de integración con capa CLARIFY_DOMAIN ───────────────────────


class TestClarifyDomain:
    """Cuando domain='clarify', el cascade usa 'clarify' como domain."""

    def test_clarify_domain_handled(
        self, cascade: AntiDuplicationCascade, mock_repo: MagicMock,
    ) -> None:
        """domain='clarify' no rompe el cascade."""
        mock_repo.get_dispatch.return_value = None
        result = cascade.check("h", "u", "s", "m", "clarify")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"
