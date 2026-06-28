# Inventario de Rutas Huérfanas — Zenic-Flujo

> **Fase 3 del PLAN_CORRECCIONES** — documentación sin eliminación (decisión del usuario)
> **Fecha**: 2026-06-22
> **Metodología**: verificación caller por caller incluyendo template literals `${...}` (no solo strings literales)

---

## Resumen ejecutivo

- **Total rutas backend**: 182 (139 Flask + 43 FastAPI v2 efectivas, tras eliminar nlu.py v2 en Fase 1)
- **Rutas con caller frontend**: 79
- **Rutas huérfanas del frontend** (pero con callers internos/tests/scripts): 65 — **se mantienen**
- **Rutas candidatas a eliminación** (0 callers en frontend, backend, scripts, e2e, tests): **38** — **documentadas aquí para futura eliminación**

**Decisión del usuario (sesión 7)**: NO eliminar por ahora. Este documento cataloga las 38 rutas candidatas con justificación para una futura fase de limpieza.

---

## Categoría A: Rutas Flask con params dinámicos sin caller (5 rutas)

Ubicadas en `src/web/blueprints/{compliance.py, partnership.py}`. El frontend no las llama (ni literal ni con template literals) y no hay callers internos.

| Ruta | Blueprint | Línea | Caller FE | Caller BE | Script | E2E | Test | Justificación eliminación futura |
|---|---|---|---|---|---|---|---|---|
| `/api/compliance/controls/<control_id>/status` | compliance.py | — | 0 | 0 | 0 | 0 | 0 | Sin callers; el frontend usa `/api/compliance/overview` |
| `/api/compliance/typeii/periods/<period_id>/bridge-letter` | compliance.py | — | 0 | 0 | 0 | 0 | 0 | Sin callers; función de bridge letter no expuesta en UI |
| `/api/compliance/typeii/periods/<period_id>/tests` | compliance.py | — | 0 | 0 | 0 | 0 | 0 | Sin callers; tests de periodos SOC2 no expuestos en UI |
| `/api/queue/<int:item_id>/retry` | admin.py | — | 0 | 0 | 0 | 0 | 0 | Sin callers; el frontend no tiene UI de queue retry individual |
| `/api/partners/benefits/<benefit_id>/revoke` | partnership.py | — | 0 | 0 | 0 | 0 | 0 | Sin callers; revoke de benefits no expuesto en PartnersPage |

---

## Categoría B: Rutas workflows Flask sin caller frontend (5 rutas)

Ubicadas en `src/web/blueprints/workflows.py`. El frontend usa otras rutas de workflows (list, get, put, delete, activate via `<action>`, retry, environments, versions, promote, promotions) pero estas específicas no.

| Ruta | Caller FE | Caller BE | Justificación eliminación futura |
|---|---|---|---|
| `/api/workflows/<int:wf_id>/history` | 0 | 0 | Sin callers; el frontend no muestra historial de ejecuciones |
| `/api/workflows/<int:wf_id>/history/<int:exec_id>` | 0 | 0 | Sin callers; detalle de ejecución no expuesto |
| `/api/workflows/<int:wf_id>/export` | 0 | 0 | Sin callers; el frontend no tiene botón export workflow |
| `/api/workflows/<int:wf_id>/execute` | 0 | 0 | Sin callers; la ejecución es vía `/api/workflows/<id>/<action>` |
| `/api/workflows/<int:wf_id>/activate` | 0 | 0 | Sin callers; activate se hace vía `/api/workflows/<id>/<action>` con action=activate |
| `/api/workflows/<int:wf_id>/pause` | 0 | 0 | Sin callers; pause se hace vía `<action>` genérica |

**Nota**: `/api/workflows/import` y `/api/workflows/<id>/retry` SÍ se mantienen (caller interno BE=1 y frontend respectivamente).

---

## Categoría C: Router FastAPI v2 `/api/v2/agents/*` completo (10 rutas)

Ubicadas en `src/api_v2/routers/agents.py`. Depende de `agents_legacy` (deprecated, ver ADR-0001). Ningún frontend las llama.

| Ruta | Caller FE | Caller BE | Justificación |
|---|---|---|---|
| `/api/v2/agents/list` | 0 | 0 | Sin callers; agents_legacy deprecated |
| `/api/v2/agents/orchestrate` | 0 | 0 | Sin callers; HAT v2 reemplaza esta función |
| `/api/v2/agents/runtime/stats` | 0 | 0 | Sin callers |
| `/api/v2/agents/spawn` | 0 | 0 | Sin callers |
| `/api/v2/agents/token-usage/budget` | 0 | 0 | Sin callers |
| `/api/v2/agents/token-usage/daily` | 0 | 0 | Sin callers |
| `/api/v2/agents/token-usage/summary` | 0 | 0 | Sin callers |
| `/api/v2/agents/{agent_id}/pause` | 0 | 0 | Sin callers |
| `/api/v2/agents/{agent_id}/resume` | 0 | 0 | Sin callers |
| `/api/v2/agents/{agent_id}/run` | 0 | 0 | Sin callers |

