"""
Tests unitarios para el módulo Conley Classifier (Mejora 3).

Verifica:
1. Construcción del Laplaciano L = H(V)
2. Cálculo del espectro (autovalores de L y J = I - βL)
3. Detección del autovalor rotacional (λ = 1)
4. Clasificación canónica: attractor/repeller/saddle/center/degenerate/trivial
5. Cálculo de β máximo recomendado
6. Casos edge: N=0, N=1, N=2 (verificación canónica del diseño)
7. Integración con CODResult
8. Determinismo
9. Stress test
10. Hiperbolicidad
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("WFD_SESSION_SECRET", "test-only")
os.environ.setdefault("WFD_LICENSE_SECRET", "test-only")

import logging

import pytest

logging.disable(logging.CRITICAL)

import numpy as np  # noqa: E402

from src.orbital.conley import (  # noqa: E402
    ConleyClassifier,
    ConleyType,
)
from src.orbital.engine import OrbitalEngine  # noqa: E402

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def synced_engine() -> OrbitalEngine:
    """Engine con 3 variables sincronizadas (atractor esperado)."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_variable("b", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_variable("c", theta=0.5, amplitude=1.0, velocity=0.1)
    engine.create_cycle("sync", ["a", "b", "c"], threshold=0.5)
    return engine


