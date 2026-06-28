"""
Tests de determinismo y fingerprinting para el Orbital Engine.

Verifica que el motor es 100% determinista:
  - Misma configuración inicial → mismo estado final (bit-a-bit)
  - Fingerprint BLAKE2b del estado es reproducible
  - Snapshot del motor es idempotente

El fingerprint usa BLAKE2b (no repr()) para evitar dependencia de float formatting.
Referencias: investigación "Floating Point Determinism" (Bruce Dawson, Glenn Fiedler).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.orbital.engine import OrbitalEngine
from src.orbital.models import TWO_PI, VariableOrbital
from src.tests.property.strategies_orbital import (
    amplitude_strategy,
    dt_strategy,
    num_ticks_strategy,
    theta_strategy,
    variable_specs_unique,
    velocity_strategy,
)


# Settings reducidos para tests de determinismo (que ejecutan OrbitalEngine completo)
_DETERMINISM_SETTINGS = settings(
    max_examples=30,  # 30 ejemplos en vez de 200 (cada test ejecuta 2 engines × N ticks)
    deadline=None,
    suppress_health_check=[
        __import__("hypothesis", fromlist=["HealthCheck"]).HealthCheck.too_slow,
        __import__("hypothesis", fromlist=["HealthCheck"]).HealthCheck.function_scoped_fixture,
    ],
)


# ─── Fingerprinting BLAKE2b ─────────────────────────────────────────────────


def orbital_fingerprint(engine: OrbitalEngine) -> str:
    """Genera fingerprint BLAKE2b del estado completo del motor.

    Serializa variables con sus theta/amplitude/velocity a JSON canónico
    (sorted keys) y hashea con BLAKE2b.

    NO usa repr() porque depende de float formatting (plataforma-dependiente).
    """
    h = hashlib.blake2b(digest_size=32)
    variables = engine.get_all_variables()
    # Serialización determinista: sorted por nombre
    state = {}
    for name in sorted(variables.keys()):
        var = variables[name]
        # Redondear a 12 decimales para estabilidad cross-platform
        state[name] = {
            "theta": round(var.theta, 12),
            "amplitude": round(var.amplitude, 12),
            "velocity": round(var.velocity, 12),
        }
    h.update(json.dumps(state, sort_keys=True).encode("utf-8"))
    return h.hexdigest()


# ─── 1. Determinismo: misma config → mismo estado final ─────────────────────


@_DETERMINISM_SETTINGS
@given(
    specs=variable_specs_unique(min_count=2, max_count=4),
    n_ticks=num_ticks_strategy(min_ticks=1, max_ticks=10),
    dt=dt_strategy(),
)
def test_determinism_same_config_same_state(
    specs: list[dict], n_ticks: int, dt: float
) -> None:
    """Dos engines con misma config inicial, mismos ticks → mismo estado final."""
    # Engine 1
    engine1 = OrbitalEngine()
    for spec in specs:
        engine1.create_variable(**spec)
    names = [s["name"] for s in specs]
    engine1.create_cycle("test_cycle", names, threshold=0.4)
    for _ in range(n_ticks):
        engine1.run_tick(dt=dt, retrofeed_damping=0.3)

    # Engine 2 (misma config)
    engine2 = OrbitalEngine()
    for spec in specs:
        engine2.create_variable(**spec)
    engine2.create_cycle("test_cycle", names, threshold=0.4)
    for _ in range(n_ticks):
        engine2.run_tick(dt=dt, retrofeed_damping=0.3)

    # Comparar fingerprints
    fp1 = orbital_fingerprint(engine1)
    fp2 = orbital_fingerprint(engine2)
    assert fp1 == fp2, (
        f"No determinismo: fingerprints difieren.\n"
        f"Engine1: {fp1[:16]}...\n"
        f"Engine2: {fp2[:16]}..."
    )


# ─── 2. Fingerprint es reproducible ─────────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_fingerprint_reproducible(specs: list[dict]) -> None:
    """El fingerprint del mismo engine debe ser idéntico dos veces seguidas."""
    engine = OrbitalEngine()
    for spec in specs:
        engine.create_variable(**spec)

    fp1 = orbital_fingerprint(engine)
    fp2 = orbital_fingerprint(engine)
    assert fp1 == fp2, "Fingerprint no es reproducible"
    assert len(fp1) == 64, f"Fingerprint debe ser 64 chars, no {len(fp1)}"


# ─── 3. Fingerprint cambia si el estado cambia ──────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_fingerprint_changes_with_state(specs: list[dict]) -> None:
    """El fingerprint debe cambiar tras advance_all si alguna variable tiene velocity != 0."""
    engine = OrbitalEngine()
    for spec in specs:
        engine.create_variable(**spec)

    fp_before = orbital_fingerprint(engine)
    engine.run_tick(dt=1.0, retrofeed_damping=0.3)
    fp_after = orbital_fingerprint(engine)

    # Solo verificar cambio si al menos una variable tiene velocity significativa
    has_velocity = any(abs(s["velocity"]) > 1e-6 for s in specs)
    if has_velocity:
        assert fp_before != fp_after, "Fingerprint no cambió tras run_tick (con velocity != 0)"


# ─── 4. Determinismo con seed explícita ─────────────────────────────────────


@_DETERMINISM_SETTINGS
@given(
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    n_ticks=num_ticks_strategy(min_ticks=1, max_ticks=5),
)
def test_determinism_with_seed(seed: int, n_ticks: int) -> None:
    """Con mismo seed, dos engines deben producir mismo estado final.

    Usamos seed para generar specs deterministamente.
    """
    import random
    rng = random.Random(seed)

    # Generar specs deterministas a partir del seed
    specs = []
    for i in range(3):
        specs.append({
            "name": f"var_{i}",
            "theta": rng.uniform(0, TWO_PI),
            "amplitude": rng.uniform(0.1, 10.0),
            "velocity": rng.uniform(-0.5, 0.5),
        })

    # Engine 1
    engine1 = OrbitalEngine()
    for spec in specs:
        engine1.create_variable(**spec)
    engine1.create_cycle("c", [s["name"] for s in specs], threshold=0.4)
    for _ in range(n_ticks):
        engine1.run_tick(dt=1.0, retrofeed_damping=0.3)

    # Engine 2 (misma seed → mismos specs)
    rng2 = random.Random(seed)
    specs2 = []
    for i in range(3):
        specs2.append({
            "name": f"var_{i}",
            "theta": rng2.uniform(0, TWO_PI),
            "amplitude": rng2.uniform(0.1, 10.0),
            "velocity": rng2.uniform(-0.5, 0.5),
        })

    engine2 = OrbitalEngine()
    for spec in specs2:
        engine2.create_variable(**spec)
    engine2.create_cycle("c", [s["name"] for s in specs2], threshold=0.4)
    for _ in range(n_ticks):
        engine2.run_tick(dt=1.0, retrofeed_damping=0.3)

    assert orbital_fingerprint(engine1) == orbital_fingerprint(engine2)


# ─── 5. Snapshot idempotente ────────────────────────────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_snapshot_idempotent(specs: list[dict]) -> None:
    """Tomar snapshot dos veces del mismo estado debe dar mismo resultado."""
    engine = OrbitalEngine()
    for spec in specs:
        engine.create_variable(**spec)

    # Serializar estado a dict
    def snapshot():
        return {
            name: {
                "theta": round(var.theta, 12),
                "amplitude": round(var.amplitude, 12),
                "velocity": round(var.velocity, 12),
            }
            for name, var in engine.get_all_variables().items()
        }

    snap1 = snapshot()
    snap2 = snapshot()
    assert snap1 == snap2, "Snapshot no es idempotente"


# ─── 6. Orden de creación no afecta fingerprint ─────────────────────────────


@given(specs=variable_specs_unique(min_count=3, max_count=5))
def test_creation_order_invariant(specs: list[dict]) -> None:
    """Crear variables en orden distinto → mismo fingerprint.

    El fingerprint debe ser invariante al orden de creación
    (porque ordena por nombre internamente).
    """
    # Engine 1: orden original
    engine1 = OrbitalEngine()
    for spec in specs:
        engine1.create_variable(**spec)

    # Engine 2: orden inverso
    engine2 = OrbitalEngine()
    for spec in reversed(specs):
        engine2.create_variable(**spec)

    assert orbital_fingerprint(engine1) == orbital_fingerprint(engine2), (
        "Fingerprint difiere por orden de creación (debe ser invariante)"
    )
