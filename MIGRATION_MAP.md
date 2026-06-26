# 🗂️ MIGRATION MAP — Mapeo Archivo por Archivo

> **Versión**: 2.0 · **Fecha**: 2026-06-20
> Estructura FINAL: 5 niveles (1-5) con numeración explícita
> Mapeo completo del estado actual → estado final HAT v2

## 🎯 Estructura Final Confirmada

```
src/hat/
├── level1_orchestrator/              ← NIVEL 1: Orbital central
│   ├── tick_router.py                ← HATRouter.handle() — entry point
│   ├── orbital_engine.py             ← Conexión con motor Orbital
│   ├── fsm/                          ← FSM de estados (6 estados)
│   ├── intent/                       ← Hashing sha256 + normalización
│   ├── routing/                      ← Routing por resonancia RCC
│   ├── ledger/                       ← Memoria (3 tablas: facts, hypotheses, progress)
│   ├── anti_duplication/             ← 3 capas anti-doble-llamada
│   ├── observability/                ← OpenTelemetry dispatch tracer
│   └── api/                          ← POST /api/hat/chat
│
├── level2_supervisors/               ← NIVEL 2: 3 sub-orquestadores
│   ├── operaciones/                  ← Carpeta 1 (NO conoce a las otras 2)
│   │   └── supervisor.py
│   ├── comunicaciones/               ← Carpeta 2 (NO conoce a las otras 2)
│   │   └── supervisor.py
│   └── datos_auto/                   ← Carpeta 3 (NO conoce a las otras 2)
│       └── supervisor.py
│
├── level3_specialists/               ← NIVEL 3: 9 specialists (LA MAGIA)
│   ├── operaciones/                  ← 3 specialists
│   │   ├── crm_specialist.py         ← Una sola responsabilidad: CRM
│   │   ├── invoice_specialist.py     ← Una sola responsabilidad: facturación
│   │   └── inventory_specialist.py   ← Una sola responsabilidad: inventario
│   ├── comunicaciones/               ← 3 specialists
│   │   ├── notification_specialist.py  ← Una sola responsabilidad: notifs
│   │   ├── email_specialist.py       ← Una sola responsabilidad: emails
│   │   └── chat_specialist.py        ← Una sola responsabilidad: chats
│   └── datos_auto/                   ← 3 specialists
│       ├── data_specialist.py        ← Una sola responsabilidad: datos
│       ├── api_specialist.py         ← Una sola responsabilidad: APIs
│       └── code_specialist.py        ← Una sola responsabilidad: código
│
├── level4_workers/                   ← NIVEL 4: Workers (más extenso)
│   ├── operaciones/
│   │   ├── crm/                      ← create_lead, list_leads, etc.
│   │   ├── invoice/                  ← create_invoice, mark_paid, etc.
│   │   └── inventory/                ← add_product, update_stock, etc.
│   ├── comunicaciones/
│   │   ├── notification/             ← send_email, send_whatsapp
│   │   ├── email/                    ← send, search, list_labels
│   │   └── chat/                     ← slack_msg, telegram_msg
│   └── datos_auto/
│       ├── data/                     ← insert, query, update
│       ├── api/                      ← request, xml_parse
│       └── code/                     ← run_python, evaluate_rule
│
└── level5_tools/                     ← NIVEL 5: Tools reales (base final)
    ├── business/                     ← crm, invoice, inventory
    ├── payments/                     ← stripe, mercadopago
    ├── communications/               ← notification, gmail, slack, telegram
    ├── data/                         ← data_keeper, api_connector, sheets, drive, postgresql
    └── automation/                   ← code_runner, logic_gate, autopilot, openai, ollama
```

## Convenciones

- ✅ **MOVER SIN CAMBIOS** — el archivo se reubica, código sin modificar
- 🔄 **MOVER + REFACTORIZAR** — el archivo se reubica y se modifica
- 🆕 **NUEVO** — archivo a crear
- ❌ **ELIMINAR** — archivo se borra
- 🔀 **FUSIONAR** — varios archivos se combinan en uno

---

## 1. `src/core/` — Infraestructura base

### Configuración

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/config.py` | 🔄 | `src/core/config/__init__.py` (split en paths.py, secrets.py, services.py, validation.py) |
| `src/container.py` | 🔄 | `src/core/container.py` |
| `src/airgap.py` | ✅ | `src/core/airgap.py` |

### Utils

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/utils/__init__.py` | 🔄 | `src/core/utils/__init__.py` (con `__all__`) |
| `src/utils/logger.py` | 🔄 | `src/core/logging/__init__.py` (merge con logging_config) |
| `src/utils/logging_config.py` | 🔀 | (fusionado en `src/core/logging/__init__.py`) |
| `src/utils/helpers.py` | 🔄 | `src/core/utils/{ids,time,text,templating,numeric,binaries,cron}.py` |
| `src/utils/sql.py` | ✅ | `src/core/db/sql_builder.py` |

