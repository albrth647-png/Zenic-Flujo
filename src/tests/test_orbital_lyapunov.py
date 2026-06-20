"""
Tests unitarios para el módulo Lyapunov (Mejora 1, revisión 2).

Verifica:
1. V está bien definida y acotada
2. V = 0 cuando todas las variables son ortogonales
3. V = -ΣA_iA_j cuando todas están en fase (sincronía)
4. V monótona decreciente en ticks del motor (Lyapunov-estable, ESTRICTO)
5. Detección de violaciones funciona (V forzada a aumentar)
6. Gradiente se calcula correctamente
7. Tracker reset funciona
8. Summary estadístico correcto
9. Casos edge (amplitud 0, 1 variable, vars fuera del ciclo)
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("WFD_SESSION_SECRET", "test-only")
os.environ.setdefault("WFD_LICENSE_SECRET", "test-only")

import pytest

# Silenciar logs en tests
import logging
logging.disable(logging.CRITICAL)

from src.orbital.engine import OrbitalEngine
from src.orbital.lyapunov import (
    LYAPUNOV_TOLERANCE,
    LyapunovSnapshot,
    LyapunovTracker,
)
from src.orbital.models import TWO_PI


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_engine() -> OrbitalEngine:
    """Engine con 3 variables ortogonales."""
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


@pytest.fixture
def orthogonal_engine() -> OrbitalEngine:
    """Engine con 2 variables ortogonales (Δθ = π/2)."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("b", theta=math.pi / 2, amplitude=1.0, velocity=0.1)
    engine.create_cycle("orth", ["a", "b"], threshold=0.5)
    return engine


# =============================================================================
# Test 1: V está bien definida y acotada
# =============================================================================


def test_V_acotada(simple_engine: OrbitalEngine) -> None:
    """V debe estar en el rango [-ΣA_iA_j, +ΣA_iA_j]."""
    tracker = LyapunovTracker()
    V = tracker.compute_V(simple_engine.ovc, simple_engine.tor)
    # 3 variables de amplitud 1 → 3 parejas → ΣA_iA_j = 3
    assert -3.0 - 1e-9 <= V <= 3.0 + 1e-9, f"V={V} fuera del rango esperado [-3, 3]"


def test_V_no_nan(simple_engine: OrbitalEngine) -> None:
    """V no debe ser NaN ni infinito."""
    tracker = LyapunovTracker()
    V = tracker.compute_V(simple_engine.ovc, simple_engine.tor)
    assert not math.isnan(V), "V es NaN"
    assert not math.isinf(V), "V es infinito"


def test_V_empty_engine() -> None:
    """V = 0 cuando no hay variables."""
    engine = OrbitalEngine()
    tracker = LyapunovTracker()
    V = tracker.compute_V(engine.ovc, engine.tor)
    assert V == 0.0, f"V debería ser 0 con engine vacío, got {V}"


def test_V_single_variable() -> None:
    """V = 0 con 1 sola variable (sin parejas)."""
    engine = OrbitalEngine()
    engine.create_variable("solo", theta=1.5, amplitude=2.0)
    tracker = LyapunovTracker()
    V = tracker.compute_V(engine.ovc, engine.tor)
    assert V == 0.0, f"V con 1 variable debería ser 0, got {V}"


# =============================================================================
# Test 2: V = 0 cuando todas las variables son ortogonales
# =============================================================================


def test_V_zero_orthogonal(orthogonal_engine: OrbitalEngine) -> None:
    """V ≈ 0 cuando Δθ = π/2 (cos(π/2) = 0)."""
    tracker = LyapunovTracker()
    V = tracker.compute_V(orthogonal_engine.ovc, orthogonal_engine.tor)
    assert abs(V) < 1e-9, f"V debería ser ≈0 para variables ortogonales, got {V}"


# =============================================================================
# Test 3: V = -ΣA_iA_j cuando todas están en fase (sincronía perfecta)
# =============================================================================


def test_V_min_synced(synced_engine: OrbitalEngine) -> None:
    """V = -ΣA_iA_j cuando todas las variables están en fase."""
    tracker = LyapunovTracker()
    V = tracker.compute_V(synced_engine.ovc, synced_engine.tor)
    # 3 variables de amplitud 1, todas en fase → 3 parejas con cos(0)=1
    # V = -3 * (1*1*1) = -3
    assert abs(V - (-3.0)) < 1e-9, f"V debería ser -3 para 3 variables en fase, got {V}"


