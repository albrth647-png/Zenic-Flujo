#!/usr/bin/env python3
"""
Benchmark HAT-ORBITAL F0 (F0-D8).

Mide latencia p50/p99 del HATRouter.handle() con N requests sintéticas.
Genera un reporte JSON + markdown con los resultados.

Uso:
    python scripts/benchmark_hat.py [--n 50] [--output /path/to/report.json]

Resultados esperados (DoD F0 #8):
    - p50 < 300ms
    - p99 < 800ms
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Asegurar que el repo root está en sys.path ANTES de imports de src.*
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.base import AgentConfig
from src.agents.orchestrator import MultiAgentOrchestrator
from src.hat.agents.specialists.web_researcher import WebResearcherSpecialist
from src.hat.agents.workers.query_builder import QueryBuilderWorker
from src.hat.ledger.ovc_bridge import OVCLedgerBridge
from src.hat.ledger.repository import LedgerRepository
from src.hat.orbital_n0.tick_router import HATRouter
from src.orbital.context import OrbitalContext


def setup_router() -> HATRouter:
    """Configura el HATRouter con Agent Cards publicadas."""
    OrbitalContext._reset()
    MultiAgentOrchestrator.reset_instance()

    repo = LedgerRepository()
    ctx = OrbitalContext()
    bridge = OVCLedgerBridge(repo=repo, ctx=ctx)

    specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
    specialist.publish_card(repo=repo, ctx=ctx)
    worker = QueryBuilderWorker(AgentConfig(name="qb"))
    worker.publish_card(repo=repo, ctx=ctx)

    return HATRouter(ledger=repo, ctx=ctx, bridge=bridge)


def run_benchmark(n: int) -> dict[str, Any]:
    """Ejecuta N requests sintéticas y mide latencia.

    Args:
        n: Número de requests a ejecutar.

    Returns:
        Dict con: latencies_ms, p50, p99, mean, min, max, success_rate.
    """
    router = setup_router()
    messages = [
        "buscar info de python",
        "buscar javascript",
        "buscar documentación de react",
        "investigar framework django",
        "encontrar info sobre rust",
    ]

    latencies: list[int] = []
    successes = 0
    failures: list[str] = []

    for i in range(n):
        message = messages[i % len(messages)]
        elapsed_ms, success, failure = _execute_single_request(router, i, message)
        latencies.append(elapsed_ms)
        if success:
            successes += 1
        if failure:
            failures.append(failure)

    return _build_benchmark_result(n, latencies, successes, failures)


def _execute_single_request(
    router: HATRouter, iteration: int, message: str,
) -> tuple[int, bool, str | None]:
    """Ejecuta una request y retorna (elapsed_ms, success, failure_msg).

    Args:
        router: HATRouter ya configurado.
        iteration: Índice de la iteración (para IDs únicos).
        message: Mensaje a enviar.

    Returns:
        Tupla (latencia_ms, fue_exito, mensaje_fallo_o_None).
    """
    user_id = f"bench_user_{iteration}"
    session_id = f"bench_sess_{iteration}"
    start = time.monotonic()
    try:
        result = router.handle(user_id, session_id, message)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.get("status") in ("completed", "clarify"):
            return elapsed_ms, True, None
        return elapsed_ms, False, f"iter {iteration}: status={result.get('status')}"
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return elapsed_ms, False, f"iter {iteration}: {type(exc).__name__}: {exc}"


def _build_benchmark_result(
    n: int, latencies: list[int], successes: int, failures: list[str],
) -> dict[str, Any]:
    """Construye el dict final de resultados del benchmark.

    Args:
        n: Número total de requests.
        latencies: Lista de latencias en ms.
        successes: Conteo de éxitos.
        failures: Lista de mensajes de fallo.

    Returns:
        Dict con todas las métricas del benchmark.
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
        "success_count": successes,
        "failure_count": len(failures),
        "success_rate": round(successes / n, 4),
        "failures_sample": failures[:5],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def generate_markdown_report(benchmark: dict[str, Any]) -> str:
    """Genera un reporte markdown a partir de los resultados del benchmark.

    Args:
        benchmark: Dict retornado por run_benchmark().

    Returns:
        String con el reporte en markdown.
    """
    p50 = benchmark["p50_ms"]
    p99 = benchmark["p99_ms"]
    p50_pass = p50 < 300
    p99_pass = p99 < 800

    return f"""# 📊 F0 Benchmark Report — HAT-ORBITAL

> **Fecha**: {benchmark["timestamp"]}
> **Requests**: {benchmark["n_requests"]}

## Métricas de latencia

| Métrica | Valor | Objetivo DoD F0 | ¿Cumple? |
|---------|-------|-----------------|----------|
| **p50** | {p50}ms | < 300ms | {'✅ SÍ' if p50_pass else '❌ NO'} |
| **p99** | {p99}ms | < 800ms | {'✅ SÍ' if p99_pass else '❌ NO'} |
| **media** | {benchmark["mean_ms"]}ms | — | — |
| **min** | {benchmark["min_ms"]}ms | — | — |
| **max** | {benchmark["max_ms"]}ms | — | — |
| **stdev** | {benchmark["stdev_ms"]}ms | — | — |

## Tasa de éxito

| Métrica | Valor |
|---------|-------|
| **Exitosos** | {benchmark["success_count"]}/{benchmark["n_requests"]} |
| **Fallidos** | {benchmark["failure_count"]} |
| **Tasa éxito** | {benchmark["success_rate"] * 100:.1f}% |

## Veredicto DoD F0 #8

> "Latencia p50 < 300ms, p99 < 800ms"

**Resultado**: {'✅ CUMPLE' if (p50_pass and p99_pass) else '❌ NO CUMPLE'}

"""


def main() -> int:
    """Entry point del script de benchmark."""
    parser = argparse.ArgumentParser(description="Benchmark HAT-ORBITAL F0")
    parser.add_argument(
        "--n", type=int, default=20,
        help="Número de requests sintéticas (default: 20)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Archivo JSON de salida (default: stdout)",
    )
    parser.add_argument(
        "--markdown", type=str, default=None,
        help="Archivo markdown de salida (default: stdout)",
    )
    args = parser.parse_args()

    print(f"Ejecutando benchmark con N={args.n}...")
    benchmark = run_benchmark(args.n)

    print("\n=== Resultados ===")
    print(f"p50: {benchmark['p50_ms']}ms")
    print(f"p99: {benchmark['p99_ms']}ms")
    print(f"media: {benchmark['mean_ms']}ms")
    print(f"éxito: {benchmark['success_count']}/{benchmark['n_requests']}")

    if args.output:
        Path(args.output).write_text(
            json.dumps(benchmark, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nJSON guardado en: {args.output}")

    markdown = generate_markdown_report(benchmark)
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
        print(f"Markdown guardado en: {args.markdown}")
    else:
        print("\n" + markdown)

    # Exit code: 0 si p50 < 300 y p99 < 800, 1 si no
    if benchmark["p50_ms"] < 300 and benchmark["p99_ms"] < 800:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