### Data layer

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/data/__init__.py` | 🆕 | `src/core/db/__init__.py` |
| `src/data/database_manager.py` | 🔄 | `src/core/db/sqlite_manager.py` (extraer schema a `.sql` files) |
| `src/data/interfaces.py` | ✅ | `src/core/db/interfaces.py` |
| `src/data/settings_repository.py` | ✅ | `src/core/repositories/settings_repository.py` |
| `src/data/user_repository.py` | ✅ | `src/core/repositories/user_repository.py` |
| `src/data/audit_repository.py` | ✅ | `src/core/repositories/audit_repository.py` |
| `src/data/backup_engine.py` | ✅ | `src/core/db/backup_engine.py` |
| `src/data/mongodb_service.py` | ✅ | `src/core/db/mongodb_service.py` |
| `src/data/mongodb_repository.py` | ❌ | (HUÉRFANO — 0 subclases) |
| `src/data/redis_service.py` | ✅ | `src/core/db/redis_service.py` |
| `src/data/marketplace_db.py` | ✅ | `src/marketplace/db.py` (mover al dominio) |

### i18n

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/i18n/__init__.py` | ✅ | `src/core/i18n/__init__.py` |
| `src/i18n/locales/es.py` | ✅ | `src/core/i18n/locales/es.py` |
| `src/i18n/locales/en.py` | ✅ | `src/core/i18n/locales/en.py` |
| `src/i18n/locales/pt_br.py` | ✅ | `src/core/i18n/locales/pt_br.py` |

### Observability

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/observability/__init__.py` | ✅ | `src/core/observability/__init__.py` |
| `src/observability/telemetry.py` | ✅ | `src/core/observability/telemetry.py` |
| `src/observability/telemetry_config.py` | 🔀 | (fusionado en `src/core/observability/tracing.py`) |
| `src/observability/tracing.py` | ✅ | `src/core/observability/tracing.py` |
| `src/observability/alerts.py` | ✅ | `src/core/observability/alerts.py` |
| `src/observability/logging_formatter.py` | ✅ | `src/core/observability/logging.py` (JsonLogFormatter) |
| `src/observability/metrics/__init__.py` | ✅ | `src/core/observability/metrics/__init__.py` |
| `src/observability/metrics/registry.py` | ✅ | `src/core/observability/metrics/registry.py` |
| `src/observability/metrics/auth_metrics.py` | ✅ | `src/core/observability/metrics/auth_metrics.py` |
| `src/observability/metrics/agent_metrics.py` | ✅ | `src/core/observability/metrics/agent_metrics.py` |
| `src/observability/metrics/bpmn_metrics.py` | ✅ | `src/core/observability/metrics/bpmn_metrics.py` |
| `src/observability/metrics/compliance_metrics.py` | ✅ | `src/core/observability/metrics/compliance_metrics.py` |
| `src/observability/metrics/connector_metrics.py` | ✅ | `src/core/observability/metrics/connector_metrics.py` |
| `src/observability/metrics/db_metrics.py` | ✅ | `src/core/observability/metrics/db_metrics.py` |
| `src/observability/metrics/marketplace_metrics.py` | ✅ | `src/core/observability/metrics/marketplace_metrics.py` |
| `src/observability/metrics/mobile_metrics.py` | ✅ | `src/core/observability/metrics/mobile_metrics.py` |
| `src/observability/metrics/nlu_metrics.py` | ✅ | `src/core/observability/metrics/nlu_metrics.py` |
| `src/observability/metrics/partner_metrics.py` | ✅ | `src/core/observability/metrics/partner_metrics.py` |
| `src/observability/metrics/step_metrics.py` | ✅ | `src/core/observability/metrics/step_metrics.py` |
| `src/observability/metrics/sync_metrics.py` | ✅ | `src/core/observability/metrics/sync_metrics.py` |
| `src/observability/metrics/system_metrics.py` | ✅ | `src/core/observability/metrics/system_metrics.py` |
| `src/observability/metrics/tenant_metrics.py` | ✅ | `src/core/observability/metrics/tenant_metrics.py` |
| `src/observability/metrics/workflow_metrics.py` | ✅ | `src/core/observability/metrics/workflow_metrics.py` |

### Security

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/security/__init__.py` | ✅ | `src/core/security/__init__.py` |
| `src/security/mfa.py` | ✅ | `src/core/security/mfa.py` |
| `src/security/key_manager.py` | ✅ | `src/core/security/key_manager.py` |
| `src/security/auth_shared.py` | ✅ | `src/core/security/auth_shared.py` |
| `src/security/rbac.py` | ✅ | `src/core/security/rbac.py` |
| `src/security/encryption.py` | ✅ | `src/core/security/encryption.py` |
| `src/security/vault.py` | ✅ | `src/core/security/vault.py` |
| `src/security/crypto.py` | ✅ | `src/core/security/crypto.py` |
| `src/security/sso.py` | 🔄 | `src/core/security/sso/service.py` (renombrar para evitar colisión) |
| `src/security/sso/__init__.py` | 🔄 | `src/core/security/sso/__init__.py` (eliminar hack importlib) |
| `src/security/sso/provider_manager.py` | ✅ | `src/core/security/sso/provider_manager.py` |
| `src/security/sso/saml.py` | ✅ | `src/core/security/sso/saml.py` |
| `src/security/sso/oidc.py` | ✅ | `src/core/security/sso/oidc.py` |
| `src/security/sso/keycloak.py` | ✅ | `src/core/security/sso/keycloak.py` |
| `src/security/sso/session.py` | ✅ | `src/core/security/sso/session.py` |
| `src/security/sso/routes.py` | ✅ | `src/core/security/sso/routes.py` |
| `src/security/sso/constants.py` | ✅ | `src/core/security/sso/constants.py` |

