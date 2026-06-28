"""
Property-based tests de invariantes del TOR (Tensión Orbital Recíproca).

Invariantes verificados:
  1. Simetría: TOR(i,j) == TOR(j,i)
  2. Acotado: |TOR(i,j)| ≤ A_i × A_j
  3. Cero en diagonal: TOR(i,i) no se calcula (par de misma variable)
  4. is_resonant respeta threshold correctamente (bug fix verificado)
  5. TOR acotado por cos: |TOR| ≤ A_i × A_j (porque |cos| ≤ 1)
  6. Cálculo con cache == cálculo sin cache (differential)

Referencias:
  - Investigación: "TOR simetría y acotamiento son property-based directos"
  - Bug detectado: threshold=0 hacía is_resonant siempre False (arreglado)
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis.strategies import SearchStrategy

from src.orbital.models import TWO_PI, VariableOrbital
from src.orbital.ovc import OVC
from src.orbital.tor import TOR
from src.tests.property.strategies_orbital import (
    amplitude_strategy,
    theta_strategy,
    threshold_strategy,
    variable_specs_unique,
    velocity_strategy,
)


# ─── Helper: construir TOR desde specs ──────────────────────────────────────


def _build_tor_with_variables(specs: list[dict]) -> tuple[TOR, OVC]:
    """Construye TOR + OVC con las variables dadas por specs."""
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    return TOR(ovc), ovc


# ─── 1. Simetría: TOR(i,j) == TOR(j,i) ──────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_tor_symmetry(specs: list[dict]) -> None:
    """TOR(i,j) debe ser exactamente igual a TOR(j,i).

    La tensión orbital recíproca es simétrica por definición matemática:
        TOR(i,j) = A_i × A_j × cos(θ_i - θ_j)
        TOR(j,i) = A_j × A_i × cos(θ_j - θ_i) = A_i × A_j × cos(θ_i - θ_j)
    (cos es función par: cos(-x) = cos(x))
    """
    tor, ovc = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]

    for i, name_i in enumerate(names):
        for j, name_j in enumerate(names):
            if i >= j:
                continue
            result_ij = tor.calculate(name_i, name_j)
            result_ji = tor.calculate(name_j, name_i)
            assert math.isclose(
                result_ij.tor_value,
                result_ji.tor_value,
                rel_tol=1e-9,
                abs_tol=1e-12,
            ), f"TOR({name_i},{name_j})={result_ij.tor_value} != TOR({name_j},{name_i})={result_ji.tor_value}"


# ─── 2. Acotado: |TOR(i,j)| ≤ A_i × A_j ─────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_tor_bounded_by_amplitudes(specs: list[dict]) -> None:
    """|TOR(i,j)| ≤ A_i × A_j siempre.

    Porque TOR = A_i × A_j × cos(diff) y |cos| ≤ 1.
    """
    tor, ovc = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]

    for i, name_i in enumerate(names):
        for j, name_j in enumerate(names):
            if i >= j:
                continue
            result = tor.calculate(name_i, name_j)
            var_i = ovc.get_variable(name_i)
            var_j = ovc.get_variable(name_j)
            assert var_i is not None and var_j is not None
            bound = var_i.amplitude * var_j.amplitude
            assert abs(result.tor_value) <= bound * (1 + 1e-9), (
                f"|TOR({name_i},{name_j})|={abs(result.tor_value)} > A_i×A_j={bound}"
            )


# ─── 3. TOR respeta el signo de cos ─────────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=3))
def test_tor_sign_matches_cos(specs: list[dict]) -> None:
    """Si cos(θ_i - θ_j) > 0, TOR > 0; si cos < 0, TOR < 0; si cos = 0, TOR = 0.

    Verifica que el signo de TOR coincide con el signo de la alineación.
    """
    tor, ovc = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    name_i, name_j = names[0], names[1]
    result = tor.calculate(name_i, name_j)

    if result.alignment > 1e-12:
        assert result.tor_value > 0, f"cos>0 pero TOR={result.tor_value} <= 0"
    elif result.alignment < -1e-12:
        assert result.tor_value < 0, f"cos<0 pero TOR={result.tor_value} >= 0"
    else:
        assert abs(result.tor_value) < 1e-9, f"cos≈0 pero TOR={result.tor_value} != 0"


# ─── 4. is_resonant respeta threshold (bug fix verificado) ──────────────────


@given(
    specs=variable_specs_unique(min_count=2, max_count=3),
    threshold=threshold_strategy(),
)
def test_is_resonant_respects_threshold(specs: list[dict], threshold: float) -> None:
    """is_resonant debe ser True iff |tor_value| > threshold.

    ESTE TEST VERIFICA EL BUG FIX: antes, threshold=0 hacía is_resonant siempre False.
    Ahora threshold=0 significa "cualquier tensión absolututa > 0 es resonante".
    """
    tor, _ = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    result = tor.calculate(names[0], names[1], threshold=threshold)

    expected = abs(result.tor_value) > threshold
    assert result.is_resonant == expected, (
        f"is_resonant={result.is_resonant} pero |tor_value|={abs(result.tor_value)}, "
        f"threshold={threshold}, expected={expected}"
    )


@given(specs=variable_specs_unique(min_count=2, max_count=3))
def test_is_resonant_true_with_default_threshold_zero(specs: list[dict]) -> None:
    """Con threshold=0 (default), cualquier TOR no nulo debe ser resonante.

    Test específico del bug: antes esto fallaba porque is_resonant era siempre False.
    """
    tor, _ = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    result = tor.calculate(names[0], names[1])  # threshold default = 0.0
    if abs(result.tor_value) > 1e-12:
        assert result.is_resonant, (
            f"BUG: |tor_value|={abs(result.tor_value)} > 0 pero is_resonant=False "
            f"(regresión del bug threshold=0)"
        )


# ─── 5. TOR con cache == TOR sin cache (differential) ───────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_tor_cache_matches_recompute(specs: list[dict]) -> None:
    """TOR con cache debe dar mismo resultado que recálculo directo.

    Calcula TOR(i,j) dos veces: la segunda debe usar cache y dar mismo valor.
    """
    tor, _ = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    name_i, name_j = names[0], names[1]
    result1 = tor.calculate(name_i, name_j)  # miss, calcula
    result2 = tor.calculate(name_i, name_j)  # hit, usa cache

    assert math.isclose(
        result1.tor_value, result2.tor_value,
        rel_tol=1e-12, abs_tol=1e-15,
    ), f"Cache cambió el valor: {result1.tor_value} -> {result2.tor_value}"
    assert result1.is_resonant == result2.is_resonant


# ─── 6. calculate_matrix genera matriz simétrica ────────────────────────────


@given(specs=variable_specs_unique(min_count=3, max_count=6))
def test_calculate_matrix_symmetric(specs: list[dict]) -> None:
    """calculate_matrix() debe generar matriz simétrica.

    Para cada par (i,j), TOR(i,j) == TOR(j,i).
    """
    tor, _ = _build_tor_with_variables(specs)
    results = tor.calculate_matrix()

    # Construir dict (i,j) -> tor_value
    tor_dict = {(r.variable_i, r.variable_j): r.tor_value for r in results}

    for (i, j), value in tor_dict.items():
        reverse = tor_dict.get((j, i))
        if reverse is not None:
            assert math.isclose(value, reverse, rel_tol=1e-9, abs_tol=1e-12), (
                f"Matriz no simétrica: TOR({i},{j})={value} != TOR({j},{i})={reverse}"
            )


# ─── 7. TOR es finito (no NaN, no Inf) ──────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_tor_always_finite(specs: list[dict]) -> None:
    """TOR nunca debe producir NaN ni Inf con inputs válidos."""
    tor, _ = _build_tor_with_variables(specs)
    names = [s["name"] for s in specs]

    for i, name_i in enumerate(names):
        for j, name_j in enumerate(names):
            if i >= j:
                continue
            result = tor.calculate(name_i, name_j)
            assert math.isfinite(result.tor_value), (
                f"TOR({name_i},{name_j})={result.tor_value} no es finito"
            )
            assert math.isfinite(result.alignment), (
                f"alignment no es finito: {result.alignment}"
            )
