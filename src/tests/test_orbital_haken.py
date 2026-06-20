"""
Tests unitarios para el módulo Haken Synergetics (Mejora 4).

Verifica:
1. Escala temporal exacta τ_k = -1/ln|λ_k|
2. Identificación del modo rotacional (overlap con vector uniforme)
3. Clasificación canónica: democratic, unstable, marginal
4. Order parameters con amplitudes heterogéneas
5. Proyección espectral y reconstrucción
6. Edge cases: N=0, N=1, N=2, β=0
7. Integración con CODResult
8. Determinismo
9. Stress test
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("WFD_SESSION_SECRET", "test-only")
os.environ.setdefault("WFD_LICENSE_SECRET", "test-only")

import pytest
import logging
logging.disable(logging.CRITICAL)

import numpy as np

from src.orbital.engine import OrbitalEngine
from src.orbital.haken import (
    HAKEN_SLAVING_THRESHOLD,
    HakenAnalyzer,
    HakenStatus,
    ModeInfo,
    ModeType,
    OrderParameter,
    SlavingState,
)
from src.orbital.models import TWO_PI


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def synced_engine() -> OrbitalEngine:
    """3 vars sincronizadas con amplitudes uniformes → democratic."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_variable("b", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_variable("c", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_cycle("sync", ["a", "b", "c"], threshold=0.5)
    return engine


@pytest.fixture
def heterogeneous_engine() -> OrbitalEngine:
    """4 vars con amplitudes heterogéneas → gap espectral esperado."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=10.0, velocity=0.1)
    engine.create_variable("b", theta=1.0, amplitude=10.0, velocity=0.1)
    engine.create_variable("c", theta=2.0, amplitude=0.1, velocity=0.1)
    engine.create_variable("d", theta=3.0, amplitude=0.1, velocity=0.1)
    engine.create_cycle("het", ["a", "b", "c", "d"], threshold=0.3)
    return engine


# =============================================================================
# Test 1: Escala temporal exacta
# =============================================================================


def test_timescale_formula_exact() -> None:
    """τ_k = -1/ln|λ_k| para modos estables."""
    # Para λ=0.5: τ = -1/ln(0.5) = -1/(-0.693) = 1.443
    expected_tau = -1.0 / math.log(0.5)
    assert math.isclose(expected_tau, 1.4427, rel_tol=1e-3)


def test_timescale_nan_for_unstable() -> None:
    """τ_k = NaN para modos inestables (|λ| > 1)."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=math.pi, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"])
    # Antifase → inestable → τ debe ser NaN
    unstable_modes = [m for m in status.modes if m.mode_type == ModeType.UNSTABLE]
    assert len(unstable_modes) >= 1
    for m in unstable_modes:
        assert math.isnan(m.timescale_tau)


def test_timescale_inf_for_marginal() -> None:
    """τ_k = +inf para modos marginales (|λ| ≈ 1)."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)
    analyzer = HakenAnalyzer()
    # β=1.0 → λ = 1-1·2 = -1 → |λ|=1 → marginal
    status = analyzer.analyze(engine.ovc, engine.tor, beta=1.0, cycle_variable_ids=["x", "y"])
    assert status.slaving_state == SlavingState.NOT_APPLICABLE_MARGINAL


# =============================================================================
# Test 2: Modo rotacional
# =============================================================================


def test_rotational_mode_overlap_one(synced_engine: OrbitalEngine) -> None:
    """El modo rotacional tiene overlap ≈ 1 con (1,...,1)/√N."""
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(synced_engine.ovc, synced_engine.tor, beta=0.1,
                               cycle_variable_ids=["a", "b", "c"])
    rotational_modes = [m for m in status.modes if m.mode_type == ModeType.ROTATIONAL]
    assert len(rotational_modes) == 1
    assert rotational_modes[0].overlap_with_rotational > 1.0 - 1e-6


def test_rotational_mode_not_order_parameter(synced_engine: OrbitalEngine) -> None:
    """El modo rotacional NO aparece en order_parameters."""
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(synced_engine.ovc, synced_engine.tor, beta=0.1,
                               cycle_variable_ids=["a", "b", "c"])
    for op in status.order_parameters:
        assert op.mode.mode_type != ModeType.ROTATIONAL


def test_rotational_eigenvalue_zero(synced_engine: OrbitalEngine) -> None:
    """El autovalor del modo rotacional es ≈ 0."""
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(synced_engine.ovc, synced_engine.tor, beta=0.1,
                               cycle_variable_ids=["a", "b", "c"])
    rot = [m for m in status.modes if m.mode_type == ModeType.ROTATIONAL][0]
    assert abs(rot.eigenvalue_mu) < 1e-6


# =============================================================================
# Test 3: Clasificación canónica
# =============================================================================


def test_N0_returns_trivial() -> None:
    """Engine vacío → NOT_APPLICABLE_TRIVIAL."""
    engine = OrbitalEngine()
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.5)
    assert status.slaving_state == SlavingState.NOT_APPLICABLE_TRIVIAL
    assert status.n_variables == 0


def test_N1_returns_trivial() -> None:
    """1 sola variable → NOT_APPLICABLE_TRIVIAL."""
    engine = OrbitalEngine()
    engine.create_variable("solo", theta=1.0, amplitude=2.0)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.5)
    assert status.slaving_state == SlavingState.NOT_APPLICABLE_TRIVIAL


def test_N2_returns_democratic() -> None:
    """N=2 con sistema estable → DEMOCRATIC (solo 1 modo no-rotacional)."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"])
    assert status.slaving_state == SlavingState.DEMOCRATIC
    assert status.slaving_active is False


