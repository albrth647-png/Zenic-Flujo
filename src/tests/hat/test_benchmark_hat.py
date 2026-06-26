"""
Tests para scripts/benchmark_hat.py (F0-D8 sub-feature 2).

Valida que el script de benchmark funciona correctamente sin necesidad de
ejecutarlo con N=1000 (que tomaría minutos).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_hat.py"


@pytest.fixture
def benchmark_module():
    """Carga el módulo benchmark_hat dinámicamente."""
    spec = importlib.util.spec_from_file_location("benchmark_hat", BENCHMARK_SCRIPT)
    assert spec is not None, "No se pudo cargar spec de benchmark_hat.py"
    assert spec.loader is not None, "Spec loader es None"
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_hat"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ─────────────────────────────────────────────────────────
# setup_router
# ─────────────────────────────────────────────────────────


class TestSetupRouter:
    def test_setup_router_returns_hat_router(self, benchmark_module):
        """setup_router() debe retornar una instancia de HATRouter."""
        from src.hat.level1_orchestrator.tick_router import HATRouter

        router = benchmark_module.setup_router()
        assert isinstance(router, HATRouter)

    def test_setup_router_publishes_2_cards(self, benchmark_module):
        """setup_router() publica las 2 Agent Cards (web_researcher + query_builder)."""
        from src.hat.level1_orchestrator.ledger.repository import LedgerRepository

        router = benchmark_module.setup_router()
        repo = LedgerRepository()
        cards = repo.get_agent_cards()
        agent_ids = {c["agent_id"] for c in cards}
        assert "web_researcher" in agent_ids
        assert "query_builder" in agent_ids


# ─────────────────────────────────────────────────────────
# run_benchmark
# ─────────────────────────────────────────────────────────


class TestRunBenchmark:
    def test_run_benchmark_returns_well_formed_dict(self, benchmark_module):
        """run_benchmark(N) retorna dict con todas las métricas esperadas."""
        result = benchmark_module.run_benchmark(n=3)
        required_fields = [
            "n_requests", "latencies_ms", "p50_ms", "p99_ms",
            "mean_ms", "min_ms", "max_ms", "stdev_ms",
            "success_count", "failure_count", "success_rate",
            "failures_sample", "timestamp",
        ]
        for field in required_fields:
            assert field in result, f"Falta campo {field!r}"

    def test_run_benchmark_n_equals_3(self, benchmark_module):
        """Con N=3, n_requests debe ser 3 y latencies_ms debe tener 3 elementos."""
        result = benchmark_module.run_benchmark(n=3)
        assert result["n_requests"] == 3
        assert len(result["latencies_ms"]) == 3

    def test_run_benchmark_p50_le_max(self, benchmark_module):
        """p50 nunca puede ser mayor que max."""
        result = benchmark_module.run_benchmark(n=3)
        assert result["p50_ms"] <= result["max_ms"]

    def test_run_benchmark_min_le_mean_le_max(self, benchmark_module):
        """min <= mean <= max."""
        result = benchmark_module.run_benchmark(n=3)
        assert result["min_ms"] <= result["mean_ms"] <= result["max_ms"]

    def test_run_benchmark_success_rate_in_range(self, benchmark_module):
        """success_rate debe estar en [0, 1]."""
        result = benchmark_module.run_benchmark(n=3)
        assert 0.0 <= result["success_rate"] <= 1.0

    def test_run_benchmark_timestamp_is_iso(self, benchmark_module):
        """timestamp debe ser una string ISO 8601 parseable."""
        from datetime import datetime

        result = benchmark_module.run_benchmark(n=2)
        # Debe poder parsearse como ISO
        datetime.fromisoformat(result["timestamp"])


# ─────────────────────────────────────────────────────────
# generate_markdown_report
# ─────────────────────────────────────────────────────────


class TestGenerateMarkdownReport:
    def test_returns_non_empty_string(self, benchmark_module):
        """generate_markdown_report() retorna string no vacío."""
        benchmark_data = {
            "n_requests": 5,
            "latencies_ms": [10, 20, 30, 40, 50],
            "p50_ms": 30,
            "p99_ms": 50,
            "mean_ms": 30,
            "min_ms": 10,
            "max_ms": 50,
            "stdev_ms": 15,
            "success_count": 5,
            "failure_count": 0,
            "success_rate": 1.0,
            "failures_sample": [],
            "timestamp": "2026-06-19T12:00:00+00:00",
        }
        markdown = benchmark_module.generate_markdown_report(benchmark_data)
        assert isinstance(markdown, str)
        assert len(markdown) > 0

    def test_includes_p50_and_p99(self, benchmark_module):
        """El markdown debe mencionar p50 y p99."""
        benchmark_data = {
            "n_requests": 5, "latencies_ms": [10, 20, 30, 40, 50],
            "p50_ms": 30, "p99_ms": 50, "mean_ms": 30, "min_ms": 10,
            "max_ms": 50, "stdev_ms": 15, "success_count": 5,
            "failure_count": 0, "success_rate": 1.0,
            "failures_sample": [], "timestamp": "2026-06-19T12:00:00+00:00",
        }
        markdown = benchmark_module.generate_markdown_report(benchmark_data)
        assert "p50" in markdown.lower()
        assert "p99" in markdown.lower()
        assert "30ms" in markdown
        assert "50ms" in markdown

    def test_includes_veredict_section(self, benchmark_module):
        """El markdown debe tener una sección de veredicto."""
        benchmark_data = {
            "n_requests": 5, "latencies_ms": [10, 20, 30, 40, 50],
            "p50_ms": 30, "p99_ms": 50, "mean_ms": 30, "min_ms": 10,
            "max_ms": 50, "stdev_ms": 15, "success_count": 5,
            "failure_count": 0, "success_rate": 1.0,
            "failures_sample": [], "timestamp": "2026-06-19T12:00:00+00:00",
        }
        markdown = benchmark_module.generate_markdown_report(benchmark_data)
        assert "Veredicto" in markdown or "veredicto" in markdown
        # Con p50=30 < 300 y p99=50 < 800, debe decir CUMPLE
        assert "CUMPLE" in markdown

    def test_veredict_no_cumple_when_p99_above_800(self, benchmark_module):
        """Si p99 > 800, el veredicto debe decir NO CUMPLE."""
        benchmark_data = {
            "n_requests": 5, "latencies_ms": [10, 20, 30, 40, 900],
            "p50_ms": 30, "p99_ms": 900, "mean_ms": 200, "min_ms": 10,
            "max_ms": 900, "stdev_ms": 350, "success_count": 5,
            "failure_count": 0, "success_rate": 1.0,
            "failures_sample": [], "timestamp": "2026-06-19T12:00:00+00:00",
        }
        markdown = benchmark_module.generate_markdown_report(benchmark_data)
        assert "NO CUMPLE" in markdown
