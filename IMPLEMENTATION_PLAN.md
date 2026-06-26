# 🚀 IMPLEMENTATION PLAN — Plan de Migración Ejecutable

> **Versión**: 2.0 · **Fecha**: 2026-06-20
> Estructura FINAL: 5 niveles (1-5)
> 10 fases secuenciales · ~51h estimadas

## 📋 Resumen Ejecutivo

| Fase | Acción | LOC afectadas | Esfuerzo | Riesgo |
|---|---|---|---|---|
| M1 | Crear `src/core/` y mover infraestructura base | ~6,800 | 4h | Bajo |
| M2 | Reorganizar `src/hat/` en 5 niveles (level1-level5) | ~3,420 | 4h | Bajo |
| M3 | Mover `src/tools/*` a `src/hat/level5_tools/` | ~7,400 | 2h | Bajo |
| M4 | Eliminar 14 stubs HAT (7 specialists + 7 workers) | ~970 | 1h | Bajo |
| M5 | Eliminar `src/agents/` (migrar útil a `hat/agents_legacy/`) | ~3,082 | 2h | Medio |
| M6 | Crear Nivel 3 (9 specialists con 1 responsabilidad cada uno) | ~700 | 8h | Medio |
| M7 | Crear Nivel 4 (WorkerFactory + ~59 workers auto-generados) | ~300 | 8h | Medio |
| M8 | Crear Nivel 2 (3 supervisores) + refactor Nivel 1 (tick_router) | ~700 | 6h | Alto |
| M9 | Reducir anti-dup a 3 capas + Ledger a 3 tablas | ~400 | 4h | Medio |
| M10 | Migrar tests + E2E con tools reales + lanzar api_v2 en prod | ~5000 | 12h | Bajo |
| **TOTAL** | | **neto -2,495** | **~51h** | |

---

## 🎯 Arquitectura Final (5 niveles)

```
NIVEL 1 — Orquestador central Orbital (1)
    ↓
NIVEL 2 — 3 sub-orquestadores independientes (3)
    ↓
NIVEL 3 — 9 specialists, 1 responsabilidad cada uno (LA MAGIA)
    ↓
NIVEL 4 — ~59 workers (más extenso que N3)
    ↓
NIVEL 5 — 19 tools ZF reales (base final)
```

---

## Fase M1 — Crear `src/core/` (4h)

**Objetivo**: Separar la infraestructura base (config, utils, db, security, observability, i18n) en su propio módulo `src/core/` que NO depende de HAT ni de ORBITAL.

### Tareas

1. **Crear estructura**:
```bash
mkdir -p src/core/{config,utils,db/repositories,security/sso,observability/metrics,i18n/locales,logging}
```

2. **Mover archivos sin refactorizar** (tests se rompen temporalmente):
```bash
# Config
mv src/config.py src/core/config/__init__.py.tmp
# (luego split en paths.py, secrets.py, services.py, validation.py)

# Container + Airgap
mv src/container.py src/core/container.py
mv src/airgap.py src/core/airgap.py

# Utils → split en módulos
mv src/utils/logger.py src/core/logging/__init__.py
mv src/utils/logging_config.py /tmp/merge_into_logging.py  # fusionar
mv src/utils/helpers.py /tmp/split_helpers.py  # split en 7 archivos
mv src/utils/sql.py src/core/db/sql_builder.py

# Data layer
mv src/data/database_manager.py src/core/db/sqlite_manager.py
mv src/data/interfaces.py src/core/db/interfaces.py
mv src/data/settings_repository.py src/core/repositories/settings_repository.py
mv src/data/user_repository.py src/core/repositories/user_repository.py
mv src/data/audit_repository.py src/core/repositories/audit_repository.py
mv src/data/backup_engine.py src/core/db/backup_engine.py
mv src/data/mongodb_service.py src/core/db/mongodb_service.py
mv src/data/redis_service.py src/core/db/redis_service.py
# mongodb_repository.py → ELIMINAR (huérfano)
# marketplace_db.py → mover a src/marketplace/db.py

# i18n
mv src/i18n/* src/core/i18n/

# Observability
mv src/observability/* src/core/observability/

# Security
mv src/security/* src/core/security/
# Renombrar sso.py → sso/service.py para evitar colisión paquete/módulo
```

3. **Crear archivos `__init__.py` con re-exports**:
```python
# src/core/__init__.py
from src.core.config import *
from src.core.container import container
from src.core.utils import generate_id, now_iso, resolve_variables
from src.core.db.sqlite_manager import DatabaseManager
# ... etc
```

4. **Actualizar imports en TODO el proyecto** (script automático):
```bash
# Script: scripts/migrate_imports_m1.py
# Busca y reemplaza:
#   from src.config import → from src.core.config import
#   from src.utils.logger import → from src.core.logging import
#   from src.data.database_manager import → from src.core.db.sqlite_manager import
#   from src.security. import → from src.core.security.
#   from src.observability. import → from src.core.observability.
#   from src.i18n import → from src.core.i18n import
```

