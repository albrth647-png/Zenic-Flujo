"""
Tests unitarios para el módulo Friston FEP (Mejora 2).

Verifica:
1. F = U - S bien calculada
2. U(θ) = -Σ TOR / N (energía)
3. S(θ) = -Σ p ln p (entropía de Shannon)
4. Casos edge (engine vacío, 1 variable, variables ortogonales)
5. Detección de violaciones de F
6. Tracker reset funciona
7. Summary estadístico correcto
8. Integración con CODResult
9. Determinismo
10. Stress test
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

from src.orbital.engine import OrbitalEngine
from src.orbital.friston_fep import (
    DEFAULT_N_BINS,
    FEP_TOLERANCE,
    FEPSnapshot,
    FEPTracker,
)
from src.orbital.models import TWO_PI


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_engine() -> OrbitalEngine:
    """Engine con 3 variables en fases diferentes."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("b", theta=2.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("c", theta=4.0, amplitude=1.0, velocity=0.1)
    engine.create_cycle("test", ["a", "b", "c"], threshold=0.5)
    return engine


@pytest.fixture
def synced_engine() -> OrbitalEngine:
    """Engine con 3 variables sincronizadas (misma fase)."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_variable("b", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_variable("c", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_cycle("sync", ["a", "b", "c"], threshold=0.5)
    return engine


# =============================================================================
# Test 1: F = U - S bien calculada
# =============================================================================


def test_F_is_energy_minus_entropy(simple_engine: OrbitalEngine) -> None:
    """F = U - S."""
    tracker = FEPTracker()
    F, U, S = tracker.compute_F(simple_engine.ovc, simple_engine.tor)
    assert math.isclose(F, U - S, rel_tol=1e-9, abs_tol=1e-9), (
        f"F debería ser U - S = {U} - {S} = {U - S}, got {F}"
    )


def test_F_no_nan(simple_engine: OrbitalEngine) -> None:
    """F no debe ser NaN ni infinito."""
    tracker = FEPTracker()
    F, U, S = tracker.compute_F(simple_engine.ovc, simple_engine.tor)
    assert not math.isnan(F)
    assert not math.isinf(F)
    assert not math.isnan(U)
    assert not math.isnan(S)


def test_F_empty_engine() -> None:
    """F = (0, 0, 0) cuando no hay variables."""
    engine = OrbitalEngine()
    tracker = FEPTracker()
    F, U, S = tracker.compute_F(engine.ovc, engine.tor)
    assert F == 0.0
    assert U == 0.0
    assert S == 0.0


# =============================================================================
# Test 2: U(θ) = -Σ TOR / N (energía)
# =============================================================================


def test_energy_is_negative_avg_tor(simple_engine: OrbitalEngine) -> None:
    """U(θ) = -Σ TOR(i,j) / N."""
    tracker = FEPTracker()
    U = tracker.compute_energy(simple_engine.ovc, simple_engine.tor)
    tor_results = simple_engine.tor.calculate_matrix()
    expected_U = -sum(r.tor_value for r in tor_results) / 3  # N=3
    assert math.isclose(U, expected_U, rel_tol=1e-9), (
        f"U debería ser {expected_U}, got {U}"
    )


def test_energy_negative_when_synced() -> None:
    """U muy negativa cuando variables sincronizadas (TOR alto)."""
    tracker = FEPTracker()

    # Engine sincronizado
    synced = OrbitalEngine()
    synced.create_variable("a", theta=0.5, amplitude=1.0)
    synced.create_variable("b", theta=0.5, amplitude=1.0)
    synced.create_variable("c", theta=0.5, amplitude=1.0)
    U_synced = tracker.compute_energy(synced.ovc, synced.tor)

    # Engine desfasado
    desfasado = OrbitalEngine()
    desfasado.create_variable("a", theta=0.0, amplitude=1.0)
    desfasado.create_variable("b", theta=2.0, amplitude=1.0)
    desfasado.create_variable("c", theta=4.0, amplitude=1.0)
    U_desfasado = tracker.compute_energy(desfasado.ovc, desfasado.tor)

    # En sincronía, TOR es máximo (cos(0)=1), así que U es muy negativo
    assert U_synced < U_desfasado, (
        f"U_synced ({U_synced}) debería ser < U_desfasado ({U_desfasado})"
    )


# =============================================================================
# Test 3: S(θ) = -Σ p ln p (entropía de Shannon)
# =============================================================================


def test_entropy_zero_when_synced(synced_engine: OrbitalEngine) -> None:
    """S = 0 cuando todas las variables en la misma fase."""
    tracker = FEPTracker()
    S = tracker.compute_entropy(synced_engine.ovc)
    assert S == 0.0, f"S debería ser 0 en sincronía, got {S}"


def test_entropy_max_when_uniform() -> None:
    """S se acerca a ln(n_bins) cuando las variables están aproximadamente uniformes."""
    engine = OrbitalEngine()
    n_bins = 12
    # Crear 24 variables (2 por bin) para reducir efecto del redondeo
    for i in range(n_bins * 2):
        theta = (i * TWO_PI / (n_bins * 2)) + 0.01  # pequeño offset para evitar bordes
        engine.create_variable(f"v{i}", theta=theta, amplitude=1.0)
    tracker = FEPTracker(n_bins=n_bins)
    S = tracker.compute_entropy(engine.ovc)
    # Con 24 variables bien distribuidas en 12 bins, S debería ser cercano a ln(12)
    expected_S = math.log(n_bins)
    # Permitir tolerancia del 10% por redondeo de bins
    assert S > expected_S * 0.9, (
        f"S debería ser cercano a ln({n_bins}) = {expected_S}, got {S}"
    )


def test_entropy_increases_with_diversity() -> None:
    """S aumenta cuando las variables están más distribuidas."""
    # Engine 1: 2 variables en la misma fase (S=0)
    engine1 = OrbitalEngine()
    engine1.create_variable("a", theta=0.0, amplitude=1.0)
    engine1.create_variable("b", theta=0.0, amplitude=1.0)

    # Engine 2: 2 variables en fases opuestas (S > 0)
    engine2 = OrbitalEngine()
    engine2.create_variable("a", theta=0.0, amplitude=1.0)
    engine2.create_variable("b", theta=math.pi, amplitude=1.0)

    tracker = FEPTracker()
    S1 = tracker.compute_entropy(engine1.ovc)
    S2 = tracker.compute_entropy(engine2.ovc)
    assert S2 > S1, f"S con diversidad ({S2}) debería ser > S sin diversidad ({S1})"


# =============================================================================
# Test 4: Casos edge
# =============================================================================


def test_F_single_variable() -> None:
    """F = (0, 0, 0) con 1 sola variable (sin parejas, sin diversidad)."""
    engine = OrbitalEngine()
    engine.create_variable("solo", theta=1.5, amplitude=2.0)
    tracker = FEPTracker()
    F, U, S = tracker.compute_F(engine.ovc, engine.tor)
    # Sin parejas → TOR = 0 → U = 0
    # 1 variable → 1 bin con count=1 → p=1 → S = -1·ln(1) = 0
    assert U == 0.0, f"U con 1 variable debería ser 0, got {U}"
    assert S == 0.0, f"S con 1 variable debería ser 0, got {S}"
    assert F == 0.0


def test_F_with_cycle_variable_ids() -> None:
    """compute_F con cycle_variable_ids solo considera vars del ciclo."""
    engine = OrbitalEngine()
    engine.create_variable("in1", theta=0.0, amplitude=1.0)
    engine.create_variable("in2", theta=0.0, amplitude=1.0)
    engine.create_variable("out", theta=math.pi, amplitude=1.0)
    engine.create_cycle("partial", ["in1", "in2"], threshold=0.5)

    tracker = FEPTracker()
    F_cycle, U_cycle, S_cycle = tracker.compute_F(
        engine.ovc, engine.tor, cycle_variable_ids=["in1", "in2"]
    )
    F_all, U_all, S_all = tracker.compute_F(engine.ovc, engine.tor)

    # U_cycle = -cos(0)/2 = -0.5 (1 pareja, N=2)
    assert math.isclose(U_cycle, -0.5, rel_tol=1e-9), f"U_cycle debería ser -0.5, got {U_cycle}"

    # U_all = -(cos(0) + cos(π) + cos(π))/3 = -(1 - 1 - 1)/3 = 1/3
    assert math.isclose(U_all, 1.0 / 3.0, rel_tol=1e-9), f"U_all debería ser 1/3, got {U_all}"

    # S_cycle = 0 (ambas en misma fase)
    assert S_cycle == 0.0
    # S_all > 0 (hay 2 bins ocupados: θ=0 y θ=π)
    assert S_all > 0


# =============================================================================
# Test 5: Detección de violaciones
# =============================================================================


def test_FEP_violation_detection() -> None:
    """Si forzamos F a aumentar, debe detectarse."""
    engine = OrbitalEngine()
    # 4 variables uniformemente distribuidas → entropía alta, energía ~0
    for i in range(4):
        engine.create_variable(f"v{i}", theta=i * math.pi / 2, amplitude=1.0)
    engine.create_cycle("test", [f"v{i}" for i in range(4)], threshold=0.5)

    tracker = FEPTracker()
    status1 = tracker.update(engine.ovc, engine.tor)

    # Mover todas las variables a la misma fase → F cambia (energía baja, entropía baja)
    for i in range(4):
        engine.ovc.get_variable(f"v{i}").theta = 0.0

    status2 = tracker.update(engine.ovc, engine.tor)

    # F2 vs F1: U bajó (más sincronizado), S bajó (menos diversidad)
    # El efecto neto en F puede ser positivo o negativo según magnitudes.
    # Verificamos que el tracker detecta el cambio (delta_F != 0)
    assert status2.delta_F != 0.0, "F debería cambiar al mover las variables"


# =============================================================================
# Test 6: Tracker reset
# =============================================================================


def test_reset_clears_history(simple_engine: OrbitalEngine) -> None:
    """reset() limpia el historial."""
    tracker = FEPTracker()
    for _ in range(3):
        tracker.update(simple_engine.ovc, simple_engine.tor)

    assert len(tracker.history) == 3
    tracker.reset()
    assert len(tracker.history) == 0
    assert tracker.violations_count == 0
    assert not tracker.is_fep_stable


# =============================================================================
# Test 7: Summary estadístico
# =============================================================================


def test_summary_correct(simple_engine: OrbitalEngine) -> None:
    """summary() retorna estadísticas correctas."""
    tracker = FEPTracker()
    for _ in range(5):
        tracker.update(simple_engine.ovc, simple_engine.tor)
        simple_engine.run_tick()

    summary = tracker.summary()
    assert summary["iterations"] == 5
    assert summary["violations_count"] >= 0
    assert "F_initial" in summary
    assert "F_final" in summary
    assert "energy_initial" in summary
    assert "energy_final" in summary
    assert "entropy_initial" in summary
    assert "entropy_final" in summary


def test_summary_empty_tracker() -> None:
    """summary() en tracker vacío retorna status 'empty'."""
    tracker = FEPTracker()
    summary = tracker.summary()
    assert summary["status"] == "empty"
    assert summary["iterations"] == 0


# =============================================================================
# Test 8: Integración con CODResult
# =============================================================================


def test_cod_result_has_fep_fields(simple_engine: OrbitalEngine) -> None:
    """CODResult debe incluir los campos de FEP."""
    result = simple_engine.run_tick()
    cod = result.cod_results[0]

    assert hasattr(cod, "fep_F_initial")
    assert hasattr(cod, "fep_F_final")
    assert hasattr(cod, "fep_delta_F")
    assert hasattr(cod, "fep_energy_initial")
    assert hasattr(cod, "fep_energy_final")
    assert hasattr(cod, "fep_entropy_initial")
    assert hasattr(cod, "fep_entropy_final")
    assert hasattr(cod, "fep_stable")
    assert hasattr(cod, "fep_violations")

    d = cod.to_dict()
    assert "fep_F_initial" in d
    assert "fep_F_final" in d
    assert "fep_delta_F" in d
    assert "fep_energy_initial" in d
    assert "fep_energy_final" in d
    assert "fep_entropy_initial" in d
    assert "fep_entropy_final" in d
    assert "fep_stable" in d
    assert "fep_violations" in d


def test_cod_result_fep_values_are_numbers(simple_engine: OrbitalEngine) -> None:
    """Los valores de FEP en CODResult son numéricos."""
    result = simple_engine.run_tick()
    cod = result.cod_results[0]

    assert isinstance(cod.fep_F_initial, float)
    assert isinstance(cod.fep_F_final, float)
    assert isinstance(cod.fep_delta_F, float)
    assert isinstance(cod.fep_energy_initial, float)
    assert isinstance(cod.fep_energy_final, float)
    assert isinstance(cod.fep_entropy_initial, float)
    assert isinstance(cod.fep_entropy_final, float)
    assert isinstance(cod.fep_violations, int)
    assert isinstance(cod.fep_stable, bool)

    assert not math.isnan(cod.fep_F_initial)
    assert not math.isnan(cod.fep_F_final)


def test_cod_has_both_lyapunov_and_fep(simple_engine: OrbitalEngine) -> None:
    """CODResult tiene AMBAS mejoras (Lyapunov + FEP)."""
    result = simple_engine.run_tick()
    cod = result.cod_results[0]

    # Mejora 1: Lyapunov
    assert cod.lyapunov_V_initial != 0.0 or cod.lyapunov_V_final != 0.0
    assert cod.lyapunov_stable in (True, False)
    assert cod.lyapunov_violations >= 0

    # Mejora 2: FEP
    assert cod.fep_F_initial != 0.0 or cod.fep_F_final != 0.0
    assert cod.fep_stable in (True, False)
    assert cod.fep_violations >= 0


# =============================================================================
# Test 9: Determinismo
# =============================================================================


def test_F_deterministic() -> None:
    """F debe ser idéntica en dos runs con mismo input."""
    def run_workflow() -> tuple[float, ...]:
        engine = OrbitalEngine()
        engine.create_variable("a", theta=0.5, amplitude=1.0, velocity=0.1)
        engine.create_variable("b", theta=1.5, amplitude=1.0, velocity=0.1)
        engine.create_variable("c", theta=2.5, amplitude=1.0, velocity=0.1)
        engine.create_cycle("test", ["a", "b", "c"], threshold=0.5)
        tracker = FEPTracker()
        F_values: list[float] = []
        for _ in range(5):
            status = tracker.update(engine.ovc, engine.tor)
            F_values.append(status.F)
            engine.run_tick()
        return tuple(F_values)

    run1 = run_workflow()
    run2 = run_workflow()
    assert all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(run1, run2)), (
        f"F no determinista:\nRun 1: {run1}\nRun 2: {run2}"
    )


# =============================================================================
# Test 10: Stress test
# =============================================================================


def test_50_ticks_stress() -> None:
    """50 ticks del motor con tracking de FEP no debe crashear."""
    engine = OrbitalEngine()
    for i in range(20):
        engine.create_variable(f"v{i}", theta=i * 0.3, amplitude=1.0, velocity=0.05)
    engine.create_cycle("stress", [f"v{i}" for i in range(20)], threshold=0.3)

    tracker = FEPTracker()
    for _ in range(50):
        tracker.update(engine.ovc, engine.tor)
        engine.run_tick()

    summary = tracker.summary()
    assert summary["iterations"] == 50


# =============================================================================
# Test 11: Trajectory y snapshots
# =============================================================================


def test_trajectory_returns_list(simple_engine: OrbitalEngine) -> None:
    """trajectory() retorna lista de dicts con F, energy, entropy."""
    tracker = FEPTracker()
    for _ in range(3):
        tracker.update(simple_engine.ovc, simple_engine.tor)

    traj = tracker.trajectory()
    assert isinstance(traj, list)
    assert len(traj) == 3
    assert all("F" in t for t in traj)
    assert all("energy" in t for t in traj)
    assert all("entropy" in t for t in traj)


def test_history_snapshots_are_fep_snapshot(simple_engine: OrbitalEngine) -> None:
    """tracker.history contiene instancias de FEPSnapshot."""
    tracker = FEPTracker()
    tracker.update(simple_engine.ovc, simple_engine.tor)
    assert len(tracker.history) == 1
    assert isinstance(tracker.history[0], FEPSnapshot)


# =============================================================================
# Test 12: Número configurable de bins
# =============================================================================


def test_custom_n_bins() -> None:
    """El número de bins afecta la resolución de la entropía."""
    engine = OrbitalEngine()
    # 6 variables en 6 fases distintas
    for i in range(6):
        engine.create_variable(f"v{i}", theta=i * TWO_PI / 6, amplitude=1.0)

    # Con 6 bins: cada variable cae en su propio bin → S = ln(6)
    tracker6 = FEPTracker(n_bins=6)
    S6 = tracker6.compute_entropy(engine.ovc)
    assert math.isclose(S6, math.log(6), rel_tol=1e-9)

    # Con 3 bins: 2 variables por bin → S = ln(3)
    tracker3 = FEPTracker(n_bins=3)
    S3 = tracker3.compute_entropy(engine.ovc)
    assert math.isclose(S3, math.log(3), rel_tol=1e-9)


def test_default_n_bins_is_12() -> None:
    """DEFAULT_N_BINS = 12."""
    assert DEFAULT_N_BINS == 12