@pytest.fixture
def desfasado_engine() -> OrbitalEngine:
    """Engine con 3 variables desfasadas."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("b", theta=2.0, amplitude=1.0, velocity=0.1)
    engine.create_variable("c", theta=4.0, amplitude=1.0, velocity=0.1)
    engine.create_cycle("test", ["a", "b", "c"], threshold=0.5)
    return engine


# =============================================================================
# Test 1: Construcción del Laplaciano
# =============================================================================


def test_build_laplacian_returns_symmetric_matrix(desfasado_engine: OrbitalEngine) -> None:
    """L debe ser simétrica (L = L^T)."""
    classifier = ConleyClassifier()
    L = classifier.build_laplacian(
        desfasado_engine.ovc, desfasado_engine.tor,
        cycle_variable_ids=["a", "b", "c"],
    )
    assert L.shape == (3, 3)
    # Verificar simetría
    assert np.allclose(L, L.T), f"L no es simétrica:\n{L}"


def test_build_laplacian_diagonal_equals_net_tension(desfasado_engine: OrbitalEngine) -> None:
    """L_ii = Σ_j TOR(i,j) (tensión neta sobre i)."""
    classifier = ConleyClassifier()
    L = classifier.build_laplacian(
        desfasado_engine.ovc, desfasado_engine.tor,
        cycle_variable_ids=["a", "b", "c"],
    )
    # Verificar manualmente para variable "a"
    tor_results = desfasado_engine.tor.calculate_for_cycle(["a", "b", "c"])
    net_tension_a = sum(
        r.tor_value for r in tor_results
        if r.variable_i == "a" or r.variable_j == "a"
    )
    assert math.isclose(L[0, 0], net_tension_a, rel_tol=1e-9), (
        f"L[0,0] = {L[0,0]} debería ser {net_tension_a}"
    )


def test_build_laplacian_off_diagonal_equals_neg_tor(desfasado_engine: OrbitalEngine) -> None:
    """L_ij = -TOR(i,j) para i ≠ j."""
    classifier = ConleyClassifier()
    L = classifier.build_laplacian(
        desfasado_engine.ovc, desfasado_engine.tor,
        cycle_variable_ids=["a", "b", "c"],
    )
    tor_results = desfasado_engine.tor.calculate_for_cycle(["a", "b", "c"])
    # Mapeo nombre → índice
    name_to_idx = {"a": 0, "b": 1, "c": 2}
    for r in tor_results:
        i = name_to_idx[r.variable_i]
        j = name_to_idx[r.variable_j]
        assert math.isclose(L[i, j], -r.tor_value, rel_tol=1e-9), (
            f"L[{i},{j}] = {L[i,j]} debería ser {-r.tor_value}"
        )


def test_build_laplacian_empty_engine() -> None:
    """L es matriz 0×0 cuando no hay variables."""  # noqa: RUF002
    engine = OrbitalEngine()
    classifier = ConleyClassifier()
    L = classifier.build_laplacian(engine.ovc, engine.tor)
    assert L.shape == (0, 0)


def test_build_laplacian_single_variable() -> None:
    """L es matriz 1×1 con 0 cuando hay 1 sola variable."""  # noqa: RUF002
    engine = OrbitalEngine()
    engine.create_variable("solo", theta=1.5, amplitude=2.0)
    classifier = ConleyClassifier()
    L = classifier.build_laplacian(engine.ovc, engine.tor)
    assert L.shape == (1, 1)
    assert L[0, 0] == 0.0  # sin parejas


# =============================================================================
# Test 2: Cálculo del espectro
# =============================================================================


def test_eigenvalues_all_real(desfasado_engine: OrbitalEngine) -> None:
    """Todos los autovalores de L son reales (L simétrica)."""
    classifier = ConleyClassifier()
    status = classifier.classify(
        desfasado_engine.ovc, desfasado_engine.tor,
        beta=0.1, cycle_variable_ids=["a", "b", "c"],
    )
    for mu in status.spectrum.eigenvalues_laplacian:
        assert isinstance(mu, float)
        assert not math.isnan(mu)
        assert not math.isinf(mu)


def test_rotational_eigenvalue_is_zero(desfasado_engine: OrbitalEngine) -> None:
    """L siempre tiene un autovalor ≈ 0 (simetría rotacional S^1)."""
    classifier = ConleyClassifier()
    status = classifier.classify(
        desfasado_engine.ovc, desfasado_engine.tor,
        beta=0.1, cycle_variable_ids=["a", "b", "c"],
    )
    # El autovalor rotacional de L debe ser ≈ 0
    idx = status.spectrum.rotational_idx
    mu_rot = status.spectrum.eigenvalues_laplacian[idx]
    assert abs(mu_rot) < 1e-6, (
        f"Autovalor rotacional de L debería ser ≈ 0, got {mu_rot}"
    )


def test_jacobian_eigenvalue_rotational_is_one(desfasado_engine: OrbitalEngine) -> None:
    """El autovalor rotacional del Jacobiano J = I - βL es siempre 1."""
    classifier = ConleyClassifier()
    status = classifier.classify(
        desfasado_engine.ovc, desfasado_engine.tor,
        beta=0.5, cycle_variable_ids=["a", "b", "c"],
    )
    idx = status.spectrum.rotational_idx
    lam_rot = status.spectrum.eigenvalues[idx]
    assert math.isclose(lam_rot, 1.0, abs_tol=1e-8), (
        f"Autovalor rotacional de J debería ser 1.0, got {lam_rot}"
    )


def test_jacobian_eigenvalues_formula(desfasado_engine: OrbitalEngine) -> None:
    """λ_k = 1 - β·μ_k para cada autovalor."""
    classifier = ConleyClassifier()
    beta = 0.3
    status = classifier.classify(
        desfasado_engine.ovc, desfasado_engine.tor,
        beta=beta, cycle_variable_ids=["a", "b", "c"],
    )
    for lam, mu in zip(
        status.spectrum.eigenvalues,
        status.spectrum.eigenvalues_laplacian, strict=False,
    ):
        expected = 1.0 - beta * mu
        assert math.isclose(lam, expected, rel_tol=1e-9), (
            f"λ = {lam} debería ser 1 - β·μ = 1 - {beta}·{mu} = {expected}"
        )


# =============================================================================
# Test 3: Clasificación canónica (caso N=2)
# =============================================================================


def test_classify_attractor_n2_consenso() -> None:
    """Caso N=2, consenso (Δθ=0), β=0.5 → attractor.

    Según la tabla 5.4 del diseño: μ=[0, 2], λ=[1, 0] → attractor.
    """
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)  # consenso
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    assert status.conley_type == ConleyType.ATTRACTOR, (
        f"Consenso con β=0.5 debería ser attractor, got {status.conley_type}"
    )
    assert status.morse_index == 0  # 0 direcciones inestables
    assert status.spectrum.stable_count == 1  # 1 dirección estable (N-1=1)
    assert status.spectrum.unstable_count == 0


def test_classify_repeller_n2_consenso_large_beta() -> None:
    """Caso N=2, consenso, β=1.5 → repeller.

    Según el diseño: μ=[0, 2], λ=[1, -2] → |λ|=2 > 1 → repeller.
    """
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=1.5, cycle_variable_ids=["x", "y"],
    )
    assert status.conley_type == ConleyType.REPELLER, (
        f"Consenso con β=1.5 debería ser repeller, got {status.conley_type}"
    )
    assert status.morse_index == 1


def test_classify_repeller_n2_antifase() -> None:
    """Caso N=2, antifase (Δθ=π), β=0.5 → repeller.

    Según el diseño: μ=[-2, 0], λ=[2, 1] → |λ|=2 > 1 → repeller.
    """
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=math.pi, amplitude=1.0)  # antifase
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    assert status.conley_type == ConleyType.REPELLER, (
        f"Antifase debería ser repeller, got {status.conley_type}"
    )


# =============================================================================
# Test 4: Clasificación general
# =============================================================================


def test_classify_trivial_empty() -> None:
    """Engine vacío → trivial."""
    engine = OrbitalEngine()
    classifier = ConleyClassifier()
    status = classifier.classify(engine.ovc, engine.tor, beta=0.5)
    assert status.conley_type == ConleyType.TRIVIAL
    assert status.n_variables == 0


def test_classify_trivial_single_variable() -> None:
    """1 sola variable → degenerate (sin parejas, sin dinámica)."""
    engine = OrbitalEngine()
    engine.create_variable("solo", theta=1.0, amplitude=2.0)
    classifier = ConleyClassifier()
    status = classifier.classify(engine.ovc, engine.tor, beta=0.5)
    # N=1: sin parejas → sin dinámica → DEGENERATE (alineado con diseño sección 5.3)
    assert status.conley_type == ConleyType.DEGENERATE
    assert status.n_variables == 1


def test_classify_variables_dedup() -> None:
    """Variables duplicadas en cycle_variable_ids son deduplicadas (bug fix P0-1)."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0)
    engine.create_variable("b", theta=0.0, amplitude=1.0)
    classifier = ConleyClassifier()
    # Pasar ["a", "a", "b"] — el 'a' duplicado debe ser ignorado
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5,
        cycle_variable_ids=["a", "a", "b"],
    )
    assert status.n_variables == 2, (
        f"Variables duplicadas deben ser deduplicadas: n_variables={status.n_variables}"
    )


