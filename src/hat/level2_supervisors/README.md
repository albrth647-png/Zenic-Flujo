# HAT Level 2 — Supervisores de Dominio

> **Versión**: 2.0 (M8 hardening completo)
> **Estado**: Production-ready — 89 tests, 10.0/10 score, 6/6 hard gates

El **Nivel 2** de HAT contiene 3 supervisores de dominio independientes que
reciben subtareas del `HATRouter` (Nivel 1) y las rutean al specialist correcto
del Nivel 3 mediante keyword matching.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                  NIVEL 2 — 3 Supervisores                       │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Operaciones  │  │Comunicaciones│  │  DatosAuto   │         │
│  │ Supervisor   │  │  Supervisor  │  │  Supervisor  │         │
│  │              │  │              │  │              │         │
│  │ CRM          │  │ Email        │  │ Data         │         │
│  │ Invoice      │  │ Chat         │  │ Api          │         │
│  │ Inventory    │  │ Notification │  │ Code         │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           │                                     │
│                   ┌───────▼───────┐                             │
│                   │SpecialistRouter│                            │
│                   │   (base class) │                            │
│                   └───────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## 🔒 Aislamiento

Cada supervisor **NO conoce a los otros dos**. Solo el `HATRouter` (Nivel 1)
conoce a los 3. Esto garantiza:

- Sin dependencias circulares entre dominios.
- Cambios en un dominio no afectan a los otros.
- Tests de un dominio no requieren mockear los otros.

## 📁 Estructura

```
level2_supervisors/
├── __init__.py                    # Exports: 3 supervisores
├── base_router.py                 # SpecialistRouter base class (M8 NUEVO)
├── operaciones/
│   ├── __init__.py
│   └── supervisor.py              # OperacionesSupervisor (M8: routing real)
├── comunicaciones/
│   ├── __init__.py
│   └── supervisor.py              # ComunicacionesSupervisor (M8: routing real)
└── datos_auto/
    ├── __init__.py
    └── supervisor.py              # DatosAutoSupervisor (M8: routing real)
```

## 🚀 Uso

### Desde HATRouter (Nivel 1)

```python
from src.hat.level2_supervisors.operaciones import OperacionesSupervisor
from src.hat.level2_supervisors.comunicaciones import ComunicacionesSupervisor
from src.hat.level2_supervisors.datos_auto import DatosAutoSupervisor

# Los specialists se inyectan via bootstrap.py
supervisors = {
    "operaciones": OperacionesSupervisor(specialists={
        "crm": crm_specialist,
        "invoice": invoice_specialist,
        "inventory": inventory_specialist,
    }),
    "comunicaciones": ComunicacionesSupervisor(specialists={
        "email": email_specialist,
        "chat": chat_specialist,
        "notification": notification_specialist,
    }),
    "datos_auto": DatosAutoSupervisor(specialists={
        "data": data_specialist,
        "api": api_specialist,
        "code": code_specialist,
    }),
}

# El HATRouter despacha al supervisor del dominio ganador
result = supervisors["operaciones"].handle({
    "dispatch_id": "disp_123",
    "user_id": "u1",
    "session_id": "s1",
    "description": "listar leads del CRM",
    "params": {"query": "listar leads del CRM"},
})
# → routing por keyword "lead" → CrmSpecialist
```

### Routing por keywords

Cada supervisor define un `_KEYWORD_MAP` que mapea keywords a specialist names.
El matching es **case-insensitive** y usa **substring matching** (la keyword
como substring del mensaje).

```python
# OperacionesSupervisor._KEYWORD_MAP (extracto)
{
    "producto": "inventory",    # ← PRIMERO: keywords específicas primero
    "stock": "inventory",
    "inventario": "inventory",
    "factura": "invoice",
    "cobro": "invoice",
    "cliente": "crm",
    "lead": "crm",
    # NOTA: "venta" se omite — es substring de "inventario"
}
```

**Orden de keywords importa**: si un mensaje contiene múltiples keywords,
gana el primer match en orden de inserción del dict (Python 3.7+). Por eso
ponemos keywords más específicas primero y evitamos substrings ambiguos.

### Fallback graceful

Si ningún keyword matchea, el supervisor usa el **primer specialist disponible**
(orden de inserción del dict). Esto garantiza que el sistema nunca se bloquea
por falta de routing.

## 📊 Keyword Maps por dominio

### OperacionesSupervisor

| Specialist | Keywords |
|------------|----------|
| `crm` | cliente, lead, crm, oportunidad, contacto, negocio |
| `invoice` | factura, invoice, cobro, pago, stripe, mercadopago |
| `inventory` | producto, stock, inventario, inventory |

### ComunicacionesSupervisor

| Specialist | Keywords |
|------------|----------|
| `email` | gmail, smtp, email, correo |
| `chat` | whatsapp, slack, telegram, chat |
| `notification` | notificar, notificacion, notification, cumpleanos, cumpleaños, birthday |

### DatosAutoSupervisor

| Specialist | Keywords |
|------------|----------|
| `api` | api, http, endpoint, webhook, rest |
| `code` | openai, ollama, python, codigo, code, funcion, function, script, automatizar |
| `data` | postgres, postgresql, sheets, drive, data, datos, sql |

## 🧪 Testing

```bash
# Todos los tests del Nivel 2
pytest tests/ -v

# Solo un supervisor
pytest tests/test_operaciones_supervisor.py -v

# Coverage
pytest --cov=level2_supervisors --cov-branch --cov-report=html tests/
```

**Cobertura actual**: 89 tests, 10.0/10 score, 6/6 hard gates.

## 🔧 SpecialistRouter — API base

```python
class SpecialistRouter:
    """Base class para supervisores con routing por keywords."""

    domain: str = "base"                    # Override en subclase
    _keyword_map: dict[str, str]            # Definir en __init__ de subclase

    def __init__(self, specialists: dict, ledger: Any = None) -> None
    def handle(self, subtask: dict) -> dict  # Entry point
    def _select_specialist(self, subtask: dict) -> str  # Routing interno
    def _extract_message(self, subtask: dict) -> str    # Helper message extraction
```

## 🔗 Dependencias

### Internas
- `src.core.logging.get_logger` — Logging estructurado.
- `src.hat.level3_specialists.*` — 9 specialists del Nivel 3 (inyectados via bootstrap).

### Sin dependencias externas
El Nivel 2 es puro Python — no usa FastAPI, ni SQLite, ni OrbitalContext directamente.
Toda la complejidad está en Nivel 1 (HATRouter) y Nivel 3 (Specialists).

---

**Licencia**: Propietaria — Pago Único (Zenic-Flujo v2.0.0)
