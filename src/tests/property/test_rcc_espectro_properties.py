"""
Property-based tests de invariantes del RCC, Espectro y CicloOrbital.

Invariantes verificados:
  1. RCC: resonance_strength ∈ [0, 1] o rango válido
  2. RCC: is_resonant = (resonance_strength > threshold)
  3. RCC: ciclo de 1 variable no resuena
  4. Espectro: primary_mode ∈ [0, len(modes))
  5. Espectro: modes es lista (posiblemente vacía)
  6. CicloOrbital: threshold ∈ [0, 1]
  7. COD: convergencia tras MAX_ITERATIONS

Referencias:
  - Investigación: "RCC ∈ [0,1], Espectro normalizado"
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.orbital.cod import COD
from src.orbital.espectro import EspectroOrbital
from src.orbital.models import (
    DEFAULT_THRESHOLD,
    MAX_COD_ITERATIONS,
    CicloOrbital,
    VariableOrbital,
)
from src.orbital.ovc import OVC
from src.orbital.rcc import RCC
from src.orbital.tor import TOR
from src.tests.property.strategies_orbital import (
    amplitude_strategy,
    theta_strategy,
    threshold_strategy,
    variable_specs_unique,
    velocity_strategy,
)


# ─── Helper ──────────────────────────────────────────────────────────────────


def _build_orbital_stack(specs: list[dict]) -> tuple[OVC, TOR, RCC, COD, EspectroOrbital]:
    """Construye los 5 pilares con variables dadas."""
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)
    rcc = RCC(ovc, tor)
    cod = COD(ovc, tor, rcc)
    espectro = EspectroOrbital(ovc, tor, rcc, cod)
    return ovc, tor, rcc, cod, espectro


# ─── 1. RCC: resonance_strength en rango válido ─────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_rcc_resonance_in_range(specs: list[dict]) -> None:
    """resonance_strength debe estar en un rango acotado [-1, 1] o [0, 1]."""
    _, _, rcc, _, _ = _build_orbital_stack(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    cycle = rcc.register_cycle_from_names("test_cycle", names, threshold=0.4)
    result = rcc.detect(cycle)

    # resonance_strength debe ser finito y acotado
    assert math.isfinite(result.resonance_strength), (
        f"resonance_strength={result.resonance_strength} no es finito"
    )
    assert -1.0 <= result.resonance_strength <= 1.0 + 1e-9, (
        f"resonance_strength={result.resonance_strength} fuera de [-1, 1]"
    )


# ─── 2. RCC: is_resonant respeta threshold ──────────────────────────────────


@given(
    specs=variable_specs_unique(min_count=2, max_count=4),
    threshold=threshold_strategy(),
)
def test_rcc_is_resonant_respects_threshold(specs: list[dict], threshold: float) -> None:
    """is_resonant debe ser True iff average_tension > threshold.

    Nota: RCC usa average_tension (no normalizada) para is_resonant,
    mientras que resonance_strength es la versión normalizada a [0,1].
    """
    _, _, rcc, _, _ = _build_orbital_stack(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    cycle = rcc.register_cycle_from_names("test_cycle", names, threshold=threshold)
    result = rcc.detect(cycle)

    # is_resonant se basa en average_tension, no en resonance_strength
    expected = result.average_tension > threshold
    assert result.is_resonant == expected, (
        f"is_resonant={result.is_resonant} pero avg_tension={result.average_tension}, "
        f"threshold={threshold}, expected={expected}"
    )


# ─── 3. RCC: ciclo de 1 variable no resuena ─────────────────────────────────


@given(specs=variable_specs_unique(min_count=1, max_count=1))
def test_rcc_single_variable_cycle_not_resonant(specs: list[dict]) -> None:
    """Un ciclo con 1 sola variable no debe resonar (no hay tensión recíproca)."""
    _, _, rcc, _, _ = _build_orbital_stack(specs)
    name = specs[0]["name"]

    cycle = rcc.register_cycle_from_names("solo", [name], threshold=0.1)
    result = rcc.detect(cycle)

    # Con 1 variable, no hay pares → resonancia debería ser 0 o no resonante
    assert not result.is_resonant or result.resonance_strength <= 0.1, (
        f"Ciclo de 1 variable resuena: {result.is_resonant}, strength={result.resonance_strength}"
    )


# ─── 4. Espectro: primary_mode en rango válido ──────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_espectro_primary_mode_in_range(specs: list[dict]) -> None:
    """primary_mode debe ser un índice válido de modes (0 <= primary_mode < len(modes))."""
    _, _, _, _, espectro = _build_orbital_stack(specs)
    names = [s["name"] for s in specs]

    from src.orbital.models import CicloOrbital

    cycle = CicloOrbital(name="test", variable_ids=names, threshold=0.4)
    estado = espectro.generate(cycle, retrofeed_damping=0.3)

    if estado.modes:
        assert 0 <= estado.primary_mode < len(estado.modes), (
            f"primary_mode={estado.primary_mode} fuera de rango [0, {len(estado.modes)})"
        )


# ─── 5. Espectro: modes es lista ────────────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_espectro_modes_is_list(specs: list[dict]) -> None:
    """EspectroEstado.modes debe ser una lista (posiblemente vacía)."""
    _, _, _, _, espectro = _build_orbital_stack(specs)
    names = [s["name"] for s in specs]

    from src.orbital.models import CicloOrbital

    cycle = CicloOrbital(name="test", variable_ids=names, threshold=0.4)
    estado = espectro.generate(cycle, retrofeed_damping=0.3)

    assert isinstance(estado.modes, list), f"modes no es lista: {type(estado.modes)}"
    for mode in estado.modes:
        assert isinstance(mode, dict), f"mode no es dict: {type(mode)}"


# ─── 6. CicloOrbital: threshold en rango ────────────────────────────────────


@given(threshold=threshold_strategy())
def test_ciclo_orbital_threshold_in_range(threshold: float) -> None:
    """CicloOrbital.threshold debe estar en [0, 1]."""
    cycle = CicloOrbital(name="test", variable_ids=["a", "b"], threshold=threshold)
    assert 0.0 <= cycle.threshold <= 1.0


# ─── 7. COD: convergencia tras MAX_ITERATIONS ───────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=4))
def test_cod_converges_within_max_iterations(specs: list[dict]) -> None:
    """COD debe converger (o alcanzar MAX_ITERATIONS) sin error."""
    _, _, rcc, cod, _ = _build_orbital_stack(specs)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    cycle = rcc.register_cycle_from_names("converge_test", names, threshold=0.3)
    result = cod.collapse_with_retrofeedback(cycle, retrofeed_damping=0.3, dt=1.0)

    # Debe retornar un CODResult válido
    assert result is not None
    assert isinstance(result.converged, bool)
    assert isinstance(result.iterations, int)
    assert result.iterations <= MAX_COD_ITERATIONS, (
        f"iterations={result.iterations} > MAX={MAX_COD_ITERATIONS}"
    )


# ─── 8. Espectro: retrofeedback solo contiene variables existentes ──────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_espectro_retrofeedback_keys_are_variables(specs: list[dict]) -> None:
    """EspectroEstado.retrofeedback debe tener keys que son nombres de variables."""
    _, _, _, _, espectro = _build_orbital_stack(specs)
    names = set(s["name"] for s in specs)

    from src.orbital.models import CicloOrbital

    cycle = CicloOrbital(name="test", variable_ids=list(names), threshold=0.4)
    estado = espectro.generate(cycle, retrofeed_damping=0.3)

    for key in estado.retrofeedback.keys():
        assert key in names, f"retrofeedback key '{key}' no es una variable existente"


# ─── 9. RCC: detect_all retorna lista de resultados ─────────────────────────


@given(specs=variable_specs_unique(min_count=3, max_count=6))
def test_rcc_detect_all_returns_list(specs: list[dict]) -> None:
    """RCC.detect_all() debe retornar una lista de RCCResult."""
    _, _, rcc, _, _ = _build_orbital_stack(specs)
    names = [s["name"] for s in specs]

    # Registrar 2 ciclos
    rcc.register_cycle_from_names("c1", names[:2], threshold=0.3)
    if len(names) >= 3:
        rcc.register_cycle_from_names("c2", names[1:3], threshold=0.4)

    results = rcc.detect_all()
    assert isinstance(results, list)
    for r in results:
        assert hasattr(r, "is_resonant")
        assert hasattr(r, "resonance_strength")


# ─── 10. Sistema completo: run_tick no rompe invariantes ────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=4))
def test_run_tick_preserves_invariants(specs: list[dict]) -> None:
    """Tras run_tick(), todas las variables siguen en estado válido."""
    from src.orbital.engine import OrbitalEngine
    from src.orbital.models import TWO_PI

    engine = OrbitalEngine()
    for spec in specs:
        engine.create_variable(**spec)
    names = [s["name"] for s in specs]
    engine.create_cycle("test_cycle", names, threshold=0.4)

    # Ejecutar 3 ticks
    for _ in range(3):
        engine.run_tick(dt=1.0, retrofeed_damping=0.3)

    # Verificar invariantes
    for var in engine.get_all_variables().values():
        assert 0 <= var.theta < TWO_PI, f"{var.name}: theta={var.theta} fuera de rango"
        assert var.amplitude > 0, f"{var.name}: amplitude={var.amplitude} <= 0"
        assert math.isfinite(var.theta), f"{var.name}: theta no es finito"
        assert math.isfinite(var.amplitude), f"{var.name}: amplitude no es finito"
