# HAT-ORBITAL — Guía del Módulo

> **Versión**: F0+F1 completados · 2026-06-19
> **Repo**: `src/hat/`

## ¿Qué es HAT-ORBITAL?

HAT-ORBITAL es la capa de orquestación multi-agente construida sobre el motor
determinista ORBITAL de Zenic-Flujo. Combina 5 patrones:

1. **ORBITAL Determinista** (Brouwer) como Nivel 0 — ruteo por resonancia RCC
2. **Ledger estructurado** — persistencia de Facts/Hypotheses/Plan entre sesiones
3. **FSM de desambiguación** — 4 reglas cuando ORBITAL no es concluyente
4. **Domain Supervisors** — aislamiento por dominio (Research/Build/Operate)
5. **Anti-doble-llamada** — 5 capas en cascada (Exact Match → Idempotency → TTL → Semantic → Circuit Breaker)

## Arquitectura (5 niveles)

```
N0: HATRouter (orbital_n0/tick_router.py)
    └── ORBITAL rutea por resonancia + FSM desambigua
    └── Anti-dup cascade (5 capas) cortocircuita duplicados
    └── Ledger (SQLite) persiste Facts/Hypotheses/Plan/Progress

N1: DomainSupervisor (supervisors/base.py)
    └── ResearchSupervisor (supervisors/research.py)
    └── Anti-B-05: fallback directo cuando hay 1 specialist

N2: Specialist Agents (agents/specialists/)
    └── WebResearcherSpecialist — coordina query building

N3: Worker Sub-Agents (agents/workers/)
    └── QueryBuilderWorker — expande queries con sinónimos

N4: Tools (tools/ — pendiente F2+)
    └── Reusa tools ZF (CRM, Invoice, etc.) sin MCP
```

## Endpoints API

```python
# POST /api/hat/chat
{
    "user_id": "user1",
    "session_id": "sess1",
    "message": "buscar info de python"
}
# → 200 OK
{
    "dispatch_id": "disp_abc123",
    "domain": "research",
    "response": "Generé 3 queries para búsqueda: ...",
    "orbital_resonance": 0.4143,
    "anti_dup_layer_hit": "none",
    "duration_ms": 3,
    "status": "completed"
}

# GET /api/hat/health
# → {"status": "ok", "module": "hat", "version": "f0-d7"}
```

## Anti-doble-llamada (5 capas)

| Capa | Archivo | Coste | Qué detecta |
|------|---------|-------|-------------|
| 1. Exact Match | `exact_match.py` | ~0ms (cache) | Hash idéntico completado → cache |
| 2. Idempotency | `idempotency.py` | ~3ms | Hash en ejecución → subscribe |
| 3. TTL Freshness | `ttl_freshness.py` | ~0ms (cache) | Doble-click <5s → discard |
| 4. Semantic Dedup | `semantic_dedup.py` | ~15ms | Similitud >0.85 → confirm |
| 5. Circuit Breaker | `circuit_breaker.py` | ~2ms | ≥3 fallos → fallback |

## Benchmark

- **F0**: p50=3ms, p99=4ms (objetivo: <300ms/<800ms) ✅
- **F1 anti-dup**: p50=0ms, p99=0ms (objetivo: <40ms) ✅

## Tests

```bash
# Suite HAT completa
python -m pytest src/tests/hat/ -v

# Solo anti-dup
python -m pytest src/tests/hat/test_anti_duplication.py \
  src/tests/hat/test_race_conditions.py \
  src/tests/hat/test_cache_optimization.py -v

# Benchmarks
python scripts/benchmark_hat.py --n 20
python scripts/benchmark_anti_dup.py --n 100
```

## Estructura de archivos y estado del proyecto

Ver **[PROYECTO_ESTADO.md](PROYECTO_ESTADO.md)** para el documento maestro completo
con el estado de todas las fases (F0-F5), lo implementado ✅ y lo que falta ⚪.
