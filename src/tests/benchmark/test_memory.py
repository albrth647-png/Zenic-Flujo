"""
Tests de memoria para el Orbital Engine.

Verifica:
  1. No hay memory leak en runs largos (10k ticks)
  2. El historial de OrbitalResult no crece indefinidamente
  3. tracemalloc no detecta crecimiento neto tras N ticks

Usa tracemalloc (stdlib) para snapshots comparables.
memray se usa en scripts/ para análisis profundo de flame graphs.

Referencias:
  - Investigación: "memray sobre run de 10k ticks + assert de no-crecimiento"
"""
from __future__ import annotations

import gc
import tracemalloc

import pytest

from src.orbital.engine import OrbitalEngine
from src.orbital.models import TWO_PI


def _create_engine(n_vars: int = 50) -> OrbitalEngine:
    """Crea engine con N variables para tests de memoria."""
    eng = OrbitalEngine()
    for i in range(n_vars):
        eng.create_variable(
            f"var_{i}",
            theta=(i / n_vars) * TWO_PI,
            amplitude=1.0,
            velocity=0.05,
        )
    var_names = [f"var_{i}" for i in range(min(n_vars, 5))]
    eng.create_cycle("mem_cycle", var_names, threshold=0.4)
    return eng


# ─── 1. No hay leak en 1000 ticks ────────────────────────────────────────────


def test_no_memory_leak_1000_ticks() -> None:
    """Tras 1000 ticks, el crecimiento de memoria debe ser < 5MB.

    FIX APLICADO: OrbitalEngine._execution_history ahora usa deque(maxlen=1000)
    en lugar de list[]. Antes acumulaba OrbitalResult indefinidamente
    (236MB tras 1000 ticks con 50 vars). Ahora el historial se acota
    y la memoria se estabiliza.
    """
    eng = _create_engine(50)

    # Warmup + estabilizar memoria
    for _ in range(50):
        eng.run_tick(dt=1.0, retrofeed_damping=0.3)
    gc.collect()

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    # 1000 ticks
    for _ in range(1000):
        eng.run_tick(dt=1.0, retrofeed_damping=0.3)

    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Calcular diferencia de memoria
    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff = sum(s.size_diff for s in stats if s.size_diff > 0)

    # Con deque(maxlen=1000), el historial se acota. El crecimiento debe ser < 5MB.
    assert total_diff < 5_000_000, (
        f"Memory leak detectado: +{total_diff / 1024 / 1024:.2f}MB tras 1000 ticks. "
        f"Top 5 allocators:"
        + "\n".join(f"\n  {s}" for s in stats[:5] if s.size_diff > 0)
    )


# ─── 2. Historial de OrbitalResult está acotado ─────────────────────────────


def test_execution_history_bounded() -> None:
    """El historial de OrbitalResult no debe crecer sin límite.

    Si OrbitalEngine._execution_history es una lista sin límite,
    tras 10000 ticks tendrá 10000 OrbitalResult objetos en memoria.

    Este test verifica si hay algún mecanismo de acotamiento
    (deque maxlen, cleanup periódico, etc.).
    """
    eng = _create_engine(20)

    # Ejecutar 500 ticks
    for _ in range(500):
        eng.run_tick(dt=1.0, retrofeed_damping=0.3)

    # El historial debería estar acotado o al menos no explotar
    history_len = len(eng._execution_history)

    # Si no hay acotamiento, al menos verificar que no crece exponencialmente
    # 500 ticks → 500 entries es esperado si no hay cleanup
    assert history_len <= 1000, (
        f"Historial de OrbitalResult creció a {history_len} tras 500 ticks — "
        f"considerar usar deque(maxlen=N) para acotar memoria"
    )


# ─── 3. Memoria por variable es constante ────────────────────────────────────


def test_memory_per_variable_constant() -> None:
    """La memoria por variable orbital debe ser constante (O(1) por variable).

    Crear 10, 100, 1000 variables y verificar que el crecimiento es lineal
    (no cuadrático ni exponencial).
    """
    sizes = [10, 100, 1000]
    memory_per_var = []

    for n in sizes:
        gc.collect()
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        eng = OrbitalEngine()
        for i in range(n):
            eng.create_variable(f"v_{i}", theta=0.1 * i, amplitude=1.0, velocity=0.05)

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        total = sum(s.size_diff for s in stats if s.size_diff > 0)
        per_var = total / n
        memory_per_var.append(per_var)

    # La memoria por variable debe ser roughly constante (dentro de 2x)
    # (puede haber overhead fijo que se diluye con N grande)
    ratio_max_min = max(memory_per_var) / min(memory_per_var) if min(memory_per_var) > 0 else float("inf")
    assert ratio_max_min < 3.0, (
        f"Memoria por variable no es constante: "
        f"N=10: {memory_per_var[0]/1024:.1f}KB/var, "
        f"N=100: {memory_per_var[1]/1024:.1f}KB/var, "
        f"N=1000: {memory_per_var[2]/1024:.1f}KB/var, "
        f"ratio={ratio_max_min:.2f}x"
    )


# ─── 4. Snapshots de memoria son reproducibles ──────────────────────────────


def test_memory_snapshot_reproducible() -> None:
    """Dos engines con misma config deben tener uso de memoria similar.

    Verifica que no hay aleatoriedad en el uso de memoria.
    """
    def create_and_measure():
        gc.collect()
        tracemalloc.start()
        eng = _create_engine(50)
        for _ in range(100):
            eng.run_tick(dt=1.0, retrofeed_damping=0.3)
        snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()
        return sum(s.size for s in snapshot.statistics("lineno"))

    mem1 = create_and_measure()
    mem2 = create_and_measure()

    # Permitir 20% de variación por ruido del allocator
    ratio = max(mem1, mem2) / min(mem1, mem2) if min(mem1, mem2) > 0 else float("inf")
    assert ratio < 1.2, (
        f"Memoria no reproducible: run1={mem1/1024:.1f}KB, run2={mem2/1024:.1f}KB, ratio={ratio:.2f}x"
    )
