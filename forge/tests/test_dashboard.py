"""
Tests for forge/dashboard.py — DashboardGenerator
Cobertura: load_current_scores, load_history, save_snapshot, compute_summary, generate, save
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge.dashboard import DashboardGenerator, ModuleScore


@pytest.fixture
def project_with_homologation(tmp_path: Path) -> Path:
    """Crea un proyecto temporal con homologation_summary.json."""
    forge_dir = tmp_path / ".forge" / "phase6"
    forge_dir.mkdir(parents=True)
    summary = {
        "run_id": "test-phase6",
        "modules": [
            {
                "module": "6.1-core", "path": "src/core", "stack": "python",
                "criticality": "high", "file_count": 74,
                "gates_pass": 3, "gates_total": 5, "avg_score": 9.2,
                "status": "PARCIAL",
                "results": [
                    {"name": "lint_clean", "passed": True, "evidence": "0 issues", "score": 10.0},
                    {"name": "types_clean", "passed": False, "evidence": "212 errors", "score": 5.0},
                ],
            },
            {
                "module": "6.2-orbital", "path": "src/orbital", "stack": "python",
                "criticality": "high", "file_count": 20,
                "gates_pass": 3, "gates_total": 5, "avg_score": 9.3,
                "status": "PARCIAL",
                "results": [],
            },
        ],
    }
    (forge_dir / "homologation_summary.json").write_text(json.dumps(summary, indent=2))
    return tmp_path


class TestLoadCurrentScores:
    """Tests de load_current_scores."""

    def test_loads_modules_from_homologation(self, project_with_homologation: Path):
        """Carga módulos del homologation_summary.json."""
        gen = DashboardGenerator(project_with_homologation)
        modules = gen.load_current_scores()
        assert len(modules) == 2
        assert modules[0]["name"] == "6.1-core"
        assert modules[0]["avg_score"] == 9.2
        assert modules[1]["name"] == "6.2-orbital"

    def test_returns_empty_when_no_file(self, tmp_path: Path):
        """Devuelve lista vacía si no existe homologation_summary."""
        gen = DashboardGenerator(tmp_path)
        assert gen.load_current_scores() == []

    def test_skips_skipped_modules(self, tmp_path: Path):
        """Módulos con skipped=True se omiten."""
        forge_dir = tmp_path / ".forge" / "phase6"
        forge_dir.mkdir(parents=True)
        summary = {
            "modules": [
                {"module": "active", "path": "src/a", "stack": "python", "criticality": "low",
                 "file_count": 1, "gates_pass": 1, "gates_total": 1, "avg_score": 10.0,
                 "status": "HOMOLOGADO", "results": []},
                {"name": "skipped-mod", "skipped": True, "reason": "path not found"},
            ]
        }
        (forge_dir / "homologation_summary.json").write_text(json.dumps(summary))
        gen = DashboardGenerator(tmp_path)
        modules = gen.load_current_scores()
        assert len(modules) == 1
        assert modules[0]["name"] == "active"


class TestLoadAndSaveHistory:
    """Tests de load_history y save_snapshot."""

    def test_load_empty_history(self, tmp_path: Path):
        """Devuelve lista vacía si no hay historial."""
        gen = DashboardGenerator(tmp_path)
        assert gen.load_history() == []

    def test_save_and_load_snapshot(self, project_with_homologation: Path):
        """Guarda y carga snapshots correctamente."""
        gen = DashboardGenerator(project_with_homologation)
        modules = gen.load_current_scores()
        gen.save_snapshot(modules)

        history = gen.load_history()
        assert len(history) == 1
        assert history[0]["global_avg"] > 0
        assert len(history[0]["modules"]) == 2

    def test_history_keeps_max_50(self, project_with_homologation: Path):
        """El historial mantiene máximo 50 snapshots."""
        gen = DashboardGenerator(project_with_homologation)
        modules = gen.load_current_scores()
        # Guardar 55 snapshots
        for _ in range(55):
            gen.save_snapshot(modules)

        history = gen.load_history()
        assert len(history) == 50


class TestComputeSummary:
    """Tests de compute_summary."""

    def test_empty_modules(self, tmp_path: Path):
        """compute_summary con lista vacía."""
        gen = DashboardGenerator(tmp_path)
        summary = gen.compute_summary([])
        assert summary["total_modules"] == 0
        assert summary["avg_score"] == 0.0

    def test_summary_with_modules(self, project_with_homologation: Path):
        """compute_summary calcula correctamente."""
        gen = DashboardGenerator(project_with_homologation)
        modules = gen.load_current_scores()
        summary = gen.compute_summary(modules)
        assert summary["total_modules"] == 2
        assert summary["partial"] == 2
        assert summary["homologated"] == 0
        assert summary["total_gates_pass"] == 6  # 3+3
        assert summary["total_gates"] == 10  # 5+5
        assert 9.0 < summary["avg_score"] < 9.5  # avg of 9.2 and 9.3

    def test_summary_with_mixed_statuses(self, tmp_path: Path):
        """Summary con módulos en diferentes estados."""
        modules: list[ModuleScore] = [
            ModuleScore(name="m1", path="a", stack="python", criticality="low",
                       file_count=1, gates_pass=5, gates_total=5, avg_score=10.0,
                       status="HOMOLOGADO", gates=[]),
            ModuleScore(name="m2", path="b", stack="python", criticality="low",
                       file_count=1, gates_pass=3, gates_total=5, avg_score=6.0,
                       status="PARCIAL", gates=[]),
            ModuleScore(name="m3", path="c", stack="python", criticality="low",
                       file_count=1, gates_pass=0, gates_total=5, avg_score=2.0,
                       status="NO_HOMOLOGADO", gates=[]),
        ]
        gen = DashboardGenerator(tmp_path)
        summary = gen.compute_summary(modules)
        assert summary["homologated"] == 1
        assert summary["partial"] == 1
        assert summary["not_homologated"] == 1


class TestGenerate:
    """Tests de generate (end-to-end)."""

    def test_generate_produces_valid_html(self, project_with_homologation: Path):
        """generate produce HTML válido."""
        gen = DashboardGenerator(project_with_homologation)
        html = gen.generate()
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "Code-Forge Dashboard" in html
        assert "6.1-core" in html
        assert "6.2-orbital" in html
        assert "Score Global" in html

    def test_generate_saves_snapshot(self, project_with_homologation: Path):
        """generate guarda un snapshot en el historial."""
        gen = DashboardGenerator(project_with_homologation)
        gen.generate()
        history = gen.load_history()
        assert len(history) == 1

    def test_generate_with_history_shows_delta(self, project_with_homologation: Path):
        """generate con historial previo muestra delta."""
        gen = DashboardGenerator(project_with_homologation)
        # Primera generación
        gen.generate()
        # Segunda generación
        html = gen.generate()
        assert "vs anterior" in html


class TestSave:
    """Tests de save."""

    def test_save_creates_file(self, tmp_path: Path):
        """save crea el archivo HTML en el path especificado."""
        gen = DashboardGenerator(tmp_path)
        output = tmp_path / "output" / "dashboard.html"
        saved = gen.save("<html>test</html>", output)
        assert saved.exists()
        assert saved.read_text() == "<html>test</html>"

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        """save crea directorios padre si no existen."""
        gen = DashboardGenerator(tmp_path)
        output = tmp_path / "deep" / "nested" / "dashboard.html"
        saved = gen.save("<html></html>", output)
        assert saved.exists()


class TestIntegrationWithRealData:
    """Tests de integración con datos reales del proyecto."""

    def test_generate_from_real_homologation(self):
        """generate funciona con el homologation_summary real de Fase 6."""
        project_root = Path(".")
        gen = DashboardGenerator(project_root)
        modules = gen.load_current_scores()
        if not modules:
            pytest.skip("No homologation_summary.json found")
        html = gen.generate()
        assert "<!DOCTYPE html>" in html
        assert "6.1-core" in html or "6." in html
        # Verificar que tiene al menos 12 módulos (cada uno genera un <tr>)
        tr_count = html.count("<tr>")
        assert tr_count >= 12, f"Expected >=12 <tr>, got {tr_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
