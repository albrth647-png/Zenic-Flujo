"""
ORBITAL — Benchmarks del Motor
================================

Benchmarks de rendimiento para los 5 pilares ORBITAL.
Mide tiempo de ejecución, convergencia, y throughput.

Uso:
    python -m src.orbital.benchmarks
"""

import time
import statistics
from src.orbital.ovc import OVC
from src.orbital.tor import TOR
from src.orbital.rcc import RCC
from src.orbital.cod import COD
from src.orbital.engine import OrbitalEngine


def _fmt(ns: list[float]) -> str:
    avg = statistics.mean(ns)
    s = statistics.stdev(ns) if len(ns) > 1 else 0
    return f"{avg*1000:.2f}ms ± {s*1000:.2f}ms"


class BenchORBITAL:
    """Benchmarks para el motor ORBITAL."""

    def __init__(self):
        self.results = {}

    def bench_tor_matrix(self, sizes: list[int] = [10, 25, 50, 100, 200]):
        """Mide tiempo de cálculo de matriz TOR para N variables."""
        print("\n📊 TOR — Matriz de Tensiones")
        for n in sizes:
            ovc = OVC()
            for i in range(n):
                ovc.create_variable(f"V{i}", theta=i*0.1, amplitude=10.0+(i*0.5), velocity=0.1)
            tor = TOR(ovc)
            times = []
            for _ in range(10):
                t0 = time.perf_counter()
                tor.calculate_matrix()
                times.append(time.perf_counter() - t0)
            print(f"  N={n:3d}  parejas={n*(n-1)//2:5d}  {_fmt(times)}")
            self.results[f"tor_matrix_{n}"] = times

    def bench_cod_convergence(self, sizes: list[int] = [3, 5, 8, 10, 15]):
        """Mide convergencia de COD para ciclos de N variables."""
        print("\n📊 COD — Colapso Orbital Determinista")
        for n in sizes:
            ovc = OVC()
            names = []
            for i in range(n):
                name = f"V{i}"
                ovc.create_variable(name, theta=i*0.3, amplitude=10.0, velocity=0.15)
                names.append(name)
            tor = TOR(ovc)
            rcc_ = RCC(ovc, tor)
            cycle = rcc_.register_cycle_from_names(f"Ciclo-{n}", names, threshold=0.3)
            cod = COD(ovc, tor, rcc_)
            times = []
            iterations = []
            for _ in range(5):
                t0 = time.perf_counter()
                r = cod.collapse(cycle)
                times.append(time.perf_counter() - t0)
                iterations.append(r.iterations)
            print(f"  N={n:2d}  iters={statistics.mean(iterations):.0f}  {_fmt(times)}  converged={r.converged}")
            self.results[f"cod_convergence_{n}"] = times

    def bench_cod_amplitudes(self, amplitudes: list[float] = [1, 10, 100, 1000, 10000]):
        """Mide convergencia con amplitudes extremas."""
        print("\n📊 COD — Amplitudes Extremas")
        for amp in amplitudes:
            ovc = OVC()
            ovc.create_variable("A", theta=0.0, amplitude=amp, velocity=0.2)
            ovc.create_variable("B", theta=1.0, amplitude=amp*0.8, velocity=0.15)
            ovc.create_variable("C", theta=2.0, amplitude=amp*1.2, velocity=0.1)
            tor = TOR(ovc)
            rcc_ = RCC(ovc, tor)
            cycle = rcc_.register_cycle_from_names(f"Cycle-{amp}", ["A","B","C"], threshold=0.3)
            cod = COD(ovc, tor, rcc_)
            t0 = time.perf_counter()
            r = cod.collapse(cycle)
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"  Amp={amp:6.0f}  iters={r.iterations:4d}  converged={r.converged}  delta={r.convergence_delta:.8f}  {elapsed:.2f}ms")
            self.results[f"cod_amp_{amp}"] = elapsed

    def bench_engine_throughput(self, variables: int = 10, cycles: int = 3, ticks: int = 50):
        """Mide throughput del motor completo (ticks/segundo)."""
        print(f"\n📊 OrbitalEngine — Throughput ({variables} vars, {cycles} cycles, {ticks} ticks)")
        engine = OrbitalEngine()
        for i in range(variables):
            engine.create_variable(f"V{i}", theta=i*0.2, amplitude=20.0+(i*0.5), velocity=0.1+(i*0.02))
        for c in range(cycles):
            names = [f"V{i}" for i in range(c*3, min(c*3+3, variables))]
            if len(names) >= 2:
                engine.create_cycle(f"Cycle-{c}", names, threshold=0.3)
        t0 = time.perf_counter()
        results = engine.run_ticks(ticks)
        elapsed = time.perf_counter() - t0
        tps = ticks / elapsed
        converged = sum(1 for r in results for c in r.cod_results if c.converged)
        print(f"  {ticks} ticks en {elapsed:.2f}s = {tps:.1f} ticks/s")
        print(f"  Convergencias COD: {converged}/{sum(len(r.cod_results) for r in results)}")
        self.results["engine_throughput"] = tps

    def bench_tor_cache_efficiency(self, n: int = 50, iterations: int = 100):
        """Mide eficiencia del cache TOR."""
        print(f"\n📊 TOR — Cache Efficiency ({n} vars, {iterations} iterations)")
        ovc = OVC()
        for i in range(n):
            ovc.create_variable(f"V{i}", theta=i*0.1, amplitude=10.0, velocity=0.1)
        tor = TOR(ovc)
        # Warmup
        for _ in range(5):
            tor.calculate_matrix()
        tor.clear_cache()
        timestamps = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            tor.calculate_matrix()
            timestamps.append(time.perf_counter() - t0)
        stats_data = tor.cache_stats
        print(f"  Cache hits: {stats_data['hits']}  misses: {stats_data['misses']}  rate: {stats_data['hit_rate']:.1%}")
        print(f"  Avg time: {statistics.mean(timestamps)*1000:.3f}ms")
        self.results["tor_cache"] = stats_data

    def run_all(self):
        """Ejecuta todos los benchmarks."""
        print("=" * 60)
        print("ORBITAL — Benchmark Suite v3.2")
        print("=" * 60)
        self.bench_tor_matrix()
        self.bench_cod_convergence()
        self.bench_cod_amplitudes()
        self.bench_tor_cache_efficiency()
        self.bench_engine_throughput()
        print("\n" + "=" * 60)
        print("Benchmarks completados.")
        print("=" * 60)
        return self.results


if __name__ == "__main__":
    bench = BenchORBITAL()
    bench.run_all()