**Excepción**: `/api/v2/agents/{agent_id}` (GET detalle) tiene BE=1 caller interno — se mantiene.

**Recomendación**: cuando se elimine `agents_legacy` (ver ADR-0001), eliminar este router completo.

---

## Categoría D: Router FastAPI v2 `/api/v2/bpmn/*` completo (7 rutas)

Ubicadas en `src/api_v2/routers/bpmn.py`. Sin callers en frontend, backend, scripts, e2e, o tests.

| Ruta | Caller FE | Caller BE | Test | Justificación |
|---|---|---|---|---|
| `/api/v2/bpmn/processes` | 0 | 0 | 0 | Sin callers; el frontend usa `/api/workflows/*` (Flask) |
| `/api/v2/bpmn/processes/{process_id}` | 0 | 0 | 0 | Sin callers |
| `/api/v2/bpmn/convert/{process_id}` | 0 | 0 | 0 | Sin callers; conversión BPMN→workflow no expuesta |
| `/api/v2/bpmn/export/{process_id}` | 0 | 0 | 0 | Sin callers |
| `/api/v2/bpmn/import` | 0 | 0 | 0 | Sin callers |
| `/api/v2/bpmn/validate` | 0 | 0 | 0 | Sin callers |

**Recomendación**: eliminar el router completo `src/api_v2/routers/bpmn.py` (170 LOC) + su `include_router` en `app.py:365`.

---

## Categoría E: Router FastAPI v2 `/api/v2/compliance/*` completo (10 rutas)

Ubicadas en `src/api_v2/routers/compliance.py`. Sin callers en frontend. El frontend usa `/api/compliance/overview` (Flask), no la v2.

| Ruta | Caller FE | Caller BE | Test | Justificación |
|---|---|---|---|---|
| `/api/v2/compliance/audit` | 0 | 0 | 0 | Sin callers; Flask `/api/compliance/audit` sí se usa internamente |
| `/api/v2/compliance/controls` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/controls/{control_id}/status` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/evidence` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/policies` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/policies/{policy_id}/approve` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/report` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/score` | 0 | 0 | 0 | Sin callers |
| `/api/v2/compliance/stats` | 0 | 0 | 0 | Sin callers |

**Recomendación**: eliminar el router completo `src/api_v2/routers/compliance.py` (313 LOC) + su `include_router` en `app.py:366`.

---

## Categoría F: Rutas FastAPI v2 CRM/Inventory/Invoices huérfanas (11 rutas)

### CRM (6 rutas) — `src/api_v2/routers/crm.py`
El frontend usa `/api/v2/crm/stats` (MiNegocioPage) pero NO las rutas CRUD de clients/leads.

| Ruta | Caller FE | Justificación |
|---|---|---|
| `/api/v2/crm/clients` | 0 | Sin callers; el frontend usa `/api/tools/crm/leads` (Flask) |
| `/api/v2/crm/clients/{client_id}` | 0 | Sin callers |
| `/api/v2/crm/leads` | 0 | Sin callers; el frontend usa `/api/tools/crm/leads` (Flask) |
| `/api/v2/crm/leads/{lead_id}` | 0 | Sin callers |
| `/api/v2/crm/leads/{lead_id}/advance` | 0 | Sin callers; el frontend usa `/api/tools/crm/leads/{id}/advance` (Flask) |
| `/api/v2/crm/leads/{lead_id}/convert-to-invoice` | 0 | Sin callers |

### Inventory (3 rutas) — `src/api_v2/routers/inventory.py`
El frontend usa `/api/v2/inventory/stats` (MiNegocioPage) pero NO las rutas CRUD de products.

| Ruta | Caller FE | Justificación |
|---|---|---|
| `/api/v2/inventory/products` | 0 | Sin callers; el frontend usa `/api/tools/inventory/products` (Flask) |
| `/api/v2/inventory/products/{product_id}` | 0 | Sin callers |
| `/api/v2/inventory/products/{product_id}/stock` | 0 | Sin callers |

### Invoices (3 rutas) — `src/api_v2/routers/invoices_v2.py`
El frontend usa `/api/v2/invoices/stats` (MiNegocioPage) pero NO las rutas CRUD.

| Ruta | Caller FE | Caller BE | Test | Justificación |
|---|---|---|---|---|
| `/api/v2/invoices/overdue` | 0 | 0 | 0 | Sin callers |
| `/api/v2/invoices/{invoice_id}/cancel` | 0 | 0 | 0 | Sin callers; el frontend usa `/api/tools/invoice/{id}/cancel` (Flask) |
| `/api/v2/invoices/{invoice_id}/mark-paid` | 0 | 0 | 0 | Sin callers; el frontend usa `/api/tools/invoice/{id}/pay` (Flask) |