---

## 2. `src/orbital/` — Motor determinista (sin cambios de carpeta)

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/orbital/__init__.py` | ✅ | `src/orbital/__init__.py` |
| `src/orbital/models.py` | ✅ | `src/orbital/models.py` |
| `src/orbital/ovc.py` | ✅ | `src/orbital/ovc.py` |
| `src/orbital/tor.py` | ✅ | `src/orbital/tor.py` |
| `src/orbital/rcc.py` | ✅ | `src/orbital/rcc.py` |
| `src/orbital/cod.py` | ✅ | `src/orbital/cod.py` |
| `src/orbital/espectro.py` | ✅ | `src/orbital/espectro.py` |
| `src/orbital/engine.py` | ✅ | `src/orbital/engine.py` |
| `src/orbital/context.py` | ✅ | `src/orbital/context.py` |
| `src/orbital/db.py` | ✅ | `src/orbital/db.py` |
| `src/orbital/orbital_repository.py` | ✅ | `src/orbital/orbital_repository.py` |
| `src/orbital/orbital_compiler.py` | ✅ | `src/orbital/orbital_compiler.py` |
| `src/orbital/orbital_adapter.py` | ✅ | `src/orbital/orbital_adapter.py` |
| `src/orbital/benchmarks.py` | 🔄 | `scripts/benchmark_orbital.py` (mover a scripts/) |

---

## 3. `src/hat/` — Arquitectura HAT 5 Niveles

### NIVEL 1 — Orquestador central Orbital

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/hat/__init__.py` | 🔄 | `src/hat/__init__.py` (con `__all__` re-exportando HATRouter) |
| `src/hat/orbital_n0/__init__.py` | ✅ | `src/hat/level1_orchestrator/__init__.py` |
| `src/hat/orbital_n0/tick_router.py` | 🔄 | `src/hat/level1_orchestrator/tick_router.py` (reordenar load_session antes de route_by_orbital) |
| 🆕 | 🆕 | `src/hat/level1_orchestrator/orbital_engine.py` (conexión con motor Orbital) |
| `src/hat/orbital_n0/states.py` | 🔄 | `src/hat/level1_orchestrator/fsm/states.py` (conectar con tick_router) |
| `src/hat/orbital_n0/fsm_disambiguator.py` | 🔄 | `src/hat/level1_orchestrator/fsm/disambiguator.py` |
| 🆕 | 🆕 | `src/hat/level1_orchestrator/fsm/transitions.py` (extraído de states.py) |
| `src/hat/orbital_n0/intent_hasher.py` | 🔄 | `src/hat/level1_orchestrator/intent/hasher.py` + `intent/normalizer.py` (split) |
| 🆕 | 🆕 | `src/hat/level1_orchestrator/routing/orbital_router.py` (extraído de tick_router) |
| 🆕 | 🆕 | `src/hat/level1_orchestrator/routing/keyword_router.py` (fallback) |
| 🆕 | 🆕 | `src/hat/level1_orchestrator/routing/keywords.py` (DOMAIN_KEYWORDS compartido) |
| `src/hat/ledger/__init__.py` | ✅ | `src/hat/level1_orchestrator/ledger/__init__.py` |
| `src/hat/ledger/schema.sql` | 🔄 | `src/hat/level1_orchestrator/ledger/schema.sql` (reducir a 3 tablas) |
| `src/hat/ledger/repository.py` | 🔄 | `src/hat/level1_orchestrator/ledger/repository.py` (eliminar CRUD de tablas muertas) |
| `src/hat/ledger/ovc_bridge.py` | 🔄 | `src/hat/level1_orchestrator/ledger/ovc_bridge.py` (unificar _deterministic_theta) |
| 🆕 | 🆕 | `src/hat/level1_orchestrator/ledger/facts_manager.py` (lógica Facts/Hypotheses) |
| `src/hat/anti_duplication/__init__.py` | ✅ | `src/hat/level1_orchestrator/anti_duplication/__init__.py` |
| `src/hat/anti_duplication/cascade.py` | ✅ | `src/hat/level1_orchestrator/anti_duplication/cascade.py` |
| `src/hat/anti_duplication/exact_match.py` | ✅ | `src/hat/level1_orchestrator/anti_duplication/exact_match.py` |
| `src/hat/anti_duplication/idempotency.py` | ✅ | `src/hat/level1_orchestrator/anti_duplication/idempotency.py` |
| `src/hat/anti_duplication/ttl_freshness.py` | 🔄 | `src/hat/level1_orchestrator/anti_duplication/ttl_freshness.py` (TTL=2s, mismo hash) |
| `src/hat/anti_duplication/semantic_dedup.py` | ❌ | (Jaccard da falsos positivos, sin LLM no aporta) |
| `src/hat/anti_duplication/circuit_breaker.py` | 🔄 | `src/hat/level4_workers/circuit_breaker.py` (per-worker, no global) |
| `src/hat/observability/__init__.py` | ✅ | `src/hat/level1_orchestrator/observability/__init__.py` |
| `src/hat/observability/dispatch_tracer.py` | 🔄 | `src/hat/level1_orchestrator/observability/dispatch_tracer.py` (wire en tick_router) |
| `src/hat/api/__init__.py` | ✅ | `src/hat/level1_orchestrator/api/__init__.py` |
| `src/hat/api/routes.py` | 🔄 | `src/hat/level1_orchestrator/api/routes.py` (montar en api_v2/app.py) |