def test_classify_saddle_n3_mixed() -> None:
    """Caso N=3 con configuración mixta → SADDLE.

    θ = (0, π, 0), β=0.5:
    - TOR(a,b) = cos(0-π) = -1
    - TOR(a,c) = cos(0-0) = +1
    - TOR(b,c) = cos(π-0) = -1
    - L = [[0, 1, -1], [1, 0, 1], [-1, 1, 0]]  (calculado con w_ij = TOR)
    - Autovalores L: uno positivo (estable), uno negativo (inestable), uno cero (rotacional)
    - J = I - 0.5·L: un |λ|<1, un |λ|>1, un λ=1 (rotacional)
    - Tipo: SADDLE
    """
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0)
    engine.create_variable("b", theta=math.pi, amplitude=1.0)  # antifase con a
    engine.create_variable("c", theta=0.0, amplitude=1.0)  # en fase con a
    engine.create_cycle("mixed", ["a", "b", "c"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5,
        cycle_variable_ids=["a", "b", "c"],
    )
    # Debe ser SADDLE (mezcla de estables e inestables)
    assert status.conley_type == ConleyType.SADDLE, (
        f"Configuración mixta debería ser SADDLE, got {status.conley_type}"
    )
    assert status.spectrum.stable_count >= 1
    assert status.spectrum.unstable_count >= 1


def test_classify_degenerate_at_critical_beta() -> None:
    """Caso N=2, consenso, β=1.0 → DEGENERATE (caso crítico).

    μ = [0, 2], λ = [1, 1 - 1.0·2] = [1, -1]
    |λ| = [1, 1] → ambos son marginales (m=N-1=1) → DEGENERATE.
    """
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=1.0, cycle_variable_ids=["x", "y"],
    )
    # β=1.0 es el caso crítico: |λ|=1 en dirección no-rotacional → DEGENERATE
    assert status.conley_type == ConleyType.DEGENERATE, (
        f"β=1.0 crítico debería ser DEGENERATE, got {status.conley_type}"
    )


