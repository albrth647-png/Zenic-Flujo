"""
Tests de integración Fase 5.3 — Memory + GateRunner
====================================================
Verifica que GateRunner genera reflexiones automáticas cuando un gate falla
y que las reflexiones son buscables via Jaccard similarity.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from forge import GateRunner, PersistentMemory
from forge.gates import GateResult


def _cleanup_memory(mem: PersistentMemory) -> None:
    """Limpia el directorio de memoria de forma segura."""
    try:
        if mem.workdir.exists():
            shutil.rmtree(mem.workdir, ignore_errors=True)
    except Exception:
        pass


class TestGateRunnerMemoryIntegration:
    """Tests de integración GateRunner + PersistentMemory."""

    def test_gate_runner_accepts_memory_in_constructor(self, tmp_path: Path):
        """GateRunner acepta memory en constructor."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        mem = PersistentMemory(tmp_path / "memory")
        runner = GateRunner(tmp_path, memory=mem)
        assert runner.memory is mem
        _cleanup_memory(mem)

    def test_gate_runner_without_memory_works(self, tmp_path: Path):
        """GateRunner sin memory funciona normalmente (backward compat)."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        runner = GateRunner(tmp_path)
        assert runner.memory is None
        # run_all debe funcionar sin generar reflexiones
        runner.run_all(stacks=[], exclude=set(runner.EXPENSIVE_GATES))

    def test_failed_gate_generates_reflection(self, tmp_path: Path):
        """Un gate que falla genera una reflexión en memory."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        mem = PersistentMemory(tmp_path / "memory")
        runner = GateRunner(tmp_path, memory=mem)

        # Simular un gate que falla
        runner.results["tests_pass:python"] = GateResult(
            "tests_pass",
            passed=False,
            evidence="Mock test failure: assertion error in test_x",
            stack="python",
            duration=1.5,
            score=0.0,
        )

        # Generar reflexiones
        runner._generate_reflections_on_failure()

        # Verificar que se generó la reflexión
        reflections = mem.get_all_reflections()
        assert len(reflections) == 1
        r = reflections[0]
        assert "gate-failure-tests_pass-python" in r["iteration_id"]
        assert r["score"] == 0.0
        assert "Mock test failure" in r["root_cause"]
        assert len(r["key_learnings"]) >= 1
        _cleanup_memory(mem)

    def test_passed_gate_does_not_generate_reflection(self, tmp_path: Path):
        """Un gate que pasa NO genera reflexión."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        mem = PersistentMemory(tmp_path / "memory")
        runner = GateRunner(tmp_path, memory=mem)

        runner.results["tests_pass:python"] = GateResult(
            "tests_pass",
            passed=True,
            evidence="All tests passed",
            stack="python",
            duration=1.5,
            score=10.0,
        )

        runner._generate_reflections_on_failure()

        reflections = mem.get_all_reflections()
        assert len(reflections) == 0
        _cleanup_memory(mem)

    def test_skipped_gate_does_not_generate_reflection(self, tmp_path: Path):
        """Un gate SKIPPED (airgap) NO genera reflexión."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        mem = PersistentMemory(tmp_path / "memory")
        runner = GateRunner(tmp_path, memory=mem)

        runner.results["mutation_score:python"] = GateResult(
            "mutation_score",
            passed=False,
            evidence="SKIPPED: airgap mode (network unavailable)",
            stack="python",
            duration=0.0,
            score=0.0,
        )

        runner._generate_reflections_on_failure()

        reflections = mem.get_all_reflections()
        assert len(reflections) == 0
        _cleanup_memory(mem)

    def test_multiple_failures_generate_multiple_reflections(self, tmp_path: Path):
        """Múltiples gates fallidos generan múltiples reflexiones."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        mem = PersistentMemory(tmp_path / "memory")
        runner = GateRunner(tmp_path, memory=mem)

        runner.results["tests_pass:python"] = GateResult(
            "tests_pass", passed=False, evidence="test failure 1", stack="python", duration=1.0,
        )
        runner.results["lint_clean:python"] = GateResult(
            "lint_clean", passed=False, evidence="lint error", stack="python", duration=0.5,
        )
        runner.results["types_clean:python"] = GateResult(
            "types_clean", passed=False, evidence="type error", stack="python", duration=2.0,
        )

        runner._generate_reflections_on_failure()

        reflections = mem.get_all_reflections()
        assert len(reflections) == 3
        _cleanup_memory(mem)


class TestExtractLearningsFromFailure:
    """Tests de _extract_learnings_from_failure."""

    def test_lint_clean_learnings(self):
        """lint_clean genera learnings sobre auto-fix + manual fix."""
        result = GateResult("lint_clean", passed=False, evidence="ruff errors", stack="python", duration=0.0)
        learnings = GateRunner._extract_learnings_from_failure(result)
        assert len(learnings) >= 1
        assert any("auto-fix" in learning for learning in learnings)

    def test_types_clean_learnings(self):
        """types_clean genera learnings sobre type annotations."""
        result = GateResult("types_clean", passed=False, evidence="mypy errors", stack="typescript", duration=0.0)
        learnings = GateRunner._extract_learnings_from_failure(result)
        assert any("type annotations" in learning for learning in learnings)

    def test_complexity_max_learnings(self):
        """complexity_max genera learnings sobre dict dispatch."""
        result = GateResult("complexity_max", passed=False, evidence="CC>10", stack="python", duration=0.0)
        learnings = GateRunner._extract_learnings_from_failure(result)
        assert any("dict dispatch" in learning for learning in learnings)

    def test_unknown_gate_still_generates_search_hint(self):
        """Gate desconocido genera al menos el search hint."""
        result = GateResult("unknown_gate", passed=False, evidence="?", stack="python", duration=0.0)
        learnings = GateRunner._extract_learnings_from_failure(result)
        assert len(learnings) == 1
        assert "find_similar" in learnings[0]

    def test_learnings_max_5(self):
        """Lista de learnings se limita a 5."""
        result = GateResult("tests_pass", passed=False, evidence="fail", stack="python", duration=0.0)
        learnings = GateRunner._extract_learnings_from_failure(result)
        assert len(learnings) <= 5


class TestEndToEndMemoryFlow:
    """Tests end-to-end: run gates → failures → reflections → search."""

    def test_run_all_with_memory_generates_reflections_on_failure(self, tmp_path: Path):
        """run_all con memory genera reflexiones cuando gates fallan."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")
        mem = PersistentMemory(tmp_path / "memory")
        runner = GateRunner(tmp_path, memory=mem)

        # Mock _run_cmd para simular failures
        def mock_run_cmd(cmd, cwd, timeout=120):
            return {"stdout": "", "stderr": "mock failure", "returncode": 1}

        with patch.object(runner, "_run_cmd", side_effect=mock_run_cmd):
            runner.run_all(stacks=["python"], exclude=runner.EXPENSIVE_GATES | {"test_quality"})

        # Verificar que se generaron reflexiones para gates fallidos
        reflections = mem.get_all_reflections()
        assert len(reflections) > 0

        # Verificar que las reflexiones son buscables
        similar = mem.find_similar("gate failure python tests", top_n=5)
        assert len(similar) > 0
        _cleanup_memory(mem)

    def test_reflections_persist_across_sessions(self, tmp_path: Path):
        """Las reflexiones generadas persisten entre sesiones de GateRunner."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("")

        # Sesión 1: generar reflexiones
        mem1 = PersistentMemory(tmp_path / "memory")
        runner1 = GateRunner(tmp_path, memory=mem1)
        runner1.results["tests_pass:python"] = GateResult(
            "tests_pass", passed=False, evidence="session 1 failure", stack="python", duration=1.0,
        )
        runner1._generate_reflections_on_failure()
        mem1_path = mem1.memory_path

        # Sesión 2: cargar memoria existente y buscar
        mem2 = PersistentMemory(tmp_path / "memory")
        assert mem2.memory_path == mem1_path

        similar = mem2.find_similar("tests_pass python failure", top_n=5)
        assert len(similar) > 0
        assert "session 1 failure" in similar[0]["root_cause"]
        _cleanup_memory(mem2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
