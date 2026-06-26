# HAT Level 1 — Orquestador Central Orbital

> **Versión**: 2.0 (M8 hardening completo)
> **Estado**: Production-ready — 261 tests, 10.0/10 score, 6/6 hard gates

El **Nivel 1** de HAT es el punto de entrada único al sistema HAT-ORBITAL. Contiene
el `HATRouter` (orquestador central), el sistema anti-doble-llamada de 3 capas, el
Ledger de memoria entre sesiones, y el routing por resonancia ORBITAL + FSM de
desambiguación.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                    NIVEL 1 — HATRouter                          │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Intent    │  │     FSM     │  │      Anti-Dup           │ │
│  │  Hasher +   │  │ Disambig. + │  │   Cascade (3 capas)     │ │
│  │  Normalizer │  │   States    │  │ exact → idemp → ttl     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Routing (M8)                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │   Orbital    │  │   Keyword    │  │   Facade     │  │   │
│  │  │   Router     │  │   Router     │  │   (__init__) │  │   │
│  │  │  (resonancia)│  │  (override + │  │ route_msg()  │  │   │
│  │  │              │  │   FSM deleg.)│  │  helper      │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Ledger (M9)                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ Repository   │  │ FactsManager │  │ OVC ↔ Ledger │  │   │
│  │  │  (CRUD 3     │  │  (business   │  │   Bridge     │  │   │
│  │  │   tablas)    │  │   logic)     │  │ (sync OVC ↔  │  │   │
│  │  │              │  │              │  │  SQLite)     │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────┐                      ┌─────────────────────┐  │
│  │Observability│                      │       API v2        │  │
│  │  (Dispatch  │                      │  (FastAPI routes)   │  │
│  │   Tracer)   │                      │  /chat /health      │  │
│  └─────────────┘                      └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Estructura del módulo

```
level1_orchestrator/
├── tick_router.py              # HATRouter — entry point principal
├── __init__.py                 # Exports públicos
├── fsm/
│   ├── disambiguator.py        # FSM 4 reglas (clear/active/keyword/clarify)
│   └── states.py               # 6 estados como variables orbitales
├── intent/
│   ├── hasher.py               # sha256(user|session|normalized_intent|params)
│   └── normalizer.py           # lowercase + sin acentos + sin puntuación
├── anti_duplication/
│   ├── cascade.py              # Orquestador de 3 capas
│   ├── exact_match.py          # Capa 1: hash ya completado → cache
│   ├── idempotency.py          # Capa 2: hash en progreso → subscribe
│   └── ttl_freshness.py        # Capa 3: mismo hash <2s → discard
├── routing/                    # M8: routing extraído a módulo propio
│   ├── __init__.py             # Facade + route_message() helper
│   ├── orbital_router.py       # Routing por resonancia ORBITAL (top-3)
│   ├── keyword_router.py       # Keyword override + FSM delegada
│   └── keywords.py             # Constantes DOMAIN_KEYWORDS
├── ledger/
│   ├── repository.py           # CRUD sobre 3 tablas SQLite
│   ├── facts_manager.py        # Capa de negocio (validación, atajos)
│   ├── ovc_bridge.py           # Sync OVC ↔ SQLite (load/persist session)
│   └── schema.sql              # DDL: hat_facts, hat_hypotheses, hat_progress
├── observability/
│   └── dispatch_tracer.py      # OpenTelemetry spans (no-op fallback)
└── api/
    └── routes.py               # FastAPI: POST /chat, GET /health
```

## 🚀 Uso

### Punto de entrada público

```python
from src.hat import bootstrap_hat

# Inicializa los 5 niveles (Tools → Workers → Specialists → Supervisors → HATRouter)
hat_router = bootstrap_hat(event_bus=event_bus)

# Procesa un mensaje del usuario
result = hat_router.handle(
    user_id="user1",
    session_id="session1",
    message="listar leads",
)
print(result["domain"])    # "operaciones"
print(result["response"])  # "Resultado: Juan, Maria, Carlos..."
print(result["status"])    # "completed"
```

### API REST

```bash
# Health check
curl http://localhost:8000/api/hat/health
# → {"status": "ok", "module": "hat", "version": "f0-d7"}

# Chat con HAT
curl -X POST http://localhost:8000/api/hat/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "u1",
    "session_id": "s1",
    "message": "listar leads"
  }'
```

### Routing por separado (para testing)

```python
from src.hat.level1_orchestrator.routing import route_message
from src.orbital.context import OrbitalContext

ctx = OrbitalContext()
domain, top3 = route_message(
    ctx=ctx,
    session_id="s1",
    message="enviar email al cliente",
    active_domain="operaciones",
)
# domain = "comunicaciones" (keyword override de M10.1)
# top3 = [("operaciones", 0.5), ("comunicaciones", 0.45), ...]
```

## 🔄 Flujo end-to-end del `HATRouter.handle()`