def test_conley_status_to_dict_json_safe() -> None:
    """to_dict() debe ser JSON-safe incluso con recommended_max_beta = inf."""
    # Caso N=2 antifase → no hay autovalores positivos → recommended_max_beta = inf
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=math.pi, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    d = status.to_dict()
    # Debe ser serializable a JSON
    import json
    json_str = json.dumps(d, allow_nan=False)  # no debe lanzar
    parsed = json.loads(json_str)
    # recommended_max_beta debe ser -1.0 (sentinel), no inf
    assert parsed["recommended_max_beta"] == -1.0, (
        f"recommended_max_beta debería ser -1.0 (sentinel), got {parsed['recommended_max_beta']}"
    )


def test_step_safe_false_when_no_positive_eigenvalues() -> None:
    """step_safe = False cuando no hay autovalores positivos (repeller puro)."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=math.pi, amplitude=1.0)  # antifase
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    # Antifase: μ = [-2, 0], no hay autovalores positivos → step_safe = False
    assert status.step_safe is False, (
        f"step_safe debería ser False sin autovalores positivos, got {status.step_safe}"
    )


def test_classify_attractor_when_synced(synced_engine: OrbitalEngine) -> None:
    """3 variables sincronizadas con β pequeño → attractor."""
    classifier = ConleyClassifier()
    status = classifier.classify(
        synced_engine.ovc, synced_engine.tor,
        beta=0.1, cycle_variable_ids=["a", "b", "c"],
    )
    # En sincronía perfecta, todas las parejas tienen cos(0)=1
    # L = [[2, -1, -1], [-1, 2, -1], [-1, -1, 2]], autovals = [0, 3, 3]
    # J = I - 0.1·L, autovals = [1, 0.7, 0.7] → attractor
    assert status.conley_type == ConleyType.ATTRACTOR, (
        f"Sincronía con β=0.1 debería ser attractor, got {status.conley_type}"
    )
    assert status.spectrum.stable_count == 2  # N-1 = 2
    assert status.morse_index == 0


# =============================================================================
# Test 5: Cálculo de β máximo recomendado
# =============================================================================


def test_recommended_max_beta_n2_consenso() -> None:
    """Caso N=2, consenso: μ_max = 2, β_max = 2/2 = 1."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    assert math.isclose(status.recommended_max_beta, 1.0, rel_tol=1e-9), (
        f"β_max debería ser 1.0, got {status.recommended_max_beta}"
    )


