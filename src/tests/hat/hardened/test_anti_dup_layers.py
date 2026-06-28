"""Tests para las 3 capas anti-dup: ExactMatch, Idempotency, TTLFreshness.

Cubre cada capa de forma aislada con mocks del LedgerRepository.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level1_orchestrator.anti_duplication.exact_match import ExactMatchLayer
from src.hat.level1_orchestrator.anti_duplication.idempotency import IdempotencyLayer
from src.hat.level1_orchestrator.anti_duplication.ttl_freshness import (
    DEFAULT_TTL_SECONDS,
    TTLFreshnessLayer,
)


@pytest.fixture
def mock_repo() -> MagicMock:
    """Mock del LedgerRepository."""
    repo = MagicMock()
    repo.get_dispatch.return_value = None
    repo.get_recent_dispatches_by_hash.return_value = []
    repo.increment_subscriber.return_value = 0
    return repo


# ── ExactMatchLayer (Capa 1) ───────────────────────────────────────────


class TestExactMatchLayer:
    """Capa 1: detecta dispatches idénticos ya completados."""

    def test_no_dispatch_returns_proceed(self, mock_repo: MagicMock) -> None:
        """Sin dispatch previo → proceed."""
        mock_repo.get_dispatch.return_value = None
        layer = ExactMatchLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"
        assert result["cached_result"] is None

    def test_completed_dispatch_returns_cache(self, mock_repo: MagicMock) -> None:
        """Dispatch completado → return_cache."""
        mock_repo.get_dispatch.return_value = {
            "status": "completed",
            "result_cache": {"data": "result"},
        }
        layer = ExactMatchLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is True
        assert result["action"] == "return_cache"
        assert result["cached_result"] == {"data": "result"}

    def test_in_progress_dispatch_returns_proceed(
        self, mock_repo: MagicMock,
    ) -> None:
        """Dispatch en progreso → proceed (lo maneja idempotency)."""
        mock_repo.get_dispatch.return_value = {
            "status": "running",
            "result_cache": None,
        }
        layer = ExactMatchLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_cache_hit_avoids_db_query(self, mock_repo: MagicMock) -> None:
        """Segunda llamada al mismo hash usa cache (no consulta DB)."""
        mock_repo.get_dispatch.return_value = None
        layer = ExactMatchLayer(repo=mock_repo)
        layer.check("hash123")
        layer.check("hash123")
        # Solo debe haber 1 llamada a get_dispatch (primera vez)
        assert mock_repo.get_dispatch.call_count == 1

    def test_clear_cache_resets(self, mock_repo: MagicMock) -> None:
        """clear_cache() permite re-consultar la DB."""
        mock_repo.get_dispatch.return_value = None
        layer = ExactMatchLayer(repo=mock_repo)
        layer.check("hash123")
        layer.clear_cache()
        layer.check("hash123")
        assert mock_repo.get_dispatch.call_count == 2


# ── IdempotencyLayer (Capa 2) ──────────────────────────────────────────


class TestIdempotencyLayer:
    """Capa 2: detecta dispatches in-progress y gestiona subscribers."""

    def test_no_dispatch_returns_proceed(self, mock_repo: MagicMock) -> None:
        """Sin dispatch → proceed."""
        mock_repo.get_dispatch.return_value = None
        layer = IdempotencyLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"
        assert result["subscription_id"] is None

    def test_running_dispatch_returns_subscribe(self, mock_repo: MagicMock) -> None:
        """Dispatch running → subscribe + increment_subscriber."""
        mock_repo.get_dispatch.return_value = {"status": "running", "result_cache": None}
        mock_repo.increment_subscriber.return_value = 2
        layer = IdempotencyLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is True
        assert result["action"] == "subscribe"
        assert result["subscription_id"] == "sub_hash123_2"
        mock_repo.increment_subscriber.assert_called_once_with("hash123")

    def test_dispatched_status_returns_subscribe(self, mock_repo: MagicMock) -> None:
        """Status 'dispatched' también es activo → subscribe."""
        mock_repo.get_dispatch.return_value = {
            "status": "dispatched", "result_cache": None,
        }
        mock_repo.increment_subscriber.return_value = 1
        layer = IdempotencyLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["action"] == "subscribe"

    def test_completed_dispatch_returns_proceed(self, mock_repo: MagicMock) -> None:
        """Dispatch completed → proceed (lo maneja exact_match)."""
        mock_repo.get_dispatch.return_value = {
            "status": "completed", "result_cache": None,
        }
        layer = IdempotencyLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_failed_dispatch_returns_proceed(self, mock_repo: MagicMock) -> None:
        """Dispatch failed → proceed."""
        mock_repo.get_dispatch.return_value = {
            "status": "failed", "result_cache": None,
        }
        layer = IdempotencyLayer(repo=mock_repo)
        result = layer.check("hash123")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"


# ── TTLFreshnessLayer (Capa 3) ─────────────────────────────────────────


class TestTTLFreshnessLayer:
    """Capa 3: detecta doble-click dentro de ventana TTL."""

    def test_no_recent_dispatches_returns_proceed(
        self, mock_repo: MagicMock,
    ) -> None:
        """Sin dispatches recientes → proceed."""
        mock_repo.get_recent_dispatches_by_hash.return_value = []
        layer = TTLFreshnessLayer(repo=mock_repo, ttl_seconds=2)
        result = layer.check("hash123", "u1", "s1")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_recent_dispatches_returns_discard(self, mock_repo: MagicMock) -> None:
        """Con dispatches recientes del mismo hash → discard."""
        mock_repo.get_recent_dispatches_by_hash.return_value = [
            {"id": 1, "intent_hash": "hash123"},
        ]
        layer = TTLFreshnessLayer(repo=mock_repo, ttl_seconds=2)
        result = layer.check("hash123", "u1", "s1")
        assert result["duplicate"] is True
        assert result["action"] == "discard"
        assert "1 dispatch" in result["reason"]

    def test_default_ttl_is_2_seconds(self, mock_repo: MagicMock) -> None:
        """DEFAULT_TTL_SECONDS es 2."""
        assert DEFAULT_TTL_SECONDS == 2

    def test_custom_ttl_passed_to_repo_query(
        self, mock_repo: MagicMock,
    ) -> None:
        """ttl_seconds se pasa al repo para filtrar."""
        mock_repo.get_recent_dispatches_by_hash.return_value = []
        layer = TTLFreshnessLayer(repo=mock_repo, ttl_seconds=10)
        layer.check("hash123", "u1", "s1")
        # Verificar que se llamó con since_seconds=10
        call_args = mock_repo.get_recent_dispatches_by_hash.call_args
        assert call_args is not None
        assert call_args.kwargs.get("since_seconds") == 10

    def test_cache_hit_avoids_db_query(self, mock_repo: MagicMock) -> None:
        """Segunda llamada al mismo hash dentro de TTL usa cache."""
        mock_repo.get_recent_dispatches_by_hash.return_value = []
        layer = TTLFreshnessLayer(repo=mock_repo, ttl_seconds=5)
        layer.check("hash123", "u1", "s1")
        layer.check("hash123", "u1", "s1")
        # Solo 1 llamada a la DB (segunda usa cache)
        assert mock_repo.get_recent_dispatches_by_hash.call_count == 1

    def test_clear_cache_resets(self, mock_repo: MagicMock) -> None:
        """clear_cache() fuerza re-consulta."""
        mock_repo.get_recent_dispatches_by_hash.return_value = []
        layer = TTLFreshnessLayer(repo=mock_repo, ttl_seconds=5)
        layer.check("hash123", "u1", "s1")
        layer.clear_cache()
        layer.check("hash123", "u1", "s1")
        assert mock_repo.get_recent_dispatches_by_hash.call_count == 2

    def test_multiple_recent_dispatches_counted(self, mock_repo: MagicMock) -> None:
        """Múltiples dispatches recientes se cuentan en el reason."""
        mock_repo.get_recent_dispatches_by_hash.return_value = [
            {"id": 1}, {"id": 2}, {"id": 3},
        ]
        layer = TTLFreshnessLayer(repo=mock_repo, ttl_seconds=5)
        result = layer.check("hash123", "u1", "s1")
        assert result["duplicate"] is True
        assert "3 dispatch" in result["reason"]