5. **Eliminar carpeta vacía `src/data/`** (todo migrado).

6. **Verificar**: `python -m pytest src/tests/ -x` debe pasar al 100%.

### Criterio de salida
- `src/core/` existe con toda la infraestructura
- `src/data/`, `src/utils/`, `src/i18n/`, `src/observability/`, `src/security/` ya NO existen (todo en `core/`)
- Tests pasan
- Aplicación arranca

---

## Fase M2 — Reorganizar `src/hat/` en 5 niveles (4h)

**Objetivo**: Estructurar `src/hat/` con las 5 carpetas de nivel (level1_orchestrator, level2_supervisors, level3_specialists, level4_workers, level5_tools).

### Tareas

1. **Crear estructura**:
```bash
mkdir -p src/hat/{level1_orchestrator/{fsm,intent,routing,ledger,anti_duplication,observability,api},level2_supervisors/{operaciones,comunicaciones,datos_auto},level3_specialists/{operaciones,comunicaciones,datos_auto},level4_workers/{operaciones/{crm,invoice,inventory},comunicaciones/{notification,email,chat},datos_auto/{data,api,code}},level5_tools/{business,payments,communications,data,automation}}
```

2. **Mover Nivel 1** (orbital_n0 → level1_orchestrator):
```bash
mv src/hat/orbital_n0/tick_router.py src/hat/level1_orchestrator/tick_router.py
mv src/hat/orbital_n0/states.py src/hat/level1_orchestrator/fsm/states.py
mv src/hat/orbital_n0/fsm_disambiguator.py src/hat/level1_orchestrator/fsm/disambiguator.py
mv src/hat/orbital_n0/intent_hasher.py src/hat/level1_orchestrator/intent/hasher.py
# (split normalizer.py de hasher.py)

mv src/hat/ledger/* src/hat/level1_orchestrator/ledger/
mv src/hat/anti_duplication/{cascade,exact_match,idempotency,ttl_freshness}.py src/hat/level1_orchestrator/anti_duplication/
# semantic_dedup.py → ELIMINAR
# circuit_breaker.py → mover a level4_workers/

mv src/hat/observability/* src/hat/level1_orchestrator/observability/
mv src/hat/api/* src/hat/level1_orchestrator/api/

# Eliminar orbital_n0/ vacío
rm -rf src/hat/orbital_n0 src/hat/ledger src/hat/anti_duplication src/hat/observability src/hat/api
```

3. **Mover Nivel 2** (supervisors → level2_supervisors):
```bash
mv src/hat/supervisors/base.py src/hat/level2_supervisors/base.py
# research.py, build.py, operate.py → ELIMINAR (dominios arbitrarios)
rm -rf src/hat/supervisors
```

4. **Mover Nivel 3 base** (agents/cards + card_publisher → level3_specialists/base):
```bash
mkdir -p src/hat/level3_specialists/base
mv src/hat/agents/cards.py src/hat/level3_specialists/base/cards.py
mv src/hat/agents/card_publisher.py src/hat/level3_specialists/base/card_publisher.py
# specialists/* y workers/* → ELIMINAR (stubs)
rm -rf src/hat/agents
```

5. **Crear `src/hat/__init__.py`** con re-export público:
```python
from src.hat.level1_orchestrator.tick_router import HATRouter
from src.hat.bootstrap import bootstrap_hat, get_hat_router

__all__ = ["HATRouter", "bootstrap_hat", "get_hat_router"]
__version__ = "2.0.0"
```

6. **Actualizar imports en TODO el proyecto** (script):
```bash
# scripts/migrate_imports_m2.py
# from src.hat.orbital_n0.tick_router import → from src.hat.level1_orchestrator.tick_router import
# from src.hat.ledger.repository import → from src.hat.level1_orchestrator.ledger.repository import
# from src.hat.anti_duplication.cascade import → from src.hat.level1_orchestrator.anti_duplication.cascade import
# from src.hat.agents.cards import → from src.hat.level3_specialists.base.cards import
# etc.
```

### Criterio de salida
- `src/hat/` tiene 5 subcarpetas (level1-level5)
- `src/hat/orbital_n0/`, `src/hat/ledger/`, `src/hat/anti_duplication/`, `src/hat/agents/`, `src/hat/supervisors/` ya NO existen
- Tests pasan

---

## Fase M3 — Mover `src/tools/*` a `src/hat/level5_tools/` (2h)

**Objetivo**: Las tools ZF se mueven a su ubicación final dentro de HAT (Nivel 5), organizadas por categoría.

### Tareas