def test_step_safe_when_beta_below_max() -> None:
    """step_safe = True cuando β < β_max."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status_safe = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    assert status_safe.step_safe is True

    status_unsafe = classifier.classify(
        engine.ovc, engine.tor, beta=1.5, cycle_variable_ids=["x", "y"],
    )
    assert status_unsafe.step_safe is False


# =============================================================================
# Test 6: compute_beta helper
# =============================================================================


def test_compute_beta_formula() -> None:
    """β = convergence_scale · dt · relaxation / amplitude_norm."""
    classifier = ConleyClassifier()
    beta = classifier.compute_beta(
        convergence_scale=0.5,
        dt=1.0,
        relaxation=1.0,
        amplitude_norm=3.0,
    )
    assert math.isclose(beta, 0.5 / 3.0, rel_tol=1e-9)


def test_compute_beta_zero_amplitude() -> None:
    """β = 0 cuando amplitude_norm = 0 (evita división por cero)."""
    classifier = ConleyClassifier()
    beta = classifier.compute_beta(
        convergence_scale=0.5,
        dt=1.0,
        relaxation=1.0,
        amplitude_norm=0.0,
    )
    assert beta == 0.0


# =============================================================================
# Test 7: Integración con CODResult
# =============================================================================


def test_cod_result_has_conley_fields(desfasado_engine: OrbitalEngine) -> None:
    """CODResult debe incluir los campos de Conley."""
    result = desfasado_engine.run_tick()
    cod = result.cod_results[0]

    assert hasattr(cod, "conley_type")
    assert hasattr(cod, "conley_morse_index")
    assert hasattr(cod, "conley_step_safe")
    assert hasattr(cod, "conley_recommended_max_beta")
    assert hasattr(cod, "conley_is_hyperbolic")
    assert hasattr(cod, "conley_stable_count")
    assert hasattr(cod, "conley_unstable_count")
    assert hasattr(cod, "conley_marginal_count")
    assert hasattr(cod, "conley_beta")

    d = cod.to_dict()
    assert "conley_type" in d
    assert "conley_morse_index" in d
    assert "conley_beta" in d


def test_cod_conley_type_is_attractor_after_convergence(synced_engine: OrbitalEngine) -> None:
    """Tras convergencia, el COD debe reportar attractor (no trivial/degenerate).

    Usamos synced_engine (3 vars en θ=0.5, ya en sincronía) para garantizar
    convergencia en 1 tick.
    """
    result = synced_engine.run_tick()
    cod = result.cod_results[0]

    assert cod.converged, "COD debe converger con variables sincronizadas"
    # Tras convergencia a sincronía, debe ser attractor
    assert cod.conley_type == "attractor", (
        f"Tipo Conley tras convergencia debería ser 'attractor', got '{cod.conley_type}'"
    )
    assert cod.conley_morse_index == 0, f"Morse index de atractor debe ser 0, got {cod.conley_morse_index}"
    assert cod.conley_beta > 0, f"β debe ser > 0 tras convergencia, got {cod.conley_beta}"
    assert cod.conley_stable_count >= 1, "Atractor debe tener al menos 1 dirección estable"
    assert cod.conley_unstable_count == 0, "Atractor debe tener 0 direcciones inestables"


def test_cod_has_all_three_improvements(desfasado_engine: OrbitalEngine) -> None:
    """CODResult tiene las 3 mejoras integradas."""
    result = desfasado_engine.run_tick()
    cod = result.cod_results[0]

    # Mejora 1: Lyapunov
    assert hasattr(cod, "lyapunov_V_initial")
    assert hasattr(cod, "lyapunov_stable")

    # Mejora 2: FEP
    assert hasattr(cod, "fep_F_initial")
    assert hasattr(cod, "fep_stable")

    # Mejora 3: Conley
    assert hasattr(cod, "conley_type")
    assert hasattr(cod, "conley_morse_index")


# =============================================================================
# Test 8: Determinismo
# =============================================================================


def test_conley_deterministic() -> None:
    """La clasificación Conley debe ser idéntica en dos runs con mismo input."""
    def run_workflow() -> str:
        engine = OrbitalEngine()
        engine.create_variable("a", theta=0.5, amplitude=1.0, velocity=0.1)
        engine.create_variable("b", theta=1.5, amplitude=1.0, velocity=0.1)
        engine.create_variable("c", theta=2.5, amplitude=1.0, velocity=0.1)
        engine.create_cycle("test", ["a", "b", "c"], threshold=0.5)
        classifier = ConleyClassifier()
        status = classifier.classify(
            engine.ovc, engine.tor, beta=0.3,
            cycle_variable_ids=["a", "b", "c"],
        )
        return (
            f"{status.conley_type.value}|"
            f"{status.morse_index}|"
            f"{round(status.spectrum.eigenvalues[0], 8)}|"
            f"{round(status.spectrum.eigenvalues[1], 8)}|"
            f"{round(status.spectrum.eigenvalues[2], 8)}"
        )

    run1 = run_workflow()
    run2 = run_workflow()
    assert run1 == run2, f"Conley no determinista:\nRun 1: {run1}\nRun 2: {run2}"


# =============================================================================
# Test 9: Stress test
# =============================================================================


def test_stress_50_variables() -> None:
    """50 variables: la clasificación no debe crashear."""
    engine = OrbitalEngine()
    for i in range(50):
        engine.create_variable(f"v{i}", theta=i * 0.13, amplitude=1.0, velocity=0.05)
    engine.create_cycle("stress", [f"v{i}" for i in range(50)], threshold=0.3)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.01,
        cycle_variable_ids=[f"v{i}" for i in range(50)],
    )
    assert status.n_variables == 50
    assert status.conley_type in ConleyType
    # Suma de direcciones = N-1 = 49
    total = (
        status.spectrum.stable_count
        + status.spectrum.unstable_count
        + status.spectrum.marginal_count
    )
    assert total == 49, (
        f"Suma estable+inestable+marginal debería ser 49, got {total}"
    )


# =============================================================================
# Test 10: Hiperbolicidad
# =============================================================================


def test_is_hyperbolic_for_attractor() -> None:
    """Un atractor tiene is_hyperbolic = True (sin marginales)."""
    engine = OrbitalEngine()
    engine.create_variable("x", theta=0.0, amplitude=1.0)
    engine.create_variable("y", theta=0.0, amplitude=1.0)
    engine.create_cycle("xy", ["x", "y"], threshold=0.5)

    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5, cycle_variable_ids=["x", "y"],
    )
    assert status.conley_type == ConleyType.ATTRACTOR
    assert status.is_hyperbolic is True
    assert status.spectrum.marginal_count == 0


# =============================================================================
# Test 11: ConleyStatus y ConleySpectrum to_dict
# =============================================================================


def test_conley_status_to_dict(desfasado_engine: OrbitalEngine) -> None:
    """to_dict() retorna dict con todos los campos."""
    classifier = ConleyClassifier()
    status = classifier.classify(
        desfasado_engine.ovc, desfasado_engine.tor,
        beta=0.3, cycle_variable_ids=["a", "b", "c"],
    )
    d = status.to_dict()
    assert "conley_type" in d
    assert "morse_index" in d
    assert "spectrum" in d
    assert "beta" in d
    assert "step_safe" in d
    assert "recommended_max_beta" in d
    assert "is_hyperbolic" in d
    assert "n_variables" in d


def test_conley_spectrum_to_dict(desfasado_engine: OrbitalEngine) -> None:
    """spectrum.to_dict() retorna dict con autovalores."""
    classifier = ConleyClassifier()
    status = classifier.classify(
        desfasado_engine.ovc, desfasado_engine.tor,
        beta=0.3, cycle_variable_ids=["a", "b", "c"],
    )
    d = status.spectrum.to_dict()
    assert "eigenvalues" in d
    assert "eigenvalues_laplacian" in d
    assert "rotational_idx" in d
    assert "stable_count" in d
    assert "unstable_count" in d
    assert "marginal_count" in d


# =============================================================================
# Test 12: Edge case - ciclo con variables que no existen
# =============================================================================


def test_classify_with_missing_variables() -> None:
    """Variables del ciclo que no existen en OVC son ignoradas."""
    engine = OrbitalEngine()
    engine.create_variable("a", theta=0.0, amplitude=1.0)
    engine.create_variable("b", theta=0.0, amplitude=1.0)
    # Pasamos cycle_variable_ids con un nombre inexistente
    classifier = ConleyClassifier()
    status = classifier.classify(
        engine.ovc, engine.tor, beta=0.5,
        cycle_variable_ids=["a", "b", "inexistente"],
    )
    # Solo 2 variables efectivas
    assert status.n_variables == 2