# =============================================================================
# Test 4: V monótona decreciente en ticks del motor (ESTRICTO)
# =============================================================================


def test_V_monotone_decreasing_across_ticks(simple_engine: OrbitalEngine) -> None:
    """V debe decrecer monótonamente a lo largo de 10 ticks del motor.

    Versión estricta: 0 violaciones permitidas (Lyapunov estricto).
    """
    tracker = LyapunovTracker()
    statuses = []
    for _ in range(10):
        status = tracker.update(simple_engine.ovc, simple_engine.tor)
        statuses.append(status)
        simple_engine.run_tick()

    # STRICT: 0 violaciones (V nunca aumenta)
    violations = sum(1 for s in statuses if s.violation)
    assert violations == 0, (
        f"{violations} violaciones de Lyapunov detectadas. "
        f"Delta_Vs: {[s.delta_V for s in statuses]}"
    )


def test_V_lyapunov_stable_after_5_ticks(simple_engine: OrbitalEngine) -> None:
    """Tras 5 ticks, el tracker debe reportar estabilidad Lyapunov ESTRICTA."""
    tracker = LyapunovTracker()
    for _ in range(5):
        tracker.update(simple_engine.ovc, simple_engine.tor)
        simple_engine.run_tick()

    summary = tracker.summary()
    assert summary["status"] == "lyapunov_stable", (
        f"Status debería ser 'lyapunov_stable', got {summary['status']} "
        f"con {summary['violations_count']} violaciones"
    )
    assert summary["violations_count"] == 0


# =============================================================================
# Test 5: Detección de violaciones funciona
# =============================================================================


def test_violation_detection() -> None:
    """Si forzamos V a aumentar (de sincronía a antifase), debe detectarse.

    V = -ΣA_iA_j·cos(θ_i - θ_j).
    - V MÁXIMA (más positiva) cuando cos = -1 (antifase pura entre todos)
    - V MÍNIMA (más negativa) cuando cos = +1 (sincronía perfecta)

    Empezamos con 2 variables en SINCRONÍA (V mínima = -1).
    Si las movemos a ANTIFASE (Δθ = π), V DEBE AUMENTAR a +1 (violación).
    """
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("y", theta=0.0, amplitude=1.0, velocity=0.1)  # en fase
    engine.create_cycle("pair", ["x", "y"], threshold=0.5)

    tracker = LyapunovTracker()
    status1 = tracker.update(engine.ovc, engine.tor)
    # En sincronía perfecta: V = -1·1·cos(0) = -1
    assert abs(status1.V - (-1.0)) < 1e-9, f"V inicial debería ser -1, got {status1.V}"

    # Mover y a antifase (Δθ = π)
    var_y = engine.ovc.get_variable("y")
    var_y.theta = math.pi

    status2 = tracker.update(engine.ovc, engine.tor)
    # En antifase: V = -1·1·cos(π) = -1·(-1) = +1
    assert abs(status2.V - 1.0) < 1e-9, f"V tras antifase debería ser +1, got {status2.V}"
    assert status2.V > status1.V, "V debe aumentar al ir de sincronía a antifase"
    assert status2.violation, "Debe detectar violación"
    assert tracker.violations_count >= 1


def test_violation_increases_counter_strict() -> None:
    """Forzar 3 movimientos a antifase debe incrementar el contador ≥ 1 vez.

    Versión estricta: al menos 1 violación real (no tautología).
    """
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("y", theta=0.0, amplitude=1.0, velocity=0.1)
    engine.create_cycle("pair", ["x", "y"], threshold=0.5)

    tracker = LyapunovTracker()
    initial_count = tracker.violations_count  # = 0
    assert initial_count == 0

    # Snapshot en sincronía (V=-1)
    tracker.update(engine.ovc, engine.tor)

    # Mover y a antifase → V aumenta a +1 (violación)
    var_y = engine.ovc.get_variable("y")
    var_y.theta = math.pi
    tracker.update(engine.ovc, engine.tor)
    # V debería haber aumentado → violación detectada
    assert tracker.violations_count >= 1, (
        f"Tras forzar antifase, debería haber ≥1 violación, got {tracker.violations_count}"
    )