1. **Mover tools por categoría**:
```bash
# Business
mkdir -p src/hat/level5_tools/business/{crm,invoice,inventory}
mv src/tools/crm/* src/hat/level5_tools/business/crm/
mv src/tools/invoice/* src/hat/level5_tools/business/invoice/
mv src/tools/inventory/* src/hat/level5_tools/business/inventory/

# Payments
mkdir -p src/hat/level5_tools/payments
mv src/tools/integrations/stripe_service.py src/hat/level5_tools/payments/
mv src/tools/integrations/mercadopago_service.py src/hat/level5_tools/payments/

# Communications
mkdir -p src/hat/level5_tools/communications/notification
mv src/tools/notification/* src/hat/level5_tools/communications/notification/
mv src/tools/integrations/{gmail,slack,telegram}_service.py src/hat/level5_tools/communications/

# Data
mkdir -p src/hat/level5_tools/data/{data_keeper,api_connector}
mv src/tools/data_keeper/* src/hat/level5_tools/data/data_keeper/
mv src/tools/api_connector/* src/hat/level5_tools/data/api_connector/
mv src/tools/integrations/{sheets,drive,postgresql}_service.py src/hat/level5_tools/data/

# Automation
mkdir -p src/hat/level5_tools/automation/{code_runner,logic_gate,autopilot}
mv src/tools/code_runner/* src/hat/level5_tools/automation/code_runner/
mv src/tools/logic_gate/* src/hat/level5_tools/automation/logic_gate/
mv src/tools/autopilot/* src/hat/level5_tools/automation/autopilot/
mv src/tools/integrations/{openai,ollama}_service.py src/hat/level5_tools/automation/

# whatsapp_service.py → ELIMINAR (duplicado de notification)

# Eliminar src/tools/ vacío
rm -rf src/tools
```

2. **Crear `src/hat/level5_tools/registry.py`** (registro central de tools).

3. **Actualizar `src/main.py`** para usar `ToolsRegistry.register_all()`:
```python
# Antes:
from src.tools.crm.service import CRMService
# ... 18 imports manuales
engine.register_tool("crm", CRMService(event_bus=event_bus))
# ... 18 registros manuales

# Después:
from src.hat.level5_tools.registry import get_tools_registry
tools = get_tools_registry().register_all(event_bus=event_bus)
for name, tool in tools.items():
    engine.register_tool(name, tool)
```

4. **Actualizar imports en TODO el proyecto**:
```bash
# scripts/migrate_imports_m3.py
# from src.tools.crm.service import → from src.hat.level5_tools.business.crm.service import
# from src.tools.invoice.service import → from src.hat.level5_tools.business.invoice.service import
# etc.
```

### Criterio de salida
- `src/tools/` ya NO existe
- `src/hat/level5_tools/` contiene las 19 tools organizadas por categoría (business, payments, communications, data, automation)
- `ToolsRegistry.register_all()` instancia todas las tools al startup
- Aplicación arranca con tools funcionando

---

## Fase M4 — Eliminar 14 stubs HAT (1h)

**Objetivo**: Eliminar los 14 archivos stub de specialists y workers que retornan fake data.

### Tareas

1. **Eliminar 7 specialists stub**:
```bash
rm src/hat/level3_specialists/specialists/web_researcher.py  # (si migró en M2)
rm src/hat/level3_specialists/specialists/code_generator.py
rm src/hat/level3_specialists/specialists/test_engineer.py
rm src/hat/level3_specialists/specialists/deploy_agent.py
rm src/hat/level3_specialists/specialists/monitor_agent.py
rm src/hat/level3_specialists/specialists/log_analyzer.py
rm src/hat/level3_specialists/specialists/incident_responder.py
```

2. **Eliminar 7 workers stub**:
```bash
rm src/hat/level4_workers/workers/query_builder.py
rm src/hat/level4_workers/workers/code_writer.py
rm src/hat/level4_workers/workers/test_runner.py
rm src/hat/level4_workers/workers/container_builder.py
rm src/hat/level4_workers/workers/metrics_scraper.py
rm src/hat/level4_workers/workers/log_filter.py
rm src/hat/level4_workers/workers/alert_dispatcher.py
```

3. **Eliminar tests que validan stubs** (se reescribirán en M10):
```bash
rm src/tests/hat/test_build_domain.py
rm src/tests/hat/test_operate_domain.py
rm src/tests/hat/test_supervisors_research.py
```

4. **Actualizar tests restantes** que importaban stubs eliminados.

### Criterio de salida
- 14 archivos stub eliminados (~970 LOC menos)
- 3 archivos de test eliminados
- Tests que quedan pasan

---

## Fase M5 — Eliminar `src/agents/` (2h)

**Objetivo**: Migrar lo útil de `src/agents/` a `src/hat/agents_legacy/` y eliminar el resto.

### Tareas

