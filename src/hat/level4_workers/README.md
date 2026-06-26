# HAT Level 4 — Workers (auto-generados, circuit breaker per-worker)

> **Versión**: 2.0 (M8 hardening completo)
> **Estado**: Production-ready — 68 tests, 10.0/10 score, 6/6 hard gates

El **Nivel 4** de HAT contiene workers auto-generados por introspección de
las tools del Nivel 5. Cada worker envuelve **un solo método** de una tool,
con circuit breaker per-worker e idempotency tracking.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                  NIVEL 4 — Workers Auto-generados               │
│                                                                 │
│  ┌─────────────────── BASE ────────────────────┐               │
│  │ ToolWorker        WorkerRegistry   Idempotency│              │
│  │ (circuit breaker  (lookup por      (sha256    │              │
│  │  per-worker)       tool+action)     hash)     │              │
│  └──────────────────────────────────────────────┘               │
│                                                                 │
│  ┌─────────── WorkerFactory ──────────────────┐                │
│  │ generate_for_tool(tool_name, tool_instance) │                │
│  │   → introspecciona métodos públicos         │                │
│  │   → crea 1 ToolWorker por método            │                │
│  │   → registra en WorkerRegistry              │                │
│  │ generate_all()                               │                │
│  │   → itera sobre ToolsRegistry (Nivel 5)     │                │
│  │   → genera ~100 workers para 19 tools       │                │
│  └─────────────────────────────────────────────┘                │
│                                                                 │
│  ┌─────────── CircuitBreakerLayer ────────────┐                │
│  │ check(domain, user_id, session_id)          │                │
│  │   → si domain tiene >=3 fallos consecutivos │                │
│  │     → retorna action='fallback'             │                │
│  └─────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Estructura

```
level4_workers/
├── __init__.py
├── circuit_breaker.py              # CircuitBreakerLayer (anti-dup nivel dominio)
├── base/
│   ├── __init__.py
│   ├── tool_worker.py              # ToolWorker (circuit breaker + idempotency)
│   ├── worker_factory.py           # WorkerFactory (auto-generación por introspección)
│   ├── registry.py                 # WorkerRegistry (lookup por tool+action)
│   └── idempotency.py              # compute_worker_hash (sha256 de tool+action+params)
├── operaciones/                    # Workers generados (vacío — se crean en runtime)
├── comunicaciones/
└── datos_auto/
```

## 🚀 Uso

### Auto-generación al startup

```python
from src.hat.level4_workers.base.worker_factory import WorkerFactory

# WorkerFactory.generate_all() introspecciona todas las tools del Nivel 5
# y crea 1 worker por método público
factory = WorkerFactory()
all_workers = factory.generate_all()
# → {"crm": {"create_lead": CrmCreateLeadWorker, "list_leads": ...},
#    "invoice": {...}, "notification": {...}, ...}

# Lookup directo por tool+action
worker = factory.get_worker("crm", "create_lead")
result = worker.run(params={"name": "Juan", "email": "juan@example.com"})
# → {"status": "completed", "action": "create_lead", "tool": "crm",
#    "result": {"id": 1, "name": "Juan"}, "params_hash": "a1b2c3d4..."}
```

### Circuit breaker per-worker

Cada `ToolWorker` tiene su propio circuit breaker:
- **closed**: estado normal, las llamadas se ejecutan.
- **open**: tras 3 fallos consecutivos, las llamadas se rechazan con `status='circuit_open'`.
- **half_open**: tras 60 segundos, se permite 1 intento de recuperación.

```python
worker = factory.get_worker("crm", "create_lead")
# Si la tool falla 3 veces seguidas:
for _ in range(3):
    worker.run()  # tool lanza excepción

# Ahora el circuit está open:
result = worker.run()
# → {"status": "circuit_open", "error": "circuit breaker open for crm.create_lead"}

# Tras 60 segundos, half-open:
# Si el próximo call tiene éxito → circuit closes.
# Si falla → circuit stays open.
```

### CircuitBreakerLayer (nivel dominio)

```python
from src.hat.level4_workers.circuit_breaker import CircuitBreakerLayer

cb = CircuitBreakerLayer(repo=ledger_repo, failure_threshold=3)
result = cb.check("operaciones", "u1", "s1")
# Si "operaciones" tiene >=3 fallos consecutivos recientes:
# → {"duplicate": True, "action": "fallback", "failure_count": 3}
# Sino:
# → {"duplicate": False, "action": "proceed"}
```

## 📊 Componentes

### ToolWorker

| Atributo | Descripción |
|----------|-------------|
| `tool_name` | Nombre de la tool (ej: `"crm"`) |
| `action_name` | Nombre del método (ej: `"create_lead"`) |
| `tool` | Instancia de la tool (Nivel 5) |
| `method` | Método bound de la tool |
| `_failure_count` | Fallos consecutivos actuales |
| `_failure_threshold` | Umbral para abrir circuit (default: 3) |
| `_circuit_open` | Si el circuit breaker está abierto |
| `_recovery_timeout` | Segundos antes de half-open (default: 60) |

| Property | Descripción |
|----------|-------------|
| `idempotency_key` | `"tool_name.action_name"` |
| `circuit_state` | `"closed"` / `"open"` / `"half_open"` |

### WorkerFactory

| Método | Descripción |
|--------|-------------|
| `generate_for_tool(tool_name, tool_instance)` | Genera workers para una tool |
| `generate_all()` | Genera para todas las tools del Nivel 5 |
| `get_worker(tool_name, action_name)` | Lookup por tool+action |
| `list_actions(tool_name)` | Actions disponibles para una tool |
| `total_count()` | Total de workers registrados |

### WorkerRegistry

| Método | Descripción |
|--------|-------------|
| `register(tool_name, action_name, worker)` | Añade worker al registry |
| `get(tool_name, action_name)` | Obtiene worker por tool+action |
| `list_actions(tool_name)` | Actions de una tool (sorted) |
| `list_tools()` | Tools con workers (sorted) |
| `list_all()` | Dict completo `{(tool, action): worker}` |

### Métodos excluidos

WorkerFactory NO genera workers para estos métodos (administrativos):

```python
_EXCLUDED_METHODS = frozenset({
    "get_tool_definition", "get_status", "configure",
    "test_connection", "configure_smtp", "configure_whatsapp",
    "get_whatsapp_status", "get_collection_info",
})
```

## 🧪 Testing

```bash
pytest tests/ -v
# 68 tests covering:
# - ToolWorker: run, circuit breaker, idempotency, error handling
# - WorkerRegistry: register, get, list_actions, list_tools, len
# - WorkerFactory: generate_for_tool, generate_all, class naming, registry integration
# - CircuitBreakerLayer: check, threshold, reset on success
# - idempotency: determinism, format, params ordering, non-serializable
```

**Cobertura**: 10.0/10 score, 6/6 hard gates.

---

**Licencia**: Propietaria — Pago Único (Zenic-Flujo v2.0.0)
