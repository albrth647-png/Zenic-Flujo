# ADR-0001: Estado deprecated de `src/hat/agents_legacy/`

**Estado**: Aceptado
**Fecha**: 2026-06-22
**Fase del plan**: Fase 2 (Opción B) del PLAN_CORRECCIONES

## Contexto

Durante la auditoría profunda (sesión 4, AUDITORIA_PROFUNDA.md Parte 4) se detectó que `src/hat/agents_legacy/` (4 archivos, ~45 KB) tiene un nombre que sugiere "código muerto", pero en realidad **SÍ se usa en producción**:

- `src/api_v2/routers/agents.py:17-22` importa `AgentConfig, AgentState, BaseAgent, MultiAgentOrchestrator, AgentRuntime`
- `src/api_v2/app.py:449` importa `AgentRuntime`
- 9 archivos de tests en `src/tests/hat/` lo usan extensivamente (~15 imports)

El plan original (Fase 2 del PLAN_CORRECCIONES) proponía renombrar el módulo a `agents_runtime` para eliminar la confusión. Sin embargo, al aplicar `doubt-driven-development` y leer el `__init__.py` del propio módulo, se descubrió que **el módulo se declara oficialmente DEPRECATED**:

```python
# src/hat/agents_legacy/__init__.py (líneas 1-18)
"""HAT Agents Legacy — DEPRECATED.

Este módulo contiene el framework de agents anterior a HAT v2.
HAT v2 reemplaza esta funcionalidad con:
- Nivel 2: Supervisores (routing por dominio)
- Nivel 3: Specialists (1 responsabilidad cada uno)
- Nivel 4: Workers (auto-generados con circuit breaker)
- Nivel 5: Tools (19 tools ZF reales)

Este modulo se mantiene solo para compatibilidad con tests existentes
y el endpoint /api/v2/agents. Se eliminara en una futura version.
"""
```

Es decir, el nombre `agents_legacy` **es honesto y correcto**: el módulo ES legacy (anterior a HAT v2) y está marcado para eliminación futura.

## Decisión

**NO renombrar** el módulo. Mantener el nombre `agents_legacy` porque refleja fielmente su estado. En su lugar, documentar la deuda técnica para que futuros mantenedores tomen una decisión informada.

## Consecuencias

### Positivas
- El nombre `agents_legacy` es consistente con el docstring DEPRECATED del propio módulo
- No se desperdicia trabajo renombrando un módulo que se eliminará
- La deuda técnica queda visible y documentada (no oculta bajo un nombre "neutro")

### Negativas
- El nombre puede seguir confundiendo a nuevos desarrolladores que vean los imports en `api_v2/routers/agents.py` sin leer este ADR
- Mitigación: este ADR + el docstring del módulo + un comment en `agents.py`

### Deuda técnica registrada

Las siguientes dependencias de código deprecated deben migrarse o eliminarse en el futuro:

1. **`src/api_v2/routers/agents.py`** (249 LOC) — endpoint `/api/v2/agents/*` (spawn, orchestrate, pause, resume, run, token-usage). Usa `MultiAgentOrchestrator` y `AgentRuntime` de agents_legacy. **Ningún frontend lo llama** (auditoría sesión 4 confirmó 0 callers en `frontend/src/`). Debería migrarse a HAT v2 o eliminarse si no hay consumidores externos.

2. **`src/api_v2/app.py:449`** — import inline de `AgentRuntime` para un endpoint de health/status de agents. Misma situación que el punto 1.

3. **`src/tests/hat/`** (9 archivos: test_api_routes, test_tick_router, test_hardening, test_anti_duplication, test_e2e_f0, test_race_conditions, test_api_anti_dup, test_cards_publisher) — tests que validan el comportamiento de agents_legacy. Si se elimina el módulo, estos tests deben reescribirse contra HAT v2 o eliminarse.

## Plan de migración futuro (cuando se decida eliminar agents_legacy)

1. **Verificar consumidores externos** del endpoint `/api/v2/agents/*` (SDK, móvil, scripts) — si existen, proporcionar migración a HAT v2 equivalente
2. **Migrar o eliminar** `src/api_v2/routers/agents.py` — si HAT v2 expone funcionalidad equivalente, redirigir; si no, eliminar
3. **Reescribir tests** de `src/tests/hat/` contra HAT v2 (`bootstrap_hat`, `HATRouter`)
4. **Eliminar** `src/hat/agents_legacy/`
5. **Verificar** que HAT v2 cubre todos los casos de uso que agents_legacy cubría

## Referencias

- `AUDITORIA_PROFUNDA.md` Parte 4 — hallazgo original
- `PLAN_CORRECCIONES.md` Fase 2 — plan original (renombrar) que esta decisión reemplaza
- `src/hat/agents_legacy/__init__.py` — docstring DEPRECATED
- `src/hat/bootstrap.py` — HAT v2 (`get_hat_router`, `bootstrap_hat`)
- `src/hat/level1_orchestrator/tick_router.py` — `HATRouter` (sucesor de `MultiAgentOrchestrator`)