1. **Crear `src/hat/agents_legacy/`** y migrar:
```bash
mkdir -p src/hat/agents_legacy
mv src/agents/base.py src/hat/agents_legacy/base.py
mv src/agents/orchestrator.py src/hat/agents_legacy/orchestrator.py
mv src/agents/runtime.py src/hat/agents_legacy/runtime.py
mv src/agents/token_tracking.py src/core/observability/token_tracking.py
# (fix TypeError bug en línea 293 al migrar)
```

2. **Eliminar huérfanos**:
```bash
rm src/agents/memory.py  # fake embeddings, 0 callers
rm src/agents/tools.py  # AgentToolRegistry huérfano, 0 callers
```

3. **Crear `src/hat/agents_legacy/__init__.py`** con re-exports:
```python
from src.hat.agents_legacy.base import BaseAgent, AgentConfig, AgentCapability
from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator, OrchestrationPattern
from src.hat.agents_legacy.runtime import AgentRuntime

__all__ = ["BaseAgent", "AgentConfig", "AgentCapability",
           "MultiAgentOrchestrator", "OrchestrationPattern", "AgentRuntime"]
```

4. **Eliminar `src/agents/`** vacío.

5. **Actualizar imports**:
```bash
# from src.agents.base import → from src.hat.agents_legacy.base import
# from src.agents.orchestrator import → from src.hat.agents_legacy.orchestrator import
# from src.agents.runtime import → from src.hat.agents_legacy.runtime import
# from src.agents.token_tracking import → from src.core.observability.token_tracking import
```

### Criterio de salida
- `src/agents/` ya NO existe
- `src/hat/agents_legacy/` contiene BaseAgent + MultiAgentOrchestrator + AgentRuntime
- `src/core/observability/token_tracking.py` con bug arreglado
- Tests pasan

---

## Fase M6 — Nivel 3: 9 Specialists (8h) — LA MAGIA

**Objetivo**: Implementar los 9 specialists (3 por supervisor) con una sola responsabilidad cada uno. Cada specialist decide qué tools/workers llamar.

### Tareas

1. **Crear `src/hat/level3_specialists/base/specialist_agent.py`** — SpecialistAgent ABC.

2. **Crear `src/hat/level3_specialists/base/worker_resolver.py`** — decide qué worker del N4 llamar.

3. **Crear 9 specialists concretos** (una responsabilidad cada uno):

```
src/hat/level3_specialists/
├── operaciones/
│   ├── crm_specialist.py         ← Gestión de clientes/leads
│   ├── invoice_specialist.py     ← Facturación
│   └── inventory_specialist.py   ← Inventario/stock
├── comunicaciones/
│   ├── notification_specialist.py  ← Notificaciones (email+WhatsApp)
│   ├── email_specialist.py       ← Gmail
│   └── chat_specialist.py        ← Slack + Telegram
└── datos_auto/
    ├── data_specialist.py        ← DataKeeper + Sheets + Drive + PostgreSQL
    ├── api_specialist.py         ← ApiConnector
    └── code_specialist.py        ← CodeRunner + LogicGate + Autopilot + OpenAI + Ollama
```

Ejemplo de implementación:
```python
# src/hat/level3_specialists/operaciones/crm_specialist.py
class CrmSpecialist(SpecialistAgent):
    """UNA SOLA RESPONSABILIDAD: Gestión de clientes/leads."""

    def __init__(self, tools_registry):
        super().__init__(
            specialist_name="crm",
            responsibility="gestion_clientes_leads",
            tools={"crm": tools_registry.get("crm")},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="crm",
            agent_name="CRM",
            domain="operaciones",
            tier="specialist",
            orbital_keywords=["cliente", "lead", "venta", "oportunidad", "negocio"],
            orbital_amplitude=1.5,
        )

    def route_action(self, subtask):
        """LA MAGIA: decide qué tool/worker llamar."""
        desc = subtask.get("description", "").lower()
        params = subtask.get("params", {})

        if "crear" in desc or "nuevo" in desc:
            return "crm", "create_lead", params
        if "listar" in desc or "mostrar" in desc:
            return "crm", "list_leads", params
        if "avanzar" in desc:
            return "crm", "advance_stage", params
        if "ganado" in desc:
            return "crm", "close_won", params
        # ... etc
        return "crm", "list_leads", params  # default seguro
```

4. **Tests unitarios por specialist**:
   - Cada specialist publica AgentCard correctamente
   - Cada specialist rutea acciones según keywords
   - Cada specialist invoca método correcto de la tool del N5
   - Cada specialist retorna resultado estructurado

### Criterio de salida
- 9 specialists creados (3 por supervisor)
- Cada specialist tiene UNA sola responsabilidad documentada
- Cada specialist decide qué tool/worker llamar (LA MAGIA)
- Tests unitarios por specialist pasan

---