```
1. dispatch_id = "disp_" + uuid4().hex[:12]
2. intent_hash = sha256(user|session|normalize(message)|sorted(params))
3. _set_current_session(session_id)   → namespacing OVC
4. bridge.load_session(user, session) → carga Facts + Hypotheses al OVC

5. top3 = orbital_router.route(message)
   a. Crea variable OVC hat_<session>__user_intent_current
   b. Recopila Agent Cards por dominio (metadata.type='agent_card')
   c. Para cada dominio: TOR(intent, card) promedio normalizado
   d. Retorna top-3 (domain, resonance)

6. active_domain = ledger.get_fact(user, session, "active_domain")
7. keyword_router.set_active_domain(active_domain)
8. domain = keyword_router.disambiguate(top3, message)
   a. Keyword override (M10.1): si mensaje tiene keyword de dominio en top3 → ese
   b. Sino: fsm_disambiguate(top3, message, active_domain)
      - Clear winner (diff > 0.15) → top1
      - Active domain en top2 → active
      - Keyword match en top2 → ese
      - Sino → 'clarify'

9. anti_dup_result = cascade.check(intent_hash, user, session, message, domain)
   - Capa 1 (exact_match): hash ya completado → return_cache
   - Capa 2 (idempotency): hash en progreso → subscribe
   - Capa 3 (ttl_freshness): mismo hash <2s → discard
   - Si duplicate → return respuesta anti-dup (cortocircuito)

10. ledger.register_dispatch(intent_hash, user, session, domain)
11. supervisor_result = supervisor.handle(subtask)
12. ledger.complete_dispatch(intent_hash, supervisor_result, "completed")
13. bridge.persist_session(user, session)   → snapshot OVC → SQLite
14. Sintetizar respuesta legible al usuario
```

## 🛡️ Anti-doble-llamada (Cascade de 3 capas)

| Capa | Archivo | Coste | Qué detecta | Acción |
|------|---------|-------|-------------|--------|
| 1 | `exact_match.py` | ~1ms | Hash ya completado | `return_cache` |
| 2 | `idempotency.py` | ~3ms | Hash en progreso | `subscribe` |
| 3 | `ttl_freshness.py` | <1ms | Mismo hash <2s | `discard` |

**Probabilidad de doble despacho**: <0.01%
**Coste total peor caso**: ~5ms

## 📊 Ledger (3 tablas SQLite, reducidas de 7 en M9)

| Tabla | Propósito | θ en OVC |
|-------|-----------|----------|
| `hat_facts` | Hechos confirmados (ej: `active_domain`) | 0.0 (alta confianza) |
| `hat_hypotheses` | Creencias no verificadas | π/4 (confianza media) |
| `hat_progress` | Historial de despachos + intent_hash + ttl | — |

## 🧪 Testing

```bash
# Tests del Nivel 1 completo
pytest tests/ -v

# Solo routing
pytest tests/test_orbital_router.py tests/test_keyword_router.py -v

# Solo anti-dup
pytest tests/test_anti_dup_cascade.py tests/test_anti_dup_layers.py -v

# Coverage
pytest --cov=level1_orchestrator --cov-branch --cov-report=html tests/
```

**Cobertura actual**: 261 tests, 98.67% en `facts_manager.py`, 6/6 hard gates pasando.

## 🔒 Seguridad

- **HATRouter singleton**: `api/routes.py` usa `get_hat_router()` en vez de
  instanciar por request (evita crear Ledgers/Contextos duplicados).
- **Sin eval/exec**: AST scan automático en CI (hard gate `no_security_issues`).
- **Sin secrets en código**: `detect-secrets` escanea todos los archivos.
- **Env sanitization**: el sandbox v4 stripa siempre `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, etc.
- **HTTPException re-raise**: errores HTTP no se envuelven en 500
  (evita info leak del traceback).

## 🔧 Configuración

### Constantes ajustables

| Constante | Default | Archivo | Descripción |
|-----------|---------|---------|-------------|
| `DISAMBIGUATION_THRESHOLD` | 0.15 | `fsm/disambiguator.py` | Diff top1-top2 para clear winner |
| `DEFAULT_TTL_SECONDS` | 2 | `anti_duplication/ttl_freshness.py` | Ventana anti doble-click |
| `TOP_N_DOMAINS` | 3 | `routing/orbital_router.py` | Cuántos dominios retorna el routing |
| `INTENT_AMPLITUDE` | 1.0 | `routing/orbital_router.py` | Amplitud OVC del user_intent |
| `FACT_THETA` | 0.0 | `ledger/facts_manager.py` | θ de Facts (no orbitan) |
| `HYPOTHESIS_THETA` | π/4 | `ledger/facts_manager.py` | θ de Hypotheses |

### Dominios canónicos (M8)

- `operaciones` — CRM, Invoice, Inventory
- `comunicaciones` — Notification, Email, Chat
- `datos_auto` — Data, Api, Code

## 📈 Métricas

| Métrica | Valor |
|---------|-------|
| Tests | 261 |
| Coverage (facts_manager) | 98.67% |
| Hard gates | 6/6 |
| Soft score | 10.0/10 |
| LOC (código) | ~1,700 |
| LOC (tests) | ~1,800 |
| Módulos | 9 (fsm, intent, anti_dup, routing, ledger, observability, api, + tick_router) |

## 🔗 Dependencias

### Internas
- `src.orbital.context.OrbitalContext` — Singleton del motor ORBITAL (5 pilares).
- `src.hat.level2_supervisors.*` — 3 supervisores del Nivel 2.
- `src.hat.level3_specialists.*` — 9 specialists del Nivel 3.
- `src.core.db.sqlite_manager.DatabaseManager` — Singleton SQLite.

### Externas
- `fastapi` — API REST.
- `pydantic` — Validación de request/response.
- `opentelemetry` (opcional) — Tracing distribuido.

## 📚 Referencias

- `IMPLEMENTATION_PLAN.md` — Plan maestro M1-M10.
- `ARCHITECTURE.md` — Arquitectura HAT-ORBITAL v2.
- `FASE1_ERRORES_REPORT.md` — Reporte de bugs (ya cerrados en este hardening).
- `docs/hat/QUICKSTART.md` — Quickstart para desarrolladores.

---

**Licencia**: Propietaria — Pago Único (Zenic-Flujo v2.0.0)
