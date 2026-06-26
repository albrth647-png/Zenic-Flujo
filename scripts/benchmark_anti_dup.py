#!/usr/bin/env python3
"""
Benchmark Anti-Doble-Llamada F1-D2.

Mide latencia p50/p99 del AntiDuplicationCascade.check() con N calls.
Objetivo DoD F1: p99 < 40ms.

Uso:
    python scripts/benchmark_anti_dup.py [--n 100] [--output report.json] [--markdown report.md]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.hat.anti_duplication.cascade import AntiDuplicationCascade
from src.hat.ledger.repository import LedgerRepository


def run_benchmark(n: int) -> dict[str, Any]:
    """Ejecuta N calls al cascade y mide latencia.

    Args:
        n: Número de calls a ejecutar.

    Returns:
        Dict con métricas: latencies_ms, p50, p99, mean, min, max, success_rate.
    """
    repo = LedgerRepository()
    cascade = AntiDuplicationCascade(repo=repo)
    messages = [
        "buscar python", "buscar javascript", "investigar rust",
        "encontrar info de react", "buscar documentación de django",
    ]

    latencies: list[int] = []
    blocked_count = 0

    for i in range(n):
        user_id = f"bench_user_{i}"
        session_id = f"bench_sess_{i}"
        message = messages[i % len(messages)]
        intent_hash = f"hash_{i}_{hash(message)}"

        start = time.monotonic()
        try:
            result = cascade.check(
                intent_hash=intent_hash,
                user_id=user_id,
                session_id=session_id,
                message=message,
                domain="research",
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            latencies.append(elapsed_ms)
            if result.get("duplicate"):
                blocked_count += 1
        except (sqlite3.Error, RuntimeError, ValueError):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            latencies.append(elapsed_ms)

    return _build_result(n, latencies, blocked_count)


def _build_result(
    n: int, latencies: list[int], blocked_count: int,
) -> dict[str, Any]:
    """Construye el dict de resultados del benchmark.

    Args:
        n: Total de requests.
        latencies: Lista de latencias en ms.
        blocked_count: Requests bloqueadas por anti-dup.

    Returns:
        Dict con todas las métricas.
    """
    if not latencies:
        return {"error": "no latencies collected"}
    latencies_sorted = sorted(latencies)
    p50_idx = max(0, len(latencies_sorted) // 2)
    p99_idx = max(0, int(len(latencies_sorted) * 0.99) - 1)
    return {
        "n_requests": n,
        "latencies_ms": latencies_sorted,
        "p50_ms": latencies_sorted[p50_idx],
        "p99_ms": latencies_sorted[p99_idx],
        "mean_ms": int(statistics.mean(latencies)),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "stdev_ms": int(statistics.stdev(latencies)) if len(latencies) > 1 else 0,
        "blocked_count": blocked_count,
        "block_rate": round(blocked_count / n, 4),
        "timestamp": datetime.now(UTC).isoformat(),
    }


def generate_markdown_report(benchmark: dict[str, Any]) -> str:
    """Genera un reporte markdown a partir de los resultados.

    Args:
        benchmark: Dict retornado por run_benchmark().

    Returns:
        String con el reporte en markdown.
    """
    p99 = benchmark["p99_ms"]
    p99_pass = p99 < 40
    return f"""# 📊 F1-D2 Benchmark Report — Anti-Doble-Llamada

> **Fecha**: {benchmark["timestamp"]}
> **Requests**: {benchmark["n_requests"]}

## Métricas de latencia del cascade

| Métrica | Valor | Objetivo DoD F1 | ¿Cumple? |
|---------|-------|-----------------|----------|
| **p50** | {benchmark["p50_ms"]}ms | — | — |
| **p99** | {p99}ms | < 40ms | {'✅ SÍ' if p99_pass else '❌ NO'} |
| **media** | {benchmark["mean_ms"]}ms | — | — |
| **min** | {benchmark["min_ms"]}ms | — | — |
| **max** | {benchmark["max_ms"]}ms | — | — |
| **stdev** | {benchmark["stdev_ms"]}ms | — | — |

## Tasa de bloqueo anti-dup

| Métrica | Valor |
|---------|-------|
| **Bloqueadas** | {benchmark["blocked_count"]}/{benchmark["n_requests"]} |
| **Tasa bloqueo** | {benchmark["block_rate"] * 100:.1f}% |

## Veredicto DoD F1

> "p99 < 40ms"

**Resultado**: {'✅ CUMPLE' if p99_pass else '❌ NO CUMPLE'}
"""


def main() -> int:
    """Entry point del script de benchmark anti-dup."""
    parser = argparse.ArgumentParser(description="Benchmark Anti-Doble-Llamada F1-D2")
    parser.add_argument("--n", type=int, default=50, help="Número de calls (default: 50)")
    parser.add_argument("--output", type=str, default=None, help="Archivo JSON de salida")
    parser.add_argument("--markdown", type=str, default=None, help="Archivo markdown de salida")
    args = parser.parse_args()

    print(f"Ejecutando benchmark anti-dup con N={args.n}...")
    benchmark = run_benchmark(args.n)

    print("\n=== Resultados ===")
    print(f"p50: {benchmark['p50_ms']}ms")
    print(f"p99: {benchmark['p99_ms']}ms")
    print(f"media: {benchmark['mean_ms']}ms")
    print(f"bloqueadas: {benchmark['blocked_count']}/{benchmark['n_requests']}")

    if args.output:
        Path(args.output).write_text(json.dumps(benchmark, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON guardado en: {args.output}")

    markdown = generate_markdown_report(benchmark)
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
        print(f"Markdown guardado en: {args.markdown}")
    else:
        print("\n" + markdown)

    return 0 if benchmark["p99_ms"] < 40 else 1


if __name__ == "__main__":
    sys.exit(main())
