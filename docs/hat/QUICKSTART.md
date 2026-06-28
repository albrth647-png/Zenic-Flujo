# 🚀 HAT-ORBITAL Quickstart

## ¿Qué es HAT?

HAT (Híbrida Actor + Three-capas-memory) es la arquitectura de orquestación de Zenic-Flujo. Combina:
- **Motor ORBITAL determinista** (5 pilares: OVC → TOR → RCC → COD → Espectro)
- **5 niveles de orquestación** (HATRouter → Supervisores → Specialists → Workers → Tools)
- **Memoria estructurada** (Ledger con Facts, Hypotheses, Progress)

## Arquitectura de 5 niveles

```
NIVEL 1 — HATRouter (Orquestador central Orbital)
    ↓
NIVEL 2 — 3 sub-orquestadores (operaciones, comunicaciones, datos_auto)
    ↓
NIVEL 3 — 9 specialists (1 responsabilidad cada uno)
    ↓
NIVEL 4 — 101 workers (auto-generados, más extenso que N3)
    ↓
NIVEL 5 — 19 tools ZF reales (base final)
```

## Inicialización

```python
from src.events.bus import EventBus
from src.hat import bootstrap_hat

# Inicializa los 5 niveles
hat_router = bootstrap_hat(event_bus=EventBus())
```

## Procesar un mensaje

```python
result = hat_router.handle(
    user_id="user1",
    session_id="session1",
    message="listar leads",
)

print(result["domain"])    # "operaciones"
print(result["status"])    # "completed"
print(result["response"])  # "[{'id': 1, 'name': 'Juan', ...}]"
```

## API REST

```bash
# HAT API (FastAPI, port 8000)
curl -X POST http://localhost:8000/api/hat/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","session_id":"s1","message":"listar leads"}'

# Web Chat (Flask, port 8080)
curl -X POST http://localhost:8080/api/workflows/chat \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{"message":"listar leads"}'
```

## Añadir una tool nueva

1. Crear la tool en `src/hat/level5_tools/<categoria>/`
2. Añadir 1 entrada en `src/hat/level5_tools/registry.py`:
```python
ToolRegistration(
    name="mi_tool",
    domain="operaciones",
    category="business",
    import_path="src.hat.level5_tools.business.mi_tool.service",
    class_name="MiToolService",
)
```
3. Reiniciar — WorkerFactory genera workers automáticamente, SpecialistFactory crea specialist, AgentCard se publica

## Dominios disponibles

| Dominio | Supervisor | Specialists | Tools |
|---|---|---|---|
| operaciones | OperacionesSupervisor | CRM, Invoice, Inventory | crm, invoice, inventory, stripe, mercadopago |
| comunicaciones | ComunicacionesSupervisor | Notification, Email, Chat | notification, gmail, slack, telegram |
| datos_auto | DatosAutoSupervisor | Data, Api, Code | data_keeper, api_connector, sheets, drive, postgresql, code_runner, logic_gate, autopilot, openai, ollama |

## Anti-doble-llamada (3 capas)

1. **Exact Match** — hash idéntico ya completado → devuelve cache
2. **Idempotency** — hash en ejecución → suscríbete
3. **TTL Freshness** — mismo hash <2s → descarta

## Ledger (3 tablas SQLite)

- `hat_facts` — Hechos confirmados (θ=0 en OVC)
- `hat_hypotheses` — Creencias no verificadas (θ=π/4 en OVC)
- `hat_progress` — Historial de despachos + intent_hash + TTL

## Métricas

```
GET /metrics  — Prometheus scrape (sin auth)
GET /api/admin/metrics/prometheus  — Con auth (debugging)
```