### NIVEL 2 — 3 Sub-orquestadores (NO se conocen entre sí)

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/hat/supervisors/__init__.py` | ❌ | (eliminar, se reorganiza) |
| `src/hat/supervisors/base.py` | 🔄 | `src/hat/level2_supervisors/base.py` (DomainSupervisor ABC) |
| `src/hat/supervisors/research.py` | ❌ | (dominio arbitrario) |
| `src/hat/supervisors/build.py` | ❌ | (dominio arbitrario) |
| `src/hat/supervisors/operate.py` | ❌ | (dominio arbitrario) |
| 🆕 | 🆕 | `src/hat/level2_supervisors/operaciones/supervisor.py` (OperacionesSupervisor) |
| 🆕 | 🆕 | `src/hat/level2_supervisors/comunicaciones/supervisor.py` (ComunicacionesSupervisor) |
| 🆕 | 🆕 | `src/hat/level2_supervisors/datos_auto/supervisor.py` (DatosAutoSupervisor) |

**Cada supervisor en su propia carpeta** — aisla completamente el código. Ningún supervisor importa de otro supervisor.

### NIVEL 3 — 9 Specialists (LA MAGIA — 1 responsabilidad cada uno)

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/hat/agents/__init__.py` | ❌ | (vaciar, todo migrado) |
| `src/hat/agents/cards.py` | ✅ | `src/hat/level3_specialists/base/cards.py` (AgentCard dataclass) |
| `src/hat/agents/card_publisher.py` | 🔄 | `src/hat/level3_specialists/base/card_publisher.py` (unificar _deterministic_theta) |
| `src/hat/agents/specialists/__init__.py` | ❌ | (eliminar stubs) |
| `src/hat/agents/specialists/web_researcher.py` | ❌ | (stub) |
| `src/hat/agents/specialists/code_generator.py` | ❌ | (stub) |
| `src/hat/agents/specialists/test_engineer.py` | ❌ | (stub) |
| `src/hat/agents/specialists/deploy_agent.py` | ❌ | (stub) |
| `src/hat/agents/specialists/monitor_agent.py` | ❌ | (stub) |
| `src/hat/agents/specialists/log_analyzer.py` | ❌ | (stub) |
| `src/hat/agents/specialists/incident_responder.py` | ❌ | (stub) |
| 🆕 | 🆕 | `src/hat/level3_specialists/base/__init__.py` |
| 🆕 | 🆕 | `src/hat/level3_specialists/base/specialist_agent.py` (SpecialistAgent ABC) |
| 🆕 | 🆕 | `src/hat/level3_specialists/base/worker_resolver.py` (decide qué worker del N4 llamar) |

**9 specialists concretos** (una sola responsabilidad cada uno):

| Specialist | Acción | Nueva ubicación | Responsabilidad única |
|---|---|---|---|
| 🆕 CrmSpecialist | 🆕 | `src/hat/level3_specialists/operaciones/crm_specialist.py` | Gestión de clientes/leads |
| 🆕 InvoiceSpecialist | 🆕 | `src/hat/level3_specialists/operaciones/invoice_specialist.py` | Facturación |
| 🆕 InventorySpecialist | 🆕 | `src/hat/level3_specialists/operaciones/inventory_specialist.py` | Inventario/stock |
| 🆕 NotificationSpecialist | 🆕 | `src/hat/level3_specialists/comunicaciones/notification_specialist.py` | Notificaciones (email+WhatsApp) |
| 🆕 EmailSpecialist | 🆕 | `src/hat/level3_specialists/comunicaciones/email_specialist.py` | Gmail |
| 🆕 ChatSpecialist | 🆕 | `src/hat/level3_specialists/comunicaciones/chat_specialist.py` | Slack + Telegram |
| 🆕 DataSpecialist | 🆕 | `src/hat/level3_specialists/datos_auto/data_specialist.py` | DataKeeper + Sheets + Drive + PostgreSQL |
| 🆕 ApiSpecialist | 🆕 | `src/hat/level3_specialists/datos_auto/api_specialist.py` | ApiConnector |
| 🆕 CodeSpecialist | 🆕 | `src/hat/level3_specialists/datos_auto/code_specialist.py` | CodeRunner + LogicGate + Autopilot + OpenAI + Ollama |

