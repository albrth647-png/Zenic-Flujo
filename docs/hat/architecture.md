# HAT-ORBITAL — Arquitectura

> **Versión**: F5 Release · 2026-06-19

## Visión general

HAT-ORBITAL es la capa de orquestación multi-agente construida sobre el motor
determinista ORBITAL de Zenic-Flujo. ORBITAL es el orquestador principal;
todo lo demás (Ledger, Supervisors, Anti-dup) son módulos que sirven a ORBITAL.

## 5 Niveles

```
N0: HATRouter (orbital_n0/tick_router.py)
    ├── ORBITAL rutea por resonancia RCC entre user_intent y Agent Cards
    ├── FSM desambigua cuando ORBITAL no es concluyente (4 reglas)
    ├── Anti-dup cascade (5 capas) cortocircuita duplicados
    └── Ledger (SQLite WAL) persiste Facts/Hypotheses/Plan/Progress

N1: DomainSupervisor (supervisors/base.py)
    ├── ResearchSupervisor → 1 specialist (fallback directo)
    ├── BuildSupervisor → 3 specialists (HIERARCHICAL)
    └── OperateSupervisor → 3 specialists (HIERARCHICAL)

N2: Specialist Agents (agents/specialists/)
    ├── WebResearcherSpecialist → coordina QueryBuilder
    ├── CodeGeneratorSpecialist → coordina CodeWriter
    ├── TestEngineerSpecialist → coordina TestRunner
    ├── DeployAgentSpecialist → coordina ContainerBuilder
    ├── MonitorAgentSpecialist → coordina MetricsScraper
    ├── LogAnalyzerSpecialist → coordina LogFilter
    └── IncidentResponderSpecialist → coordina AlertDispatcher

N3: Worker Sub-Agents (agents/workers/)
    └── 7 workers atómicos (1-3 tools cada uno)

N4: Tools (tools/ — pendiente)
    └── Reusa tools ZF (CRM, Invoice, etc.) sin MCP
```

## Total: 21 agentes

3 dominios × (1 supervisor + 3 specialists + 3 workers) = 21 agentes.
Research tiene 1 specialist (F0 MVP); Build y Operate tienen 3 cada uno.

## Flujo end-to-end

```
Usuario → POST /api/hat/chat
    │
    ▼
HATRouter.handle(user_id, session_id, message)
    │
    ├── 1. compute_intent_hash(sha256)
    ├── 2. Anti-dup cascade (5 capas en cascada)
    │      ├── Exact Match (cache LRU 256) → return_cache si hit
    │      ├── Idempotency → subscribe si in_progress
    │      ├── TTL Freshness (cache sesión) → discard si <5s
    │      ├── Semantic Dedup (Jaccard >0.85) → confirm
    │      └── Circuit Breaker (≥3 fallos) → fallback
    ├── 3. OVCLedgerBridge.load_session() → variables OVC
    ├── 4. _route_by_orbital(message) → top-3 dominios por RCC
    ├── 5. fsm_disambiguate(top3, message, active_domain)
    ├── 6. DomainSupervisor.handle(subtask)
    │      └── HIERARCHICAL o fallback directo
    ├── 7. complete_dispatch() + persist_session()
    └── 8. _synthesize_response() → HATResponse JSON
```

## 7 tablas Ledger (SQLite WAL)

| Tabla | Propósito |
|-------|-----------|
| hat_facts | Hechos confirmados (θ=0 en OVC) |
| hat_hypotheses | Creencias no verificadas (θ=π/4 en OVC) |
| hat_plan | Próximos N pasos planificados |
| hat_progress | Historial de despachos ejecutados |
| hat_dispatch_registry | Anti-doble-llamada (hash → status, cache, ttl) |
| hat_agent_cards | Capacidades declaradas por cada agente |
| hat_sessions | Metadata de cada sesión de usuario |

## Bugs heredados fixeados

| Bug | Fix | Fase |
|-----|-----|------|
| B-01 | CompileResult.nlu_result + fallback type confusion | F0 |
| B-05 | DomainSupervisor guard para 1 specialist | F0 |
| BUG-W5 | OrbitalEngine.reset() preserva pilares | F4 |
