# HAT Level 5 — Tools ZF (19 herramientas reales)

> **Versión**: 2.0 (M8 hardening completo)
> **Estado**: Production-ready — 69 tests, 10.0/10 score, 6/6 hard gates

El **Nivel 5** de HAT contiene las 19 tools ZF reales con side effects en
SQLite, APIs externas y filesystem. Es la base de la pirámide — todo lo que
el sistema puede **hacer** vive aquí.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                  NIVEL 5 — 19 Tools ZF Reales                   │
│                                                                 │
│  ┌─────────── BUSINESS (3) ───────────┐                        │
│  │ CRMService    InvoiceService       │                        │
│  │ InventoryService                   │                        │
│  └────────────────────────────────────┘                        │
│                                                                 │
│  ┌─────────── PAYMENTS (2) ──────────┐                         │
│  │ StripeService   MercadoPagoService│                         │
│  └────────────────────────────────────┘                        │
│                                                                 │
│  ┌─────────── COMMUNICATIONS (4) ────┐                         │
│  │ NotificationService  GmailService │                         │
│  │ SlackService   TelegramService    │                         │
│  └────────────────────────────────────┘                        │
│                                                                 │
│  ┌─────────── DATA (5) ──────────────┐                         │
│  │ DataKeeperService  APIConnectorService│                     │
│  │ SheetsService  DriveService        │                        │
│  │ PostgreSQLService                  │                        │
│  └────────────────────────────────────┘                        │
│                                                                 │
│  ┌─────────── AUTOMATION (5) ────────┐                         │
│  │ CodeRunnerTool   LogicGateService │                        │
│  │ AutoPilotService  OpenAIService   │                        │
│  │ OllamaService                     │                        │
│  └────────────────────────────────────┘                        │
│                                                                 │
│  ┌─────────── ToolsRegistry ─────────┐                         │
│  │ Singleton que instancia las 19    │                        │
│  │ tools al startup y las expone     │                        │
│  │ via get(name), list_by_domain()   │                        │
│  └────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Estructura

```
level5_tools/
├── __init__.py
├── registry.py                    # ToolsRegistry + ToolRegistration + _REGISTRY (19 entries)
├── business/
│   ├── crm/service.py             # CRMService (create_lead, list_leads, advance_stage...)
│   ├── invoice/service.py         # InvoiceService (create_invoice, mark_paid, cancel...)
│   └── inventory/service.py       # InventoryService (add_product, update_stock...)
├── payments/
│   ├── stripe_service.py          # StripeService (create_payment_intent, create_customer...)
│   └── mercadopago_service.py     # MercadoPagoService
├── communications/
│   ├── notification/service.py    # NotificationService (send_email, send_whatsapp...)
│   ├── gmail_service.py           # GmailService
│   ├── slack_service.py           # SlackService
│   └── telegram_service.py        # TelegramService
├── data/
│   ├── data_keeper/service.py     # DataKeeperService (insert, query, create_collection)
│   ├── api_connector/service.py   # APIConnectorService (request, validate_url)
│   ├── sheets_service.py          # SheetsService
│   ├── drive_service.py           # DriveService
│   └── postgresql_service.py      # PostgreSQLService
└── automation/
    ├── code_runner/service.py     # CodeRunnerTool (run_python, sandbox)
    ├── logic_gate/service.py      # LogicGateService (requires event_bus)
    ├── autopilot/service.py       # AutoPilotService (requires src.nlu)
    ├── openai_service.py          # OpenAIService
    └── ollama_service.py          # OllamaService
```

## 🚀 Uso

### Desde bootstrap.py (startup)

```python
from src.hat.level5_tools.registry import get_tools_registry

# Instancia las 19 tools al startup
tools = get_tools_registry().register_all(event_bus=event_bus)
# → {"crm": CRMService(...), "invoice": InvoiceService(...), ...}

# Lookup por nombre
crm = get_tools_registry().get("crm")
leads = crm.list_leads()
```

### Desde un specialist (Nivel 3)

```python
class CrmSpecialist(SpecialistAgent):
    def __init__(self, tools=None):
        super().__init__(tools=tools or {})
    
    def handle(self, subtask):
        # El specialist recibe las tools inyectadas via bootstrap
        crm = self._tools.get("crm")
        return crm.create_lead(name="Juan", email="juan@test.com")
```

### Añadir una tool nueva