### NIVEL 4 — Workers (más extenso que N3, 1+ por specialist)

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/hat/agents/workers/__init__.py` | ❌ | (eliminar stubs) |
| `src/hat/agents/workers/query_builder.py` | ❌ | (stub) |
| `src/hat/agents/workers/code_writer.py` | ❌ | (stub) |
| `src/hat/agents/workers/test_runner.py` | ❌ | (stub) |
| `src/hat/agents/workers/container_builder.py` | ❌ | (stub) |
| `src/hat/agents/workers/metrics_scraper.py` | ❌ | (stub) |
| `src/hat/agents/workers/log_filter.py` | ❌ | (stub) |
| `src/hat/agents/workers/alert_dispatcher.py` | ❌ | (stub) |
| 🆕 | 🆕 | `src/hat/level4_workers/base/__init__.py` |
| 🆕 | 🆕 | `src/hat/level4_workers/base/tool_worker.py` (ToolWorker ABC) |
| 🆕 | 🆕 | `src/hat/level4_workers/base/worker_factory.py` (auto-genera por introspección) |
| 🆕 | 🆕 | `src/hat/level4_workers/base/registry.py` ((tool, action) → WorkerClass) |
| 🆕 | 🆕 | `src/hat/level4_workers/base/idempotency.py` (hash tool+action+params) |
| 🆕 | 🆕 | `src/hat/level4_workers/circuit_breaker.py` (per-worker) |

**Workers organizados por especialidad** (carpetas por specialist):

| Carpeta | Workers esperados |
|---|---|
| `level4_workers/operaciones/crm/` | CrmCreateLeadWorker, CrmUpdateLeadWorker, CrmListLeadsWorker, CrmAdvanceStageWorker, CrmCloseWonWorker, CrmCloseLostWorker, CrmGetLeadWorker, CrmDeleteLeadWorker, CrmGetStatsWorker (~9 workers) |
| `level4_workers/operaciones/invoice/` | InvoiceCreateWorker, InvoiceMarkPaidWorker, InvoiceMarkOverdueWorker, InvoiceCancelWorker, InvoiceGetWorker, InvoiceListWorker, InvoiceGetOverdueWorker, InvoiceGetStatsWorker (~8 workers) |
| `level4_workers/operaciones/inventory/` | InventoryAddProductWorker, InventoryUpdateStockWorker, InventoryUpdateProductWorker, InventoryGetProductWorker, InventoryListProductsWorker, InventoryDeleteProductWorker, InventoryGetLowStockWorker, InventoryGetStatsWorker (~8 workers) |
| `level4_workers/comunicaciones/notification/` | NotificationSendEmailWorker, NotificationSendWhatsAppWorker, NotificationConfigureWorker, NotificationTestConnectionWorker (~4 workers) |
| `level4_workers/comunicaciones/email/` | EmailSendWorker, EmailSearchWorker, EmailGetMessageWorker, EmailListLabelsWorker (~4 workers) |
| `level4_workers/comunicaciones/chat/` | SlackSendMessageWorker, SlackListChannelsWorker, TelegramSendMessageWorker, TelegramGetUpdatesWorker (~4 workers) |
| `level4_workers/datos_auto/data/` | DataKeeperCreateCollectionWorker, DataKeeperInsertWorker, DataKeeperQueryWorker, DataKeeperUpdateWorker, DataKeeperDeleteWorker, SheetsReadWorker, SheetsWriteWorker, DriveUploadWorker, DriveDownloadWorker, PostgreSQLQueryWorker (~10 workers) |
| `level4_workers/datos_auto/api/` | ApiRequestWorker, ApiXmlParseWorker, ApiXmlGenerateWorker, ApiValidateUrlWorker (~4 workers) |
| `level4_workers/datos_auto/code/` | CodeRunnerRunPythonWorker, CodeRunnerValidateWorker, LogicGateEvaluateRuleWorker, LogicGateValidateExpressionWorker, AutopilotSuggestTemplatesWorker, AutopilotCreateFromTemplateWorker, OpenAIChatWorker, OllamaChatWorker (~8 workers) |

**Total estimado**: ~59 workers (más extenso que los 9 specialists, como pidió el usuario)

### NIVEL 5 — Tools ZF reales (base final)

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/tools/__init__.py` | ❌ | (vaciar, todo migrado a level5_tools) |
| `src/tools/crm/__init__.py` | ✅ | `src/hat/level5_tools/business/crm/__init__.py` |
| `src/tools/crm/service.py` | ✅ | `src/hat/level5_tools/business/crm/service.py` |
| `src/tools/crm/repository.py` | ✅ | `src/hat/level5_tools/business/crm/repository.py` |
| `src/tools/crm/models.py` | ✅ | `src/hat/level5_tools/business/crm/models.py` |
| `src/tools/invoice/__init__.py` | ✅ | `src/hat/level5_tools/business/invoice/__init__.py` |
| `src/tools/invoice/service.py` | ✅ | `src/hat/level5_tools/business/invoice/service.py` |
| `src/tools/invoice/repository.py` | ✅ | `src/hat/level5_tools/business/invoice/repository.py` |
| `src/tools/invoice/models.py` | ✅ | `src/hat/level5_tools/business/invoice/models.py` |
| `src/tools/inventory/__init__.py` | ✅ | `src/hat/level5_tools/business/inventory/__init__.py` |
| `src/tools/inventory/service.py` | ✅ | `src/hat/level5_tools/business/inventory/service.py` |
| `src/tools/inventory/repository.py` | ✅ | `src/hat/level5_tools/business/inventory/repository.py` |
| `src/tools/inventory/models.py` | ✅ | `src/hat/level5_tools/business/inventory/models.py` |
| `src/tools/notification/__init__.py` | ✅ | `src/hat/level5_tools/communications/notification/__init__.py` |
| `src/tools/notification/service.py` | ✅ | `src/hat/level5_tools/communications/notification/service.py` |
| `src/tools/notification/models.py` | ✅ | `src/hat/level5_tools/communications/notification/models.py` |
| `src/tools/code_runner/__init__.py` | ✅ | `src/hat/level5_tools/automation/code_runner/__init__.py` |
| `src/tools/code_runner/service.py` | ✅ | `src/hat/level5_tools/automation/code_runner/service.py` |
| `src/tools/code_runner/sandbox.py` | ✅ | `src/hat/level5_tools/automation/code_runner/sandbox.py` |
| `src/tools/logic_gate/__init__.py` | ✅ | `src/hat/level5_tools/automation/logic_gate/__init__.py` |
| `src/tools/logic_gate/service.py` | ✅ | `src/hat/level5_tools/automation/logic_gate/service.py` |
| `src/tools/data_keeper/__init__.py` | ✅ | `src/hat/level5_tools/data/data_keeper/__init__.py` |
| `src/tools/data_keeper/service.py` | ✅ | `src/hat/level5_tools/data/data_keeper/service.py` |
| `src/tools/data_keeper/repository.py` | ✅ | `src/hat/level5_tools/data/data_keeper/repository.py` |
| `src/tools/data_keeper/models.py` | ✅ | `src/hat/level5_tools/data/data_keeper/models.py` |
| `src/tools/api_connector/__init__.py` | ✅ | `src/hat/level5_tools/data/api_connector/__init__.py` |
| `src/tools/api_connector/service.py` | ✅ | `src/hat/level5_tools/data/api_connector/service.py` |
| `src/tools/api_connector/http_client.py` | ✅ | `src/hat/level5_tools/data/api_connector/http_client.py` |
| `src/tools/api_connector/pagination.py` | ✅ | `src/hat/level5_tools/data/api_connector/pagination.py` |
| `src/tools/api_connector/rate_limiter.py` | ✅ | `src/hat/level5_tools/data/api_connector/rate_limiter.py` |
| `src/tools/api_connector/response_cache.py` | ✅ | `src/hat/level5_tools/data/api_connector/response_cache.py` |
| `src/tools/api_connector/xml_processor.py` | ✅ | `src/hat/level5_tools/data/api_connector/xml_processor.py` |
| `src/tools/api_connector/webhooks.py` | ✅ | `src/hat/level5_tools/data/api_connector/webhooks.py` |
| `src/tools/autopilot/__init__.py` | ✅ | `src/hat/level5_tools/automation/autopilot/__init__.py` |
| `src/tools/autopilot/service.py` | ✅ | `src/hat/level5_tools/automation/autopilot/service.py` |
| `src/tools/integrations/__init__.py` | ✅ | `src/hat/level5_tools/payments/__init__.py` (split por tipo) |
| `src/tools/integrations/gmail_service.py` | ✅ | `src/hat/level5_tools/communications/gmail_service.py` |
| `src/tools/integrations/slack_service.py` | ✅ | `src/hat/level5_tools/communications/slack_service.py` |
| `src/tools/integrations/whatsapp_service.py` | 🔀 | (fusionar en `communications/notification/service.py`) |
| `src/tools/integrations/telegram_service.py` | ✅ | `src/hat/level5_tools/communications/telegram_service.py` |
| `src/tools/integrations/sheets_service.py` | ✅ | `src/hat/level5_tools/data/sheets_service.py` |
| `src/tools/integrations/drive_service.py` | ✅ | `src/hat/level5_tools/data/drive_service.py` |
| `src/tools/integrations/stripe_service.py` | ✅ | `src/hat/level5_tools/payments/stripe_service.py` |
| `src/tools/integrations/mercadopago_service.py` | ✅ | `src/hat/level5_tools/payments/mercadopago_service.py` |
| `src/tools/integrations/openai_service.py` | ✅ | `src/hat/level5_tools/automation/openai_service.py` |
| `src/tools/integrations/ollama_service.py` | ✅ | `src/hat/level5_tools/automation/ollama_service.py` |
| `src/tools/integrations/postgresql_service.py` | ✅ | `src/hat/level5_tools/data/postgresql_service.py` |
| 🆕 | 🆕 | `src/hat/level5_tools/__init__.py` |
| 🆕 | 🆕 | `src/hat/level5_tools/registry.py` (registro central) |
| 🆕 | 🆕 | `src/hat/level5_tools/adapter.py` (tools → Specialists/Workers) |