**Recomendación**: mantener los routers `crm.py`, `inventory.py`, `invoices_v2.py` porque tienen rutas `/stats` que el frontend SÍ usa. Eliminar solo los handlers CRUD huérfanos.

---

## Rutas que se MANTIENEN (justificadas, NO eliminar)

### Rutas Flask con callers internos backend (mantener)
- `/api/admin/metrics/prometheus` (BE=1) — scraper Prometheus
- `/api/compliance/{audit,controls,gdpr/*,hipaa/*,policies,report,typeii/periods,typeii/subservices}` (BE>0) — gestión compliance interna
- `/api/dead-letter/notify/<id>` (BE=1) — webhook interno
- `/api/marketplace/stats` (BE=1) — stats internas
- `/api/queue/{enqueue,cleanup}` (BE=1) — callers internos
- `/api/sync/{import,receive}` (BE=1) — sync interno
- `/api/reports/audit/<fmt>` (BE=1, Script=2) — export auditoría desde scripts
- `/api/workflows/<id>/<action>` (BE=52) — ruta genérica usada masivamente
- `/api/workflows/import` (BE=1) — caller interno

### Rutas Flask con callers frontend dinámicos (mantener)
- `/api/integrations/<name>/{configure,test,disconnect,status}` — IntegrationsPage
- `/api/marketplace/connectors/<name>/{install,uninstall}` y `/connectors/<name>` — Plugins
- `/api/partners/<partner_id>/{approve,promote}` — PartnersPage
- `/api/dead-letter/<id>/{retry,discard}` — DeadLetterTab
- `/api/admin/alerts/<id>/resolve` — AlertsTab
- `/api/tools/crm/leads/<id>/{advance}` y `/leads/<id>` — CrmPage
- `/api/tools/inventory/products/<id>` — InventoryPage
- `/api/tools/invoice/<id>/{pay,cancel}` — InvoicesPage
- `/api/workflows/<id>/{retry,environments,environments/<env>,versions,versions/<n>/rollback,promote,promotions}` — Editor/Workflows/EnvironmentsTab/PromotionDialog

### Rutas FastAPI v2 con callers (mantener)
- `/api/v2/crm/stats` — MiNegocioPage
- `/api/v2/inventory/stats` — MiNegocioPage
- `/api/v2/invoices/stats` — MiNegocioPage
- `/api/v2/invoices/` (BE=2, Test=1) — ruta raíz invoices
- `/api/v2/fiscal/{countries,issue,cancel,pdf,status}` — FacturacionElectronicaPage
- `/api/v2/agents/{agent_id}` (BE=1) — detalle agente
- Routers `tenants`, `marketplace`, `connectors`, `auth_routes`, `workflows` v2 — API pública para integraciones

---

## Plan de eliminación futuro (cuando el usuario decida)

### Fase de eliminación rápida (bajo riesgo)
1. Eliminar router `bpmn.py` completo (Categoría D, 170 LOC) — 0 callers en todo el repo
2. Eliminar router `compliance.py` v2 completo (Categoría E, 313 LOC) — 0 callers en todo el repo
3. Eliminar handlers CRUD huérfanos de `crm.py`, `inventory.py`, `invoices_v2.py` (Categoría F) — mantener `/stats`

### Fase de eliminación media (riesgo moderado)
4. Eliminar 5 rutas Flask workflows huérfanas (Categoría B) — verificar que no hay scripts externos
5. Eliminar 5 rutas Flask con params huérfanas (Categoría A) — compliance/queue/partners

### Fase de eliminación diferida (depende de ADR-0001)
6. Cuando se elimine `agents_legacy`, eliminar router `agents.py` v2 completo (Categoría C, 249 LOC)

### Verificación previa a cualquier eliminación
- Confirmar que no hay consumidores externos (SDK, móvil, partners) llamando estas rutas
- Para rutas FastAPI v2: revisar logs de acceso en producción si están disponibles
- Para rutas Flask: verificar que no hay scripts de cron/CI que las llamen

---

## Métricas del inventario

| Métrica | Valor |
|---|---|
| Total rutas backend | 182 |
| Rutas con caller frontend | 79 |
| Rutas huérfanas del frontend pero con callers internos | 65 |
| **Rutas candidatas a eliminación (0 callers)** | **38** |
| - Categoría A (Flask params) | 5 |
| - Categoría B (Flask workflows) | 5 |
| - Categoría C (FastAPI agents v2) | 10 |
| - Categoría D (FastAPI bpmn v2) | 7 |
| - Categoría E (FastAPI compliance v2) | 10 |
| - Categoría F (FastAPI CRM/Inv/Inv v2) | 11 |
| LOC eliminables (estimado) | ~1,200 LOC |
