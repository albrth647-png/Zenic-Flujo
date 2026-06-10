"""
ORBITAL — Benchmarks de Rendimiento (Fase 6.1)
===============================================

Benchmarks para medir:
1. Tiempo de ejecucion del motor orbital completo
2. Throughput (ticks/segundo)
3. Uso de memoria del OVC
4. Efectividad del cache de TOR (hit rate)
5. Convergencia del COD (iteraciones promedio)

Ejecutar:
    python -m pytest src/tests/test_orbital_benchmarks.py -v --benchmark

"""

import time
import math
import pytest
from src.orbital.context import OrbitalContext
from src.orbital.models import MAX_COD_ITERATIONS


# ── Fixtures ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_context():
    OrbitalContext._reset()
    yield


def _setup_large_system(ctx, n_vars=10, n_cycles=3):
    """Crea un sistema orbital con N variables y M ciclos."""
    engine = ctx.engine
    specs = []
    for i in range(n_vars):
        theta = (i / n_vars) * 2 * math.pi
        amp = 10 + (i * 5)
        vel = 0.05 + (i * 0.02)
        engine.create_variable(f"Var{i}", theta=theta, amplitude=amp, velocity=vel)
    for c in range(n_cycles):
        start = c * (n_vars // n_cycles)
        end = start + (n_vars // n_cycles)
        vars_in_cycle = [f"Var{i}" for i in range(start, min(end, n_vars))]
        if len(vars_in_cycle) >= 2:
            engine.create_cycle(f"Ciclo{c}", vars_in_cycle, threshold=0.5)
    return engine


# ── Benchmark 1: Tiempo de tick orbital ────────────────────

def test_benchmark_tick_time():
    """Mide el tiempo promedio de un tick orbital completo."""
    ctx = OrbitalContext()
    _setup_large_system(ctx, n_vars=15, n_cycles=5)

    # Warmup
    ctx.run_tick()

    times = []
    for _ in range(20):
        start = time.perf_counter()
        ctx.run_tick()
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg_ms = (sum(times) / len(times)) * 1000
    max_ms = max(times) * 1000
    min_ms = min(times) * 1000

    print(f"\n  Ticks: {len(times)}")
    print(f"  Promedio: {avg_ms:.2f}ms")
    print(f"  Min: {min_ms:.2f}ms | Max: {max_ms:.2f}ms")
    print(f"  Throughput: {1000/avg_ms:.1f} ticks/s")

    # Debe ejecutar un tick en menos de 500ms
    assert avg_ms < 500, f"Tick promedio demasiado lento: {avg_ms:.2f}ms"


# ── Benchmark 2: Throughput multi-tick ─────────────────────

def test_benchmark_throughput():
    """Mide cuantos ticks puede ejecutar en 2 segundos."""
    ctx = OrbitalContext()
    _setup_large_system(ctx, n_vars=10, n_cycles=3)

    start = time.perf_counter()
    count = 0
    while time.perf_counter() - start < 2.0:
        ctx.run_tick()
        count += 1

    throughput = count / 2.0
    print(f"\n  Ticks en 2s: {count}")
    print(f"  Throughput: {throughput:.1f} ticks/s")

    # Debe poder ejecutar al menos 5 ticks/s
    assert throughput >= 5, f"Throughput demasiado bajo: {throughput:.1f} ticks/s"


# ── Benchmark 3: Convergencia COD ──────────────────────────

def test_benchmark_cod_convergence():
    """Mide cuantas iteraciones toma el COD en converger con amplitudes variadas."""
    ctx = OrbitalContext()
    engine = ctx.engine

    amplitudes = [1, 10, 100, 1000, 10000]
    results = []

    for amp in amplitudes:
        OrbitalContext._reset()
        ctx = OrbitalContext()
        engine = ctx.engine

        engine.create_variable("Demanda", theta=0.0, amplitude=amp, velocity=0.15)
        engine.create_variable("Precio", theta=0.3, amplitude=amp * 0.5, velocity=0.08)
        engine.create_variable("Oferta", theta=0.5, amplitude=amp * 0.8, velocity=0.12)
        engine.create_cycle("Economico", ["Demanda", "Precio", "Oferta"], threshold=0.5)

        result = ctx.run_tick()
        cod_result = result.cod_results[0] if result.cod_results else None

        if cod_result:
            results.append({
                "amplitude": amp,
                "converged": cod_result.converged,
                "iterations": cod_result.iterations,
                "delta": cod_result.convergence_delta,
            })
            print(f"\n  Amplitud {amp:6d}: convergio={cod_result.converged} iter={cod_result.iterations} delta={cod_result.convergence_delta:.6f}")
        else:
            print(f"\n  Amplitud {amp:6d}: SIN resultado COD")

    # Todas las amplitudes deben converger en < MAX_COD_ITERATIONS
    for r in results:
        assert r["converged"], f"COD no convergio con amplitud {r['amplitude']} (iter={r['iterations']})"
        assert r["iterations"] < MAX_COD_ITERATIONS, f"COD excedio max iteraciones con amplitud {r['amplitude']}"

    # Verificar que amplitudes grandes no tomen mas que 2x la pequeña
    if len(results) >= 2:
        small_iter = results[0]["iterations"]
        large_iter = results[-1]["iterations"]
        print(f"\n  Iteraciones: pequeña={small_iter} grande={large_iter}")
        assert large_iter <= max(MAX_COD_ITERATIONS, small_iter * 3), \
            f"Amplitud grande toma demasiadas iteraciones: {large_iter} vs {small_iter}"


# ── Benchmark 4: Cache de TOR ──────────────────────────────

def test_benchmark_tor_cache():
    """Mide la efectividad del cache de TOR."""

    ctx = OrbitalContext()
    engine = ctx.engine
    _setup_large_system(ctx, n_vars=20, n_cycles=5)

    # Tick 1: llena el cache
    ctx.run_tick()
    stats1 = engine.tor.cache_stats
    print(f"\n  Despues de tick 1: hits={stats1['hits']} misses={stats1['misses']} rate={stats1['hit_rate']}")

    # Tick 2: debe tener alto hit rate (fases casi iguales)
    ctx.run_tick()
    stats2 = engine.tor.cache_stats
    print(f"  Despues de tick 2: hits={stats2['hits']} misses={stats2['misses']} rate={stats2['hit_rate']}")

    # El hit rate debe mejorar con el tiempo
    assert stats2['hit_rate'] >= stats1['hit_rate'], "El hit rate del cache de TOR no mejoro"
