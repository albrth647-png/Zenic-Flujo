"""
Property-based tests de invariantes del OVC (Orbita Variable Circular).

Invariantes verificados:
  1. θ siempre normalizado a [0, 2π)
  2. Amplitud siempre > 0
  3. advance_all(dt) incrementa θ por velocity*dt (mod 2π)
  4. create_variable respeta los parámetros dados
  5. Variables con mismo nombre se sobreescriben (no duplicados)
  6. delete_variable elimina correctamente
  7. Estado del OVC es siempre válido tras N operaciones

Referencias:
  - Investigación: "OVC: theta ∈ [0, 2π) siempre (normalizado)"
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.orbital.models import TWO_PI
from src.orbital.ovc import OVC
from src.tests.property.strategies_orbital import (
    amplitude_strategy,
    dt_strategy,
    num_ticks_strategy,
    theta_strategy,
    variable_specs_unique,
    velocity_strategy,
)


# ─── 1. θ siempre normalizado a [0, 2π) ─────────────────────────────────────


@given(
    theta=st.floats(
        min_value=-100 * math.pi,
        max_value=100 * math.pi,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    ),
    amplitude=amplitude_strategy(),
    velocity=velocity_strategy(),
)
def test_theta_normalized_on_create(theta: float, amplitude: float, velocity: float) -> None:
    """create_variable debe normalizar θ a [0, 2π) sin importar el input."""
    ovc = OVC()
    var = ovc.create_variable("test", theta=theta, amplitude=amplitude, velocity=velocity)
    assert 0 <= var.theta < TWO_PI, f"theta={var.theta} no está en [0, 2π)"


@given(
    theta=theta_strategy(),
    velocity=velocity_strategy(),
    dt=dt_strategy(),
)
def test_theta_normalized_after_advance(theta: float, velocity: float, dt: float) -> None:
    """advance_all(dt) debe dejar θ en [0, 2π) tras avanzar."""
    ovc = OVC()
    ovc.create_variable("test", theta=theta, amplitude=1.0, velocity=velocity)
    ovc.advance_all(dt)
    var = ovc.get_variable("test")
    assert var is not None
    assert 0 <= var.theta < TWO_PI, f"theta={var.theta} fuera de rango tras advance_all"


# ─── 2. Amplitud siempre > 0 ────────────────────────────────────────────────


@given(amplitude=amplitude_strategy())
def test_amplitude_positive_on_create(amplitude: float) -> None:
    """create_variable debe garantizar amplitude > 0."""
    ovc = OVC()
    var = ovc.create_variable("test", theta=0.0, amplitude=amplitude, velocity=0.1)
    assert var.amplitude > 0, f"amplitude={var.amplitude} no es positiva"


@given(
    amplitude=st.floats(
        min_value=-1e3,
        max_value=-1e-3,  # amplitudes negativas
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_amplitude_clamped_when_negative(amplitude: float) -> None:
    """Si se pasa amplitude negativa, OVC debe clamparla a valor positivo o rechazarla.

    Comportamiento esperado (según models.py __post_init__):
    amplitude = abs(amplitude) o raise ValueError.
    """
    ovc = OVC()
    try:
        var = ovc.create_variable("test", theta=0.0, amplitude=amplitude, velocity=0.1)
        # Si se creó, amplitude debe ser positiva
        assert var.amplitude > 0, f"amplitude negativa pasó: {var.amplitude}"
    except ValueError:
        # Aceptable: rechazar amplitudes negativas
        pass


# ─── 3. advance_all incrementa θ correctamente ──────────────────────────────


@given(
    theta=theta_strategy(),
    velocity=velocity_strategy(),
    dt=dt_strategy(),
)
def test_advance_increments_theta(theta: float, velocity: float, dt: float) -> None:
    """advance_all(dt) debe incrementar θ por velocity*dt (mod 2π)."""
    ovc = OVC()
    ovc.create_variable("test", theta=theta, amplitude=1.0, velocity=velocity)
    var_before = ovc.get_variable("test")
    assert var_before is not None
    # Capturar theta antes de avanzar (get_variable retorna referencia, no copia)
    theta_before = var_before.theta

    ovc.advance_all(dt)
    var_after = ovc.get_variable("test")
    assert var_after is not None

    # θ esperado = (θ_before + velocity*dt) mod 2π
    expected_theta = (theta_before + velocity * dt) % TWO_PI
    # Aplicar doble modulo por si el redondeo FP da exactamente TWO_PI
    if expected_theta >= TWO_PI:
        expected_theta = expected_theta % TWO_PI
    assert math.isclose(
        var_after.theta, expected_theta,
        rel_tol=1e-9, abs_tol=1e-12,
    ), f"theta_after={var_after.theta} != expected={expected_theta}"


@given(
    velocity=velocity_strategy(),
    dt=dt_strategy(),
    n_ticks=num_ticks_strategy(min_ticks=1, max_ticks=50),
)
def test_advance_n_times(velocity: float, dt: float, n_ticks: int) -> None:
    """Tras N advance_all(dt), θ = (θ_0 + N*velocity*dt) mod 2π."""
    ovc = OVC()
    ovc.create_variable("test", theta=0.0, amplitude=1.0, velocity=velocity)
    var_initial = ovc.get_variable("test")
    assert var_initial is not None
    theta_0 = var_initial.theta  # capturar antes de avanzar

    for _ in range(n_ticks):
        ovc.advance_all(dt)

    var_final = ovc.get_variable("test")
    assert var_final is not None
    expected_theta = (theta_0 + n_ticks * velocity * dt) % TWO_PI
    # Doble modulo para casos edge donde FP redondea a exactamente TWO_PI
    if expected_theta >= TWO_PI:
        expected_theta = expected_theta % TWO_PI
    # Para valores muy pequeños, normalizar a 0 si están muy cerca de TWO_PI o 0
    if expected_theta > TWO_PI - 1e-10:
        expected_theta = 0.0
    assert math.isclose(
        var_final.theta, expected_theta,
        rel_tol=1e-9, abs_tol=1e-12,
    ) or (
        # Caso edge: ambos son ~0 o ~TWO_PI (equivalentes modularmente)
        abs(var_final.theta - expected_theta) < 1e-10
        or abs(var_final.theta - expected_theta - TWO_PI) < 1e-10
        or abs(var_final.theta - expected_theta + TWO_PI) < 1e-10
    ), f"Tras {n_ticks} ticks: theta={var_final.theta} != expected={expected_theta}"


# ─── 4. create_variable respeta parámetros ──────────────────────────────────


@given(
    theta=theta_strategy(),
    amplitude=amplitude_strategy(),
    velocity=velocity_strategy(),
)
def test_create_variable_stores_params(theta: float, amplitude: float, velocity: float) -> None:
    """create_variable debe almacenar los parámetros correctamente."""
    ovc = OVC()
    var = ovc.create_variable(
        "test", theta=theta, amplitude=amplitude, velocity=velocity
    )
    assert var.name == "test"
    assert math.isclose(var.amplitude, amplitude, rel_tol=1e-9)
    assert math.isclose(var.velocity, velocity, rel_tol=1e-9)
    # theta se normaliza pero debe ser equivalente mod 2π
    expected_theta = theta % TWO_PI
    assert math.isclose(var.theta, expected_theta, rel_tol=1e-9, abs_tol=1e-12)


# ─── 5. Variables con mismo nombre se sobreescriben ─────────────────────────


@given(
    theta1=theta_strategy(),
    theta2=theta_strategy(),
)
def test_create_variable_same_name_raises(theta1: float, theta2: float) -> None:
    """Crear una variable con nombre existente debe lanzar ValueError (no sobreescribir)."""
    ovc = OVC()
    ovc.create_variable("test", theta=theta1, amplitude=1.0, velocity=0.1)

    # Segunda creación con mismo nombre debe fallar
    with pytest.raises(ValueError, match="ya existe"):
        ovc.create_variable("test", theta=theta2, amplitude=2.0, velocity=0.2)

    # La variable original debe estar intacta
    assert ovc.variable_count == 1
    var = ovc.get_variable("test")
    assert var is not None
    assert math.isclose(var.amplitude, 1.0, rel_tol=1e-9)


# ─── 6. delete_variable elimina correctamente ───────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_delete_variable(specs: list[dict]) -> None:
    """delete_variable debe eliminar la variable y reducir el count."""
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)

    initial_count = ovc.variable_count
    name_to_delete = specs[0]["name"]
    deleted = ovc.delete_variable(name_to_delete)

    assert deleted, f"delete_variable({name_to_delete}) retornó False"
    assert ovc.variable_count == initial_count - 1
    assert ovc.get_variable(name_to_delete) is None


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_delete_nonexistent_variable_returns_false(specs: list[dict]) -> None:
    """delete_variable de nombre inexistente debe retornar False."""
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)

    deleted = ovc.delete_variable("nonexistent_var_xyz")
    assert not deleted
    assert ovc.variable_count == len(specs)


# ─── 7. Estado del OVC siempre válido ───────────────────────────────────────


@given(specs=variable_specs_unique(min_count=1, max_count=10))
def test_all_variables_have_valid_state(specs: list[dict]) -> None:
    """Todas las variables en el OVC deben tener estado válido:
    - theta ∈ [0, 2π)
    - amplitude > 0
    - velocity finito
    """
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)

    for var in ovc.get_all_variables().values():
        assert 0 <= var.theta < TWO_PI, f"{var.name}: theta={var.theta} fuera de rango"
        assert var.amplitude > 0, f"{var.name}: amplitude={var.amplitude} <= 0"
        assert math.isfinite(var.velocity), f"{var.name}: velocity={var.velocity} no finito"
        assert var.name != "", "Variable sin nombre"


@given(
    specs=variable_specs_unique(min_count=2, max_count=5),
    n_ticks=num_ticks_strategy(min_ticks=1, max_ticks=20),
    dt=dt_strategy(),
)
def test_state_valid_after_n_ticks(specs: list[dict], n_ticks: int, dt: float) -> None:
    """Tras N ticks, todas las variables siguen en estado válido."""
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)

    for _ in range(n_ticks):
        ovc.advance_all(dt)

    for var in ovc.get_all_variables().values():
        assert 0 <= var.theta < TWO_PI
        assert var.amplitude > 0
        assert math.isfinite(var.theta)
        assert math.isfinite(var.amplitude)