## Fase M7 — Nivel 4: WorkerFactory + ~59 workers (8h)

**Objetivo**: Implementar auto-generación de workers por introspección de métodos públicos de cada tool. Más extenso que Nivel 3 (9 specialists → ~59 workers).

### Tareas

1. **Crear `src/hat/level4_workers/base/tool_worker.py`** — ToolWorker ABC.

2. **Crear `src/hat/level4_workers/base/worker_factory.py`**:
```python
import inspect
from src.hat.level4_workers.base.tool_worker import ToolWorker

class WorkerFactory:
    """Genera workers dinámicamente desde métodos públicos de una tool."""

    def generate_for_tool(self, tool_name: str, tool_instance: Any) -> dict[str, ToolWorker]:
        """Genera 1 worker por método público de la tool.

        Returns:
            Dict {action_name: ToolWorker instance}
        """
        workers = {}
        for name, method in inspect.getmembers(tool_instance, predicate=inspect.ismethod):
            if name.startswith("_") or name in ("get_tool_definition", "get_status", "configure", "test_connection"):
                continue
            worker_class = type(
                f"{tool_name}_{name}_worker".title().replace("_", ""),
                (ToolWorker,),
                {"tool_name": tool_name, "action_name": name}
            )
            workers[name] = worker_class(tool_instance=tool_instance)
        return workers

    def generate_all(self) -> dict[str, dict[str, ToolWorker]]:
        """Genera workers para todas las tools registradas en N5."""
        from src.hat.level5_tools.registry import get_tools_registry
        tools = get_tools_registry().list_all()
        return {name: self.generate_for_tool(name, tool) for name, tool in tools.items()}
```

3. **Crear `src/hat/level4_workers/base/registry.py`** (lookup por tool+action).

4. **Crear `src/hat/level4_workers/base/idempotency.py`** (hash tool+action+params).

5. **Mover `circuit_breaker.py`** desde anti_duplication → level4_workers (per-worker).

6. **Wire WorkerFactory en SpecialistAgent**: cada specialist obtiene sus workers automáticamente.

7. **Tests**: verificar auto-generación:
   - CrmSpecialist tiene 9 workers (create_lead, list_leads, etc.)
   - InvoiceSpecialist tiene 9 workers
   - Total ~59 workers generados automáticamente

### Distribución esperada de workers (~59 total)

| Carpeta | Workers esperados |
|---|---|
| `level4_workers/operaciones/crm/` | ~9 (create_lead, list_leads, advance_stage, close_won, close_lost, get_lead, delete_lead, update_lead, get_stats) |
| `level4_workers/operaciones/invoice/` | ~8 (create_invoice, mark_paid, mark_overdue, cancel, get_invoice, list_invoices, get_overdue, get_stats) |
| `level4_workers/operaciones/inventory/` | ~8 (add_product, update_stock, update_product, get_product, list_products, delete_product, get_low_stock, get_stats) |
| `level4_workers/comunicaciones/notification/` | ~4 (send_email, send_whatsapp, configure_smtp, test_connection) |
| `level4_workers/comunicaciones/email/` | ~4 (send_email, search_emails, get_message, list_labels) |
| `level4_workers/comunicaciones/chat/` | ~4 (slack_send, slack_list_channels, telegram_send, telegram_get_updates) |
| `level4_workers/datos_auto/data/` | ~10 (data_keeper CRUD + sheets + drive + postgresql) |
| `level4_workers/datos_auto/api/` | ~4 (request, xml_parse, xml_generate, validate_url) |
| `level4_workers/datos_auto/code/` | ~8 (run_python, validate, evaluate_rule, suggest_templates, openai_chat, ollama_chat) |
| **TOTAL** | **~59 workers** |

### Criterio de salida
- `WorkerFactory.generate_all()` genera ~59 workers
- Cada specialist delega a sus workers correctamente
- Idempotency por tool+action+params funciona
- Circuit breaker per-worker activo

---

## Fase M8 — Nivel 2: 3 supervisores + refactor Nivel 1 (6h, riesgo ALTO)

**Objetivo**: Implementar los 3 supervisores de dominio (NO se conocen entre sí) y conectar todo en el HATRouter (Nivel 1).

### Tareas

1. **Crear `src/hat/level2_supervisors/base.py`** — DomainSupervisor ABC.

2. **3 supervisores concretos** (cada uno en su propia carpeta, aisla código):

