"""
Tests para scripts/benchmark_anti_dup.py (F1-D2 sub-feature 1).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_SCRIPT = REPO_ROOT / "scripts" / "benchmark_anti_dup.py"


@pytest.fixture
def benchmark_module():
    """Carga el módulo benchmark_anti_dup dinámicamente."""
    spec = importlib.util.spec_from_file_location("benchmark_anti_dup", BENCHMARK_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmark_anti_dup"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class TestRunBenchmark:
    def test_returns_well_formed_dict(self, benchmark_module):
        result = benchmark_module.run_benchmark(n=3)
        required = [
            "n_requests", "latencies_ms", "p50_ms", "p99_ms",
            "mean_ms", "min_ms", "max_ms", "stdev_ms",
            "blocked_count", "block_rate", "timestamp",
        ]
        for field in required:
            assert field in result, f"Falta campo {field!r}"

    def test_n_equals_3(self, benchmark_module):
        result = benchmark_module.run_benchmark(n=3)
        assert result["n_requests"] == 3
        assert len(result["latencies_ms"]) == 3

    def test_p50_le_max(self, benchmark_module):
        result = benchmark_module.run_benchmark(n=3)
        assert result["p50_ms"] <= result["max_ms"]

    def test_min_le_mean_le_max(self, benchmark_module):
        result = benchmark_module.run_benchmark(n=3)
        assert result["min_ms"] <= result["mean_ms"] <= result["max_ms"]

    def test_block_rate_in_range(self, benchmark_module):
        result = benchmark_module.run_benchmark(n=3)
        assert 0.0 <= result["block_rate"] <= 1.0


class TestGenerateMarkdownReport:
    def test_returns_non_empty_string(self, benchmark_module):
        data = {
            "n_requests": 5, "latencies_ms": [1, 2, 3, 4, 5],
            "p50_ms": 3, "p99_ms": 5, "mean_ms": 3, "min_ms": 1,
            "max_ms": 5, "stdev_ms": 1, "blocked_count": 0,
            "block_rate": 0.0, "timestamp": "2026-06-19T12:00:00+00:00",
        }
        md = benchmark_module.generate_markdown_report(data)
        assert isinstance(md, str)
        assert len(md) > 0

    def test_includes_p99(self, benchmark_module):
        data = {
            "n_requests": 5, "latencies_ms": [1, 2, 3, 4, 5],
            "p50_ms": 3, "p99_ms": 5, "mean_ms": 3, "min_ms": 1,
            "max_ms": 5, "stdev_ms": 1, "blocked_count": 0,
            "block_rate": 0.0, "timestamp": "2026-06-19T12:00:00+00:00",
        }
        md = benchmark_module.generate_markdown_report(data)
        assert "p99" in md.lower()
        assert "5ms" in md

    def test_cumple_when_p99_below_40(self, benchmark_module):
        data = {
            "n_requests": 5, "latencies_ms": [1, 2, 3, 4, 5],
            "p50_ms": 3, "p99_ms": 5, "mean_ms": 3, "min_ms": 1,
            "max_ms": 5, "stdev_ms": 1, "blocked_count": 0,
            "block_rate": 0.0, "timestamp": "2026-06-19T12:00:00+00:00",
        }
        md = benchmark_module.generate_markdown_report(data)
        assert "CUMPLE" in md

    def test_no_cumple_when_p99_above_40(self, benchmark_module):
        data = {
            "n_requests": 5, "latencies_ms": [1, 2, 3, 4, 50],
            "p50_ms": 3, "p99_ms": 50, "mean_ms": 12, "min_ms": 1,
            "max_ms": 50, "stdev_ms": 20, "blocked_count": 0,
            "block_rate": 0.0, "timestamp": "2026-06-19T12:00:00+00:00",
        }
        md = benchmark_module.generate_markdown_report(data)
        assert "NO CUMPLE" in md