# =============================================================================
# Test 6: Gradiente se calcula correctamente
# =============================================================================


def test_gradient_norm_nonnegative(simple_engine: OrbitalEngine) -> None:
    """||∇V|| ≥ 0 siempre."""
    tracker = LyapunovTracker()
    status = tracker.update(simple_engine.ovc, simple_engine.tor)
    assert status.gradient_norm >= 0, f"Gradiente negativo: {status.gradient_norm}"


def test_gradient_zero_at_synced_state(synced_engine: OrbitalEngine) -> None:
    """Cuando todas las variables están en fase, ∇V = 0 (punto crítico)."""
    tracker = LyapunovTracker()
    status = tracker.update(synced_engine.ovc, synced_engine.tor)
    # En sincronía perfecta, sin(θ_i - θ_j) = sin(0) = 0 → gradiente = 0
    assert status.gradient_norm < 1e-6, (
        f"Gradiente debería ser ≈0 en sincronía, got {status.gradient_norm}"
    )


def test_gradient_nonzero_when_out_of_sync(simple_engine: OrbitalEngine) -> None:
    """Con variables desfasadas, ∇V ≠ 0."""
    tracker = LyapunovTracker()
    status = tracker.update(simple_engine.ovc, simple_engine.tor)
    assert status.gradient_norm > 0.01, (
        f"Gradiente debería ser >0 con variables desfasadas, got {status.gradient_norm}"
    )


def test_gradient_returns_dict_per_variable(simple_engine: OrbitalEngine) -> None:
    """compute_gradient retorna dict {var_name: dV/dθ} para cada variable."""
    tracker = LyapunovTracker()
    grad = tracker.compute_gradient(simple_engine.ovc, simple_engine.tor)
    assert isinstance(grad, dict)
    assert "a" in grad and "b" in grad and "c" in grad
    assert all(isinstance(v, float) for v in grad.values())


def test_gradient_zero_amplitude_no_crash() -> None:
    """Variable con amplitud pequeña no rompe el gradiente.

    Nota: VariableOrbital.__post_init__ fuerza amplitud > 0 con DEFAULT_AMPLITUDE=1.0
    cuando se asigna 0, así que no podemos forzar amplitud=0 directamente.
    En su lugar, testeamos con una amplitud muy pequeña.
    """
    engine = OrbitalEngine()
    engine.create_variable("z", theta=0.0, amplitude=0.001)  # amplitud muy pequeña
    engine.create_variable("w", theta=1.0, amplitude=1.0)
    engine.create_cycle("zw", ["z", "w"], threshold=0.5)
    tracker = LyapunovTracker()
    grad = tracker.compute_gradient(engine.ovc, engine.tor)
    # z tiene amplitud pequeña → A_z·A_w = 0.001 → contribución pequeña
    assert abs(grad["z"]) < 0.01, f"grad[z] debería ser pequeño, got {grad['z']}"


def test_gradient_orthogonal_phase_no_crash() -> None:
    """cos_diff = 0 (fase ortogonal) no rompe el cálculo del gradiente."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0)
    engine.create_variable("b", theta=math.pi / 2, amplitude=1.0)  # Δθ = π/2
    engine.create_cycle("ab", ["a", "b"], threshold=0.5)
    tracker = LyapunovTracker()
    grad = tracker.compute_gradient(engine.ovc, engine.tor)
    # dV/dθ_a = A_a·A_b·sin(θ_a - θ_b) = 1·1·sin(0 - π/2) = sin(-π/2) = -1
    # dV/dθ_b = A_a·A_b·sin(θ_b - θ_a) = sin(π/2) = +1
    assert abs(grad["a"] - (-1.0)) < 1e-9, f"grad[a] debería ser -1, got {grad['a']}"
    assert abs(grad["b"] - 1.0) < 1e-9, f"grad[b] debería ser +1, got {grad['b']}"


# =============================================================================
# Test 7: Tracker reset funciona
# =============================================================================


def test_reset_clears_history(simple_engine: OrbitalEngine) -> None:
    """reset() limpia el historial y los contadores."""
    tracker = LyapunovTracker()
    for _ in range(3):
        tracker.update(simple_engine.ovc, simple_engine.tor)

    assert len(tracker.history) == 3

    tracker.reset()

    assert len(tracker.history) == 0
    assert tracker.violations_count == 0
    assert not tracker.is_lyapunov_stable


def test_reset_clears_violations_after_real_violations() -> None:
    """reset() limpia violations_count incluso después de violaciones reales."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    tracker = LyapunovTracker()
    tracker.update(engine.ovc, engine.tor)
    # Forzar violación
    engine.ovc.get_variable("y").theta = math.pi
    tracker.update(engine.ovc, engine.tor)
    assert tracker.violations_count >= 1

    tracker.reset()
    assert tracker.violations_count == 0
    assert len(tracker.history) == 0