```python
# src/hat/level2_supervisors/operaciones/supervisor.py
class OperacionesSupervisor(DomainSupervisor):
    """Sub-orquestador de operaciones. NO conoce a Comunicaciones ni DatosAuto."""
    domain = "operaciones"

    def _select_specialist(self, subtask):
        # Decide según Orbital qué specialist del N3 usar
        # Solo conoce specialists de operaciones: CRM, Invoice, Inventory
        ...

# src/hat/level2_supervisors/comunicaciones/supervisor.py
class ComunicacionesSupervisor(DomainSupervisor):
    """Sub-orquestador de comunicaciones. NO conoce a Operaciones ni DatosAuto."""
    domain = "comunicaciones"
    # Solo conoce specialists de comunicaciones: Notification, Email, Chat
    ...

# src/hat/level2_supervisors/datos_auto/supervisor.py
class DatosAutoSupervisor(DomainSupervisor):
    """Sub-orquestador de datos/automatización. NO conoce a Operaciones ni Comunicaciones."""
    domain = "datos_auto"
    # Solo conoce specialists de datos_auto: Data, Api, Code
    ...
```

3. **Crear `src/hat/bootstrap.py`** — orquesta la inicialización de los 5 niveles:
```python
def bootstrap_hat(event_bus=None) -> HATRouter:
    # Nivel 5: Tools
    tools = get_tools_registry().register_all(event_bus=event_bus)

    # Nivel 4: Workers (auto-generados)
    workers = WorkerFactory().generate_all()

    # Nivel 3: Specialists (9)
    specialists = SpecialistFactory().generate_all(workers)

    # Publicar AgentCards (CRÍTICO para routing RCC del N1)
    specialists.publish_all_cards()

    # Nivel 2: Supervisores (3)
    supervisors = {
        "operaciones": OperacionesSupervisor(specialists=specialists.by_domain("operaciones")),
        "comunicaciones": ComunicacionesSupervisor(specialists=specialists.by_domain("comunicaciones")),
        "datos_auto": DatosAutoSupervisor(specialists=specialists.by_domain("datos_auto")),
    }

    # Nivel 1: HATRouter (Orbital central)
    hat_router = HATRouter(supervisors=supervisors, ledger=ledger, ctx=orbital_ctx)
    return hat_router
```

4. **Refactor `src/hat/level1_orchestrator/tick_router.py`**:
   - Reordenar `handle()`: `load_session()` ANTES de `_route_by_orbital()` (bug actual)
   - En `__init__`, llamar `bootstrap_hat()` si supervisors no se pasan
   - Actualizar `_SUPERVISORS_BY_DOMAIN` con los 3 dominios nuevos:
     ```python
     _SUPERVISORS_BY_DOMAIN = {
         "operaciones": OperacionesSupervisor,
         "comunicaciones": ComunicacionesSupervisor,
         "datos_auto": DatosAutoSupervisor,
     }
     ```
   - Actualizar `fsm_disambiguator.DOMAIN_KEYWORDS` con keywords de los 3 dominios nuevos:
     ```python
     DOMAIN_KEYWORDS = {
         "operaciones": ("cliente", "lead", "venta", "factura", "invoice", "producto", "stock", "inventario", "pago", "stripe", "mercadopago"),
         "comunicaciones": ("email", "correo", "whatsapp", "slack", "telegram", "notificar", "mensaje", "gmail"),
         "datos_auto": ("código", "python", "regla", "plantilla", "openai", "ollama", "api", "http", "sql", "sheets", "drive", "datos"),
     }
     ```
   - Actualizar `VALID_DOMAINS` en fsm_disambiguator:
     ```python
     VALID_DOMAINS = frozenset({"operaciones", "comunicaciones", "datos_auto"})
     ```

5. **Montar HATRouter en `src/api_v2/app.py`**:
```python
from src.hat.level1_orchestrator.api.routes import router as hat_router
app.include_router(hat_router)
```

6. **Cambiar `src/web/blueprints/nlu.py:api_chat()`** para usar HATRouter:
```python
from src.hat import get_hat_router

@bp.route("/api/workflows/chat", methods=["POST"])
@login_required
def api_chat():
    hat_router = get_hat_router()
    result = hat_router.handle(
        user_id=str(session.get("user_id", "1")),
        session_id=str(session.get("session_id", "default")),
        message=request.json.get("message", ""),
    )
    return jsonify(result)
```

### Criterio de salida
- `bootstrap_hat()` inicializa los 5 niveles correctamente
- HATRouter atiende requests con routing RCC funcional
- 3 supervisores rutean a sus specialists
- `/api/hat/chat` responde 200 en producción
- Web chat usa HATRouter (no NLU directo)

### Verificación crítica
```bash
# 1. App arranca
python src/main.py

# 2. HAT responde
curl -X POST http://localhost:8000/api/hat/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","session_id":"s1","message":"crear lead Juan"}'
# Debe retornar 200 con domain="operaciones", status="completed"

# 3. Web chat usa HAT
# Abrir http://localhost:8080/chat y escribir "crear lead Juan"
# Debe crear un lead real en SQLite
```

---

## Fase M9 — Anti-dup 3 capas + Ledger 3 tablas (4h)

