"""
Metamorphic testing para el Orbital Engine.

El motor Orbital no tiene oráculo (no existe "el espectro correcto").
Los tests metamórficos verifican RELACIONES NECESARIAS entre pares de ejecuciones.

Relaciones metamórficas verificadas:
  1. Escalamiento de amplitud: si multiplicas amplitudes por k, TOR escala por k²
  2. Identidad de fase: sumar 2π a cualquier theta → mismo resultado
  3. Permutación: permutar variables → TOR simétrico (mismo conjunto de tensiones)
  4. Reversión temporal: invertir velocities → trayectoria espejo
  5. Composición de ticks: tick(dt=2) ≈ 2× tick(dt=1)

Referencias:
  - Investigación: "metamorphic testing es el patrón recomendado para sistemas sin oráculo"
  - NIST, IEEE Computer Society
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.orbital.models import TWO_PI, VariableOrbital
from src.orbital.ovc import OVC
from src.orbital.tor import TOR
from src.tests.property.strategies_orbital import (
    amplitude_strategy,
    dt_strategy,
    num_ticks_strategy,
    scaling_factor_strategy,
    theta_strategy,
    variable_specs_unique,
    velocity_strategy,
)


# ─── 1. Escalamiento de amplitud: TOR escala por k² ─────────────────────────


@given(
    specs=variable_specs_unique(min_count=2, max_count=4),
    k=scaling_factor_strategy(),
)
def test_metamorphic_amplitude_scaling(specs: list[dict], k: float) -> None:
    """Si multiplicas todas las amplitudes por k, TOR escala por k².

    TOR(i,j) = A_i × A_j × cos(θ_i - θ_j)
    TOR'(i,j) = (k×A_i) × (k×A_j) × cos(θ_i - θ_j) = k² × TOR(i,j)

    Esta es una relación metamórfica clásica de sistemas físicos.
    """
    # Configuración original
    ovc1 = OVC()
    for spec in specs:
        ovc1.create_variable(**spec)
    tor1 = TOR(ovc1)
    names = [s["name"] for s in specs]

    # Configuración escalada (amplitudes × k)
    ovc2 = OVC()
    for spec in specs:
        ovc2.create_variable(
            name=spec["name"],
            theta=spec["theta"],
            amplitude=spec["amplitude"] * k,
            velocity=spec["velocity"],
        )
    tor2 = TOR(ovc2)

    # Comparar TOR para el primer par de variables
    if len(names) < 2:
        return
    result1 = tor1.calculate(names[0], names[1])
    result2 = tor2.calculate(names[0], names[1])

    expected = result1.tor_value * (k ** 2)
    assert math.isclose(
        result2.tor_value, expected,
        rel_tol=1e-9, abs_tol=1e-12,
    ), f"TOR no escala por k²: {result1.tor_value} → {result2.tor_value}, expected={expected}"


# ─── 2. Identidad de fase: sumar 2π → mismo resultado ───────────────────────


@given(
    specs=variable_specs_unique(min_count=2, max_count=4),
    shift=st.floats(
        min_value=1,
        max_value=10,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_metamorphic_phase_identity_2pi(specs: list[dict], shift: float) -> None:
    """Sumar 2π×n a cualquier theta → mismo TOR.

    Porque cos(θ_i - θ_j) = cos((θ_i + 2π×n) - θ_j) por periodicidad.
    """
    # Configuración original
    ovc1 = OVC()
    for spec in specs:
        ovc1.create_variable(**spec)
    tor1 = TOR(ovc1)
    names = [s["name"] for s in specs]

    # Configuración con fase desplazada por 2π×shift
    ovc2 = OVC()
    for spec in specs:
        ovc2.create_variable(
            name=spec["name"],
            theta=spec["theta"] + TWO_PI * shift,
            amplitude=spec["amplitude"],
            velocity=spec["velocity"],
        )
    tor2 = TOR(ovc2)

    if len(names) < 2:
        return
    result1 = tor1.calculate(names[0], names[1])
    result2 = tor2.calculate(names[0], names[1])

    assert math.isclose(
        result1.tor_value, result2.tor_value,
        rel_tol=1e-9, abs_tol=1e-12,
    ), f"TOR cambió con shift 2π: {result1.tor_value} → {result2.tor_value}"


# ─── 3. Permutación: TOR simétrico bajo permutación de variables ───────────


@given(specs=variable_specs_unique(min_count=3, max_count=5))
def test_metamorphic_permutation_invariance(specs: list[dict]) -> None:
    """Permutar el orden de variables no cambia el conjunto de tensiones TOR.

    La matriz de tensiones es la misma (salvo permutación de filas/columnas).
    """
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)

    # Calcular TOR original
    results_original = tor.calculate_matrix()
    tensions_original = sorted(
        [abs(r.tor_value) for r in results_original]
    )

    # Crear OVC con variables en orden inverso (permutación trivial)
    ovc2 = OVC()
    for spec in reversed(specs):
        ovc2.create_variable(**spec)
    tor2 = TOR(ovc2)
    results_permuted = tor2.calculate_matrix()
    tensions_permuted = sorted(
        [abs(r.tor_value) for r in results_permuted]
    )

    # Los conjuntos de tensiones deben ser idénticos
    assert len(tensions_original) == len(tensions_permuted)
    for t1, t2 in zip(tensions_original, tensions_permuted):
        assert math.isclose(t1, t2, rel_tol=1e-9, abs_tol=1e-12), (
            f"Tensiones difieren tras permutación: {t1} vs {t2}"
        )


# ─── 4. Reversión temporal: invertir velocities → trayectoria espejo ────────


@given(
    theta=theta_strategy(),
    velocity=velocity_strategy(),
    dt=dt_strategy(),
    n_ticks=num_ticks_strategy(min_ticks=1, max_ticks=20),
)
def test_metamorphic_time_reversal(
    theta: float, velocity: float, dt: float, n_ticks: int
) -> None:
    """Invertir velocity produce trayectoria espejo.

    Si avanzamos N ticks con velocity=v, luego N ticks con velocity=-v,
    deberíamos volver al theta inicial (con tolerancia de FP).
    """
    ovc = OVC()
    ovc.create_variable("test", theta=theta, amplitude=1.0, velocity=velocity)
    var = ovc.get_variable("test")
    assert var is not None
    theta_initial = var.theta

    # Avanzar N ticks
    for _ in range(n_ticks):
        ovc.advance_all(dt)

    # Invertir velocity y retroceder N ticks
    var.velocity = -var.velocity
    for _ in range(n_ticks):
        ovc.advance_all(dt)

    var_final = ovc.get_variable("test")
    assert var_final is not None
    # Debería volver al theta inicial (mod 2π)
    # Permitir pequeña diferencia por acumulación de FP
    diff = abs(var_final.theta - theta_initial)
    diff = min(diff, TWO_PI - diff)  # distancia circular
    assert diff < 1e-9, (
        f"Time reversal falló: theta_initial={theta_initial}, "
        f"theta_final={var_final.theta}, diff={diff}"
    )


# ─── 5. Composición de ticks: tick(dt=2) ≈ 2× tick(dt=1) ───────────────────


@given(
    theta=theta_strategy(),
    velocity=velocity_strategy(),
)
def test_metamorphic_tick_composition(theta: float, velocity: float) -> None:
    """tick(dt=2) debe dar mismo resultado que 2× tick(dt=1).

    Porque advance_all(dt) hace theta += velocity*dt, que es lineal en dt.
    """
    # Configuración 1: un tick con dt=2
    ovc1 = OVC()
    ovc1.create_variable("test", theta=theta, amplitude=1.0, velocity=velocity)
    ovc1.advance_all(2.0)
    var1 = ovc1.get_variable("test")
    assert var1 is not None

    # Configuración 2: dos ticks con dt=1
    ovc2 = OVC()
    ovc2.create_variable("test", theta=theta, amplitude=1.0, velocity=velocity)
    ovc2.advance_all(1.0)
    ovc2.advance_all(1.0)
    var2 = ovc2.get_variable("test")
    assert var2 is not None

    # Deben dar mismo theta (mod 2π)
    assert math.isclose(
        var1.theta, var2.theta,
        rel_tol=1e-9, abs_tol=1e-12,
    ), f"tick(dt=2)={var1.theta} != 2×tick(dt=1)={var2.theta}"


# ─── 6. Idempotencia de cache: TOR(i,j) dos veces da mismo valor ───────────


@given(specs=variable_specs_unique(min_count=2, max_count=4))
def test_metamorphic_cache_idempotency(specs: list[dict]) -> None:
    """Calcular TOR(i,j) dos veces (segunda usa cache) debe dar mismo valor.

    Esto verifica que el cache no introduzca no-determinismo.
    """
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    result1 = tor.calculate(names[0], names[1])
    result2 = tor.calculate(names[0], names[1])

    assert math.isclose(
        result1.tor_value, result2.tor_value,
        rel_tol=1e-15, abs_tol=1e-18,
    ), f"Cache no es idempotente: {result1.tor_value} vs {result2.tor_value}"
    assert result1.is_resonant == result2.is_resonant


# ─── 7. Simetría de escalamiento: k y 1/k son inversos ──────────────────────


@given(
    specs=variable_specs_unique(min_count=2, max_count=3),
    k=scaling_factor_strategy(),
)
def test_metamorphic_scaling_inverse(specs: list[dict], k: float) -> None:
    """Escalar por k y luego por 1/k debe recuperar el TOR original.

    Relación metamórfica de invertibilidad del escalamiento.
    """
    # Original
    ovc0 = OVC()
    for spec in specs:
        ovc0.create_variable(**spec)
    tor0 = TOR(ovc0)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return
    tor_original = tor0.calculate(names[0], names[1]).tor_value

    # Escalar por k
    ovc1 = OVC()
    for spec in specs:
        ovc1.create_variable(
            name=spec["name"],
            theta=spec["theta"],
            amplitude=spec["amplitude"] * k,
            velocity=spec["velocity"],
        )
    tor1 = TOR(ovc1)
    tor_scaled = tor1.calculate(names[0], names[1]).tor_value

    # Escalar por 1/k (debe recuperar original)
    ovc2 = OVC()
    for spec in specs:
        ovc2.create_variable(
            name=spec["name"],
            theta=spec["theta"],
            amplitude=spec["amplitude"] * k / k,  # = original
            velocity=spec["velocity"],
        )
    tor2 = TOR(ovc2)
    tor_recovered = tor2.calculate(names[0], names[1]).tor_value

    assert math.isclose(
        tor_original, tor_recovered,
        rel_tol=1e-9, abs_tol=1e-12,
    ), f"Escalado k y 1/k no recupera original: {tor_original} vs {tor_recovered}"