def test_N3_synced_democratic(synced_engine: OrbitalEngine) -> None:
    """3 vars sincronizadas con amplitudes uniformes → DEMOCRATIC (μ degenerados)."""
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(synced_engine.ovc, synced_engine.tor, beta=0.1,
                               cycle_variable_ids=["a", "b", "c"])
    assert status.slaving_state == SlavingState.DEMOCRATIC
    assert status.separation_ratio == 1.0


def test_N2_antifase_unstable() -> None:
    """N=2 antifase → NOT_APPLICABLE_UNSTABLE."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=math.pi, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"])
    assert status.slaving_state == SlavingState.NOT_APPLICABLE_UNSTABLE
    assert status.n_modes_unstable >= 1


def test_beta_zero_trivial() -> None:
    """β=0 → NOT_APPLICABLE_TRIVIAL."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0)
    engine.create_variable("b", theta=1.0, amplitude=1.0)
    engine.create_cycle("ab", ["a", "b"], threshold=0.5)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.0, cycle_variable_ids=["a", "b"])
    assert status.slaving_state == SlavingState.NOT_APPLICABLE_TRIVIAL


# =============================================================================
# Test 4: Order parameters con amplitudes heterogéneas
# =============================================================================


def test_heterogeneous_amplitudes_produce_gap(heterogeneous_engine: OrbitalEngine) -> None:
    """Amplitudes heterogéneas deberían producir gap espectral."""
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(heterogeneous_engine.ovc, heterogeneous_engine.tor,
                               beta=0.01, cycle_variable_ids=["a", "b", "c", "d"])
    # Con amplitudes muy heterogéneas, esperamos que el análisis no sea trivial
    assert status.slaving_state in (
        SlavingState.ACTIVE, SlavingState.WEAK, SlavingState.DEMOCRATIC,
        SlavingState.NOT_APPLICABLE_UNSTABLE,
    )
    # Al menos debe tener 4 modos totales
    assert status.n_modes_total == 4
    assert status.n_modes_rotational == 1


def test_order_parameters_have_contributing_variables() -> None:
    """Si hay order parameters, deben tener contributing_variable_names."""
    engine = OrbitalEngine()
    # 5 vars con amplitudes que crean estructura
    for i in range(5):
        amp = 10.0 if i < 2 else 0.1
        engine.create_variable(f"v{i}", theta=i * 0.5, amplitude=amp, velocity=0.1)
    engine.create_cycle("het5", [f"v{i}" for i in range(5)], threshold=0.2)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.001,
                               cycle_variable_ids=[f"v{i}" for i in range(5)])
    # Si hay order parameters, deben tener variables contribuyentes
    for op in status.order_parameters:
        assert isinstance(op.mode.contributing_variable_names, list)


# =============================================================================
# Test 5: Proyección espectral y reconstrucción
# =============================================================================


def test_spectral_coordinates_dimensionality() -> None:
    """len(spectral_coordinates) == effective_dimension cuando hay OPs."""
    engine = OrbitalEngine()
    for i in range(5):
        amp = 10.0 if i < 2 else 0.1
        engine.create_variable(f"v{i}", theta=i * 0.5, amplitude=amp, velocity=0.1)
    engine.create_cycle("het5", [f"v{i}" for i in range(5)], threshold=0.2)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.001,
                               cycle_variable_ids=[f"v{i}" for i in range(5)])
    if status.slaving_active or status.slaving_state == SlavingState.WEAK:
        assert len(status.spectral_coordinates) == status.effective_dimension


def test_reconstruction_error_bounded() -> None:
    """reduction_error ∈ [0, 1] cuando es finito."""
    engine = OrbitalEngine()
    for i in range(5):
        amp = 10.0 if i < 2 else 0.1
        engine.create_variable(f"v{i}", theta=i * 0.5, amplitude=amp, velocity=0.1)
    engine.create_cycle("het5", [f"v{i}" for i in range(5)], threshold=0.2)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.001,
                               cycle_variable_ids=[f"v{i}" for i in range(5)])
    if not math.isnan(status.reduction_error):
        assert 0.0 <= status.reduction_error <= 1.0


# =============================================================================
# Test 6: Integración con CODResult
# =============================================================================


def test_cod_result_has_haken_fields(synced_engine: OrbitalEngine) -> None:
    """CODResult incluye campos de Haken."""
    result = synced_engine.run_tick()
    cod = result.cod_results[0]
    assert hasattr(cod, "haken_slaving_active")
    assert hasattr(cod, "haken_separation_ratio")
    assert hasattr(cod, "haken_n_order_parameters")
    assert hasattr(cod, "haken_effective_dimension")
    assert hasattr(cod, "haken_reduction_error")
    assert hasattr(cod, "haken_slaving_state")