**Objetivo**: Reducir anti-dup de 5 a 3 capas y Ledger de 7 a 3 tablas.

### Tareas

1. **Eliminar capas anti-dup innecesarias**:
```bash
rm src/hat/level1_orchestrator/anti_duplication/semantic_dedup.py
mv src/hat/level1_orchestrator/anti_duplication/circuit_breaker.py src/hat/level4_workers/circuit_breaker.py
```

2. **Actualizar `cascade.py`** para usar solo 3 capas:
```python
def _build_layer_sequence(self, ...):
    return [
        ("exact_match", lambda: self._exact_match.check(intent_hash)),
        ("idempotency", lambda: self._idempotency.check(intent_hash)),
        ("ttl_freshness", lambda: self._ttl_freshness.check(intent_hash, user_id, session_id)),
    ]
```

3. **Mejorar `ttl_freshness.py`**:
   - TTL default = 2s (no 5s)
   - Filtrar por `intent_hash` (no por sesión completa)
   - Eliminar cache en memoria por sesión

4. **Reducer Ledger a 3 tablas** — actualizar `schema.sql`:
```sql
-- ELIMINAR: hat_plan, hat_dispatch_registry, hat_agent_cards, hat_sessions
-- MANTENER: hat_facts, hat_hypotheses, hat_progress
```

5. **Actualizar `repository.py`**:
   - Eliminar métodos de tablas muertas
   - Añadir columna `intent_hash` y `ttl_expires_at` a `hat_progress` (reemplaza `hat_dispatch_registry`)

6. **Actualizar `ovc_bridge.py`**:
   - Eliminar `_load_plan`, `_load_agent_cards` (las cards se generan en memoria al startup)
   - Mantener `_load_facts`, `_load_hypotheses`

7. **Migración DB**: crear script `scripts/migrate_hat_v2.sql` que:
   - Hace backup de tablas a eliminar
   - Añade columnas nuevas a `hat_progress`
   - Migra datos de `hat_dispatch_registry` → `hat_progress`

### Criterio de salida
- 3 capas anti-dup funcionando (exact_match, idempotency, ttl_freshness)
- 3 tablas en Ledger (facts, hypotheses, progress)
- TTL Freshness no rompe UX
- Migración DB aplicada sin pérdida de datos

---

## Fase M10 — Tests E2E + lanzar api_v2 en prod (12h)

**Objetivo**: Tests end-to-end reales con tools, y lanzar FastAPI v2 + HAT en producción.

### Tareas

1. **Crear tests E2E reales** (con side effects en SQLite):
```python
# src/tests/hat/e2e/test_operaciones_create_lead.py
def test_create_lead_e2e():
    """E2E: usuario pide 'crear lead Juan' → lead se crea en SQLite."""
    hat_router = get_hat_router()
    result = hat_router.handle(
        user_id="test_user",
        session_id="test_session",
        message="crear lead Juan email juan@example.com",
    )
    assert result["status"] == "completed"
    assert result["domain"] == "operaciones"
    # Verificar side effect en DB
    db = DatabaseManager()
    leads = db.fetchall("SELECT * FROM leads WHERE name = ?", ("Juan",))
    assert len(leads) == 1
    assert leads[0]["email"] == "juan@example.com"
```

Replicar para:
- `test_operaciones_create_invoice.py`
- `test_operaciones_add_product.py`
- `test_comunicaciones_send_email.py`
- `test_datos_auto_create_collection.py`
- `test_datos_auto_run_python.py`
- `test_e2e_full_dispatch.py` (chain completa N1→N2→N3→N4→N5)

2. **Lanzar FastAPI v2 en producción**:
   - En `src/main.py`, lanzar Flask Y FastAPI en procesos paralelos o usar `werkzeug.DispatcherMiddleware`
   - Actualizar `start_server.sh` para lanzar ambos
   - Actualizar `Dockerfile` para exponer ambos puertos (8080 Flask, 8000 FastAPI)

3. **CSRF protection en Flask**:
```bash
pip install flask-wtf
```
```python
# src/web/app.py
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect()
def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SESSION_SECRET
    csrf.init_app(app)
    # ...
```

4. **Cerrar `api_register`** con admin gate:
```python
@bp.route("/api/auth/register", methods=["POST"])
@login_required
@require_role("admin")  # solo admin puede registrar nuevos usuarios
def api_register():
    ...
```

5. **Wire 14 metrics mixins muertos**:
   - `record_workflow_start/end` → `WorkflowEngine.execute()`
   - `record_nlu_result` → `Pipeline.process()`
   - `record_login_attempt` → `auth.py`
   - etc.

6. **Fix Prometheus path**:
   - Añadir ruta `/metrics` (sin auth, con bearer token opcional)
   - Actualizar k8s/helm scrape configs