**Categorías finales en Nivel 5**:
- `business/` → crm, invoice, inventory (3 tools)
- `payments/` → stripe, mercadopago (2 tools)
- `communications/` → notification, gmail, slack, telegram (4 tools)
- `data/` → data_keeper, api_connector, sheets, drive, postgresql (5 tools)
- `automation/` → code_runner, logic_gate, autopilot, openai, ollama (5 tools)

**Total**: 19 tools reales en Nivel 5

---

## 4. Módulos no-HAT (sin cambios de carpeta)

| Carpeta | Acción | Notas |
|---|---|---|
| `src/events/` | ✅ | Sin cambios |
| `src/nlu/` | ✅ | Sin cambios (alimentado por HAT) |
| `src/workflow/` | ✅ | Sin cambios (elimina `durable/` y `fork_handler.py` shim) |
| `src/connectors/` | ✅ | Sin cambios (40+ connectors) |
| `src/bpmn/` | ✅ | Sin cambios (usar defusedxml) |
| `src/tenant/` | ✅ | Sin cambios |
| `src/license/` | ✅ | Sin cambios (Ed25519 sólido) |
| `src/compliance/` | ✅ | Sin cambios |
| `src/marketplace/` | ✅ | Sin cambios (wire MarketplaceService a router) |
| `src/partnership/` | ✅ | Sin cambios |
| `src/sync/` | ✅ | Sin cambios |
| `src/mobile/` | ✅ | Sin cambios |
| `src/web/` | ✅ | Sin cambios (chat usa HATRouter) |
| `src/api_v2/` | ✅ | Sin cambios (LANZAR en prod!) |
| `src/cli/` | ✅ | Sin cambios |
| `src/installer/` | ✅ | Sin cambios (mover de repo root a `src/`) |