# =============================================================================
# Test 8: Summary estadístico correcto
# =============================================================================


def test_summary_correct(simple_engine: OrbitalEngine) -> None:
    """summary() retorna estadísticas correctas."""
    tracker = LyapunovTracker()
    for _ in range(5):
        tracker.update(simple_engine.ovc, simple_engine.tor)
        simple_engine.run_tick()

    summary = tracker.summary()
    assert summary["iterations"] == 5
    assert summary["violations_count"] == 0  # ESTRICTO: sin violaciones
    assert summary["decreases"] + summary["increases"] + summary["same"] == 4


def test_summary_empty_tracker() -> None:
    """summary() en tracker vacío retorna status 'empty'."""
    tracker = LyapunovTracker()
    summary = tracker.summary()
    assert summary["status"] == "empty"
    assert summary["iterations"] == 0


# =============================================================================
# Test 9: Integración con CODResult
# =============================================================================


def test_cod_result_has_lyapunov_fields(simple_engine: OrbitalEngine) -> None:
    """CODResult debe incluir los campos de Lyapunov."""
    result = simple_engine.run_tick()
    cod_result = result.cod_results[0]

    # Campos nuevos presentes
    assert hasattr(cod_result, "lyapunov_V_initial")
    assert hasattr(cod_result, "lyapunov_V_final")
    assert hasattr(cod_result, "lyapunov_delta_V")
    assert hasattr(cod_result, "lyapunov_stable")
    assert hasattr(cod_result, "lyapunov_violations")

    # to_dict() los incluye
    d = cod_result.to_dict()
    assert "lyapunov_V_initial" in d
    assert "lyapunov_V_final" in d
    assert "lyapunov_delta_V" in d
    assert "lyapunov_stable" in d
    assert "lyapunov_violations" in d


def test_cod_result_lyapunov_values_are_numbers(simple_engine: OrbitalEngine) -> None:
    """Los valores de Lyapunov en CODResult son numéricos."""
    result = simple_engine.run_tick()
    cod = result.cod_results[0]

    assert isinstance(cod.lyapunov_V_initial, float)
    assert isinstance(cod.lyapunov_V_final, float)
    assert isinstance(cod.lyapunov_delta_V, float)
    assert isinstance(cod.lyapunov_violations, int)
    assert isinstance(cod.lyapunov_stable, bool)

    assert not math.isnan(cod.lyapunov_V_initial)
    assert not math.isnan(cod.lyapunov_V_final)


def test_cod_lyapunov_stable_no_violations(simple_engine: OrbitalEngine) -> None:
    """El COD debe reportar 0 violaciones de Lyapunov en cada tick."""
    for _ in range(3):
        result = simple_engine.run_tick()
        cod = result.cod_results[0]
        assert cod.lyapunov_violations == 0, (
            f"COD reportó {cod.lyapunov_violations} violaciones en un tick"
        )
        assert cod.lyapunov_stable, "COD debería reportar lyapunov_stable=True"


# =============================================================================
# Test 10: Determinismo — V reproducible
# =============================================================================


def test_V_deterministic() -> None:
    """V debe ser idéntica en dos runs con mismo input."""
    def run_workflow() -> tuple[float, ...]:
        engine = OrbitalEngine()
        engine.create_variable("a", theta=0.5, amplitude=1.0, velocity=0.1)
        engine.create_variable("b", theta=1.5, amplitude=1.0, velocity=0.1)
        engine.create_variable("c", theta=2.5, amplitude=1.0, velocity=0.1)
        engine.create_cycle("test", ["a", "b", "c"], threshold=0.5)
        tracker = LyapunovTracker()
        V_values: list[float] = []
        for _ in range(5):
            status = tracker.update(engine.ovc, engine.tor)
            V_values.append(status.V)
            engine.run_tick()
        return tuple(V_values)

    run1 = run_workflow()
    run2 = run_workflow()

    # Comparación estricta con math.isclose
    assert all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(run1, run2)), (
        f"V no determinista:\nRun 1: {run1}\nRun 2: {run2}"
    )