7. **Documentación final**:
   - Actualizar `README.md` con nueva arquitectura
   - Actualizar `docs/hat/architecture.md`
   - Crear `docs/hat/QUICKSTART.md` con ejemplo end-to-end

### Criterio de salida
- ~50 tests E2E reales pasan (con side effects en SQLite)
- FastAPI v2 sirve en puerto 8000
- `/api/hat/chat` responde 200 en producción
- `/metrics` accesible por Prometheus
- CSRF protection activa
- Registro de usuarios cerrado a admins

---

## 📅 Cronograma Sugerido

| Semana | Fases | Esfuerzo | Entregable |
|---|---|---|---|
| Semana 1 | M1 + M2 + M3 | 10h | Estructura de carpetas lista, tools migradas |
| Semana 2 | M4 + M5 + M6 | 11h | Stubs eliminados, 9 specialists del N3 creados |
| Semana 3 | M7 + M8 | 14h | Workers del N4 + 3 supervisores del N2 + HATRouter del N1 conectados |
| Semana 4 | M9 + M10 | 16h | Anti-dup + Ledger reducidos, E2E + deploy prod |

**Total**: 4 semanas (~51h esfuerzo real)

---

## ✅ Checklist Final

Después de completar M1-M10:

- [ ] `src/core/` contiene toda la infraestructura base
- [ ] `src/orbital/` está separado y limpio
- [ ] **Nivel 1**: `src/hat/level1_orchestrator/` tiene HATRouter funcional apuntando a Orbital
- [ ] **Nivel 2**: `src/hat/level2_supervisors/` tiene 3 supervisores en carpetas independientes (no se conocen)
- [ ] **Nivel 3**: `src/hat/level3_specialists/` tiene 9 specialists con 1 responsabilidad cada uno
- [ ] **Nivel 4**: `src/hat/level4_workers/` tiene ~59 workers auto-generados (más extenso que N3)
- [ ] **Nivel 5**: `src/hat/level5_tools/` tiene 19 tools ZF reales
- [ ] `src/hat/bootstrap.py` inicializa los 5 niveles al startup
- [ ] `/api/hat/chat` responde 200 en producción
- [ ] Web chat usa HATRouter (no NLU directo)
- [ ] Anti-dup tiene 3 capas (no 5)
- [ ] Ledger tiene 3 tablas (no 7)
- [ ] FastAPI v2 lanzada en producción
- [ ] CSRF protection activa
- [ ] 50+ tests E2E reales pasan
- [ ] Métricas Prometheus funcionando
- [ ] `src/agents/` eliminado (migrado a `hat/agents_legacy/`)
- [ ] 14 stubs HAT eliminados
- [ ] `src/tools/` migrado a `hat/level5_tools/`
- [ ] Código neto reducido ~2,495 LOC

---

## 🆘 Rollback Plan

Si algo sale mal en alguna fase:

1. **M1-M3** (mover archivos): `git checkout .` restaura todo
2. **M4-M5** (eliminar stubs): `git revert <commit>` restaura stubs
3. **M6-M8** (factories + supervisors): mantener `git branch hat-v2` separado
4. **M9** (reducir anti-dup): mantener `cascade_old.py` como backup
5. **M10** (E2E + deploy): mantener Flask + NLU legacy corriendo en paralelo

**Estrategia**: cada fase en su propio commit/PR. Si algo se rompe, revertir solo esa fase.

---

## 🎯 Próximos pasos después de M10

1. **Escalar tools**: añadir nuevas tools es trivial (1 entrada en `level5_tools/registry.py`)
2. **Escalar specialists**: añadir nuevo specialist = 1 archivo en `level3_specialists/`
3. **Escalar supervisores**: añadir dominio nuevo (ej: "compliance") = 1 carpeta en `level2_supervisors/`
4. **Mejorar NLU**: integrar Agent Cards de HAT en `IntentClassifier` para mejor routing
5. **Observabilidad**: wire DispatchTracer en tick_router (spans por fase)
6. **Multi-tenant HAT**: bridge `tenant_id` en HAT sessions
7. **Mobile real**: implementar FCM real + sync `_apply_*` methods

---

## 📊 Distribución Final por Nivel

| Nivel | Rol | Archivos | LOC | Independencia |
|---|---|---|---|---|
| **Nivel 1** | Orquestador central Orbital | ~15 | ~1,500 | Conoce N2 |
| **Nivel 2** | 3 sub-orquestadores | 4 | ~250 | NO se conocen entre sí |
| **Nivel 3** | 9 specialists (LA MAGIA) | 12 | ~700 | 1 responsabilidad cada uno |
| **Nivel 4** | ~59 workers (más extenso) | ~65 | ~1,200 | 1+ por specialist |
| **Nivel 5** | 19 tools reales | ~45 | ~6,500 | Base final |
| **TOTAL HAT** | | ~141 | ~10,150 | |
