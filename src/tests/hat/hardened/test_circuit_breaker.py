"""Tests para CircuitBreakerLayer — anti-dup nivel dominio.

Cubre:
- check() con dominio sin fallos → proceed.
- check() con dominio con >= threshold fallos → fallback.
- Failure threshold configurable.
- Sin progreso previo → proceed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level4_workers.circuit_breaker import CircuitBreakerLayer


@pytest.fixture
def mock_repo() -> MagicMock:
    """Mock del LedgerRepository."""
    repo = MagicMock()
    repo.get_progress.return_value = []
    return repo


@pytest.fixture
def layer(mock_repo: MagicMock) -> CircuitBreakerLayer:
    """CircuitBreakerLayer con repo mockeado."""
    return CircuitBreakerLayer(repo=mock_repo, failure_threshold=3)


class TestCheckNoFailures:
    """check() cuando no hay fallos previos."""

    def test_no_progress_returns_proceed(
        self, layer: CircuitBreakerLayer, mock_repo: MagicMock,
    ) -> None:
        """Sin dispatches previos → proceed."""
        mock_repo.get_progress.return_value = []
        result = layer.check("operaciones", "u1", "s1")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_only_completed_dispatches_returns_proceed(
        self, layer: CircuitBreakerLayer, mock_repo: MagicMock,
    ) -> None:
        """Solo dispatches completados → proceed."""
        mock_repo.get_progress.return_value = [
            {"domain": "operaciones", "status": "completed"},
            {"domain": "operaciones", "status": "completed"},
        ]
        result = layer.check("operaciones", "u1", "s1")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"


class TestCheckWithFailures:
    """check() cuando hay fallos previos."""

    def test_threshold_failures_triggers_fallback(
        self, layer: CircuitBreakerLayer, mock_repo: MagicMock,
    ) -> None:
        """>= threshold fallos consecutivos → fallback."""
        mock_repo.get_progress.return_value = [
            {"domain": "operaciones", "status": "failed"},
            {"domain": "operaciones", "status": "failed"},
            {"domain": "operaciones", "status": "failed"},
        ]
        result = layer.check("operaciones", "u1", "s1")
        assert result["duplicate"] is True
        assert result["action"] == "fallback"

    def test_below_threshold_does_not_trigger(
        self, layer: CircuitBreakerLayer, mock_repo: MagicMock,
    ) -> None:
        """< threshold fallos → proceed."""
        mock_repo.get_progress.return_value = [
            {"domain": "operaciones", "status": "failed"},
            {"domain": "operaciones", "status": "failed"},
        ]
        result = layer.check("operaciones", "u1", "s1")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_failed_then_completed_resets_count(
        self, layer: CircuitBreakerLayer, mock_repo: MagicMock,
    ) -> None:
        """Un completed entre failed resetea el contador consecutivo."""
        mock_repo.get_progress.return_value = [
            {"domain": "operaciones", "status": "failed"},
            {"domain": "operaciones", "status": "failed"},
            {"domain": "operaciones", "status": "completed"},  # reset
            {"domain": "operaciones", "status": "failed"},
            {"domain": "operaciones", "status": "failed"},
        ]
        result = layer.check("operaciones", "u1", "s1")
        # Solo 2 fallos consecutivos después del completed → proceed
        assert result["duplicate"] is False
        assert result["action"] == "proceed"

    def test_other_domain_failures_not_counted(
        self, layer: CircuitBreakerLayer, mock_repo: MagicMock,
    ) -> None:
        """Fallos de otro dominio no se cuentan."""
        mock_repo.get_progress.return_value = [
            {"domain": "comunicaciones", "status": "failed"},
            {"domain": "comunicaciones", "status": "failed"},
            {"domain": "comunicaciones", "status": "failed"},
        ]
        result = layer.check("operaciones", "u1", "s1")
        assert result["duplicate"] is False
        assert result["action"] == "proceed"


class TestConfigurableThreshold:
    """Threshold configurable."""

    def test_custom_threshold_5(
        self, mock_repo: MagicMock,
    ) -> None:
        """Threshold=5 requiere 5 fallos para abrir."""
        layer = CircuitBreakerLayer(repo=mock_repo, failure_threshold=5)
        mock_repo.get_progress.return_value = [
            {"domain": "d", "status": "failed"} for _ in range(4)
        ]
        result = layer.check("d", "u", "s")
        assert result["duplicate"] is False  # 4 < 5

        mock_repo.get_progress.return_value = [
            {"domain": "d", "status": "failed"} for _ in range(5)
        ]
        result = layer.check("d", "u", "s")
        assert result["duplicate"] is True  # 5 >= 5

    def test_default_threshold_is_3(self) -> None:
        """DEFAULT_FAILURE_THRESHOLD es 3."""
        from src.hat.level4_workers.circuit_breaker import DEFAULT_FAILURE_THRESHOLD
        assert DEFAULT_FAILURE_THRESHOLD == 3
