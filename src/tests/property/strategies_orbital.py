"""
Strategies de Hypothesis para el Orbital Engine.

Strategies reutilizables para generar:
  - theta ∈ [0, 2π) con allow_nan=False
  - amplitudes positivas finitas
  - velocities razonables (no extremas)
  - VariableOrbital válidas
  - OrbitalEngine con configuraciones variadas

Reglas críticas (trampas documentadas en la investigación):
  - SIEMPRE allow_nan=False, allow_infinity=False, allow_subnormal=False en floats
  - NO usar UUIDs como identidad entre runs (usar name)
  - NO mezclar @given con pytest.mark.parametrize
"""
from __future__ import annotations

import math
from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

# ─── Constantes ──────────────────────────────────────────────────────────────

TWO_PI = 2 * math.pi
MAX_AMPLITUDE = 1e6  # límite superior para evitar overflow en productos
MAX_VELOCITY = 1.0  # rad/tick: velocidades extremas causan divergencia rápida


# ─── Strategies atómicas ─────────────────────────────────────────────────────


def theta_strategy() -> SearchStrategy[float]:
    """Fase orbital θ ∈ [0, 2π).

    Excluye NaN, Inf, subnormales (causan issues cross-platform).
    """
    return st.floats(
        min_value=0.0,
        max_value=TWO_PI,
        exclude_max=True,  # [0, 2π)
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def amplitude_strategy() -> SearchStrategy[float]:
    """Amplitud A > 0, finita, no extrema.

    Acotada a [1e-3, 1e6] para evitar:
      - Underflow (amplitudes ~0 hacen TOR ~0 siempre)
      - Overflow (amplitudes ~1e308 causan Inf en productos)
    """
    return st.floats(
        min_value=1e-3,
        max_value=MAX_AMPLITUDE,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def velocity_strategy() -> SearchStrategy[float]:
    """Velocidad orbital ω ∈ [-1, 1] rad/tick.

    Acotada para evitar divergencia rápida en tests de N ticks.
    """
    return st.floats(
        min_value=-MAX_VELOCITY,
        max_value=MAX_VELOCITY,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def threshold_strategy() -> SearchStrategy[float]:
    """Threshold de resonancia ∈ [0, 1].

    Incluye 0 (cualquier tensión > 0 es resonante) y 1 (tensión máxima).
    """
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def dt_strategy() -> SearchStrategy[float]:
    """Paso temporal dt ∈ (0, 2].

    Acotado para evitar avances extremos en un solo tick.
    """
    return st.floats(
        min_value=1e-3,
        max_value=2.0,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def damping_strategy() -> SearchStrategy[float]:
    """Factor de retroalimentación ∈ [0, 1].

    0 = sin retroalimentación, 1 = retroalimentación total.
    """
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


# ─── Strategies compuestas ───────────────────────────────────────────────────


def variable_spec_strategy(
    name_strategy: SearchStrategy[str] | None = None,
) -> SearchStrategy[dict]:
    """Spec de VariableOrbital como dict (para create_variable).

    Genera specs con theta/amplitude/velocity válidos.
    """
    if name_strategy is None:
        # Nombres cortos, alfanuméricos, sin colisiones típicas
        name_strategy = st.text(
            alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            min_size=1,
            max_size=10,
        )
    return st.fixed_dictionaries(
        {
            "name": name_strategy,
            "theta": theta_strategy(),
            "amplitude": amplitude_strategy(),
            "velocity": velocity_strategy(),
        }
    )


def variable_specs_unique(
    min_count: int = 2,
    max_count: int = 5,
) -> SearchStrategy[list[dict]]:
    """Lista de specs con nombres únicos (sin colisiones).

    Usa st.lists con unique_by para garantizar nombres distintos.
    """
    return st.lists(
        variable_spec_strategy(),
        min_size=min_count,
        max_size=max_count,
        unique_by=lambda spec: spec["name"],
    )


def engine_state_strategy(
    min_variables: int = 2,
    max_variables: int = 5,
) -> SearchStrategy[dict]:
    """Estado completo de un OrbitalEngine: variables + ciclos opcionales.

    Retorna dict con:
      - variables: lista de specs con nombres únicos
      - cycles: lista de (name, variable_names_subset, threshold)
    """
    return st.builds(
        lambda specs: {
            "variables": specs,
            "cycles": _cycles_for_variables(specs),
        },
        variable_specs_unique(min_variables, max_variables),
    )


def _cycles_for_variables(specs: list[dict]) -> list[dict]:
    """Genera ciclos válidos a partir de specs de variables.

    Esta función NO es una strategy; es un helper para engine_state_strategy.
    Crea 0-2 ciclos con subconjuntos de variables.
    """
    # En una implementación real usaríamos st.builds, pero para simplicidad
    # retornamos un ciclo fijo con las primeras 2-3 variables.
    if len(specs) < 2:
        return []
    var_names = [s["name"] for s in specs[:3]]  # máximo 3 vars por ciclo
    return [
        {
            "name": "test_cycle",
            "variable_names": var_names,
            "threshold": 0.4,
        }
    ]


# ─── Strategies para tests metamórficos ──────────────────────────────────────


def scaling_factor_strategy() -> SearchStrategy[float]:
    """Factor de escalamiento k ∈ [0.1, 10] para tests metamórficos.

    Acotado para evitar overflow/underflow al escalar amplitudes.
    """
    return st.floats(
        min_value=0.1,
        max_value=10.0,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def perturbation_strategy() -> SearchStrategy[float]:
    """Perturbación ε ∈ [1e-6, 1e-2] para tests de Lyapunov stability.

    Pequeña pero no subnormal.
    """
    return st.floats(
        min_value=1e-6,
        max_value=1e-2,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
    )


def num_ticks_strategy(
    min_ticks: int = 1,
    max_ticks: int = 100,
) -> SearchStrategy[int]:
    """Número de ticks para tests de ejecución.

    Acotado para que los tests no tarden demasiado.
    """
    return st.integers(min_value=min_ticks, max_value=max_ticks)


def seed_strategy() -> SearchStrategy[int]:
    """Semilla entera para tests de determinismo."""
    return st.integers(min_value=0, max_value=2**32 - 1)