```python
# 1. Crear la tool en src/hat/level5_tools/<categoria>/<tool_name>/service.py
class MyToolService:
    def my_action(self, param: str) -> dict:
        return {"result": param}

# 2. Añadir 1 entrada en _REGISTRY (registry.py)
ToolRegistration(
    name="my_tool",
    domain="datos_auto",          # operaciones | comunicaciones | datos_auto
    category="automation",         # business | payments | communications | data | automation
    import_path="src.hat.level5_tools.automation.my_tool.service",
    class_name="MyToolService",
    requires_event_bus=False,      # True si la tool acepta event_bus en __init__
)

# 3. Reiniciar — WorkerFactory genera workers automáticamente
```

## 📊 Las 19 Tools

| # | Tool | Dominio | Categoría | Clase | EventBus |
|---|------|---------|-----------|-------|----------|
| 1 | `crm` | operaciones | business | `CRMService` | ✅ |
| 2 | `invoice` | operaciones | business | `InvoiceService` | ✅ |
| 3 | `inventory` | operaciones | business | `InventoryService` | ✅ |
| 4 | `stripe` | operaciones | payments | `StripeService` | ❌ |
| 5 | `mercadopago` | operaciones | payments | `MercadoPagoService` | ❌ |
| 6 | `notification` | comunicaciones | communications | `NotificationService` | ❌ |
| 7 | `gmail` | comunicaciones | communications | `GmailService` | ❌ |
| 8 | `slack` | comunicaciones | communications | `SlackService` | ❌ |
| 9 | `telegram` | comunicaciones | communications | `TelegramService` | ❌ |
| 10 | `data_keeper` | datos_auto | data | `DataKeeperService` | ❌ |
| 11 | `api_connector` | datos_auto | data | `APIConnectorService` | ❌ |
| 12 | `sheets` | datos_auto | data | `SheetsService` | ❌ |
| 13 | `drive` | datos_auto | data | `DriveService` | ❌ |
| 14 | `postgresql` | datos_auto | data | `PostgreSQLService` | ❌ |
| 15 | `code_runner` | datos_auto | automation | `CodeRunnerTool` | ❌ |
| 16 | `logic_gate` | datos_auto | automation | `LogicGateService` | ✅ |
| 17 | `autopilot` | datos_auto | automation | `AutoPilotService` | ❌ |
| 18 | `openai` | datos_auto | automation | `OpenAIService` | ❌ |
| 19 | `ollama` | datos_auto | automation | `OllamaService` | ❌ |

## 🔧 ToolsRegistry API

```python
class ToolsRegistry:
    """Singleton que gestiona las 19 tools."""
    
    def register_all(event_bus=None) -> dict[str, Any]  # Instancia todas
    def get(name: str) -> Any | None                    # Lookup por nombre
    def get_spec(name: str) -> ToolRegistration | None  # Metadatos
    def list_all() -> dict[str, Any]                    # Todas las instancias
    def list_by_domain(domain: str) -> dict[str, Any]  # Filtrar por dominio
    def list_by_category(category: str) -> dict[str, Any]  # Filtrar por categoría
    def list_domains() -> list[str]                     # Dominios únicos
    def list_categories() -> list[str]                  # Categorías únicas
    def __len__() -> int                                # Total instanciadas
    def __contains__(name) -> bool                      # name in registry
```

## 🧪 Testing

```bash
pytest tests/ -v
# 69 tests covering:
# - ToolsRegistry: singleton, register_all, get, list_by_domain/category
# - ToolRegistration: frozen dataclass, requires_event_bus default
# - _REGISTRY: 19 entries, 5 categorías, 3 dominios, names únicos
# - CRMService: create_lead, list_leads, advance_stage, close_won/lost
# - InvoiceService: create_invoice, list_invoices, get_invoice
# - InventoryService: add_product, list_products, get_product
# - Notification/Gmail/Slack/Telegram: existencia de métodos
# - DataKeeper/ApiConnector/Sheets/Drive/PostgreSQL: existencia de métodos
# - CodeRunner/LogicGate/AutoPilot/OpenAI/Ollama: existencia de métodos
# - Stripe/MercadoPago: existencia de métodos de pago
```

**Cobertura**: 10.0/10 score, 6/6 hard gates.

---

**Licencia**: Propietaria — Pago Único (Zenic-Flujo v2.0.0)
