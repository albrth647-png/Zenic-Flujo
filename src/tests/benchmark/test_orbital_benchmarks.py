"""
Benchmarks del Orbital Engine con pytest-benchmark.

Mide:
  1. Tick frío (cache vacío): O(N²) puro
  2. Tick caliente (cache poblado): O(cambios) esperado
  3. calculate_matrix solo (sin tick completo)
  4. Escalamiento N = 10, 50, 100, 500, 1000

Ejecutar:
    pytest src/tests/benchmark/ --benchmark-only -v
    pytest src/tests/benchmark/ --benchmark-only --benchmark-save=baseline
    pytest src/tests/benchmark/ --benchmark-only --benchmark-compare=baseline

Comparación con regresión (fail si empeora >20%):
    pytest src/tests/benchmark/ --benchmark-only \\
        --benchmark-compare=baseline --benchmark-compare-fail=mean:20%

Referencias:
  - Investigación: "pytest-benchmark pedantic mode, GC off, warmup controlado"
  - Skill: .opencode/skills/any-best-practices/SKILL.md §10
"""
from __future__ import annotations

import pytest

from src.orbital.engine import OrbitalEngine
from src.orbital.models import TWO_PI


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _create_engine_with_vars(n: int, velocity: float = 0.05) -> OrbitalEngine:
    """Crea un OrbitalEngine con N variables distribuidas uniformemente."""
    engine = OrbitalEngine()
    for i in range(n):
        engine.create_variable(
            f"var_{i}",
            theta=(i / n) * TWO_PI,
            amplitude=1.0 + 0.01 * i,
            velocity=velocity,
        )
    # Crear un ciclo para que RCC/COD/Espectro tengan trabajo
    if n >= 2:
        var_names = [f"var_{i}" for i in range(min(n, 5))]
        engine.create_cycle("bench_cycle", var_names, threshold=0.4)
    return engine


@pytest.fixture(
    params=[10, 50, 100, 500, 1000],
    ids=["N10", "N50", "N100", "N500", "N1000"],
)
def engine_n(request) -> OrbitalEngine:
    """Engine con N variables (parametrizado)."""
    return _create_engine_with_vars(request.param)


@pytest.fixture(
    params=[10, 50, 100],
    ids=["N10", "N50", "N100"],
)
def engine_warm(request) -> OrbitalEngine:
    """Engine con N variables, cache pre-calentado (50 ticks warmup)."""
    eng = _create_engine_with_vars(request.param)
    # Warmup: ejecutar 50 ticks para llenar el cache del TOR
    for _ in range(50):
        eng.run_tick(dt=1.0, retrofeed_damping=0.3)
    return eng


# ─── Benchmarks de tick ──────────────────────────────────────────────────────


@pytest.mark.benchmark(group="tick_cold")
def test_tick_cold(benchmark, engine_n) -> None:
    """Tick FRÍO (sin warmup): mide O(N²) puro del TOR.

    Este benchmark debe escalar cuadráticamente con N.
    """
    result = benchmark.pedantic(
        engine_n.run_tick,
        rounds=10,
        iterations=1,
        warmup_rounds=1,
    )
    assert result is not None


@pytest.mark.benchmark(group="tick_warm")
def test_tick_warm(benchmark, engine_warm) -> None:
    """Tick CALIENTE (cache pre-calentado): mide O(cambios) esperado.

    Con cache hit rate >95%, este benchmark debe ser significativamente
    más rápido que tick_cold para el mismo N.
    """
    result = benchmark.pedantic(
        engine_warm.run_tick,
        rounds=20,
        iterations=5,
        warmup_rounds=3,
    )
    assert result is not None


# ─── Benchmarks de TOR (matriz de tensiones) ────────────────────────────────


@pytest.mark.benchmark(group="tor_matrix")
def test_tor_calculate_matrix(benchmark, engine_n) -> None:
    """calculate_matrix() solo (sin tick completo).

    Aísla el costo del TOR del resto del pipeline.
    """
    benchmark.pedantic(
        engine_n.tor.calculate_matrix,
        rounds=20,
        iterations=3,
        warmup_rounds=2,
    )


# ─── Benchmarks de OVC (advance_all) ─────────────────────────────────────────


@pytest.mark.benchmark(group="ovc_advance")
def test_ovc_advance_all(benchmark, engine_n) -> None:
    """OVC.advance_all() solo: debe ser O(N) lineal."""
    benchmark.pedantic(
        engine_n.ovc.advance_all,
        rounds=30,
        iterations=5,
        warmup_rounds=3,
    )


# ─── Benchmark de creación de variables ──────────────────────────────────────


@pytest.mark.benchmark(group="create_variable")
@pytest.mark.parametrize("n", [10, 100, 1000], ids=["N10", "N100", "N1000"])
def test_create_n_variables(benchmark, n: int) -> None:
    """Crear N variables desde cero: debe ser O(N) lineal."""
    def create_n():
        eng = OrbitalEngine()
        for i in range(n):
            eng.create_variable(f"v_{i}", theta=0.1 * i, amplitude=1.0, velocity=0.05)
        return eng

    benchmark.pedantic(
        create_n,
        rounds=10,
        iterations=1,
        warmup_rounds=1,
    )


# ─── Benchmark de cache hit rate ─────────────────────────────────────────────


def test_cache_hit_rate_warm() -> None:
    """Verifica que el cache hit rate del TOR sea >95% en estado estable.

    Este NO es un benchmark de timing sino una aserción de métrica.
    Convierte el claim publicado en test hard-fail.
    """
    eng = _create_engine_with_vars(50, velocity=0.05)

    # Warmup
    for _ in range(20):
        eng.run_tick(dt=1.0, retrofeed_damping=0.3)

    # Reset contadores
    eng.tor._cache_hits = 0
    eng.tor._cache_misses = 0

    # 100 ticks midiendo
    for _ in range(100):
        eng.run_tick(dt=1.0, retrofeed_damping=0.3)

    total = eng.tor._cache_hits + eng.tor._cache_misses
    hit_rate = eng.tor._cache_hits / total if total > 0 else 0.0
    print(f"\n  Cache hit rate: {hit_rate:.4f} (hits={eng.tor._cache_hits}, misses={eng.tor._cache_misses})")

    assert hit_rate > 0.95, f"Cache hit rate={hit_rate:.4f} < 0.95"
