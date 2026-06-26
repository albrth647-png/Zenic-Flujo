# HAT Level 3 — Specialists (1 responsabilidad cada uno)

> **Versión**: 2.0 (M8 hardening completo)
> **Estado**: Production-ready — 87 tests, 10.0/10 score, 6/6 hard gates

El **Nivel 3** de HAT contiene 9 specialists, cada uno con **UNA sola
responsabilidad**. Cada specialist decide qué tool/worker invocar del Nivel 4
mediante keyword routing, y publica una `AgentCard` al OVC para que el
`OrbitalRouter` del Nivel 1 pueda calcular resonancia.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                  NIVEL 3 — 9 Specialists                        │
│                                                                 │
│  ┌─────────────────── OPERACIONES ────────────────────┐        │
│  │ CrmSpecialist    InvoiceSpecialist   InventorySpec │        │
│  │ (clientes/leads) (facturación)       (inventario)   │        │
│  └────────────────────────────────────────────────────┘        │
│                                                                 │
│  ┌──────────────── COMUNICACIONES ────────────────────┐        │
│  │ NotificationSpec  EmailSpecialist   ChatSpecialist │        │
│  │ (email+WhatsApp)  (Gmail)           (Slack+Telegram)│       │
│  └────────────────────────────────────────────────────┘        │
│                                                                 │
│  ┌───────────────── DATOS_AUTO ──────────────────────┐         │
│  │ DataSpecialist  ApiSpecialist   CodeSpecialist    │         │
│  │ (Sheets+Drive+  (ApiConnector)  (CodeRunner+      │         │
│  │  PostgreSQL)                     OpenAI+Ollama)   │         │
│  └───────────────────────────────────────────────────┘         │
│                                                                 │
│  ┌─────────────────── BASE ──────────────────────────┐         │
│  │ SpecialistAgent (ABC)  AgentCard  CardPublisherMixin│       │
│  └───────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Estructura

```
level3_specialists/
├── __init__.py
├── base/
│   ├── __init__.py
│   ├── cards.py              # AgentCard dataclass (frozen)
│   ├── card_publisher.py     # CardPublisherMixin (publica cards al OVC)
│   └── specialist_agent.py   # SpecialistAgent ABC (handle, route_action)
├── operaciones/
│   ├── crm_specialist.py     # CrmSpecialist
│   ├── invoice_specialist.py # InvoiceSpecialist
│   └── inventory_specialist.py # InventorySpecialist
├── comunicaciones/
│   ├── notification_specialist.py
│   ├── email_specialist.py
│   └── chat_specialist.py
└── datos_auto/
    ├── data_specialist.py
    ├── api_specialist.py
    └── code_specialist.py
```

## 🚀 Uso

### Desde un supervisor del Nivel 2

```python
from src.hat.level3_specialists.operaciones import CrmSpecialist

crm = CrmSpecialist(tools={"crm": crm_tool_instance})

# El supervisor del Nivel 2 llama a handle()
result = crm.handle({
    "dispatch_id": "disp_123",
    "description": "listar leads del CRM",
    "params": {},
})
# → route_action("listar leads") → ("crm", "list_leads", {})
# → crm_tool.list_leads() → [{"id": 1, "name": "Juan"}]
# → {"status": "completed", "action": "list_leads", "result": [...]}
```

### Publicación de AgentCard

```python
# Al iniciar el sistema, bootstrap.py llama publish_card() para los 9 specialists.
# Esto inyecta una variable OVC por cada specialist, con:
# - name: "card_<agent_id>"
# - theta: determinista desde keywords (MD5 hash)
# - amplitude: peso en resonancia ORBITAL
# - metadata: {"type": "agent_card", "domain": ..., "capabilities": ...}

crm.publish_card()
# → OVC ahora tiene "card_crm" como variable orbital
# → OrbitalRouter (Nivel 1) puede calcular TOR(user_intent, card_crm)
```

## 📊 Specialists por dominio

### Operaciones (3 specialists)

| Specialist | Tools | Keywords de routing |
|------------|-------|---------------------|
| `CrmSpecialist` | crm | cliente, lead, crm, venta, contacto, oportunidad |
| `InvoiceSpecialist` | invoice, stripe, mercadopago | factura, invoice, cobro, pago, stripe |
| `InventorySpecialist` | inventory | producto, stock, inventario, inventory |

### Comunicaciones (3 specialists)

| Specialist | Tools | Keywords de routing |
|------------|-------|---------------------|
| `NotificationSpecialist` | notification | email, correo, whatsapp, notificar, cumpleaños |
| `EmailSpecialist` | gmail | gmail, correo, email, smtp |
| `ChatSpecialist` | slack, telegram | slack, telegram, chat, mensaje |

### Datos/Auto (3 specialists)

| Specialist | Tools | Keywords de routing |
|------------|-------|---------------------|
| `DataSpecialist` | data_keeper, sheets, drive, postgresql | data, datos, sheets, drive, postgres, sql |
| `ApiSpecialist` | api_connector | api, http, endpoint, webhook, rest |
| `CodeSpecialist` | code_runner, logic_gate, autopilot, openai, ollama | codigo, python, openai, ollama, funcion, script |

## 🧪 Testing

```bash
pytest tests/ -v
# 87 tests covering:
# - AgentCard construction, immutability, serialization
# - SpecialistAgent ABC, handle() flow, error handling
# - CardPublisherMixin publish_card(), deterministic theta
# - 9 specialists: get_card(), route_action(), handle()
```

**Cobertura**: 10.0/10 score, 6/6 hard gates.

---

**Licencia**: Propietaria — Pago Único (Zenic-Flujo v2.0.0)