# =============================================================================
# Test 11: Stress test — 50 ticks sin violaciones
# =============================================================================


def test_50_ticks_stress_no_violations() -> None:
    """50 ticks del motor con tracking de Lyapunov: 0 violaciones (ESTRICTO)."""
    engine = OrbitalEngine()
    for i in range(20):
        engine.create_variable(f"v{i}", theta=i * 0.3, amplitude=1.0, velocity=0.05)
    engine.create_cycle("stress", [f"v{i}" for i in range(20)], threshold=0.3)

    tracker = LyapunovTracker()
    for _ in range(50):
        tracker.update(engine.ovc, engine.tor)
        engine.run_tick()

    summary = tracker.summary()
    assert summary["iterations"] == 50
    # STRICT: 0 violaciones en stress test
    assert summary["violations_count"] == 0, (
        f"Stress test reportó {summary['violations_count']} violaciones"
    )


# =============================================================================
# Test 12: Trajectory retorna lista de snapshots
# =============================================================================


def test_trajectory_returns_list(simple_engine: OrbitalEngine) -> None:
    """trajectory() retorna lista de dicts con iter, V, grad."""
    tracker = LyapunovTracker()
    for _ in range(3):
        tracker.update(simple_engine.ovc, simple_engine.tor)

    traj = tracker.trajectory()
    assert isinstance(traj, list)
    assert len(traj) == 3
    assert all("iteration" in t for t in traj)
    assert all("V" in t for t in traj)
    assert all("gradient_norm" in t for t in traj)


def test_history_snapshots_are_lyapunov_snapshot(simple_engine: OrbitalEngine) -> None:
    """tracker.history contiene instancias de LyapunovSnapshot."""
    tracker = LyapunovTracker()
    tracker.update(simple_engine.ovc, simple_engine.tor)
    assert len(tracker.history) == 1
    assert isinstance(tracker.history[0], LyapunovSnapshot)


# =============================================================================
# Test 13: Variables fuera del ciclo
# =============================================================================


def test_compute_V_with_cycle_variable_ids() -> None:
    """compute_V con cycle_variable_ids solo considera las vars del ciclo."""
    engine = OrbitalEngine()
    engine.create_variable("in1", theta=0.0, amplitude=1.0)
    engine.create_variable("in2", theta=0.0, amplitude=1.0)
    engine.create_variable("out", theta=math.pi, amplitude=1.0)  # fuera del ciclo
    engine.create_cycle("partial", ["in1", "in2"], threshold=0.5)

    tracker = LyapunovTracker()
    # V solo del ciclo (in1, in2)
    V_cycle = tracker.compute_V(engine.ovc, engine.tor, cycle_variable_ids=["in1", "in2"])
    # V de todas las parejas
    V_all = tracker.compute_V(engine.ovc, engine.tor)

    # V_cycle = -1·1·cos(0) = -1 (solo la pareja in1-in2 en fase)
    assert abs(V_cycle - (-1.0)) < 1e-9, f"V_cycle debería ser -1, got {V_cycle}"

    # V_all incluye la pareja in1-out (antifase) y in2-out (antifase)
    # V_all = -cos(0) - cos(π) - cos(π) = -1 + 1 + 1 = +1
    assert abs(V_all - 1.0) < 1e-9, f"V_all debería ser +1, got {V_all}"


def test_compute_gradient_with_cycle_variable_ids() -> None:
    """compute_gradient con cycle_variable_ids solo devuelve las vars del ciclo."""
    engine = OrbitalEngine()
    engine.create_variable("in1", theta=0.0, amplitude=1.0)
    engine.create_variable("in2", theta=math.pi / 2, amplitude=1.0)
    engine.create_variable("out", theta=math.pi, amplitude=1.0)
    engine.create_cycle("partial", ["in1", "in2"], threshold=0.5)

    tracker = LyapunovTracker()
    grad = tracker.compute_gradient(engine.ovc, engine.tor, cycle_variable_ids=["in1", "in2"])

    # Solo debe contener in1 e in2, NO out
    assert "in1" in grad
    assert "in2" in grad
    assert "out" not in grad