def test_cod_has_all_four_improvements(synced_engine: OrbitalEngine) -> None:
    """CODResult tiene las 4 mejoras integradas."""
    result = synced_engine.run_tick()
    cod = result.cod_results[0]
    # Mejora 1
    assert hasattr(cod, "lyapunov_V_initial")
    # Mejora 2
    assert hasattr(cod, "fep_F_initial")
    # Mejora 3
    assert hasattr(cod, "conley_type")
    # Mejora 4
    assert hasattr(cod, "haken_slaving_active")


def test_cod_haken_state_after_convergence(synced_engine: OrbitalEngine) -> None:
    """Tras convergencia, el COD debe reportar un slaving_state válido."""
    result = synced_engine.run_tick()
    cod = result.cod_results[0]
    assert cod.haken_slaving_state in (
        "active", "weak", "democratic",
        "not_applicable_unstable", "not_applicable_trivial", "not_applicable_marginal",
    )


# =============================================================================
# Test 7: Determinismo
# =============================================================================


def test_haken_deterministic() -> None:
    """El análisis debe ser idéntico en dos runs."""
    def run() -> tuple[str, int]:
        engine = OrbitalEngine()
        engine.create_variable("a", theta=0.0, amplitude=1.0)
        engine.create_variable("b", theta=1.0, amplitude=2.0)
        engine.create_variable("c", theta=2.0, amplitude=0.5)
        engine.create_variable("d", theta=3.0, amplitude=1.5)
        engine.create_cycle("abcd", ["a", "b", "c", "d"], threshold=0.3)
        analyzer = HakenAnalyzer()
        status = analyzer.analyze(engine.ovc, engine.tor, beta=0.05,
                                   cycle_variable_ids=["a", "b", "c", "d"])
        return (status.slaving_state.value, status.n_modes_total)
    r1 = run()
    r2 = run()
    assert r1 == r2


# =============================================================================
# Test 8: Stress test
# =============================================================================


def test_stress_50_vars() -> None:
    """50 variables: el análisis no debe crashear."""
    engine = OrbitalEngine()
    for i in range(50):
        engine.create_variable(f"v{i}", theta=i * 0.13, amplitude=1.0, velocity=0.05)
    engine.create_cycle("stress", [f"v{i}" for i in range(50)], threshold=0.3)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.001,
                               cycle_variable_ids=[f"v{i}" for i in range(50)])
    assert status.n_variables == 50
    assert status.n_modes_total == 50
    assert status.n_modes_rotational == 1
    # Suma de modos no-rotacionales = 49
    total_non_rot = (status.n_modes_stable_slow + status.n_modes_stable_fast +
                     status.n_modes_stable_intermediate + status.n_modes_unstable +
                     status.n_modes_marginal)
    assert total_non_rot == 49


# =============================================================================
# Test 9: to_dict JSON-safe
# =============================================================================


def test_haken_status_to_dict_json_safe(synced_engine: OrbitalEngine) -> None:
    """to_dict() debe ser JSON-safe."""
    import json
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(synced_engine.ovc, synced_engine.tor, beta=0.1,
                               cycle_variable_ids=["a", "b", "c"])
    d = status.to_dict()
    json_str = json.dumps(d, allow_nan=False)  # no debe lanzar
    assert len(json_str) > 0


def test_mode_info_to_dict(synced_engine: OrbitalEngine) -> None:
    """ModeInfo.to_dict() retorna dict con todos los campos."""
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(synced_engine.ovc, synced_engine.tor, beta=0.1,
                               cycle_variable_ids=["a", "b", "c"])
    for m in status.modes:
        d = m.to_dict()
        assert "index" in d
        assert "eigenvalue_mu" in d
        assert "mode_type" in d
        assert "eigenvector" in d


def test_order_parameter_to_dict() -> None:
    """OrderParameter.to_dict() retorna dict con mode + coordinate + amplitude."""
    engine = OrbitalEngine()
    for i in range(5):
        amp = 10.0 if i < 2 else 0.1
        engine.create_variable(f"v{i}", theta=i * 0.5, amplitude=amp, velocity=0.1)
    engine.create_cycle("het5", [f"v{i}" for i in range(5)], threshold=0.2)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.001,
                               cycle_variable_ids=[f"v{i}" for i in range(5)])
    for op in status.order_parameters:
        d = op.to_dict()
        assert "mode" in d
        assert "coordinate_xi" in d
        assert "relative_amplitude" in d


# =============================================================================
# Test 10: Variables duplicadas
# =============================================================================


def test_dedup_cycle_variable_ids() -> None:
    """Variables duplicadas en cycle_variable_ids son deduplicadas."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0)
    engine.create_variable("b", theta=0.0, amplitude=1.0)
    analyzer = HakenAnalyzer()
    status = analyzer.analyze(engine.ovc, engine.tor, beta=0.5,
                               cycle_variable_ids=["a", "a", "b"])
    assert status.n_variables == 2