### Detalles `src/workflow/`

| Archivo | Acción | Nueva ubicación |
|---|---|---|
| `src/workflow/durable/__init__.py` | ❌ | (código muerto, nunca activado) |
| `src/workflow/durable/events.py` | ❌ | (eliminar) |
| `src/workflow/durable/checkpoints.py` | ❌ | (eliminar) |
| `src/workflow/durable/heartbeat.py` | ❌ | (eliminar) |
| `src/workflow/durable/cleanup.py` | ❌ | (eliminar) |
| `src/workflow/durable_models.py` | ❌ | (eliminar) |
| `src/workflow/fork_handler.py` | ❌ | (shim huérfano, 0 importers directos) |
| Resto | ✅ | Sin cambios |

---

## 5. `src/agents/` y `src/sdk/` — Limpieza profunda

### `src/agents/` (DEPRECADO)

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/agents/__init__.py` | 🔄 | `src/hat/agents_legacy/__init__.py` (solo BaseAgent, MultiAgentOrchestrator, AgentRuntime, TokenCostTracker) |
| `src/agents/base.py` | ✅ | `src/hat/agents_legacy/base.py` |
| `src/agents/orchestrator.py` | ✅ | `src/hat/agents_legacy/orchestrator.py` |
| `src/agents/runtime.py` | ✅ | `src/hat/agents_legacy/runtime.py` |
| `src/agents/memory.py` | ❌ | (HUÉRFANO + fake embeddings) |
| `src/agents/token_tracking.py` | 🔄 | `src/core/observability/token_tracking.py` (fix TypeError) |
| `src/agents/tools.py` | ❌ | (HUÉRFANO, 0 callers) |

### `src/sdk/`

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/sdk/__init__.py` | 🔄 | `src/sdk/__init__.py` (eliminar re-exports muertos) |
| `src/sdk/base.py` (shim) | ✅ | `src/sdk/base.py` |
| `src/sdk/base/__init__.py` | ✅ | `src/sdk/base/__init__.py` |
| `src/sdk/base/configs.py` | ✅ | `src/sdk/base/configs.py` |
| `src/sdk/base/connector.py` | ✅ | `src/sdk/base/connector.py` |
| `src/sdk/schema.py` | ✅ | `src/sdk/schema.py` |
| `src/sdk/http_client.py` | ✅ | `src/sdk/http_client.py` |
| `src/sdk/exceptions.py` | ✅ | `src/sdk/exceptions.py` |
| `src/sdk/registry.py` | ✅ | `src/sdk/registry.py` |
| `src/sdk/decorators.py` | ❌ | (shim, eliminar) |
| `src/sdk/decorators/__init__.py` | ❌ | (0 usos en cualquier connector) |
| `src/sdk/decorators/action.py` | ❌ | (0 usos) |
| `src/sdk/decorators/retry.py` | ❌ | (0 usos) |
| `src/sdk/decorators/circuit.py` | ❌ | (0 usos) |
| `src/sdk/decorators/ratelimit.py` | ❌ | (0 usos) |
| `src/sdk/decorators/metrics.py` | ❌ | (0 usos) |
| `src/sdk/decorators/validation.py` | ❌ | (0 usos) |
| `src/sdk/decorators/_helpers.py` | ❌ | (0 usos) |
| `src/sdk/auth/__init__.py` | 🔄 | `src/sdk/auth/__init__.py` (solo AuthProvider, APIKeyAuth, CustomAuth) |
| `src/sdk/auth/base.py` | 🔄 | `src/sdk/auth/base.py` (añadir `get_credentials()` abstract) |
| `src/sdk/auth/api_key.py` | ✅ | `src/sdk/auth/api_key.py` |
| `src/sdk/auth/custom.py` | ✅ | `src/sdk/auth/custom.py` |
| `src/sdk/auth/basic.py` | ❌ | (0 instanciaciones) |
| `src/sdk/auth/oauth1.py` | ❌ | (0 instanciaciones) |
| `src/sdk/auth/oauth2.py` | ❌ | (0 instanciaciones) |
| `src/sdk/auth/mtls.py` | ❌ | (0 instanciaciones) |

