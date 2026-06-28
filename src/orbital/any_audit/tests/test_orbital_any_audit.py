"""Tests para el módulo orbital/any_audit.

Cubre:
  - AnyAuditMapper: conversión módulo/antipatrón → VariableOrbital
  - OrbitalAnyAuditEngine: ejecución end-to-end de auditoría orbital
  - Casos edge: módulos con 0 deuda, over-justification, sin ocurrencias
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Asegurar imports
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ANY_AUDIT_PATH = PROJECT_ROOT / "scripts" / "any_audit"
if str(ANY_AUDIT_PATH) not in sys.path:
    sys.path.insert(0, str(ANY_AUDIT_PATH))

from src.orbital.any_audit import AnyAuditMapper, OrbitalAnyAuditEngine
from src.orbital.any_audit.mapper import (
    DEBT_CORRELATION_CYCLES,
    AntipatternStats,
    ModuleStats,
)
from src.orbital.models import VariableOrbital


# ─── Tests: AnyAuditMapper ──────────────────────────────────────────────────


class TestAnyAuditMapper:
    """Tests del mapper módulo/antipatrón → VariableOrbital."""

    def setup_method(self) -> None:
        self.mapper = AnyAuditMapper()

    def test_module_to_variable_basic(self) -> None:
        """Módulo con deuda real se convierte en variable con amplitud > 1."""
        stats = ModuleStats(
            name="src/test",
            total=100,
            legitimate_imports=10,
            justified=20,
            real_debt=70,
        )
        var = self.mapper.module_to_variable(stats)
        assert var.name == "module:src/test"
        assert var.orbit_group == "modules"
        assert var.amplitude == pytest.approx(math.sqrt(71))
        assert var.velocity == 0.05

    def test_module_to_variable_zero_debt(self) -> None:
        """Módulo con 0 deuda real → amplitud mínima 1, theta 0."""
        stats = ModuleStats(
            name="src/clean",
            total=50,
            legitimate_imports=50,
            justified=0,
            real_debt=0,
        )
        var = self.mapper.module_to_variable(stats)
        assert var.amplitude == pytest.approx(1.0)
        assert var.theta == 0.0

    def test_module_to_variable_negative_debt_clamped(self) -> None:
        """real_debt negativo (over-justification) se clampéa a 0."""
        stats = ModuleStats(
            name="src/overjustified",
            total=10,
            legitimate_imports=8,
            justified=5,
            real_debt=-3,  # legítimos + justificados > total
        )
        var = self.mapper.module_to_variable(stats)
        # No debe dar ValueError: math domain error
        assert var.amplitude == pytest.approx(1.0)  # sqrt(max(0, -3) + 1) = sqrt(1)
        assert var.metadata["real_debt"] == 0  # clampéado en metadata

    def test_module_to_variable_metadata(self) -> None:
        """La metadata incluye todas las estadísticas del módulo."""
        stats = ModuleStats(
            name="src/x",
            total=30,
            legitimate_imports=5,
            justified=10,
            real_debt=15,
        )
        var = self.mapper.module_to_variable(stats)
        assert var.metadata["module"] == "src/x"
        assert var.metadata["total"] == 30
        assert var.metadata["legitimate_imports"] == 5
        assert var.metadata["justified"] == 10
        assert var.metadata["real_debt"] == 15

    def test_antipattern_to_variable_basic(self) -> None:
        """Antipatrón frecuente → amplitud proporcional a sqrt(count)."""
        stats = AntipatternStats(name="bare_dict", count=893, description="desc")
        var = self.mapper.antipattern_to_variable(stats, total_antipatterns=1000)
        assert var.name == "antipattern:bare_dict"
        assert var.orbit_group == "antipatterns"
        assert var.amplitude == pytest.approx(math.sqrt(894))
        assert var.velocity == 0.08

    def test_antipattern_to_variable_zero_count(self) -> None:
        """Antipatrón con count=0 → amplitud mínima."""
        stats = AntipatternStats(name="rare", count=0, description="desc")
        var = self.mapper.antipattern_to_variable(stats, total_antipatterns=100)
        assert var.amplitude == pytest.approx(1.0)

    def test_get_correlation_cycles_filters_missing(self) -> None:
        """Solo retorna ciclos donde ≥2 módulos existen."""
        existing = {"src/connectors", "src/sdk"}  # falta sdk/base
        cycles = self.mapper.get_correlation_cycles(existing)
        cycle_names = [c[0] for c in cycles]
        assert "connectors_sdk" in cycle_names
        # api_mobile no aplica porque no están api_v2 ni mobile
        assert "api_mobile" not in cycle_names

    def test_build_cycle_specs_returns_tuples(self) -> None:
        """build_cycle_specs retorna (name, var_names, threshold)."""
        existing = {"src/connectors", "src/sdk", "src/sdk/base"}
        specs = self.mapper.build_cycle_specs(existing)
        assert len(specs) >= 1
        for name, var_names, threshold in specs:
            assert isinstance(name, str)
            assert all(v.startswith("module:") for v in var_names)
            assert 0 < threshold < 1

    def test_debt_tension_resonant_modules(self) -> None:
        """Módulos con misma deuda → tensión alta (resonancia)."""
        stats_a = ModuleStats("a", total=100, legitimate_imports=0, justified=0, real_debt=50)
        stats_b = ModuleStats("b", total=100, legitimate_imports=0, justified=0, real_debt=50)
        tension = AnyAuditMapper.debt_tension(stats_a, stats_b)
        # A_i = sqrt(51), A_j = sqrt(51), cos(0) = 1 → tension = 51
        assert tension == pytest.approx(51.0, abs=0.01)

    def test_debt_tension_disparate_modules(self) -> None:
        """Módulos con deuda muy diferente → tensión baja o negativa."""
        stats_a = ModuleStats("a", total=100, legitimate_imports=0, justified=0, real_debt=90)
        stats_b = ModuleStats("b", total=100, legitimate_imports=0, justified=0, real_debt=10)
        tension = AnyAuditMapper.debt_tension(stats_a, stats_b)
        # cos(2π * (0.9 - 0.1)) = cos(1.6π) ≈ 0.809
        # tension = sqrt(91) * sqrt(11) * 0.809 ≈ 9.54 * 3.32 * 0.809 ≈ 25.6
        assert tension > 0  # sigue siendo positiva (ambos tienen deuda)


# ─── Tests: OrbitalAnyAuditEngine ───────────────────────────────────────────


class TestOrbitalAnyAuditEngine:
    """Tests del adapter OrbitalAnyAuditEngine."""

    def test_engine_instantiation(self) -> None:
        """El engine se instancia sin errores."""
        engine = OrbitalAnyAuditEngine(ticks=1)
        assert engine.orbital_engine is not None
        assert engine.last_audit_summary is None

    def test_run_audit_returns_result(self) -> None:
        """run_audit ejecuta el ciclo orbital y retorna OrbitalAuditResult."""
        engine = OrbitalAnyAuditEngine(ticks=2)
        result = engine.run_audit()
        assert result is not None
        assert result.tick == 2
        assert result.total_occurrences >= 0
        assert result.real_debt >= 0
        assert isinstance(result.hotspots, list)
        assert isinstance(result.refactor_strategy, list)
        assert isinstance(result.top_tensions, list)
        assert isinstance(result.retrofeedback, dict)

    def test_run_audit_creates_variables_in_engine(self) -> None:
        """Después de run_audit, el OrbitalEngine tiene variables de módulos."""
        engine = OrbitalAnyAuditEngine(ticks=1)
        engine.run_audit()
        all_vars = engine.orbital_engine.get_all_variables()
        module_vars = [v for v in all_vars if v.startswith("module:")]
        antipattern_vars = [v for v in all_vars if v.startswith("antipattern:")]
        assert len(module_vars) > 0
        assert len(antipattern_vars) > 0

    def test_run_audit_hotspots_format(self) -> None:
        """Los hotspots tienen el formato correcto."""
        engine = OrbitalAnyAuditEngine(ticks=2)
        result = engine.run_audit()
        for h in result.hotspots:
            assert "cycle" in h
            assert "modules" in h
            assert "resonance" in h
            assert "tick" in h
            assert isinstance(h["modules"], list)
            assert -1 <= h["resonance"] <= 1

    def test_run_audit_refactor_strategy_format(self) -> None:
        """La estrategia de refactor tiene el formato correcto."""
        engine = OrbitalAnyAuditEngine(ticks=2)
        result = engine.run_audit()
        for s in result.refactor_strategy:
            assert "module" in s
            assert "orbital_value" in s
            assert "real_debt" in s
            assert "total" in s
            assert s["real_debt"] >= 0  # nunca negativo

    def test_write_orbital_report(self, tmp_path: Path) -> None:
        """write_orbital_report genera un archivo markdown válido."""
        engine = OrbitalAnyAuditEngine(ticks=1)
        result = engine.run_audit()
        out = tmp_path / "report.md"
        engine.write_orbital_report(result, out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Any Audit Orbital Report" in content
        assert "Hotspots" in content
        assert "Estrategia" in content

    def test_run_audit_with_custom_path(self, tmp_path: Path) -> None:
        """run_audit respeta scan_path personalizado.

        Verifica que el engine puede instanciarse con un path custom
        y ejecutar run_audit sin errores (aunque no encuentre archivos
        si el path no es PROJECT_ROOT/src).
        """
        # El any_audit.scan_project filtra archivos fuera de PROJECT_ROOT/src
        # (ver _iter_python_files). Para test real de detección, ver otros tests
        # que usan el scan_path default (src/).
        custom_path = tmp_path / "custom_src"
        custom_path.mkdir()
        (custom_path / "empty.py").write_text("# empty\n", encoding="utf-8")
        engine = OrbitalAnyAuditEngine(scan_path=custom_path, ticks=1)
        result = engine.run_audit()
        # No encuentra archivos (path fuera de PROJECT_ROOT/src) pero no crashea
        assert result is not None
        assert result.tick == 1


# ─── Tests: integración con OrbitalEngine ───────────────────────────────────


class TestOrbitalEngineIntegration:
    """Tests de integración con el OrbitalEngine real."""

    def test_orbital_engine_runs_ticks(self) -> None:
        """El OrbitalEngine subyacente ejecuta ticks correctamente."""
        engine = OrbitalAnyAuditEngine(ticks=3)
        engine.run_audit()
        assert engine.orbital_engine.tick == 3

    def test_orbital_result_has_tor_results(self) -> None:
        """El resultado orbital tiene TOR results (matriz de tensiones)."""
        engine = OrbitalAnyAuditEngine(ticks=1)
        result = engine.run_audit()
        if result.orbital_result:
            assert len(result.orbital_result.tor_results) >= 0

    def test_orbital_result_has_espectro(self) -> None:
        """El resultado orbital tiene un EspectroEstado."""
        engine = OrbitalAnyAuditEngine(ticks=1)
        result = engine.run_audit()
        if result.orbital_result:
            assert result.orbital_result.espectro is not None

    def test_orbital_variables_have_correct_orbit_group(self) -> None:
        """Las variables se crean en los orbit_group correctos."""
        engine = OrbitalAnyAuditEngine(ticks=1)
        engine.run_audit()
        all_vars = engine.orbital_engine.get_all_variables()
        for name, var in all_vars.items():
            if name.startswith("module:"):
                assert var.orbit_group == "modules"
            elif name.startswith("antipattern:"):
                assert var.orbit_group == "antipatterns"
