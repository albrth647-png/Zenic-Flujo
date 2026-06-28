# HAT-ORBITAL — Runbook de Operación

## Health Check

```bash
curl http://localhost:8000/api/hat/health
# → {"status": "ok", "module": "hat", "version": "f0-d7"}
```

## Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/hat/chat` | POST | Procesar mensaje del usuario |
| `/api/hat/health` | GET | Health check |

## Dominios disponibles

| Dominio | Supervisor | Specialists |
|---------|------------|-------------|
| research | ResearchSupervisor | WebResearcher |
| build | BuildSupervisor | CodeGenerator, TestEngineer, DeployAgent |
| operate | OperateSupervisor | MonitorAgent, LogAnalyzer, IncidentResponder |
| clarify | (ninguno) | FSM no resolvió — pedir aclaración |

## Anti-doble-llamada

Si el endpoint responde `status: "anti_dup_blocked"`, revisar `anti_dup_layer_hit`:

| Layer | Acción | Causa |
|-------|--------|-------|
| exact_match | return_cache | Request idéntica ya completada |
| idempotency | subscribe | Request idéntica en ejecución |
| ttl_freshness | discard | Doble-click <5s |
| semantic_dedup | confirm | Request similar a reciente |
| circuit_breaker | fallback | ≥3 fallos consecutivos del dominio |

## Troubleshooting

### "database is locked"

SQLite WAL tiene contención bajo concurrencia. Soluciones:
1. Reducir concurrencia (1 worker process)
2. Migrar a Postgres (F5+)
3. Aumentar `busy_timeout` en `DatabaseManager.get_connection()`

### "domain: clarify" siempre

Las Agent Cards no están publicadas en el OVC. Solución:
```python
from src.hat.agents.specialists.web_researcher import WebResearcherSpecialist
from src.agents.base import AgentConfig
specialist = WebResearcherSpecialist(AgentConfig(name="wr"))
specialist.publish_card()  # publica en DB + OVC
```

### Latencia alta (>500ms)

1. Ejecutar benchmark: `python scripts/benchmark_hat.py --n 20`
2. Verificar que cache LRU está activo (ExactMatchLayer._cache)
3. Verificar que no hay dispatches in_progress colgados

### Reset OrbitalContext (para tests)

```python
from src.orbital.context import OrbitalContext
OrbitalContext._reset()  # recrea singleton desde cero
```

## Logs

Los logs de HAT usan el logger `src.hat.*`. Niveles:
- INFO: dispatches completados, cards publicadas, sessions cargadas
- WARNING: anti-dup bloqueos, fallback de supervisor
- ERROR: fallos de supervisor, DB errors

## Benchmarks

```bash
# HAT completo
python scripts/benchmark_hat.py --n 20
# Esperado: p50 <5ms, p99 <10ms

# Anti-dup cascade
python scripts/benchmark_anti_dup.py --n 100
# Esperado: p50 <1ms, p99 <1ms
```

## Migration

```bash
python scripts/migrate_zf_to_hat.py
# Verifica que las 7 tablas HAT existen en la DB
```