---

## 6. Otros archivos

| Archivo actual | Acción | Nueva ubicación |
|---|---|---|
| `src/schemas/__init__.py` | ✅ | `src/core/schemas/__init__.py` (o eliminar si está vacío) |
| `src/main.py` | 🔄 | `src/main.py` (lanzar api_v2 en prod, montar HAT) |
| `src/tests/__init__.py` | ✅ | `src/tests/__init__.py` |
| `src/tests/conftest.py` | ✅ | `src/tests/conftest.py` |
| `src/tests/test_*.py` (todos) | ✅ | `src/tests/test_*.py` (ajustar imports) |
| `src/tests/hat/test_*.py` (todos) | 🔄 | `src/tests/hat/{level1,level2,level3,level4,level5,e2e}/test_*.py` (reorganizar) |

### Frontend y assets

| Carpeta | Acción |
|---|---|
| `frontend/` | ✅ Sin cambios |
| `scripts/` | ✅ Sin cambios (añadir `benchmark_orbital.py`) |
| `deploy/` | ✅ Sin cambios |
| `docs/` | ✅ Sin cambios |
| `installer/` (repo root) | 🔄 Mover a `src/installer/` |
| `helm/` (repo root) | 🔄 Mover a `deploy/helm/` |

---

## 📊 Resumen de Cambios

### Archivos a eliminar (~5,800 LOC)

| Categoría | Archivos | LOC |
|---|---|---|
| HAT stubs (workers N4 viejos) | 7 | ~470 |
| HAT stubs (specialists N3 viejos) | 7 | ~440 |
| HAT supervisores arbitrarios (N2 viejos) | 3 | ~125 |
| `agents/memory.py` + `tools.py` | 2 | ~1,113 |
| `sdk/decorators/*` | 8 | ~390 |
| `sdk/auth/{basic,oauth1,oauth2,mtls}.py` | 4 | ~500 |
| `workflow/durable/*` | 6 | ~640 |
| `workflow/fork_handler.py` (shim) | 1 | 20 |
| `data/mongodb_repository.py` (huérfano) | 1 | 229 |
| `tools/integrations/whatsapp_service.py` (huérfano) | 1 | 587 |
| `web/api_versioning.py` (huérfano) | 1 | 267 |
| `hat/anti_duplication/semantic_dedup.py` | 1 | 114 |
| **TOTAL ELIMINABLE** | **42** | **~4,895** |

### Archivos nuevos a crear (~2,800 LOC)

| Categoría | Archivos | LOC estimada |
|---|---|---|
| `level2_supervisors/` (3 supervisores + base) | 4 | ~250 |
| `level3_specialists/` (base + 9 concretos) | 12 | ~700 |
| `level4_workers/` (base + factory + registry + idempotency + circuit_breaker) | 5 | ~300 |
| `level5_tools/` (registry + adapter) | 2 | ~150 |
| `level1_orchestrator/` reorganización (fsm/transitions, intent/normalizer, routing/, ledger/facts_manager) | 6 | ~400 |
| `core/config/` split | 4 | ~200 |
| `core/utils/` split | 7 | ~250 |
| `hat/bootstrap.py` (orquesta 5 niveles) | 1 | ~150 |
| **TOTAL NUEVO** | **41** | **~2,400** |

### Resultado neto

- **Eliminados**: ~4,895 LOC
- **Nuevos**: ~2,400 LOC
- **Neto**: −2,495 LOC (más simple y mantenible)
- **Tests**: ~130 tests de stubs a reescribir como E2E reales

### Distribución final por nivel

| Nivel | Archivos | LOC estimada | Rol |
|---|---|---|---|
| **Nivel 1** (Orquestador Orbital) | ~15 | ~1,500 | 1 orquestador central, visión global |
| **Nivel 2** (3 supervisores) | 4 | ~250 | 3 sub-orquestadores independientes |
| **Nivel 3** (9 specialists) | 12 | ~700 | LA MAGIA — cada uno 1 responsabilidad |
| **Nivel 4** (~59 workers) | ~65 | ~1,200 | Más extenso, 1+ por specialist |
| **Nivel 5** (19 tools) | ~45 | ~6,500 | Base final, tools reales |
| **TOTAL HAT** | ~141 | ~10,150 | |

---

## ✅ Próximo paso

Ver `IMPLEMENTATION_PLAN.md` para las 10 fases ejecutables de migración.
