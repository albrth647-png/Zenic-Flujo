# HAT-ORBITAL — Migration Guide (ZF → HAT)

## Qué migra

La migración de Zenic-Flujo (ZF) a HAT-ORBITAL añade las 7 tablas HAT a la
DB SQLite existente. **No modifica tablas existentes de ZF** — HAT convive
con ZF en la misma DB.

## Script de migración

```bash
python scripts/migrate_zf_to_hat.py
```

El script:
1. Verifica que la DB de ZF existe
2. Crea las 7 tablas HAT (`hat_*`) si no existen
3. Verifica que `src/hat/` está instalado
4. Reporta tablas creadas/verificadas

## Tablas HAT (nuevas)

| Tabla | Propósito |
|-------|-----------|
| `hat_facts` | Facts confirmados del Ledger |
| `hat_hypotheses` | Hipótesis no verificadas |
| `hat_plan` | Plan de pasos futuros |
| `hat_progress` | Historial de despachos |
| `hat_dispatch_registry` | Anti-doble-llamada |
| `hat_agent_cards` | Capacidades de agentes |
| `hat_sessions` | Metadata de sesiones |

## Tablas ZF (existentes, no modificadas)

Todas las tablas existentes de ZF (`users`, `workflows`, `executions`, etc.)
permanecen sin cambios. HAT las lee vía `DatabaseManager` singleton pero no
escribe en ellas.

## Compatibilidad

- HAT y ZF pueden correr simultáneamente
- El endpoint `/api/hat/chat` es nuevo (no afecta endpoints ZF existentes)
- `WorkflowEngine` de ZF sigue funcionando independientemente
- `OrbitalContext` singleton es compartido entre ZF y HAT (namespacing por prefijo)

## Rollback

Para revertir HAT (sin afectar ZF):

```sql
DROP TABLE IF EXISTS hat_facts;
DROP TABLE IF EXISTS hat_hypotheses;
DROP TABLE IF EXISTS hat_plan;
DROP TABLE IF EXISTS hat_progress;
DROP TABLE IF EXISTS hat_dispatch_registry;
DROP TABLE IF EXISTS hat_agent_cards;
DROP TABLE IF EXISTS hat_sessions;
```

## Post-migración

1. Verificar health: `curl http://localhost:8000/api/hat/health`
2. Test E2E: `curl -X POST http://localhost:8000/api/hat/chat -d '{"user_id":"test","session_id":"s1","message":"buscar python"}' -H "Content-Type: application/json"`
3. Ejecutar benchmark: `python scripts/benchmark_hat.py --n 20`
