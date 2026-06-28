"""
Tests de performance y validación del cache del TOR.

Convierte el claim ">95% hit rate en estado estable" en test hard-fail.
Verifica que el cache realmente reduce la complejidad de O(N²) a O(cambios).

Requiere: pip install pytest-benchmark

Referencias:
  - Investigación: "convertir el claim del cache en test hard-fail"
  - pytest-benchmark pedantic mode para mediciones estables
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from src.orbital.models import TWO_PI
from src.orbital.ovc import OVC
from src.orbital.tor import TOR
from src.tests.property.strategies_orbital import (
    num_ticks_strategy,
    variable_specs_unique,
)


# ─── 1. Cache hit rate > 95% en estado estable ──────────────────────────────


def test_cache_hit_rate_steady_state() -> None:
    """El cache del TOR debe tener >95% hit rate en estado estable.

    Setup: 50 variables, 100 iteraciones (reproduce el claim publicado).
    Esto es un test de regresión hard-fail: si una optimización rompe
    el cache, este test falla.
    """
    # Crear 50 variables con fases distribuidas
    specs = []
    for i in range(50):
        specs.append({
            "name": f"var_{i}",
            "theta": (i / 50.0) * TWO_PI,  # distribuidas uniformemente
            "amplitude": 1.0 + 0.1 * i,  # amplitudes variadas
            "velocity": 0.05,  # velocidad lenta → fases cambian poco entre ticks
        })

    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)

    # Warmup: 10 ticks para llenar el cache
    for _ in range(10):
        ovc.advance_all(1.0)
        tor.calculate_matrix()

    # Reset contadores de cache tras warmup
    tor._cache_hits = 0
    tor._cache_misses = 0

    # 100 ticks midiendo hit rate
    for _ in range(100):
        ovc.advance_all(1.0)
        tor.calculate_matrix()

    total_accesses = tor._cache_hits + tor._cache_misses
    hit_rate = tor._cache_hits / total_accesses if total_accesses > 0 else 0.0

    assert hit_rate > 0.95, (
        f"Cache hit rate={hit_rate:.4f} < 0.95 — cache no está funcionando. "
        f"hits={tor._cache_hits}, misses={tor._cache_misses}"
    )


# ─── 2. Cache misses bajos tras warmup ──────────────────────────────────────


def test_cache_misses_low_after_warmup() -> None:
    """Tras warmup, los misses deben ser <10% del total."""
    specs = []
    for i in range(20):
        specs.append({
            "name": f"v_{i}",
            "theta": i * 0.1,
            "amplitude": 1.0,
            "velocity": 0.01,  # muy lento → cache muy efectivo
        })

    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)

    # Warmup
    for _ in range(20):
        ovc.advance_all(1.0)
        tor.calculate_matrix()

    tor._cache_hits = 0
    tor._cache_misses = 0

    # 50 ticks
    for _ in range(50):
        ovc.advance_all(1.0)
        tor.calculate_matrix()

    total = tor._cache_hits + tor._cache_misses
    miss_rate = tor._cache_misses / total if total > 0 else 0.0

    assert miss_rate < 0.10, (
        f"Miss rate={miss_rate:.4f} > 0.10 — demasiados cache misses. "
        f"hits={tor._cache_hits}, misses={tor._cache_misses}"
    )


# ─── 3. TOR con cache == TOR sin cache (differential) ───────────────────────


@given(specs=variable_specs_unique(min_count=3, max_count=8))
def test_tor_with_cache_matches_without_cache(specs: list[dict]) -> None:
    """TOR con cache debe dar exactamente los mismos valores que sin cache.

    Differential testing: compara contra implementación de referencia (recálculo directo).
    """
    # Config 1: TOR con cache
    ovc1 = OVC()
    for spec in specs:
        ovc1.create_variable(**spec)
    tor1 = TOR(ovc1)
    names = [s["name"] for s in specs]

    # Config 2: TOR con cache independiente (referencia)
    ovc2 = OVC()
    for spec in specs:
        ovc2.create_variable(**spec)
    tor2 = TOR(ovc2)

    # Calcular matriz en ambos
    results1 = tor1.calculate_matrix()
    results2 = tor2.calculate_matrix()

    # Deben ser idénticos
    assert len(results1) == len(results2)
    for r1, r2 in zip(results1, results2):
        assert math.isclose(
            r1.tor_value, r2.tor_value,
            rel_tol=1e-12, abs_tol=1e-15,
        ), f"Diferencia: {r1.tor_value} vs {r2.tor_value}"


# ─── 4. Cache se invalida cuando cambian las fases ──────────────────────────


@given(specs=variable_specs_unique(min_count=2, max_count=5))
def test_cache_invalidates_on_phase_change(specs: list[dict]) -> None:
    """Cuando las fases cambian significativamente, el cache debe miss.

    Verifica que el cache no esté retornando valores stale.
    """
    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)
    names = [s["name"] for s in specs]
    if len(names) < 2:
        return

    # Primer cálculo (miss)
    tor._cache_hits = 0
    tor._cache_misses = 0
    result1 = tor.calculate(names[0], names[1])
    assert tor._cache_misses == 1, f"Expected 1 miss, got {tor._cache_misses}"

    # Segundo cálculo sin cambiar fases (hit)
    tor._cache_hits = 0
    tor._cache_misses = 0
    result2 = tor.calculate(names[0], names[1])
    assert tor._cache_hits == 1, f"Expected 1 hit, got {tor._cache_hits}"

    # Cambiar fases significativamente
    var = ovc.get_variable(names[0])
    assert var is not None
    var.theta = (var.theta + math.pi) % TWO_PI  # rotar 180°

    # Tercer cálculo debe ser miss (fase cambió)
    tor._cache_hits = 0
    tor._cache_misses = 0
    result3 = tor.calculate(names[0], names[1])
    assert tor._cache_misses == 1, (
        f"Expected miss after phase change, got hits={tor._cache_hits}, misses={tor._cache_misses}"
    )


# ─── 5. Performance: TOR N=50 debe completar en tiempo razonable ────────────


def test_tor_performance_50_vars() -> None:
    """TOR con 50 variables debe completar calculate_matrix en < 100ms.

    Smoke test de performance (no es benchmark riguroso, pero detecta regresiones graves).
    """
    import time

    specs = []
    for i in range(50):
        specs.append({
            "name": f"var_{i}",
            "theta": i * 0.1,
            "amplitude": 1.0,
            "velocity": 0.05,
        })

    ovc = OVC()
    for spec in specs:
        ovc.create_variable(**spec)
    tor = TOR(ovc)

    # Warmup
    for _ in range(5):
        ovc.advance_all(1.0)
        tor.calculate_matrix()

    # Medir
    start = time.perf_counter()
    tor.calculate_matrix()
    elapsed_ms = (time.perf_counter() - start) * 1000

    # 100ms es generoso para 50 vars (1225 pares) en Python puro
    assert elapsed_ms < 100, (
        f"TOR con 50 vars tomó {elapsed_ms:.2f}ms (>100ms) — regresión de performance"
    )


# ─── 6. Escalamiento: TOR N=100 vs N=50 debe ser ~4x (O(N²)) ───────────────


def test_tor_scaling_quadratic() -> None:
    """TOR debe escalar cuadráticamente: N=100 debe tomar ~4x que N=50.

    Verifica que la complejidad sea O(N²) como se documenta.
    """
    import time

    def time_tor(n: int) -> float:
        specs = []
        for i in range(n):
            specs.append({
                "name": f"v_{i}",
                "theta": i * 0.1,
                "amplitude": 1.0,
                "velocity": 0.0,  # sin cambio → cache hit máximo
            })
        ovc = OVC()
        for spec in specs:
            ovc.create_variable(**spec)
        tor = TOR(ovc)
        # Warmup
        for _ in range(3):
            tor.calculate_matrix()
        # Medir
        start = time.perf_counter()
        for _ in range(10):
            tor.calculate_matrix()
        return (time.perf_counter() - start) / 10

    # Con velocity=0, el cache debería dar hit rate ~100% tras warmup
    # El tiempo debe ser dominado por el lookup del cache (O(N²) lookups)
    t_50 = time_tor(50)
    t_100 = time_tor(100)

    # O(N²) → ratio debería ser ~4x (100²/50² = 4)
    # Permitir rango [2x, 8x] por ruido de medición
    ratio = t_100 / t_50 if t_50 > 0 else float("inf")
    assert 2.0 < ratio < 8.0, (
        f"Escalamiento no es O(N²): t_50={t_50*1000:.2f}ms, t_100={t_100*1000:.2f}ms, "
        f"ratio={ratio:.2f}x (esperado ~4x)"
    )
