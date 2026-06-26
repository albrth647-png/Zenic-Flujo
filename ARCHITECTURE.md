# 🏗️ HAT-ORBITAL v2 — Arquitectura del Proyecto

> **Versión**: 2.0 · **Fecha**: 2026-06-20
> **Estado**: Plan maestro de reorganización

## 📐 Visión General

El proyecto Zenic-Flujo se reorganiza completamente dentro de la arquitectura HAT de **5 niveles**. Todo el código existente se redistribuye sin perder funcionalidad — solo cambia su ubicación y relación con los demás módulos.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NIVEL 0 — HATRouter (Orquestador)                │
│  FSM Orbital + Anti-Dup + Ledger + Intent Hasher + Routing RCC     │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│              NIVEL 1 — Domain Supervisors (6 dominios)              │
│  ventas · facturacion · inventario · comunicaciones · datos · auto  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│         NIVEL 2 — Specialist Agents (1 por tool, auto-gen)          │
│  CrmSpecialist · InvoiceSpecialist · InventorySpecialist · ...      │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│         NIVEL 3 — Tool Workers (1 por método, auto-gen)             │
│  CrmCreateLeadWorker · InvoiceMarkPaidWorker · ... (~58 workers)    │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────────┐
│         NIVEL 4 — Tools ZF (13+ herramientas reales)                │
│  crm · invoice · inventory · notification · code_runner · ...       │
└─────────────────────────────────────────────────────────────────────┘
```

## 🎯 Principios de Diseño

1. **Un solo orquestador** — `HATRouter` en N0 es el único punto de entrada
2. **Auto-generación** — Specialists (N2) y Workers (N3) se generan por introspección de tools (N4)
3. **Aislamiento por dominio** — Cada supervisor N1 no conoce a los demás
4. **Dirección de dependencias** — Los niveles solo conocen a su inferior directo
5. **Orbital compartido** — `OrbitalContext` singleton cruza todos los niveles
6. **Sin MCP ni actor model** — Stack ligero Python + SQLite + ORBITAL (offline)

## 📁 Estructura Completa

```
zenic-flujo/
├── src/
│   │
│   ├── core/                              ← Infraestructura base
│   │   ├── __init__.py
│   │   ├── config/                        ← Configuración global
│   │   │   ├── __init__.py
│   │   │   ├── paths.py                   ← Paths y constantes
│   │   │   ├── secrets.py                 ← SESSION_SECRET, LICENSE_SECRET_KEY
│   │   │   ├── services.py                ← SMTP, Ollama, web config
│   │   │   └── validation.py              ← validate_config()
│   │   ├── container.py                   ← IoC container
│   │   ├── airgap.py                      ← Modo offline
│   │   ├── utils/                         ← Helpers genéricos
│   │   │   ├── __init__.py
│   │   │   ├── ids.py                     ← generate_id, generate_secure_token
│   │   │   ├── time.py                    ← now_iso
│   │   │   ├── text.py                    ← truncate, safe_get
│   │   │   ├── templating.py              ← resolve_variables
│   │   │   ├── numeric.py                 ← coerce_numeric
│   │   │   ├── binaries.py                ← resolve_binary
│   │   │   └── cron.py                    ← parse_cron_expression
│   │   ├── db/                            ← Capa de persistencia
│   │   │   ├── __init__.py
│   │   │   ├── sqlite_manager.py          ← DatabaseManager singleton
│   │   │   ├── interfaces.py              ← DatabaseInterface
│   │   │   ├── sql_builder.py             ← build_update_query, validate_identifier
│   │   │   ├── backup_engine.py           ← BackupEngine
│   │   │   └── schema/                    ← SQL files por dominio
│   │   │       ├── core.sql               ← users, settings, audit_log
│   │   │       ├── workflow.sql           ← workflow_definitions, executions
│   │   │       ├── crm.sql                ← leads, lead_activities
│   │   │       ├── invoice.sql            ← invoices
│   │   │       └── ...
│   │   ├── repositories/                  ← CRUD base
│   │   │   ├── __init__.py
│   │   │   ├── user_repository.py
│   │   │   ├── settings_repository.py
│   │   │   └── audit_repository.py
│   │   ├── security/                      ← Auth + Crypto cross-cutting
│   │   │   ├── __init__.py
│   │   │   ├── auth_shared.py             ← verify_password, has_permission
│   │   │   ├── mfa.py                     ← TOTP + recovery codes
│   │   │   ├── rbac.py                    ← RBACManager
│   │   │   ├── key_manager.py             ← KEK + RSA keys
│   │   │   ├── crypto.py                  ← AES-256-GCM
│   │   │   ├── encryption.py              ← EncryptionService
│   │   │   ├── vault.py                   ← SecretVault
│   │   │   └── sso/                       ← SSO providers
│   │   │       ├── __init__.py
│   │   │       ├── service.py             ← SSOService (antes sso.py)
│   │   │       ├── provider_manager.py
│   │   │       ├── saml.py
│   │   │       ├── oidc.py
│   │   │       ├── keycloak.py
│   │   │       ├── session.py
│   │   │       ├── routes.py
│   │   │       └── constants.py
│   │   ├── observability/                 ← Telemetría global
│   │   │   ├── __init__.py
│   │   │   ├── telemetry.py               ← TelemetryService
│   │   │   ├── tracing.py                 ← TracingManager
│   │   │   ├── logging.py                 ← setup_logging, JsonLogFormatter
│   │   │   ├── alerts.py                  ← AlertService
│   │   │   └── metrics/                   ← 15 mixins + registry
│   │   │       ├── __init__.py
│   │   │       ├── registry.py            ← MetricsRegistry
│   │   │       ├── auth_metrics.py
│   │   │       ├── agent_metrics.py
│   │   │       ├── workflow_metrics.py
│   │   │       └── ... (12 más)
│   │   ├── i18n/                          ← Internacionalización
│   │   │   ├── __init__.py                ← t(), set_language()
│   │   │   └── locales/
│   │   │       ├── es.py
│   │   │       ├── en.py
│   │   │       └── pt_br.py
│   │   └── logging/                       ← Logger setup
│   │       └── __init__.py
│   │
│   ├── orbital/                           ← MOTOR DETERMINISTA (separado de HAT)
│   │   ├── __init__.py                    ← Re-export público
│   │   ├── models.py                      ← Dataclasses (VariableOrbital, etc.)
│   │   ├── ovc.py                         ← Pilar 1: Órbita Variable Circular
│   │   ├── tor.py                         ← Pilar 2: Tensión Orbital Recíproca
│   │   ├── rcc.py                         ← Pilar 3: Resonancia Ciclo Cerrado
│   │   ├── cod.py                         ← Pilar 4: Colapso Orbital Determinista
│   │   ├── espectro.py                    ← Pilar 5: Espectro Orbital
│   │   ├── engine.py                      ← OrbitalEngine (coordinador)
│   │   ├── context.py                     ← OrbitalContext (singleton)
│   │   ├── db.py                          ← OrbitalDB (persistencia)
│   │   ├── orbital_repository.py          ← Bridge WorkflowDefinition → Orbital
│   │   ├── orbital_compiler.py            ← Compila texto → orbital
│   │   ├── orbital_adapter.py             ← Adapter tools → orbital
│   │   └── benchmarks.py                  ← Suite benchmarks (mover a scripts/)
│   │
│   ├── hat/                               ← ARQUITECTURA HAT 5 NIVELES
│   │   ├── __init__.py                    ← Re-export público (HATRouter)
│   │   │
│   │   ├── level0_orchestrator/           ← NIVEL 0 — HATRouter
│   │   │   ├── __init__.py
│   │   │   ├── tick_router.py             ← HATRouter.handle() (entry point)
│   │   │   ├── fsm/                       ← FSM del orquestador
│   │   │   │   ├── __init__.py
│   │   │   │   ├── states.py              ← 6 estados (IDLE→ROUTING→…→IDLE)
│   │   │   │   ├── disambiguator.py       ← 4 reglas FSM cuando RCC < 0.15
│   │   │   │   └── transitions.py         ← FORWARD_TRANSITIONS + validación
│   │   │   ├── intent/                    ← Hashing y normalización
│   │   │   │   ├── __init__.py
│   │   │   │   ├── hasher.py              ← sha256(user+session+intent+params)
│   │   │   │   └── normalizer.py          ← lowercase, sin acentos
│   │   │   ├── routing/                   ← Decisión de ruteo
│   │   │   │   ├── __init__.py
│   │   │   │   ├── orbital_router.py      ← Ruteo por resonancia RCC
│   │   │   │   └── keyword_router.py      ← Fallback por keywords ES/EN
│   │   │   ├── ledger/                    ← Memoria estructurada
│   │   │   │   ├── __init__.py
│   │   │   │   ├── schema.sql             ← 3 tablas (facts, hypotheses, progress)
│   │   │   │   ├── repository.py          ← CRUD sobre 3 tablas
│   │   │   │   ├── ovc_bridge.py          ← Bridge Ledger ↔ OVC
│   │   │   │   └── facts_manager.py       ← Lógica de Facts/Hypotheses
│   │   │   ├── anti_duplication/          ← 3 capas anti-doble-llamada
│   │   │   │   ├── __init__.py
│   │   │   │   ├── cascade.py             ← Orquestador
│   │   │   │   ├── exact_match.py         ← Capa 1: hash exacto (LRU 256)
│   │   │   │   ├── idempotency.py         ← Capa 2: en progreso → subscribe
│   │   │   │   └── ttl_freshness.py       ← Capa 3: mismo hash <2s → discard
│   │   │   ├── observability/             ← Trazabilidad HAT
│   │   │   │   └── dispatch_tracer.py     ← OpenTelemetry spans
│   │   │   └── api/                       ← API HAT
│   │   │       └── routes.py              ← POST /api/hat/chat
│   │   │
│   │   ├── level1_supervisors/            ← NIVEL 1 — 6 Domain Supervisors
│   │   │   ├── __init__.py
│   │   │   ├── base.py                    ← DomainSupervisor ABC
│   │   │   ├── ventas.py                  ← VentasSupervisor (CRM)
│   │   │   ├── facturacion.py             ← FacturacionSupervisor (Invoice, pagos)
│   │   │   ├── inventario.py              ← InventarioSupervisor (Inventory)
│   │   │   ├── comunicaciones.py          ← ComunicacionesSupervisor (Notification)
│   │   │   ├── datos.py                   ← DatosSupervisor (DataKeeper, ApiConnector)
│   │   │   └── automatizacion.py          ← AutomatizacionSupervisor (CodeRunner, LogicGate)
│   │   │
│   │   ├── level2_specialists/            ← NIVEL 2 — Specialists (1 por tool)
│   │   │   ├── __init__.py
│   │   │   ├── base.py                    ← SpecialistAgent ABC
│   │   │   ├── factory.py                 ← Genera Specialist por introspección
│   │   │   ├── cards.py                   ← AgentCard dataclass
│   │   │   ├── card_publisher.py          ← Mixin: publish_card()
│   │   │   ├── registry.py                ← Registro de specialists activos
│   │   │   ├── crm_specialist.py          ← Wraps CRMService
│   │   │   ├── invoice_specialist.py
│   │   │   ├── inventory_specialist.py
│   │   │   ├── notification_specialist.py
│   │   │   ├── code_runner_specialist.py
│   │   │   ├── data_keeper_specialist.py
│   │   │   ├── api_connector_specialist.py
│   │   │   ├── logic_gate_specialist.py
│   │   │   ├── autopilot_specialist.py
│   │   │   └── integrations/              ← Specialists para integrations
│   │   │       ├── gmail_specialist.py
│   │   │       ├── slack_specialist.py
│   │   │       ├── whatsapp_specialist.py
│   │   │       ├── telegram_specialist.py
│   │   │       ├── sheets_specialist.py
│   │   │       ├── drive_specialist.py
│   │   │       ├── stripe_specialist.py
│   │   │       ├── mercadopago_specialist.py
│   │   │       ├── openai_specialist.py
│   │   │       ├── ollama_specialist.py
│   │   │       └── postgresql_specialist.py
│   │   │
│   │   ├── level3_workers/                ← NIVEL 3 — Workers (1 por método)
│   │   │   ├── __init__.py
│   │   │   ├── base.py                    ← ToolWorker ABC
│   │   │   ├── factory.py                 ← Genera Worker por introspección
│   │   │   ├── registry.py                ← (tool, action) → WorkerClass
│   │   │   ├── idempotency.py             ← Hash tool+action+params
│   │   │   ├── circuit_breaker.py         ← Per-worker circuit breaker
│   │   │   └── generated/                 ← Workers auto-generados (NO commitear)
│   │   │       ├── crm_create_lead_worker.py
│   │   │       ├── crm_list_leads_worker.py
│   │   │       ├── invoice_create_invoice_worker.py
│   │   │       └── ... (~58 workers)
│   │   │
│   │   └── level4_tools/                  ← NIVEL 4 — Tools ZF reales
│   │       ├── __init__.py
│   │       ├── registry.py                ← Registro central de tools al startup
│   │       ├── adapter.py                 ← Adapter tools → Specialist/Worker
│   │       ├── business/                  ← Tools de negocio
│   │       │   ├── crm/
│   │       │   │   ├── service.py
│   │       │   │   ├── repository.py
│   │       │   │   └── models.py
│   │       │   ├── invoice/
│   │       │   │   ├── service.py
│   │       │   │   ├── repository.py
│   │       │   │   └── models.py
│   │       │   └── inventory/
│   │       │       ├── service.py
│   │       │       ├── repository.py
│   │       │       └── models.py
│   │       ├── communications/            ← Comunicaciones
│   │       │   └── notification/
│   │       │       ├── service.py
│   │       │       └── models.py
│   │       ├── computation/               ← Cálculo y ejecución
│   │       │   ├── code_runner/
│   │       │   │   ├── service.py
│   │       │   │   └── sandbox.py
│   │       │   └── logic_gate/
│   │       │       └── service.py
│   │       ├── data/                      ← Almacenamiento y HTTP
│   │       │   ├── data_keeper/
│   │       │   │   ├── service.py
│   │       │   │   ├── repository.py
│   │       │   │   └── models.py
│   │       │   └── api_connector/
│   │       │       ├── service.py
│   │       │       ├── http_client.py
│   │       │       ├── pagination.py
│   │       │       ├── rate_limiter.py
│   │       │       ├── response_cache.py
│   │       │       ├── xml_processor.py
│   │       │       └── webhooks.py
│   │       ├── automation/                ← Plantillas y automatización
│   │       │   └── autopilot/
│   │       │       └── service.py
│   │       └── integrations/              ← Integraciones externas
│   │           ├── gmail_service.py
│   │           ├── slack_service.py
│   │           ├── whatsapp_service.py    ← Fusionar con notification
│   │           ├── telegram_service.py
│   │           ├── sheets_service.py
│   │           ├── drive_service.py
│   │           ├── stripe_service.py
│   │           ├── mercadopago_service.py
│   │           ├── openai_service.py
│   │           ├── ollama_service.py
│   │           └── postgresql_service.py
│   │
│   ├── events/                            ← Sistema de eventos (cross-cutting)
│   │   ├── __init__.py
│   │   ├── bus.py                         ← EventBus in-memory pub/sub
│   │   ├── queue_service.py               ← SQLite persistent queue
│   │   ├── work_queue.py                  ← Async workflow queue
│   │   ├── worker_manager.py              ← Background workers
│   │   ├── workflow_subscriber.py         ← Reacts to events → dispara workflows
│   │   ├── email_watcher.py               ← Trigger: emails nuevos
│   │   ├── file_watcher.py                ← Trigger: cambios en archivos
│   │   ├── db_trigger.py                  ← Trigger: cambios en DB
│   │   ├── webhook_server.py              ← Trigger: webhooks entrantes
│   │   └── schedule_worker.py             ← Trigger: cron-like
│   │
│   ├── nlu/                               ← NLU determinista (alimentado por HAT)
│   │   ├── __init__.py                    ← Pipeline, understand, compile
│   │   ├── pipeline.py                    ← 13-stage NLU pipeline
│   │   ├── tokenizer.py
│   │   ├── normalizer.py
│   │   ├── intent_classifier.py           ← Alimentado por Agent Cards de HAT
│   │   ├── slot_filler.py                 ← Extrae entidades para params de workers
│   │   ├── disambiguator.py
│   │   ├── language_router.py
│   │   ├── bilingual_router.py
│   │   ├── compiler.py
│   │   ├── validator.py
│   │   ├── dry_run.py
│   │   ├── explainer.py
│   │   ├── ai_config.py
│   │   ├── ai_generator.py
│   │   ├── synonym_learner.py
│   │   ├── templates.py
│   │   ├── fragments.py
│   │   ├── fallback.py
│   │   ├── entities/                      ← Extractores de entidades
│   │   │   ├── __init__.py
│   │   │   ├── extractor.py
│   │   │   ├── base.py
│   │   │   ├── condition.py
│   │   │   ├── money.py
│   │   │   ├── duration.py
│   │   │   └── quantity.py
│   │   └── guardrails/                    ← PII, content safety
│   │       ├── __init__.py
│   │       ├── manager.py
│   │       ├── pii.py
│   │       ├── content.py
│   │       ├── result.py
│   │       └── execution.py
│   │
│   ├── workflow/                          ← Motor de workflows (invocado por HAT N0)
│   │   ├── __init__.py
│   │   ├── engine.py                      ← WorkflowEngine singleton
│   │   ├── repository.py                  ← Persistencia de workflow defs
│   │   ├── step_executor.py               ← StepExecutor (con ORBITAL)
│   │   ├── condition_evaluator.py
│   │   ├── branch_handler.py
│   │   ├── loop_handler.py
│   │   ├── fork_handler.py                ← (thin shim → execution.parallel)
│   │   ├── error_handler.py
│   │   ├── dead_letter.py
│   │   ├── versioning.py                  ← Versions + environments + promotions
│   │   ├── workflow_variables.py
│   │   ├── workflow_templates.py
│   │   ├── constants.py
│   │   ├── durable_models.py              ← (eliminar si no se usa)
│   │   ├── durable/                       ← (eliminar si no se usa)
│   │   ├── execution/                     ← Servicios de ejecución
│   │   │   ├── __init__.py
│   │   │   ├── step_execution.py
│   │   │   ├── parallel.py                ← ForkHandler + JoinHandler
│   │   │   ├── subworkflow.py
│   │   │   ├── async_executor.py
│   │   │   └── result.py
│   │   └── orbital/                       ← Adapter ORBITAL ↔ workflow
│   │       ├── __init__.py
│   │       ├── steps.py                   ← Inyecta steps como vars OVC
│   │       └── trigger.py                 ← Inyecta trigger como var OVC
│   │
│   ├── connectors/                        ← SDK connectors externos (40+)
│   │   ├── __init__.py                    ← register_all_connectors()
│   │   ├── salesforce.py
│   │   ├── hubspot.py
│   │   ├── jira.py
│   │   ├── github.py
│   │   └── ... (60 connectors total)
│   │
│   ├── sdk/                               ← SDK para construir tools/connectors
│   │   ├── __init__.py
│   │   ├── base/
│   │   │   ├── __init__.py
│   │   │   ├── connector.py               ← BaseConnector ABC
│   │   │   └── configs.py                 ← RetryConfig, RateLimitConfig
│   │   ├── schema.py                      ← Pydantic schemas + OpenAPI gen
│   │   ├── http_client.py                 ← HttpClient (sync, requests)
│   │   ├── exceptions.py                  ← ConnectorError hierarchy
│   │   ├── registry.py                    ← ConnectorRegistry singleton
│   │   ├── auth/                          ← Auth providers (eliminar no usados)
│   │   │   ├── __init__.py
│   │   │   ├── base.py                    ← AuthProvider ABC
│   │   │   ├── api_key.py                 ← APIKeyAuth (usado)
│   │   │   ├── custom.py                  ← CustomAuth (escape hatch)
│   │   │   └── (eliminar basic, oauth1, oauth2, mtls)
│   │   └── decorators/                    ← (ELIMINAR — 0 usos)
│   │
│   ├── bpmn/                              ← BPMN 2.0 import/export
│   │   ├── __init__.py
│   │   ├── parser.py                      ← BPMNParser (usar defusedxml)
│   │   ├── exporter.py
│   │   ├── converter.py                   ← BPMN ↔ WorkflowDefinition
│   │   ├── builder.py
│   │   └── models.py
│   │
│   ├── tenant/                            ← Multi-tenant
│   │   ├── __init__.py
│   │   ├── context.py
│   │   ├── resolver.py
│   │   ├── middleware.py
│   │   ├── provisioner.py
│   │   ├── service.py
│   │   ├── settings_service.py
│   │   ├── features.py
│   │   └── storage.py
│   │
│   ├── license/                           ← Licencias (pago único, Ed25519)
│   │   ├── __init__.py
│   │   ├── generator.py
│   │   ├── validator.py
│   │   └── keys.py
│   │
│   ├── compliance/                        ← HIPAA, GDPR, SOC2
│   │   ├── __init__.py                    ← ComplianceManager
│   │   ├── hipaa.py                       ← BAAManager
│   │   ├── gdpr.py                        ← ConsentManager
│   │   └── soc2_type_ii.py                ← SOC2TypeIIManager
│   │
│   ├── marketplace/                       ← Marketplace de tools/workflows
│   │   ├── __init__.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── certification.py
│   │   └── models.py
│   │
│   ├── partnership/                       ← Programa de partners
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── service.py
│   │
│   ├── sync/                              ← Sync cloud (opcional)
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── models.py
│   │
│   ├── mobile/                            ← API mobile companion
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── push.py
│   │   └── sync.py
│   │
│   ├── web/                               ← Web UI (Flask)
│   │   ├── __init__.py
│   │   ├── app.py                         ← create_app()
│   │   ├── helpers.py                     ← Shared helpers + auth decorators
│   │   ├── realtime/
│   │   │   └── sse.py                     ← Server-Sent Events
│   │   ├── reports/                       ← PDF + CSV generators
│   │   │   └── __init__.py
│   │   ├── blueprints/                    ← Flask blueprints (UI + API v1)
│   │   │   ├── __init__.py                ← register_blueprints()
│   │   │   ├── auth.py
│   │   │   ├── pages.py
│   │   │   ├── workflows.py
│   │   │   ├── orbital.py
│   │   │   ├── tools.py
│   │   │   ├── admin.py
│   │   │   ├── integrations.py
│   │   │   ├── reports.py
│   │   │   ├── marketplace.py
│   │   │   ├── partnership.py
│   │   │   ├── sync.py
│   │   │   ├── nlu.py                     ← Chat usando HATRouter (no NLU directo)
│   │   │   └── compliance.py
│   │   ├── templates/                     ← Jinja2 templates
│   │   └── static/                        ← CSS, JS, assets
│   │
│   ├── api_v2/                            ← API REST v2 (FastAPI)
│   │   ├── __init__.py
│   │   ├── app.py                         ← FastAPI app (LANzar en prod!)
│   │   ├── auth.py                        ← JWT + API key auth
│   │   ├── dependencies.py                ← Shared FastAPI deps
│   │   ├── models.py                      ← Pydantic models
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── auth_routes.py
│   │       ├── agents.py
│   │       ├── workflows.py
│   │       ├── marketplace.py
│   │       ├── tenants.py
│   │       ├── connectors.py
│   │       ├── compliance.py
│   │       ├── bpmn.py
│   │       └── nlu.py
│   │
│   ├── cli/                               ← CLI para desarrollo
│   │   ├── __init__.py
│   │   ├── main.py                        ← python -m src.cli.main
│   │   ├── sandbox.py                     ← SandboxExecutor
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── init_cmd.py
│   │   │   ├── validate_cmd.py
│   │   │   ├── test_cmd.py
│   │   │   ├── publish_cmd.py
│   │   │   ├── info_cmd.py
│   │   │   ├── list_cmd.py
│   │   │   └── version_cmd.py
│   │   └── templates/
│   │       ├── __init__.py
│   │       ├── generators.py
│   │       └── helpers.py
│   │
│   ├── installer/                         ← Instalador end-user
│   │   ├── __init__.py
│   │   ├── installer_main.py
│   │   ├── steps.py
│   │   ├── ui.py
│   │   ├── config.py
│   │   ├── build_pyinstaller.sh
│   │   └── build_nuitka.sh
│   │
│   ├── tests/                             ← Suite de tests
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── core/                          ← Tests de core/
│   │   ├── orbital/                       ← Tests del motor
│   │   ├── hat/                           ← Tests HAT (5 niveles)
│   │   │   ├── level0/                    ← Tests del HATRouter
│   │   │   ├── level1/                    ← Tests de supervisores
│   │   │   ├── level2/                    ← Tests de specialists
│   │   │   ├── level3/                    ← Tests de workers
│   │   │   ├── level4/                    ← Tests de tools
│   │   │   └── e2e/                       ← Tests end-to-end reales
│   │   ├── events/
│   │   ├── nlu/
│   │   ├── workflow/
│   │   └── ...
│   │
│   └── main.py                            ← ENTRY POINT ÚNICO
│
├── frontend/                              ← SPA React (sin cambios)
├── scripts/                               ← Scripts de ops
├── deploy/                                ← Helm + k8s + istio + grafana
├── docs/                                  ← Documentación
├── installer/                             ← (mover contenido a src/installer/)
├── helm/                                  ← (mover a deploy/helm/)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── package.json
├── ruff.toml
├── start_server.sh
├── LICENSE
├── README.md
├── CHANGELOG.md
└── VERSION
```

## 🔗 Reglas de Dependencia (Ley de Demeter)

```
core/         → solo stdlib + 3rd party (NADIE arriba)
orbital/      → core/  (NADIE arriba excepto hat/)
nlu/          → core/, orbital/  (HAT lo usa, NLU no conoce HAT)
events/       → core/, orbital/, workflow/
workflow/     → core/, orbital/, events/, nlu/
hat/          → core/, orbital/, nlu/, events/, workflow/
hat/level0    → hat/level1 (interfaces) + core/ + orbital/ + events/
hat/level1    → hat/level2 (interfaces) + hat/level0/ledger (escritura)
hat/level2    → hat/level3 (interfaces) + hat/level4/registry
hat/level3    → hat/level4 (tools concretas)
hat/level4    → core/ + sdk/ + connectors/  (NO hat/ arriba)
```

**Regla crítica**: Los niveles NO se conocen hacia arriba. `hat/level3_workers/` NO puede importar `hat/level2_specialists/` ni `hat/level1_supervisors/`.

## 🎯 Justificación por Carpeta

### `src/core/` — La base sobre la que todo se construye

**Por qué existe**: Son dependencias transversales que TODOS los niveles de HAT necesitan pero NINGÚN nivel de HAT debería implementar. Si HAT tuviera su propio `database_manager.py`, violaríamos DRY.

**Regla**: `core/` NO puede importar de `hat/`, `orbital/`, `workflow/`, `nlu/`.

### `src/orbital/` — El motor determinista (separado de HAT)

**Por qué está separado de HAT**: ORBITAL es agnóstico al orquestador. Se usa tanto en HAT (`hat/level0_orchestrator/routing/orbital_router.py`) como en `workflow/step_executor.py`. Separarlo lo hace testeable y reutilizable.

**Es el diferenciador competitivo del producto** — mantenerlo limpio permite usarlo en otros proyectos.

### `src/hat/level0_orchestrator/` — NIVEL 0

**Por qué aquí**: Es el ÚNICO punto de entrada al sistema HAT. Nadie más debe orquestar. Contiene:

- `tick_router.py` — el `HATRouter.handle()` (única función pública)
- `fsm/` — estados y transiciones del orquestador (6 estados, 4 reglas)
- `intent/` — hashing determinista (sha256) para anti-dup
- `routing/` — decisión por resonancia RCC + fallback keywords
- `ledger/` — memoria entre sesiones (3 tablas SQLite)
- `anti_duplication/` — 3 capas en cascada
- `observability/` — OpenTelemetry spans (con no-op fallback)
- `api/` — endpoint FastAPI `POST /api/hat/chat`

### `src/hat/level1_supervisors/` — NIVEL 1

**Por qué aquí**: Aislamiento funcional. Un supervisor de "ventas" no sabe que existe "facturacion". Cada supervisor aplica políticas locales (rate limits, retries, fallbacks) y delega a specialists.

**6 dominios alineados con tools ZF**:
- `ventas` → CRM
- `facturacion` → Invoice, Stripe, MercadoPago
- `inventario` → Inventory
- `comunicaciones` → Notification, Gmail, Slack, WhatsApp, Telegram
- `datos` → DataKeeper, ApiConnector, Sheets, Drive, PostgreSQL
- `automatizacion` → CodeRunner, LogicGate, Autopilot, OpenAI, Ollama

### `src/hat/level2_specialists/` — NIVEL 2

**Por qué aquí**: Cada specialist envuelve 1 tool completa. Conoce todos los métodos públicos de esa tool. Publica su AgentCard con keywords del dominio.

**Auto-generación**: `factory.py` introspecciona las tools registradas en `level4_tools/registry.py` y genera dinámicamente la clase Specialist correspondiente. Añadir tool nueva = Specialist aparece automáticamente.

### `src/hat/level3_workers/` — NIVEL 3

**Por qué aquí**: Atomicidad. Cada worker hace UNA sola cosa (un método de una tool). Auto-generados por `factory.py` desde los métodos públicos de cada Specialist.

**`generated/` carpeta**: Los workers auto-generados NO se commitean al repo. Se generan al startup en memoria. Esto evita mantenimiento manual cuando se añaden métodos a una tool.

### `src/hat/level4_tools/` — NIVEL 4

**Por qué aquí**: Las tools ZF reales con implementación funcional. Se invocan directamente desde workers N3.

**Categorías**:
- `business/` — CRM, Invoice, Inventory (negocio)
- `communications/` — Notification (email, WhatsApp)
- `computation/` — CodeRunner (sandbox Python), LogicGate
- `data/` — DataKeeper, ApiConnector
- `automation/` — Autopilot (plantillas)
- `integrations/` — 11 servicios externos

**`registry.py`**: Punto de extensión — añadir tool nueva = 1 archivo + 1 línea en registry.

### `src/events/` — Cross-cutting (no es nivel HAT)

**Por qué separado**: Los eventos son observables cross-cutting. Cualquier nivel puede publicar/suscribir. Los triggers (email_watcher, file_watcher) generan inputs para HAT pero no son parte de HAT.

### `src/nlu/` — Pre-procesamiento (alimentado por HAT)

**Por qué separado**: NLU transforma texto del usuario en algo que HAT puede procesar. Es preprocessing. Las Agent Cards de HAT N2 alimentan el `intent_classifier` (las keywords de las cards se vuelven templates NLU).

**Regla**: NLU no decide ruteo — eso lo hace HAT N0.

### `src/workflow/` — Motor de workflows (invocado por HAT)

**Por qué separado**: El `WorkflowEngine` ejecuta workflows multi-step. HAT lo usa para dispatch, pero el motor es independiente. Workflows pueden ejecutarse sin HAT (ej: workflow programado por `schedule_worker.py`).

### `src/connectors/` — SDK connectors (40+)

**Por qué separado de `level4_tools/integrations/`**: Los connectors son drivers HTTP para APIs externas. No tienen lógica de negocio. Las `integrations/` son wrappers con lógica de negocio.

### `src/sdk/` — SDK para construir tools

**Por qué aquí**: Es el contrato público para que terceros construyan tools (marketplace). Las tools N4 lo usan indirectamente vía connectors.

### Módulos auxiliares (al mismo nivel que hat/)

`tenant/`, `license/`, `compliance/`, `marketplace/`, `partnership/`, `sync/`, `mobile/`, `bpmn/` — son funcionalidades de producto que USAN HAT pero no son parte del orquestador.

### `src/web/` + `src/api_v2/` — Capas de presentación

**Por qué separadas**: `web/` (Flask) es UI server-rendered legacy. `api_v2/` (FastAPI) es API REST moderna. Ambas consumen HAT vía `HATRouter.handle()`.

#### API Layers (3 capas de API)

El backend expone **3 capas de API** con propósitos distintos:

| Capa | Framework | Puerto | Rutas | Audiencia | Propósito |
|---|---|---|---|---|---|
| **Flask** | Flask + Jinja2 | 8080 | 139 | SPA React (interna) | API interna consumida por el frontend React. Incluye auth (cookie/session), workflows, tools, compliance, marketplace, sync, airgap, orbital, dashboard, etc. |
| **FastAPI v2** | FastAPI | 8000 | 43 | Integraciones externas (SDK, móvil, partners) | API REST pública moderna con JWT + API key auth. Routers: agents, auth_routes, bpmn, compliance, connectors, crm, fiscal, inventory, invoices, marketplace, tenants, workflows. |
| **SSE** | Flask + EventSource | 8080 | 1 | SPA React (interna) | Streaming de eventos en tiempo real (`/api/events/stream`) para el dashboard live feed. |

**Arquitectura de puertos**:
- `main.py` arranca Flask (8080) + FastAPI v2 (8000, en un hilo daemon) + webhook server (8081)
- En producción, nginx proxyea:
  - `/api/v2/*` → FastAPI:8000
  - `/api/*` (resto) → Flask:8080
  - `/api/events/stream` → Flask:8080 (SSE, buffering off)
  - `/static/spa/*` → archivos estáticos del build React
- En desarrollo, Vite proxyea `/api/v2` → localhost:8000 y `/api` → localhost:5000

**Routers FastAPI v2 (12 incluidos)**:

| Router | Prefix | LOC | Audience | Purpose |
|---|---|---|---|---|
| `agents` | `/api/v2/agents` | 249 | External (deprecated, ADR-0001) | Lifecycle management de agents legacy |
| `auth_routes` | `/api/v2/auth` | 490 | External | Auth con JWT + API key (alternativa a Flask cookie auth) |
| `bpmn` | `/api/v2/bpmn` | 170 | External | Import/export/validate procesos BPMN |
| `compliance` | `/api/v2/compliance` | 313 | External | Compliance management (GDPR, HIPAA, SOC2) |
| `connectors` | `/api/v2/connectors` | 402 | External | CRUD de connectors (paralelo a Flask `/api/integrations`) |
| `crm` | `/api/v2/crm` | 131 | External + SPA | CRM stats (usado por MiNegocioPage) + CRUD clients/leads |
| `fiscal` | `/api/v2/fiscal` | 180 | External + SPA | Facturación electrónica LATAM (usado por FacturacionElectronicaPage) |
| `inventory` | `/api/v2/inventory` | 67 | External + SPA | Inventory stats (usado por MiNegocioPage) + CRUD products |
| `invoices_v2` | `/api/v2/invoices` | 68 | External + SPA | Invoices stats (usado por MiNegocioPage) + CRUD invoices |
| `marketplace` | `/api/v2/marketplace` | 461 | External | Marketplace de connectors (paralelo a Flask) |
| `tenants` | `/api/v2/tenants` | 325 | External | Multi-tenancy management |
| `workflows` | `/api/v2/workflows` | 410 | External | Workflow management (paralelo a Flask) |

**Nota**: el router `nlu.py` v2 fue eliminado en Fase 1 (294 LOC, nunca incluido en `app.py`).

**PWA Offline**: el frontend React es una PWA instalable con service worker (`/static/sw.js`) que cachea assets del SPA y API GETs de lectura para funcionamiento offline. Ver `src/web/static/sw.js` y `frontend/src/main.tsx` (registro).

### `src/cli/`, `src/installer/` — Ops

Entry points alternativos para desarrollo/instalación.

## 📊 Métricas de la Reorganización

| Métrica | Antes | Después |
|---|---|---|
| LOC código HAT | ~3,420 (con stubs) | ~1,500 (auto-generados) |
| Workers N3 | 7 stubs (fake data) | ~58 (auto-generados, tools reales) |
| Specialists N2 | 7 stubs | 9+11 (uno por tool + integration) |
| Supervisores N1 | 3 arbitrarios | 6 alineados con tools |
| Tools N4 | 0 (workers fakeaban) | 13+11 (tools ZF reales) |
| Agent Cards | 21 hardcoded, 0 publicadas | ~20 auto-publicadas al startup |
| Anti-dup capas | 5 (TTL rompe UX) | 3 (TTL=2s, mismo hash) |
| Ledger tablas | 7 (4 sin uso) | 3 útiles |
| Dominios | research/build/operate | 6 alineados con tools |

## 🔄 Flujo End-to-End

```
Usuario: "crea factura para Juan"
    │
    ▼
POST /api/hat/chat  (api_v2 o web/blueprints/nlu.py)
    │
    ▼
HATRouter.handle()  [NIVEL 0]
    ├── compute_intent_hash() → sha256(...)
    ├── AntiDuplicationCascade.check()  [3 capas]
    │   ├── ExactMatch (cache LRU) → no hit
    │   ├── Idempotency → no in_progress
    │   └── TTLFreshness (TTL=2s, mismo hash) → proceed
    ├── OVCLedgerBridge.load_session() → carga Facts del Ledger a OVC
    ├── _route_by_orbital(message)  [routing/orbital_router.py]
    │   ├── Inyecta user_intent como var OVC (θ=0, A=1.0)
    │   ├── Calcula TOR(user_intent, cada AgentCard) por dominio
    │   ├── Top-3 dominios por resonancia RCC
    │   └── fsm_disambiguate() si top1-top2 < 0.15
    │       → ganador: "facturacion"
    ├── _dispatch_to_supervisor("facturacion", subtask)
    │   │
    │   ▼
    │   FacturacionSupervisor.handle(subtask)  [NIVEL 1]
    │   ├── Selecciona specialist por resonancia RCC interna
    │   │   → InvoiceSpecialist (ruteo FSM interno)
    │   ├── Delegate a specialist
    │   │   │
    │   │   ▼
    │   │   InvoiceSpecialist.handle(subtask)  [NIVEL 2]
    │   │   ├── FSM interno: "crea" → action "create_invoice"
    │   │   ├── Selecciona worker
    │   │   │   │
    │   │   │   ▼
    │   │   │   CreateInvoiceWorker.run(params)  [NIVEL 3]
    │   │   │   ├── Validación idempotency: hash(tool+action+params)
    │   │   │   ├── Circuit breaker check
    │   │   │   ├── Invocar tool
    │   │   │   │   │
    │   │   │   │   ▼
    │   │   │   │   InvoiceService.create_invoice(...)  [NIVEL 4]
    │   │   │   │   ├── Genera FAC-2026-XXX
    │   │   │   │   ├── Calcula subtotal + tax + total
    │   │   │   │   ├── Persiste en SQLite
    │   │   │   │   ├── Publica "invoice.created" en EventBus
    │   │   │   │   └── Retorna dict con factura completa
    │   │   │   │
    │   │   │   └── Retorna StepResult
    │   │   │
    │   │   └── Agrega resultado del worker
    │   │
    │   └── Retorna al supervisor
    │
    ├── _consolidate() → actualiza hat_facts, hat_progress
    ├── OVCLedgerBridge.persist_session() → snapshot OVC → Ledger
    └── _synthesize_response()
        → "Factura FAC-2026-XXX creada para Juan. Total: $1,160.00"
    │
    ▼
HATResponse JSON  →  Usuario
```

**Latencia total típica**: ~85ms para una factura real (vs ~3ms actual que solo retorna strings).

---

## 🚀 Plan de Implementación

Ver `MIGRATION_MAP.md` para el mapeo archivo por archivo.
Ver `IMPLEMENTATION_PLAN.md` para las 10 fases de migración ejecutables.
