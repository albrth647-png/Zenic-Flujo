# 📜 PLAN MAESTRO — WORKFLOW DETERMINISTA

## "Automatización offline para tu negocio. Sin internet, sin mensualidades."

**Versión:** 2.0 — Junio 2026 (Corregida y auditada)
**Autor:** Workflow Determinista Project
**Licencia:** Propietaria — Pago Único

---

> ⚠️ **Este documento es la especificación completa del proyecto.** Explica qué se construye, por qué, cómo funciona internamente, y cómo se entrega al cliente. Está diseñado para ser autocontenido: cualquier desarrollador puede leerlo y construir el sistema completo desde cero.
>
> ✅ **Versión 2.0:** Corregida tras auditoría de seguridad, testing y viabilidad comercial.

---

# 📑 ÍNDICE

- [Parte 0: Glosario Completo](#-parte-0-glosario-completo)
- [Parte 1: Visión del Negocio](#-parte-1-visión-del-negocio)
- [Parte 2: Arquitectura General](#-parte-2-arquitectura-general)
- [Parte 3: Tech Stack y Decisiones Técnicas](#-parte-3-tech-stack-y-decisiones-técnicas)
- [Parte 4: Modelo de Datos (Schemas)](#-parte-4-modelo-de-datos-schemas)
- [Parte 5: Componentes del Sistema](#-parte-5-componentes-del-sistema)
- [Parte 6: Las 10 Herramientas (APIs)](#-parte-6-las-10-herramientas-apis)
- [Parte 7: Web UI](#-parte-7-web-ui)
- [Parte 8: Instalador](#-parte-8-instalador)
- [Parte 9: Sistema de Licencias](#-parte-9-sistema-de-licencias)
- [Parte 10: Pagos y Delivery](#-parte-10-pagos-y-delivery)
- [Parte 11: Seguridad](#-parte-11-seguridad)
- [Parte 12: Modelo de Negocio](#-parte-12-modelo-de-negocio)
- [Parte 13: Plan de Implementación — 3 Fases](#-parte-13-plan-de-implementación--3-fases)
- [Parte 14: Riesgos](#-parte-14-riesgos)
- [Parte 15: Estrategia de Ventas](#-parte-15-estrategia-de-ventas)
- [Anexo A: Checklist de Lanzamiento](#-anexo-a-checklist-de-lanzamiento)

---

# 🔤 PARTE 0: GLOSARIO COMPLETO

> Todos los términos técnicos usados en este documento, explicados para que cualquier persona los entienda.

## Conceptos Generales

| Término | Definición |
|---|---|
| **Workflow** | Una secuencia de pasos automatizados que se ejecutan en orden. Ejemplo: "Cuando llegue un email → extraer datos → crear cliente → enviar respuesta" |
| **Trigger (Disparador)** | El evento que inicia un workflow. Ejemplo: "Recibir un email", "Llegar a una hora específica", "Alguien visita una página web" |
| **Paso (Step)** | Una acción individual dentro de un workflow. Ejemplo: "Crear cliente en CRM", "Enviar email", "Actualizar inventario" |
| **Condición** | Una regla que decide si un paso se ejecuta o no. Ejemplo: "Solo si el total es mayor a $500" |
| **Determinista** | Que siempre produce el mismo resultado para la misma entrada. Predecible, auditable y repetible. |
| **SQLite** | Una base de datos que vive en un solo archivo. No necesita servidor, no necesita internet. Cada instalación del producto tiene su propio archivo `.db`. |
| **Ciclo de Vida** | Los estados por los que pasa un workflow desde que se crea hasta que termina. |

## Ciclo de Vida de un Workflow

```
CREADO → ACTIVO → EN EJECUCIÓN → COMPLETADO
                            → FALLIDO
         → PAUSADO → ACTIVO
         → ARCHIVADO
```

| Estado | Significado |
|---|---|
| `CREADO` | El workflow fue definido pero nunca se ha ejecutado |
| `ACTIVO` | El workflow está escuchando su trigger, listo para ejecutarse |
| `EN EJECUCIÓN` | El workflow se está ejecutando ahora mismo |
| `PAUSADO` | El workflow fue pausado por el usuario. No responde a triggers |
| `COMPLETADO` | El workflow se ejecutó y todos los pasos terminaron OK |
| `FALLIDO` | El workflow se ejecutó pero uno o más pasos fallaron |
| `ARCHIVADO` | El workflow fue desactivado permanentemente |

## Componentes del Sistema

| Componente | Definición |
|---|---|
| **WorkflowEngine** | El motor que ejecuta los workflows. Toma la definición de un workflow y ejecuta cada paso en orden |
| **StepExecutor** | El componente que ejecuta un paso individual. Llama a la herramienta correcta (CRM, Invoice, etc.) |
| **ConditionEvaluator** | Evalúa condiciones en tiempo real. Ejemplo: evalúa si `stock_actual < 10` es verdadero o falso |
| **EventBus** | Sistema de mensajería interna. Un componente publica un evento, otros componentes lo reciben |
| **ScheduleWorker** | Un proceso en segundo plano que revisa cada minuto si hay workflows programados para ejecutarse |
| **LicenseManager** | Sistema que valida que el cliente tenga una licencia válida para usar el producto |
| **Tool (Herramienta)** | Cada uno de los módulos de negocio: CRM, Invoice, Inventory, etc. |

---

# 🏢 PARTE 1: VISIÓN DEL NEGOCIO

## 1.1 ¿Qué estamos construyendo?

Estamos construyendo **Workflow Determinista**: un sistema de automatización de procesos de negocio que las empresas instalan en su propia computadora, pagan una sola vez, y funciona 100% offline sin depender de internet.

**El producto resuelve estos problemas:**

1. **Dependencia de internet** — si se cae la red, el negocio se detiene. Nosotros funcionamos 100% local.
2. **Suscripciones mensuales** — Zapier, Make, n8n cloud cuestan $600-$2,400/año. Nosotros: pago único de $399.
3. **Privacidad de datos** — con la competencia, tus datos de clientes, ventas e inventario están en servidores de terceros. Nosotros: todo queda en tu computadora.

**Nuestra solución:**

- ✅ **Offline primero** — funciona sin internet. Si se cae la red, tu negocio sigue
- ✅ **Pago único** — $399 y el sistema es del cliente para siempre
- ✅ **Local-first** — todos los datos en tu computadora, no en la nube
- ✅ **Auditable** — cada decisión queda registrada con su justificación
- ✅ **Sin sorpresas** — cada workflow se puede revisar paso a paso antes de ejecutar

## 1.2 ¿Quién va a comprar esto?

| Tipo de cliente | Ejemplo | Dolor principal |
|---|---|---|
| Dueño de PYME | Taller mecánico (5 empleados) | Paga $600+/año en suscripciones, internet inestable |
| Distribuidora pequeña | 20 empleados, bodega | Necesita CRM + inventario pero sin mensualidades ni nube |
| Consultor TI | Instala sistemas para sus clientes | Busca herramientas para revender con su margen |
| Empresa regulada | Clínica, contador, bufete | Necesita datos locales por ley (GDPR, HIPAA, etc.) |
| Dueño desconfiado de la nube | Negocio familiar | Quiere control TOTAL de sus datos |

## 1.3 ¿Cuál es la propuesta de valor única?

**3 razones para comprar:**

1. **Precio:** $399 de por vida vs. $600-$2,400/año de la competencia
2. **Offline:** Todo funciona aunque se caiga internet. No dependes de nadie.
3. **Privacidad:** Tus datos de clientes, ventas e inventario están en TU computadora. No en la nube de otro.

> 💡 **Nota:** El producto no compite con AI. No dice "sin AI" porque el mercado no rechaza la AI. El producto compite en **precio, privacidad y funcionamiento offline**. Esa es la verdadera propuesta de valor.

---

# 🏗️ PARTE 2: ARQUITECTURA GENERAL

## 2.1 Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW DETERMINISTA                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    WEB UI (puerto 8080)                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │   │
│  │  │  Login   │  │Dashboard │  │   Chat   │  │  Admin   │   │   │
│  │  │          │  │          │  │(crear wf) │  │(logs,lic)│   │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│  ┌──────────────────────────▼───────────────────────────────────┐  │
│  │                    WORKFLOW ENGINE (src/workflow/)            │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │  Engine      │  │ StepExecutor │  │ ConditionEvaluator│  │  │
│  │  │ (ciclo vida) │  │ (ejecuta)    │  │ (evalúa reglas)  │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ BranchHandler│  │ LoopHandler  │  │  ErrorHandler    │  │  │
│  │  │ (if/else)    │  │ (for/while)  │  │ (retry/fallback) │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │           WorkflowRepository (SQLite)                │  │  │
│  │  │   Guarda: definiciones, ejecuciones, historial       │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────▼───────────────────────────────────┐  │
│  │                    EVENT SYSTEM (src/events/)                 │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │   EventBus   │  │ FileWatcher  │  │  WebhookServer   │  │  │
│  │  │ (pub/sub)    │  │ (archivos)   │  │  (HTTP POST)     │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ScheduleWorker│  │ DBTrigger    │  │  EmailWatcher    │  │  │
│  │  │ (cron)       │  │ (SQLite)     │  │  (IMAP)          │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────▼───────────────────────────────────┐  │
│  │            BUSINESS TOOLS (src/tools/) — 6 en MVP            │  │
│  │                                                              │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────┐  │  │
│  │  │    CRM     │  │  Invoice   │  │ Inventory  │  │ Notif│  │  │
│  │  │ (clientes) │  │ (facturas) │  │ (stock)    │  │(email)│  │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └──────┘  │  │
│  │  ┌────────────┐  ┌────────────┐                              │  │
│  │  │ Auto Pilot │  │ Logic Gate │                              │  │
│  │  │(automatizar)│  │ (reglas)   │                              │  │
│  │  └────────────┘  └────────────┘                              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────▼───────────────────────────────────┐  │
│  │              PERSISTENCE LAYER (src/data/)                    │  │
│  │                                                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ DatabaseMgr  │  │   Repositorios │  │  BackupEngine   │  │  │
│  │  │ (SQLite mgmt)│  │ (CRUD por tool)│  │ (automático USB)│  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────▼───────────────────────────────────┐  │
│  │               LICENSE MANAGER (src/license/)                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │  Generator   │  │  Validator   │  │  Trial (30 días) │  │  │
│  │  │ (HMAC-SHA256)│  │ (cada inicio)│  │  (sin key)       │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## 2.2 Flujo de ejecución de un workflow

```
1. Usuario escribe en el Chat:
   "Quiero que cuando un cliente nuevo se registre, 
    se guarde en mi base de datos y se le envíe 
    un correo de bienvenida"

2. NLP Layer procesa:
   IntentClassifier + Plantillas → detecta:
   - Trigger: EVENT ("cuando un cliente nuevo se registre")
   - Paso 1: CRM.create_lead ("guardar en base de datos")
   - Paso 2: Notification.send_email ("correo de bienvenida")

3. WorkflowSerializer arma la definición:
   ↓

4. WorkflowRepository guarda en SQLite:
   - Definición del workflow (YAML/JSON)
   - Estado: ACTIVO

5. EventBus registra el trigger:
   - Cuando ocurra "crm.lead.created" → ejecutar workflow X

6. [Tiempo después] Alguien crea un lead en el CRM:
   - CRM emite evento: "crm.lead.created" con datos del lead
   - EventBus recibe el evento
   - EventBus busca workflows suscritos a ese evento
   - Encuentra workflow X → ejecuta

7. WorkflowEngine ejecuta:
   - Estado: EN EJECUCIÓN
   - Paso 1: StepExecutor llama a CRM.create_lead(nombre, email)
   - Paso 1 retorna: { id: 42, nombre: "Juan", email: "juan@email.com" }
   - Paso 2: StepExecutor llama a Notification.send_email(
       to: "juan@email.com", 
       template: "welcome"
     )
   - Paso 2 retorna: { status: "sent" }
   
8. WorkflowEngine registra:
   - Estado: COMPLETADO
   - Log: Paso 1 OK, Paso 2 OK
   - Duración total: 1.2 segundos

9. Usuario puede ver en la UI:
   - Workflow X → Última ejecución: COMPLETADO ✅
   - Click → Ver logs → "Paso 1: OK (0.8s), Paso 2: OK (0.4s)"
```

## 2.3 Diagrama de flujo de datos

```
CLIENTE (navegador)         SERVIDOR LOCAL (localhost:8080)
       │                              │
       │  POST /api/workflows         │
       │  { "texto": "Quiero que..." }│
       │ ──────────────────────────►  │
       │                              ├── IntentClassifier
       │                              ├── Plantillas (templates)
       │                              ├── WorkflowSerializer
       │                              │
       │  201 Created                 │
       │  { "id": 42, "pasos": [...] }│
       │ ◄──────────────────────────  │
       │                              │
       │  POST /api/workflows/42/     │
       │  activate                    │
       │ ──────────────────────────►  │
       │                              ├── WorkflowRepository.activate()
       │                              ├── EventBus.subscribe(trigger, wf_id)
       │                              │
       │  200 OK                      │
       │ ◄──────────────────────────  │
       │                              │
       │  ─── [pasa el tiempo] ───    │
       │                              │
       │                              │  EventBus recibe evento
       │                              │  └── WorkflowEngine.execute(42)
       │                              │      ├── Estado → RUNNING
       │                              │      ├── Paso 1 → OK
       │                              │      ├── Paso 2 → OK
       │                              │      └── Estado → COMPLETED
       │                              │
       │  GET /api/workflows/42/      │
       │  history                     │
       │ ──────────────────────────►  │
       │                              ├── WorkflowRepository.get_history()
       │                              │
       │  200 OK                      │
       │  { "ejecuciones": [...] }   │
       │ ◄──────────────────────────  │
```

---

# 🛠️ PARTE 3: TECH STACK Y DECISIONES TÉCNICAS

## 3.1 Stack completo

| Capa | Tecnología | Versión | Por qué |
|---|---|---|---|
| Lenguaje | **Python** | 3.10+ | Portable, SQLite nativo, empaquetable, el cliente no instala nada extra |
| Web Framework | **Flask** | 3.x | Ligero, zero dependencias innecesarias, suficiente para un servidor local |
| Base de datos | **SQLite** | 3.x (nativo Python) | Zero config, zero servidor, zero internet, un solo archivo |
| Frontend | **HTML + CSS + JS vanilla** | — | Sin framework, sin node_modules, sin build step, funciona del zip |
| Empaquetado | **PyInstaller** (primario) / **Nuitka** (alternativo) | 6.x / 2.x | Convierte Python en .exe. Nuitka produce menos falsos positivos de antivirus |
| Servidor web | **Werkzeug** (incluido en Flask) | — | Suficiente para uso local |
| Tiempo/CRON | **threading.Timer** + SQLite (loop interno) | — | Zero dependencias. Sin APScheduler. Un hilo que revisa cada 60s |
| Cifrado | **hashlib + hmac** (stdlib) + **bcrypt** | — | bcrypt para contraseñas de usuario. HMAC-SHA256 para License Keys |
| Testing | **pytest** + **pytest-cov** | 8.x | Tests unitarios por componente, cobertura mínima 70% |
| Parser seguro | **lark-parser** (si se requiere sintaxis compleja) o **parser recursivo manual** | — | Para ConditionEvaluator. NUNCA `eval()` |

## 3.2 Decisiones de arquitectura

### ¿Por qué NO TypeScript/React/Node?
- El cliente necesita **un solo archivo ejecutable**. Node.js requiere npm install, node_modules, etc.
- Python + PyInstaller/Nuitka = un solo .exe de ~80MB. Listo.
- JS vanilla sin framework = el frontend cabe en 3 archivos, sin build step.

### ¿Por qué NO PostgreSQL/MySQL?
- El producto se instala en la computadora del cliente. No podemos asumir que tenga PostgreSQL.
- SQLite es zero config, zero mantenimiento, y aguanta perfectamente para una PYME (gigabytes de datos).

### ¿Por qué una SOLA base SQLite y no 5?
- **v1.0 tenía 5 bases separadas (workflows.db, crm.db, inventory.db, invoices.db, config.db).** Esto complicaba backups, conexiones y consultas跨 base.
- **v2.0: Una sola base de datos** `workflow_determinista.db` con todas las tablas. Un solo archivo de backup, una sola conexión, joins directos entre tablas.

### ¿Por qué NO APScheduler?
- APScheduler agrega 200KB+ al .exe, tiene su propio event loop que puede interferir con Flask, y tiene bugs conocidos con hilos.
- Un `threading.Timer` recursivo que revisa cada 60s + consulta SQLite es más simple, más predecible, y zero dependencias.

### ¿Por qué NO Docker?
- Docker requiere que el cliente instale Docker. Eso es una barrera de entrada enorme.
- PyInstaller/Nuitka produce un `.exe` que corre en cualquier Windows 10/11 sin instalar nada.

### ¿Por qué NO asincrónico (asyncio)?
- Para un servidor local con 1-5 usuarios concurrentes, Flask síncrono es más que suficiente.
- asyncio agrega complejidad sin beneficio real para este caso de uso.

## 3.3 Estructura de directorios

```
WorkflowDeterminista/
├── src/
│   ├── main.py                    # Entry point: inicia servidor web + workers
│   ├── config.py                  # Configuración global
│   │
│   ├── web/                       # Web UI
│   │   ├── app.py                 # Flask app, rutas
│   │   ├── templates/             # HTML templates
│   │   │   ├── login.html
│   │   │   ├── dashboard.html
│   │   │   ├── chat.html
│   │   │   ├── editor.html        # ✨ NUEVO: Editor visual de workflows
│   │   │   ├── workflow_list.html
│   │   │   ├── workflow_detail.html
│   │   │   └── settings.html
│   │   └── static/                # CSS + JS
│   │       ├── style.css
│   │       ├── app.js
│   │       └── editor.js          # ✨ NUEVO: Lógica del editor visual
│   │
│   ├── workflow/                  # Workflow Engine
│   │   ├── engine.py              # WorkflowEngine (ciclo de vida)
│   │   ├── step_executor.py       # StepExecutor (ejecuta pasos)
│   │   ├── condition_evaluator.py # ConditionEvaluator (evalúa reglas con parser seguro)
│   │   ├── branch_handler.py      # BranchHandler (if/else/switch)
│   │   ├── loop_handler.py        # LoopHandler (for/while/for each)
│   │   ├── error_handler.py       # ErrorHandler (retry, fallback, dead-letter)
│   │   └── repository.py          # WorkflowRepository (SQLite CRUD)
│   │
│   ├── events/                    # Event System
│   │   ├── bus.py                 # EventBus (pub/sub persistente)
│   │   ├── file_watcher.py        # FileWatcher (monitoreo de archivos)
│   │   ├── webhook_server.py      # WebhookServer (HTTP triggers con API Key obligatoria)
│   │   ├── schedule_worker.py     # ScheduleWorker (cron con threading.Timer)
│   │   ├── db_trigger.py          # DatabaseTrigger (cambios en SQLite)
│   │   └── email_watcher.py       # EmailWatcher (IMAP inbox)
│   │
│   ├── tools/                     # Business Tools (6 en MVP)
│   │   ├── crm/                   # CRM Pipeline
│   │   │   ├── __init__.py
│   │   │   ├── models.py          # Lead, Stage, Pipeline
│   │   │   ├── repository.py      # SQLite CRUD
│   │   │   └── service.py         # Lógica de negocio
│   │   ├── invoice/               # Invoice Maker
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   ├── inventory/             # Stock Watch
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   ├── repository.py
│   │   │   └── service.py
│   │   ├── notification/          # Notification Dispatcher
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── service.py         # Email, SMS, push, Slack
│   │   ├── autopilot/             # Auto Pilot
│   │   │   ├── __init__.py
│   │   │   └── service.py         # Plantillas de automatización
│   │   └── logic_gate/            # Logic Gate
│   │       ├── __init__.py
│   │       └── service.py         # Evaluación de reglas
│   │
│   ├── nlp/                       # NLP Determinista
│   │   ├── intent_classifier.py   # Clasificador por keywords
│   │   ├── entity_extractor.py    # Extractor por regex
│   │   ├── templates.py           # Plantillas de intención (10+ templates)
│   │   └── bilingual_router.py    # Detector ES/EN
│   │
│   ├── data/                      # Persistencia
│   │   ├── database_manager.py    # Singleton SQLite (UN solo archivo: workflow_determinista.db)
│   │   └── backup_engine.py       # Backup automático a USB
│   │
│   ├── license/                   # Sistema de Licencias
│   │   ├── generator.py           # Genera License Keys
│   │   └── validator.py           # Valida licencias + trial (30 días)
│   │
│   ├── utils/                     # Utilidades
│   │   ├── logger.py              # Logging estructurado
│   │   └── helpers.py             # Funciones auxiliares
│   │
│   └── tests/                     # ✨ NUEVO: Tests (mismo nivel que web/, workflow/, etc.)
│       ├── conftest.py            # Fixtures compartidas (DB en memoria, app de prueba)
│       ├── test_engine.py         # Tests del WorkflowEngine
│       ├── test_step_executor.py  # Tests del StepExecutor
│       ├── test_condition_eval.py # Tests del ConditionEvaluator
│       ├── test_event_bus.py      # Tests del EventBus
│       ├── test_schedule.py       # Tests del ScheduleWorker
│       ├── test_crm.py            # Tests del CRM
│       ├── test_invoice.py        # Tests de Invoice
│       ├── test_inventory.py      # Tests de Inventory
│       ├── test_notification.py   # Tests de Notifications
│       ├── test_nlp.py            # Tests del NLP Determinista
│       ├── test_license.py        # Tests del License System
│       └── test_api.py            # Tests de integración de API
│
├── installer/                     # Instalador
│   ├── installer_main.py          # GUI de instalación
│   ├── build_pyinstaller.sh       # Script para buildear .exe con PyInstaller
│   └── build_nuitka.sh            # ✨ NUEVO: Script para buildear con Nuitka (menos falsos positivos)
│
├── scripts/                       # Scripts auxiliares
│   └── generate_license_key.py    # Script para generar License Keys manualmente
│
├── docs/                          # Documentación
│   └── MASTERPLAN-WORKFLOW-DETERMINISTA.md
│
├── requirements.txt               # Dependencias Python (bcrypt, pytest, etc.)
├── Dockerfile                     # (Opcional) Para usuarios con Docker
└── README.md                      # Instrucciones de instalación
```

---

# 💾 PARTE 4: MODELO DE DATOS (SCHEMAS)

> ✅ **v2.0:** Todos los datos se guardan en UNA SOLA base SQLite: `workflow_determinista.db`. Un solo archivo para backup, una sola conexión, joins directos entre tablas.

## 4.1 Esquema unificado: `workflow_determinista.db`

```sql
-- ============================================================
-- WORKFLOW DETERMINISTA — Esquema Unificado
-- Una sola base de datos, todas las tablas.
-- ============================================================

-- ── Workflow Engine ──────────────────────────────────────────

CREATE TABLE workflow_definitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,            -- "Registro de cliente con bienvenida"
    description     TEXT,                     -- "Cuando un cliente nuevo se registra..."
    trigger_type    TEXT NOT NULL,            -- 'schedule' | 'event' | 'webhook' | 'file' | 'manual'
    trigger_config  TEXT NOT NULL,            -- JSON: {"cron": "0 9 * * *"} o {"event": "crm.lead.created"}
    steps           TEXT NOT NULL,            -- JSON: [{"id":1, "tool":"crm", ...}]
    status          TEXT DEFAULT 'active',    -- 'active' | 'paused' | 'archived'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workflow_executions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id     INTEGER NOT NULL,
    status          TEXT NOT NULL,            -- 'running' | 'completed' | 'failed' | 'cancelled'
    trigger_data    TEXT,                     -- JSON
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP,
    duration_ms     INTEGER,
    error_message   TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id)
);

CREATE TABLE workflow_step_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id    INTEGER NOT NULL,
    step_id         INTEGER NOT NULL,
    tool            TEXT NOT NULL,
    action          TEXT NOT NULL,
    input_data      TEXT,                     -- JSON
    output_data     TEXT,                     -- JSON
    status          TEXT NOT NULL,            -- 'pending' | 'running' | 'completed' | 'failed'
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    duration_ms     INTEGER,
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    FOREIGN KEY (execution_id) REFERENCES workflow_executions(id)
);

-- ── Event Bus (cola de eventos persistente) ──────────────────

CREATE TABLE event_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    event_data      TEXT NOT NULL,            -- JSON
    workflow_id     INTEGER,                  -- NULL si no está asignado aún
    status          TEXT DEFAULT 'pending',   -- 'pending' | 'processing' | 'completed' | 'failed'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at    TIMESTAMP
);

CREATE TABLE event_subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    workflow_id     INTEGER NOT NULL,
    FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id)
);

-- ── CRM ─────────────────────────────────────────────────────

CREATE TABLE leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    company         TEXT,
    stage           TEXT DEFAULT 'new',       -- 'new'|'contacted'|'qualified'|'proposal'|'negotiation'|'closed_won'|'closed_lost'
    source          TEXT,                     -- 'web_form' | 'email' | 'manual'
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE lead_activities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         INTEGER NOT NULL,
    activity_type   TEXT NOT NULL,            -- 'email' | 'call' | 'meeting' | 'note'
    description     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

-- ── Inventory ───────────────────────────────────────────────

CREATE TABLE products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT UNIQUE,
    name            TEXT NOT NULL,
    description     TEXT,
    category        TEXT,
    stock           INTEGER DEFAULT 0,
    min_stock       INTEGER DEFAULT 10,       -- Umbral para alerta de stock bajo
    price           REAL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE stock_movements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL,
    type            TEXT NOT NULL,            -- 'in' | 'out' | 'adjustment'
    quantity        INTEGER NOT NULL,
    reason          TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

-- ── Invoices ────────────────────────────────────────────────

CREATE TABLE invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    number          TEXT UNIQUE,              -- "FAC-2026-0001"
    client_name     TEXT NOT NULL,
    client_email    TEXT,
    items           TEXT NOT NULL,            -- JSON array
    subtotal        REAL,
    tax_rate        REAL DEFAULT 0.16,
    tax_amount      REAL,
    discount        REAL DEFAULT 0,
    total           REAL,
    status          TEXT DEFAULT 'pending',   -- 'pending' | 'paid' | 'overdue' | 'cancelled'
    due_date        DATE,
    issued_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at         TIMESTAMP,
    notes           TEXT
);

-- ── Configuración ───────────────────────────────────────────

CREATE TABLE settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
    -- admin_password_hash, smtp_server, smtp_port, etc.
);

-- ── Licencias ───────────────────────────────────────────────

CREATE TABLE license (
    key             TEXT PRIMARY KEY,         -- "WFD-A7K2-9PL3-X5M8"
    type            TEXT NOT NULL,            -- 'individual' | 'reseller' | 'enterprise'
    client_name     TEXT,
    issued_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,
    is_trial        INTEGER DEFAULT 0,        -- 1 si es trial
    trial_started_at TIMESTAMP                -- Fecha de primer inicio sin key
);

-- ── Auditoría (TABLA PROPIA, no mezclada con config) ────────

CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event           TEXT NOT NULL,            -- 'workflow.executed' | 'tool.called' | 'settings.changed' | 'login.failed' | 'license.validated'
    details         TEXT,                     -- JSON con detalles (NUNCA incluye contraseñas o License Keys)
    ip_address      TEXT,                     -- Dirección IP desde donde se originó
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Índices para performance ────────────────────────────────

CREATE INDEX idx_workflow_status ON workflow_definitions(status);
CREATE INDEX idx_execution_workflow ON workflow_executions(workflow_id);
CREATE INDEX idx_execution_status ON workflow_executions(status);
CREATE INDEX idx_step_log_execution ON workflow_step_logs(execution_id);
CREATE INDEX idx_event_queue_status ON event_queue(status);
CREATE INDEX idx_event_subscriptions ON event_subscriptions(event_type);
CREATE INDEX idx_leads_stage ON leads(stage);
CREATE INDEX idx_products_low_stock ON products(stock, min_stock);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_audit_log_event ON audit_log(event);
CREATE INDEX idx_audit_log_created ON audit_log(created_at);
```

## 4.2 Ventajas del esquema unificado

| Aspecto | v1.0 (5 DBs separadas) | v2.0 (una sola DB) |
|---|---|---|
| Backups | 5 archivos que respaldar | 1 solo archivo |
| Conexiones | 5 conexiones abiertas | 1 conexión |
| Joins entre tablas | No posible (DBs separadas) | Joins directos SQL |
| Consistencia transaccional | No (cada DB su propia transacción) | Sí (transacción única) |
| Complejidad | Alta (5 DatabaseManager) | Baja (1 DatabaseManager) |
| Portabilidad | 5 archivos que moverse | 1 archivo |

---

# ⚙️ PARTE 5: COMPONENTES DEL SISTEMA

> Especificación detallada de cada componente. Cada sección es suficiente para que un desarrollador construya el componente.

## 5.1 WorkflowEngine (`src/workflow/engine.py`)

**Responsabilidad:** Ejecutar workflows paso a paso, manejando su ciclo de vida completo.

**API Pública:**

```python
class WorkflowEngine:
    def execute(workflow_id: int, trigger_data: dict = None) -> ExecutionResult
        # 1. Cargar definición del workflow desde WorkflowRepository
        # 2. Crear execution en estado 'running'
        # 3. Iterar sobre steps:
        #    a. Si step tiene condición → evaluar con ConditionEvaluator
        #    b. Si step es branch → BranchHandler.evaluate()
        #    c. Si step es loop → LoopHandler.execute()
        #    d. Si step es normal → StepExecutor.execute(tool, action, params)
        #    e. Si step falla → ErrorHandler.handle()
        # 4. Actualizar execution a 'completed' o 'failed'
        # 5. Guardar step_logs por cada paso
        # 6. Emitir evento 'workflow.completed' o 'workflow.failed'

    def pause(workflow_id: int) -> bool
        # Cambia estado del workflow a 'paused'
        # Workflows paused no responden a triggers

    def resume(workflow_id: int) -> bool
        # Cambia estado del workflow a 'active'
        # Vuelve a escuchar triggers

    def cancel_execution(execution_id: int) -> bool
        # Cancela una ejecución en curso

    def get_status(workflow_id: int) -> dict
        # Retorna estado actual + última ejecución
```

**Diagrama de estados internos:**

```
execute() llamado
     │
     ▼
PENDING ──► RUNNING ──► STEP_EXECUTING ──► STEP_COMPLETED ──► ...
     │                      │                      │
     │                      ▼                      ▼
     │                  STEP_FAILED          (más pasos?)
     │                      │                 │         │
     │                      ▼                 ▼         ▼
     │                 RETRY (x3)         RUNNING   COMPLETED
     │                      │
     │                      ▼
     │                 DEAD_LETTER
     ▼
  FAILED
```

## 5.2 StepExecutor (`src/workflow/step_executor.py`)

**Responsabilidad:** Ejecutar un paso individual, llamando a la herramienta correcta.

```python
class StepExecutor:
    def execute(step: dict, context: dict) -> StepResult
        # step = {
        #   "id": 1,
        #   "tool": "crm",
        #   "action": "create_lead",
        #   "params": {"name": "$input.nombre", "email": "$input.email"},
        #   "timeout": 30
        # }
        # 
        # 1. Resolver variables: $input → context, $output.step1 → context.steps_output[1]
        # 2. Validar que la tool existe
        # 3. Ejecutar con timeout
        # 4. Retornar StepResult(status, output_data, duration_ms)
```

**Resolución de variables:**
- `$input.nombre` → del trigger_data o del input original del workflow
- `$output.step1.email` → del resultado del paso con id=1
- `$settings.smtp_server` → de la tabla settings en config.db
- `$now` → datetime actual
- `$random` → string aleatorio

## 5.3 ConditionEvaluator (`src/workflow/condition_evaluator.py`)

**Responsabilidad:** Evaluar condiciones en runtime usando los datos disponibles.

```python
class ConditionEvaluator:
    def evaluate(condition: str, context: dict) -> bool
        # condition = "stock < 10"
        # context = {"stock": 5, "producto": "Tornillos"}
        # → Retorna: True

    def SUPPORTED_OPERATORS:
        - == (igual)
        - != (distinto)
        - > (mayor que)
        - < (menor que)
        - >= (mayor o igual)
        - <= (menor o igual)
        - in (está en lista)
        - contains (contiene texto)
        - AND / OR (combinación lógica)

    # ⚠️ SEGURIDAD: NUNCA usar eval() ni exec().
    # ⚠️ NUNCA permitir funciones Python arbitrarias.
    # Implementación: parser recursivo descendente (recursive descent parser)
    # que convierte la expresión en un AST y luego evalúa el AST.
    #
    # Alternativa segura: usar lark-parser con una gramática restringida
    # que solo permita los operadores listados.
    #
    # Prohibido:
    #   def evaluate(condition, context):
    #       return eval(condition)  # ❌ NUNCA
    #
    # Permitido:
    #   def evaluate(condition, context):
    #       tokens = self.tokenize(condition)
    #       ast = self.parse(tokens)    # Recursive descent
    #       return self.eval_ast(ast, context)  # ✅
```

## 5.3b WorkflowEditor (`src/web/editor.py`) — NUEVO

**Responsabilidad:** Editor visual de workflows para cuando el NLP no entienda o el usuario quiera modificar.

```python
class WorkflowEditor:
    def get_tools_and_actions() -> List[ToolDef]
        # Retorna todas las tools disponibles con sus acciones y parámetros
        # [
        #   {"tool": "crm", "actions": [
        #       {"action": "create_lead", "params": [
        #           {"name": "name", "type": "string", "required": True},
        #           {"name": "email", "type": "string", "required": True},
        #       ]}
        #   ]},
        #   ...
        # ]
        # Esto se usa en el frontend para mostrar un formulario dinámico

    def validate_step_sequence(steps: List[dict]) -> ValidationResult
        # Valida que los pasos tengan sentido:
        # - Las tools existen
        # - Los parámetros requeridos están presentes
        # - Los tipos de datos son correctos
        # - No hay referencias circulares ($output.stepX apuntando a stepY)

    def auto_complete(text: str) -> List[Completion]
        # Autocompletado para el editor:
        # Usuario escribe "crm." → muestra: create_lead, update_lead, get_lead...
```

**Flujo del editor visual:**

```
1. Usuario crea workflow desde chat (NLP)
2. NLP devuelve workflow sugerido
3. Usuario puede:
   a. ✅ Aceptar el workflow tal cual
   b. ✏️ Editarlo en el editor visual
   c. ❌ Rechazarlo y empezar desde cero en el editor

El editor visual permite:
- Agregar/quitar pasos
- Configurar condiciones (if/else)
- Configurar bucles (for each)
- Mapear variables ($input, $output, $settings)
- Probar el workflow manualmente antes de activarlo
```

## 5.4 EventBus (`src/events/bus.py`)

**Responsabilidad:** Sistema de mensajería interno pub/sub persistente.

```python
class EventBus:
    def subscribe(event_type: str, workflow_id: int)
        # Registra que workflow_id debe ejecutarse cuando ocurra event_type
        # event_type examples: "crm.lead.created", "invoice.overdue", 
        #                      "file.created", "schedule.triggered"

    def unsubscribe(event_type: str, workflow_id: int)
        # Elimina la suscripción

    def publish(event_type: str, data: dict)
        # 1. Guardar evento en SQLite (por si el sistema se apaga)
        # 2. Buscar workflows suscritos a event_type
        # 3. Para cada workflow:
        #    a. Si el workflow está 'active':
        #       - WorkflowEngine.execute(workflow_id, data)
        #    b. Si el workflow está 'paused':
        #       - Guardar evento como pendiente

    def get_pending_events() -> list
        # Retorna eventos no procesados (útil al iniciar el sistema)
```

**Eventos del sistema:**

| Evento | Cuándo se dispara | Data que lleva |
|---|---|---|
| `system.started` | Al iniciar el sistema | `{timestamp}` |
| `workflow.completed` | Workflow termina OK | `{workflow_id, execution_id, duration_ms}` |
| `workflow.failed` | Workflow falla | `{workflow_id, execution_id, error_message}` |
| `crm.lead.created` | Nuevo lead en CRM | `{lead_id, name, email, ...}` |
| `crm.lead.stage_changed` | Lead cambia de etapa | `{lead_id, from_stage, to_stage}` |
| `invoice.created` | Nueva factura | `{invoice_id, client, total, ...}` |
| `invoice.paid` | Factura pagada | `{invoice_id, amount}` |
| `invoice.overdue` | Factura vencida | `{invoice_id, client, days_overdue}` |
| `inventory.stock_low` | Stock bajo umbral | `{product_id, name, stock, min_stock}` |
| `inventory.stock_out` | Stock en cero | `{product_id, name}` |
| `file.created` | Nuevo archivo en carpeta | `{path, filename, size}` |
| `file.modified` | Archivo modificado | `{path, filename}` |
| `schedule.triggered` | Cron job ejecutado | `{workflow_id, scheduled_time}` |
| `webhook.received` | Webhook HTTP recibido | `{body, headers, method}` |

## 5.5 ScheduleWorker (`src/events/schedule_worker.py`)

**Responsabilidad:** Revisar cada 60s si hay workflows programados para ejecutarse.

> ✅ **v2.0:** Usa `threading.Timer` recursivo. Sin APScheduler. Zero dependencias externas.

```python
class ScheduleWorker:
    def __init__(self):
        self._timer = None
        self._running = False

    def start(self):
        self._running = True
        self._schedule_next()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()

    def _schedule_next(self):
        if not self._running:
            return
        self._timer = threading.Timer(60.0, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self):
        try:
            workflows = WorkflowRepository.get_active_scheduled()
            now = datetime.now()
            for wf in workflows:
                cron = self._parse_cron(wf.trigger_config["cron"])
                if self._should_run_now(cron, now):
                    EventBus.publish("schedule.triggered", {
                        "workflow_id": wf.id,
                        "scheduled_time": now.isoformat()
                    })
        except Exception as e:
            logger.error(f"ScheduleWorker error: {e}")
        finally:
            self._schedule_next()

    def _parse_cron(self, expr: str) -> dict:
        # Parsea expresión cron de 5 campos
        # Retorna dict con listas de valores permitidos por campo
        pass

    def _should_run_now(self, cron: dict, now: datetime) -> bool:
        # Verifica si la fecha/hora actual coincide con la expresión cron
        pass
```

**Formato cron soportado:** 5 campos estándar: `minuto hora día-del-mes mes día-de-la-semana`

| Ejemplo | Significado |
|---|---|
| `0 9 * * *` | Todos los días a las 9:00 AM |
| `0 9 * * 1` | Todos los lunes a las 9:00 AM |
| `*/15 * * * *` | Cada 15 minutos |
| `0 0 1 * *` | El primer día de cada mes a las 12:00 AM |
| `0 9,15 * * *` | A las 9:00 AM y 3:00 PM |

## 5.6 WebhookServer (`src/events/webhook_server.py`)

**Responsabilidad:** Servidor HTTP mínimo para recibir webhooks externos.

> ⚠️ **Seguridad:** La API Key es **OBLIGATORIA**, no opcional. Sin key válida, el webhook retorna 401.

```python
class WebhookServer:
    def __init__(self):
        self._api_key = None  # Se carga de settings al iniciar

    def start(port: int = 8081)
        # Inicia servidor HTTP en puerto 8081 (por defecto)
        # Ruta: POST /webhook/<workflow_id>
        #
        # ⚠️ VALIDACIÓN OBLIGATORIA:
        # Headers requeridos:
        #   X-API-Key: <api_key_configurada>
        #
        # POST /webhook/42
        # Headers: { "X-API-Key": "abc123" }
        # Body: {"order_id": 123, "status": "confirmed"}
        #
        # 1. Validar X-API-Key contra settings
        #    → Si no coincide: 401 Unauthorized
        # 2. Buscar workflow por ID
        #    → Si no existe: 404 Not Found
        # 3. Publicar evento:
        #    EventBus.publish("webhook.received", {workflow_id: 42, body, headers})
        # 4. Retornar 200 OK
        #
        # GET /webhook/health
        # → Retorna 200 OK (health check, sin auth)
```

## 5.7 FileWatcher (`src/events/file_watcher.py`)

**Responsabilidad:** Monitorear cambios en directorios del sistema de archivos.

```python
class FileWatcher(threading.Thread):
    def watch(directory: str, pattern: str = "*", recursive: bool = False)
        # Monitorea 'directory' en busca de archivos nuevos/modificados
        # pattern: "*.csv", "*.txt", "*orden*"
        #
        # Cuando detecta un archivo nuevo:
        # EventBus.publish("file.created", {path, filename, size, extension})
        #
        # Cuando detecta un archivo modificado:
        # EventBus.publish("file.modified", {path, filename})
```

## 5.8 ErrorHandler (`src/workflow/error_handler.py`)

**Responsabilidad:** Manejar fallos en la ejecución de pasos.

```python
class ErrorHandler:
    def handle(step: dict, error: Exception, context: dict) -> StepResult
        # 1. Si step tiene retry configurado:
        #    - Esperar delay * multiplier^attempt
        #    - Reintentar hasta max_attempts
        # 2. Si step tiene fallback action:
        #    - Ejecutar la acción de respaldo
        # 3. Si no hay retry ni fallback:
        #    - Marcar step como failed
        #    - Emitir evento 'workflow.failed'
        #    - Si hay dead-letter queue, guardar ahí

    def DEFAULT_CONFIG:
        max_retries = 3
        base_delay = 5    # segundos
        multiplier = 2    # 5, 10, 20 segundos
        use_fallback = True
```

## 5.9 DatabaseManager (`src/data/database_manager.py`)

**Responsabilidad:** Gestionar todas las bases de datos SQLite.

```python
class DatabaseManager:
    def __init__(data_dir: str)
        # data_dir = ~/.workflow_determinista/
        # Crea los archivos:
        #   - workflows.db
        #   - crm.db
        #   - inventory.db
        #   - invoices.db
        #   - config.db
        #
        # Si no existen, ejecuta CREATE TABLEs automáticamente

    def backup(path: str = None) -> str
        # Copia todos los .db a path (ej: /mnt/usb/backup_2026-06-06/)
        # Retorna: ruta del backup

    def get_connection(db_name: str) -> sqlite3.Connection
        # Retorna conexión a la base específica
        # WAL mode para mejor rendimiento
```

## 5.10 NLP Determinista (`src/nlp/`)

**Responsabilidad:** Convertir texto en lenguaje natural a definiciones de workflow.

**NO usa AI. NO usa LLM. NO usa APIs externas.**

### IntentClassifier (`intent_classifier.py`)

```python
class IntentClassifier:
    def classify(text: str) -> IntentResult
        # text: "Quiero que cuando un cliente nuevo se registre, 
        #        se guarde en mi base de datos y se le envíe 
        #        un correo de bienvenida"
        #
        # 1. Normalizar: lowercase, quitar tildes
        # 2. Detectar idioma (BilingualRouter)
        # 3. Buscar keywords en tabla de operaciones:
        #    - "registr" → CREATE
        #    - "client" / "client" → CRM
        #    - "correo" / "email" → NOTIFICATION
        #    - "base de datos" / "database" → DATA
        #    - "cuando" / "when" → TRIGGER_EVENT
        # 4. Puntuar cada candidato (2 pts exact match, 1 pt substring)
        # 5. Retornar top N con confianza 0.0-1.0
```

### Plantillas de Intención (`templates.py`)

```python
TEMPLATES = [
    {
        "name": "registro_cliente",
        "keywords_es": ["registr", "nuev", "client", "guard", "cre", "agreg"],
        "keywords_en": ["regist", "new", "client", "custom", "save", "creat", "add"],
        "trigger": {
            "type": "event",
            "config": {"event": "crm.lead.created"}
        },
        "steps": [
            {"tool": "crm", "action": "create_lead", 
             "params": {"name": "$input.nombre", "email": "$input.email"}},
            {"tool": "notification", "action": "send_email",
             "params": {"to": "$input.email", "template": "welcome",
                        "subject": "¡Bienvenido!"}}
        ]
    },
    {
        "name": "alerta_stock_bajo",
        "keywords_es": ["inventari", "stock", "baj", "alert", "compr", "product"],
        "keywords_en": ["invent", "stock", "low", "alert", "purchas", "product"],
        "trigger": {
            "type": "schedule",
            "config": {"cron": "0 9 * * *"}
        },
        "steps": [
            {"tool": "inventory", "action": "check_low_stock"},
            {"tool": "notification", "action": "send_email",
             "params": {"to": "$settings.admin_email", 
                        "subject": "Alerta: Productos con stock bajo"}}
        ]
    },
    {
        "name": "factura_automatica",
        "keywords_es": ["factur", "invoice", "cobr", "pago", "venc"],
        "keywords_en": ["invoic", "bill", "charg", "payment", "due"],
        "trigger": {
            "type": "schedule",
            "config": {"cron": "0 9 * * 1"}  # Lunes 9am
        },
        "steps": [
            {"tool": "invoice", "action": "generate_pending"},
            {"tool": "notification", "action": "send_email",
             "params": {"to": "$settings.admin_email",
                        "subject": "Facturas de la semana"}}
        ]
    },
    {
        "name": "backup_automatico",
        "keywords_es": ["backup", "respaldo", "copi", "seguridad", "base", "datos"],
        "keywords_en": ["backup", "sav", "copi", "secur", "databas"],
        "trigger": {
            "type": "schedule",
            "config": {"cron": "0 23 * * *"}  # 11pm cada día
        },
        "steps": [
            {"tool": "system", "action": "backup_database"}
        ]
    },
    {
        "name": "email_cumpleanos",
        "keywords_es": ["cumpleañ", "cumple", "felic", "navidad", "aniversari"],
        "keywords_en": ["birthday", "happy", "anniversari", "christma"],
        "trigger": {
            "type": "schedule",
            "config": {"cron": "0 8 * * *"}  # 8am cada día
        },
        "steps": [
            {"tool": "notification", "action": "send_birthday_emails"}
        ]
    }
]
```

---

# 🧰 PARTE 6: LAS 10 HERRAMIENTAS (APIs)

> **Estrategia MVP:** Lanzamos con **6 herramientas** (CRM, Invoice, Inventory, Notification, Auto Pilot, Logic Gate). Las otras 4 se agregan como actualizaciones gratuitas post-lanzamiento.

## 6.1 CRM Pipeline (MVP ✅)

**Propósito:** Gestionar clientes potenciales y ventas.

**API:**

```python
class CRMService:
    def create_lead(name, email, phone=None, company=None, source="manual") -> Lead
        # Crea un nuevo lead en etapa 'new'
        # Emite evento: 'crm.lead.created'

    def update_lead(lead_id, **fields) -> Lead
        # Actualiza campos del lead
        # Si cambia stage, emite: 'crm.lead.stage_changed'

    def get_lead(lead_id) -> Lead
    def list_leads(stage=None, limit=50, offset=0) -> List[Lead]
    def delete_lead(lead_id) -> bool

    def advance_stage(lead_id) -> Lead
        # new → contacted → qualified → proposal → negotiation
    def close_won(lead_id) -> Lead
    def close_lost(lead_id, reason=None) -> Lead

    def get_stats() -> dict
        # { total: 150, by_stage: {new:30, contacted:45, ...},
        #   conversion_rate: 0.23 }
```

**Eventos que emite:** `crm.lead.created`, `crm.lead.stage_changed`
**Eventos que escucha:** ninguno

## 6.2 Invoice Maker (MVP ✅)

**Propósito:** Generar y gestionar facturas.

**API:**

```python
class InvoiceService:
    def create_invoice(client_name, client_email, items: list, 
                      tax_rate=0.16, discount=0, due_days=30) -> Invoice
        # items = [{"description": "Servicio A", "quantity": 1, "unit_price": 100}]
        # Calcula: subtotal, tax_amount, total
        # Emite: 'invoice.created'

    def mark_paid(invoice_id, amount=None) -> Invoice
        # Marca como pagada
        # Emite: 'invoice.paid'

    def mark_overdue(invoice_id) -> Invoice
        # Emite: 'invoice.overdue'

    def cancel(invoice_id) -> Invoice
    def get_invoice(invoice_id) -> Invoice
    def list_invoices(status=None, limit=50) -> List[Invoice]
    def get_overdue_invoices() -> List[Invoice]
        # Retorna facturas con due_date < hoy y status = 'pending'

    def get_stats() -> dict
        # { total: 45, pending: 12, paid: 30, overdue: 3,
        #   total_revenue: 45000.00 }
```

**Eventos que emite:** `invoice.created`, `invoice.paid`, `invoice.overdue`
**Eventos que escucha:** ninguno

## 6.3 Stock Watch / Inventory (MVP ✅)

**Propósito:** Controlar inventario y generar alertas de stock.

**API:**

```python
class InventoryService:
    def add_product(sku, name, description="", category="", 
                   stock=0, min_stock=10, price=0) -> Product

    def update_stock(product_id, quantity, type="adjustment", reason="") -> Product
        # type: 'in' (agregar), 'out' (quitar), 'adjustment' (set)
        # Registra movimiento en stock_movements
        # Si stock < min_stock → emite: 'inventory.stock_low'
        # Si stock == 0 → emite: 'inventory.stock_out'

    def get_product(product_id) -> Product
    def list_products(category=None, low_stock_only=False) -> List[Product]
    def delete_product(product_id) -> bool

    def get_low_stock_products() -> List[Product]
        # stock < min_stock

    def get_stats() -> dict
        # { total_products: 200, low_stock: 15, out_of_stock: 3,
        #   total_value: 150000.00 }
```

**Eventos que emite:** `inventory.stock_low`, `inventory.stock_out`
**Eventos que escucha:** ninguno

## 6.4 Notification Dispatcher (MVP ✅)

**Propósito:** Enviar notificaciones por múltiples canales.

**API:**

```python
class NotificationService:
    def send_email(to, subject, body, template=None) -> NotificationResult
        # Si hay template, carga el template HTML
        # Envía vía SMTP (configurado en settings)
        # Si no hay SMTP configurado, guarda en cola

    def send_notification(channel, recipients, message, **kwargs) -> NotificationResult
        # channel: 'email' | 'log' (inicialmente solo estos dos)
        # Más canales en v1.1: 'sms' | 'push' | 'slack' | 'teams'

    def send_birthday_emails() -> int
        # Busca leads con cumpleaños hoy
        # Envía email a cada uno
        # Retorna: cantidad de emails enviados

    def configure_smtp(server, port, username, password) -> bool
        # Guarda configuración SMTP en settings

    def get_status() -> dict
        # { smtp_configured: true, queue_size: 0 }
```

**Eventos que emite:** ninguno
**Eventos que escucha:** ninguno (es llamado por otros componentes)

## 6.5 Auto Pilot (MVP ✅)

**Propósito:** Plantillas predefinidas de automatización para empezar rápido.

**API:**

```python
class AutoPilotService:
    def suggest_templates(text: str) -> List[dict]
        # Usa IntentClassifier + Templates para sugerir automatizaciones
        # Retorna: [{"name": "Registro de cliente", "confidence": 0.85, "steps": [...]}]

    def get_quick_templates() -> List[dict]
        # Retorna templates populares para la pantalla de inicio

    def create_from_template(template_name: str, params: dict) -> WorkflowDefinition
        # Crea un workflow a partir de una plantilla
        # params: valores para las variables $input en la plantilla
```

**Eventos que emite:** ninguno
**Eventos que escucha:** ninguno

## 6.6 Logic Gate (MVP ✅)

**Propósito:** Evaluar reglas de negocio y condiciones.

**API:**

```python
class LogicGateService:
    def evaluate_rule(rule: str, context: dict) -> bool
        # rule: "pago > 500 AND cliente_tipo == 'nuevo'"
        # context: {"pago": 600, "cliente_tipo": "nuevo"}
        # → True

    def evaluate_workflow_conditions(workflow_id: int, context: dict) -> List[ConditionResult]
        # Evalúa todas las condiciones de un workflow
        # Retorna qué condiciones se cumplen y cuáles no

    def validate_expression(expression: str) -> ValidationResult
        # Valida que una expresión sea sintácticamente correcta
        # Retorna: {valid: true} o {valid: false, error: "Token no esperado"}
```

**Eventos que emite:** ninguno
**Eventos que escucha:** ninguno (es llamado por WorkflowEngine)

## 6.7 API Connector (Post-MVP v1.1)

**Propósito:** Conectar sistemas externos vía API REST.

**API tentativa:**
```python
class APIConnectorService:
    def call(method, url, headers, body, timeout=30) -> APIResponse
    def configure_connection(name, base_url, auth_type, credentials)
```

## 6.8 Auth Guardian (Post-MVP v1.1)

**Propósito:** Control de acceso basado en roles.

**API tentativa:**
```python
class AuthGuardianService:
    def check_permission(user, action, resource) -> bool
    def add_user(username, role, password_hash)
    def list_users()
```

## 6.9 Data Keeper (Post-MVP v1.1)

**Propósito:** Almacenamiento genérico de datos (key-value o tablas dinámicas).

**API tentativa:**
```python
class DataKeeperService:
    def save(collection, record) -> Record
    def query(collection, filters) -> List[Record]
    def delete(collection, record_id)
```

## 6.10 Calc Engine (Post-MVP v1.1)

**Propósito:** Cálculos automáticos (impuestos, descuentos, comisiones).

**API tentativa:**
```python
class CalcEngineService:
    def calculate(expression, variables) -> float
    def define_formula(name, expression)
```

## 6.11 Structor (Post-MVP v1.1)

**Propósito:** Organizar archivos y carpetas automáticamente.

**API tentativa:**
```python
class StructorService:
    def organize(directory, rules) -> OrganizeResult
    def create_folder_structure(template, base_path)
```

---

# 🖥️ PARTE 7: WEB UI

## 7.1 Especificación de pantallas

### Pantalla 1: Login

```
┌─────────────────────────────────────────────┐
│  🔐 Workflow Determinista                   │
│                                             │
│  ┌─────────────────────────────────┐        │
│  │  Usuario: admin                  │        │
│  ├─────────────────────────────────┤        │
│  │  Contraseña: ********           │        │
│  ├─────────────────────────────────┤        │
│  │  [ Iniciar sesión ]             │        │
│  └─────────────────────────────────┘        │
│                                             │
│  ┌─────────────────────────────────┐        │
│  │  ⏳ Período de prueba: 5 días   │        │
│  │  [ Comprar licencia ]           │        │
│  └─────────────────────────────────┘        │
└─────────────────────────────────────────────┘
```

**Tecnología:** Formulario HTML + POST a `/api/auth/login`
**Seguridad:** ✅ Contraseña hasheada con **bcrypt** (cost=12). ✅ Cookie con **httpOnly, secure, sameSite=Lax**. ✅ Rate limiting: 10 intentos cada 15 minutos. ✅ Log de intentos fallidos en audit_log.

### Pantalla 2: Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Determinista    [admin] ⚙️ Configuración          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📊 Resumen                                    [+ Nuevo WF] │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                      │
│  │ 12   │ │ 8    │ │ 3    │ │ 1    │                      │
│  │Total │ │Activo│ │Error │ │Pausad│                      │
│  └──────┘ └──────┘ └──────┘ └──────┘                      │
│                                                             │
│  🕐 Últimas ejecuciones                                     │
│  ┌─────────────────────────────────────────────────┐       │
│  │ Backup diario          ✅ Completado   hoy 11pm │       │
│  │ Alerta de stock        ✅ Completado   hoy 9am  │       │
│  │ Email de cumpleaños    ❌ Fallido      ayer 8am │       │
│  │ Registro de cliente    ✅ Completado   ayer     │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
│  ⚡ Sugerencias rápidas                                      │
│  ┌─────────────────────────────────────────────────┐       │
│  │ 💡 "Quiero respaldo automático de mi base"      │       │
│  │ 💡 "Enviar facturas los lunes"                  │       │
│  │ 💡 "Alertarme cuando el stock esté bajo"        │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Pantalla 3: Chat (Crear Workflow)

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Determinista    [admin]                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🤖 Asistente Determinista                                  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 👤 Describe lo que necesitas automatizar...              ││
│  │                                                         ││
│  │ "Quiero que cuando un cliente nuevo se registre,        ││
│  │  se guarde en mi base de datos y se le envíe un         ││
│  │  correo de bienvenida"                                  ││
│  │                                                         ││
│  │                                   [ Generar workflow ]  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 🤖 Workflow generado:                                   ││
│  │                                                         ││
│  │ 📌 Nombre: Registro de cliente con bienvenida           ││
│  │ 🔄 Trigger: Cuando un lead sea creado en CRM            ││
│  │                                                         ││
│  │   Paso 1: CRM → Crear lead                              ││
│  │     Parámetros: nombre, email, teléfono                 ││
│  │                                                         ││
│  │   Paso 2: Notificación → Enviar email                   ││
│  │     Destino: $input.email                               ││
│  │     Plantilla: bienvenida                               ││
│  │                                                         ││
│  │              [✏️ Editar] [✅ Activar] [❌ Descartar]    ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘

### Pantalla 3b: Editor Visual de Workflows (NUEVA)

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Determinista    [admin]    ← Volver               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ✏️ Editar Workflow: Registro de cliente                    │
│                                                             │
│  🔄 Trigger: [Cuando un lead sea creado en CRM       ▼]    │
│                                                             │
│  ┌─ Paso 1 ─────────────────────────────────────────────┐  │
│  │ Tool: [CRM ▼]  Acción: [Crear lead             ▼]    │  │
│  │                                                      │  │
│  │ Parámetros:                                          │  │
│  │   nombre:  [$input.nombre          ]                 │  │
│  │   email:   [$input.email           ]                 │  │
│  │   teléfono:[$input.telefono        ]                 │  │
│  │                                                      │  │
│  │ ⚡ Condición: [stock < 10         ] (opcional)       │  │
│  │                                                      │  │
│  │ [+ Agregar condición]  [Eliminar paso]              │  │
│  └──────────────────────────────────────────────────────┘  │
│                          │                                  │
│                          ▼                                  │
│  ┌─ Paso 2 ─────────────────────────────────────────────┐  │
│  │ Tool: [Notificación ▼] Acción: [Enviar email    ▼]   │  │
│  │                                                      │  │
│  │ Parámetros:                                          │  │
│  │   to:      [$output.paso1.email      ]               │  │
│  │   template:[bienvenida                ]               │  │
│  │                                                      │  │
│  │ [+ Agregar paso]                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  [💾 Guardar]  [▶️ Probar]  [✅ Activar]  [❌ Cancelar]   │
└─────────────────────────────────────────────────────────────┘
```

### Pantalla 4: Lista de Workflows

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Determinista    [admin]                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📋 Mis Workflows                              [+ Nuevo]   │
│                                                             │
│  ┌────┬────────────────┬──────────┬────────────┬──────────┐│
│  │ ID │ Nombre         │ Estado   │ Última ej. │ Acciones ││
│  ├────┼────────────────┼──────────┼────────────┼──────────┤│
│  │ 1  │ Backup diario  │ ✅ Activo│ hoy 11pm   │ ⏸ ✏️ 🗑 ││
│  │ 2  │ Alerta stock   │ ✅ Activo│ hoy 9am    │ ⏸ ✏️ 🗑 ││
│  │ 3  │ Email cumple   │ ❌ Error │ ayer 8am   │ ▶️ ✏️ 🗑││
│  │ 4  │ Reg. cliente   │ ⏸ Pausad│ —          │ ▶️ ✏️ 🗑││
│  └────┴────────────────┴──────────┴────────────┴──────────┘│
│                                                             │
│  Acciones: ⏸ Pausar  ▶️ Reanudar  ✏️ Editar  🗑 Eliminar  │
└─────────────────────────────────────────────────────────────┘
```

### Pantalla 5: Detalle de Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Determinista    [admin]    ← Volver               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📄 Backup diario                         [⏸ Pausar]       │
│  ─────────────────────────────────────                      │
│  🔄 Schedule: Todos los días a las 11pm                     │
│                                                             │
│  Pasos:                                                     │
│   1. Sistema → Backup de base de datos                      │
│      📁 Destino: /mnt/usb/backups/                          │
│                                                             │
│  📊 Historial de ejecuciones                                │
│  ┌────┬──────────┬──────────┬────────┬────────────────────┐ │
│  │ #  │ Fecha    │ Estado   │ Tiempo │ Detalle            │ │
│  ├────┼──────────┼──────────┼────────┼────────────────────┤ │
│  │ 42 │ 06/06    │ ✅ OK    │ 1.2s   │ Ver logs →         │ │
│  │ 41 │ 05/06    │ ✅ OK    │ 1.1s   │ Ver logs →         │ │
│  │ 40 │ 04/06    │ ❌ Error │ —      │ Ver logs →         │ │
│  └────┴──────────┴──────────┴────────┴────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Pantalla 6: Settings

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow Determinista    [admin]                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ⚙️ Configuración                                           │
│                                                             │
│  ─── Cambiar contraseña ───                                 │
│  [ Contraseña actual    ]                                   │
│  [ Nueva contraseña     ]                                   │
│  [ Confirmar            ]                                   │
│  [ Guardar ]                                                │
│                                                             │
│  ─── Correo SMTP ───                                        │
│  [ Servidor: smtp.gmail.com ]  [ Puerto: 587 ]              │
│  [ Usuario: tu@email.com    ]                               │
│  [ Contraseña: ********     ]                               │
│  [ Guardar ]  [ Probar conexión ]                           │
│                                                             │
│  ─── Licencia ───                                           │
│  Tipo: Individual — Pago único                              │
│  Estado: ✅ Activa hasta 06/2027                            │
│  [ Ingresar License Key ]                                   │
│                                                             │
│  ── Sistema ───                                            │
│  Base de datos: 45 MB (3 backups automáticos)               │
│  [ Hacer backup ahora ]  [ Restaurar desde backup ]        │
│  Puerto web: [8080]  Puerto webhooks: [8081]               │
│                                                             │
│  ── Logs ───                                               │
│  [ Descargar logs ]  [ Ver logs en vivo ]                   │
└─────────────────────────────────────────────────────────────┘
```

## 7.2 Rutas de la API

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/auth/login` | Iniciar sesión |
| `POST` | `/api/auth/logout` | Cerrar sesión |
| `GET` | `/api/dashboard/stats` | Estadísticas del dashboard |
| `POST` | `/api/workflows/chat` | Enviar texto → recibe workflow generado |
| `GET` | `/api/workflows` | Listar workflows |
| `POST` | `/api/workflows` | Crear workflow |
| `GET` | `/api/workflows/<id>` | Detalle de workflow |
| `PUT` | `/api/workflows/<id>` | Actualizar workflow |
| `DELETE` | `/api/workflows/<id>` | Eliminar workflow |
| `POST` | `/api/workflows/<id>/activate` | Activar workflow |
| `POST` | `/api/workflows/<id>/pause` | Pausar workflow |
| `GET` | `/api/workflows/<id>/history` | Historial de ejecuciones |
| `GET` | `/api/workflows/<id>/history/<exec_id>` | Detalle de ejecución |
| `POST` | `/api/workflows/<id>/retry` | Reintentar workflow fallido |
| `GET` | `/api/tools/crm/leads` | Listar leads |
| `POST` | `/api/tools/crm/leads` | Crear lead |
| `GET` | `/api/tools/inventory/products` | Listar productos |
| `GET` | `/api/tools/inventory/low-stock` | Productos con stock bajo |
| `GET` | `/api/tools/invoice/list` | Listar facturas |
| `GET` | `/api/settings` | Obtener configuración |
| `PUT` | `/api/settings` | Actualizar configuración |
| `POST` | `/api/settings/test-email` | Probar conexión SMTP |
| `POST` | `/api/license/validate` | Validar License Key |
| `POST` | `/api/system/backup` | Hacer backup ahora |
| `GET` | `/api/system/status` | Estado del sistema |

---

# 📦 PARTE 8: INSTALADOR

## 8.1 Especificación del instalador

El instalador es una aplicación GUI que se ejecuta con **doble clic**. No requiere terminal, ni comandos, ni conocimientos técnicos.

### ⚠️ Advertencia importante: Antivirus

**PyInstaller** y **Nuitka** producen ejecutables que algunos antivirus (Windows Defender, Avast, AVG) pueden marcar como **falsos positivos**. Esto es un problema conocido con empaquetadores de Python.

**Mitigaciones:**
1. Probar ambos empaquetadores (PyInstaller y Nuitka) y elegir el que menos falsos positivos genere
2. Firmar digitalmente el .exe con un certificado de código (recomendado: SignTool + certificado OV o EV)
3. Enviar el .exe a Microsoft (https://www.microsoft.com/en-us/wdsi/filesubmission) para que lo agreguen a la lista blanca
4. Incluir en la landing page una nota: "Si tu antivirus bloquea el instalador, agrega una excepción"

### Flujo de instalación

```
1. USUARIO descarga:
   WorkflowDeterminista_v1.0.exe (Windows, ~80MB)
   ─ o ─
   WorkflowDeterminista_v1.0 (Linux, ~80MB)

2. USUARIO hace doble clic en el archivo

3. APARECE VENTANA DE INSTALACIÓN:
   ┌─────────────────────────────────────────┐
   │  🚀 Workflow Determinista               │
   │  "Automatización offline para tu negocio"│
   │                                         │
   │  🌐 Idioma: [Español ▼]                 │
   │                                         │
   │  📁 Instalar en:                        │
   │  [C:\WorkflowDeterminista\    ] [📂]    │
   │                                         │
   │  🔑 License Key (opcional):             │
   │  [________________________________]     │
   │  (Déjalo vacío para probar 30 días)     │
   │                                         │
   │  🔐 Contraseña de administrador:        │
   │  [________________________]             │
   │  [________________________] (repetir)   │
   │                                         │
   │  [            Instalar           ]      │
   └─────────────────────────────────────────┘

4. BARRA DE PROGRESO:
   ┌─────────────────────────────────────────┐
   │  Instalando... 45%                      │
   │  ████████████████░░░░░░░░░░░░░░░░░░░   │
   │  ─ Copiando archivos...                 │
   │  ─ Configurando base de datos...         │
   │  ─ Generando contraseña...              │
   └─────────────────────────────────────────┘

5. COMPLETADO:
   ┌─────────────────────────────────────────┐
   │  ✅ Instalación completada              │
   │                                         │
   │  Sistema iniciado en:                   │
   │  http://localhost:8080                  │
   │                                         │
   │  [ Abrir en el navegador ]  [ Cerrar ] │
   └─────────────────────────────────────────┘
```

### Tecnología del instalador

**Opción A: PyInstaller** (primaria)
- Maduro, ampliamente documentado
- Produce .exe de ~80MB
- **Riesgo:** Falsos positivos de antivirus conocidos
- Comando: `pyinstaller --onefile --windowed --icon=icon.ico src/main.py`

**Opción B: Nuitka** (alternativa, menos falsos positivos)
- Compila Python a C real, luego a .exe
- Ejecutable más pequeño y rápido que PyInstaller
- Menos falsos positivos de antivirus
- Comando: `nuitka --standalone --onefile --enable-plugin=tk-inter src/main.py`

**El instalador hace:**
1. Copia los archivos al directorio elegido
2. Crea el archivo `workflow_determinista.db` en `~/.workflow_determinista/`
3. Guarda la contraseña hasheada con **bcrypt** en settings
4. Guarda el License Key (o establece modo trial por 30 días)
5. Configura auto-inicio al encender la computadora
6. Inicia el servidor web en `localhost:8080`
7. Abre el navegador automáticamente

### Post-instalación

El sistema se inicia automáticamente al encender la computadora:
- **Windows:** Entrada en el Registro (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`)
- **Linux:** Archivo `.desktop` en `~/.config/autostart/`

### Sistema de actualizaciones (Auto-Update)

```python
# En src/main.py, al iniciar:
def check_for_updates():
    # 1. Consultar https://api.workflowdeterminista.com/latest-version
    # 2. Comparar con versión actual (guardada en settings)
    # 3. Si hay nueva versión:
    #    - Notificar al usuario en el Dashboard
    #    - Ofrecer descargar el nuevo instalador
    #    - El instalador nuevo reemplaza al anterior (conserva la DB)
    pass
```

**El auto-update conserva la DB** — solo reemplaza el .exe. Los datos del cliente nunca se pierden.

---

# 🔑 PARTE 9: SISTEMA DE LICENCIAS

## 9.1 Formato de License Key

```
WFD-A7K2-9PL3-X5M8
```

- **Prefijo:** `WFD` (Workflow Determinista)
- **4 bloques** de 4 caracteres alfanuméricos (mayúsculas, sin vocales para evitar palabras accidentales)
- **Caracteres permitidos:** `BCDFGHJKLMNPQRSTVWXYZ23456789`
- **Tamaño:** 19 caracteres totales (WFD + 3 guiones + 16 caracteres)

## 9.2 Generación (HMAC-SHA256)

```python
class LicenseGenerator:
    SECRET_KEY = "REDACTED"  # ⚠️ Clave maestra

    def generate(license_type: str, client_name: str, 
                 days_valid: int = 365) -> str:
        # 1. Crear payload:
        payload = f"{license_type}|{client_name}|{expiry_date}"
        
        # 2. Firmar con HMAC-SHA256:
        signature = hmac.new(SECRET_KEY, payload, hashlib.sha256).hexdigest()[:8]
        
        # 3. Formatear key:
        raw = f"{license_type[0]}{signature[:4]}-{signature[4:8]}-{random_block}"
        
        # 4. Asegurar formato WFD-XXXX-XXXX-XXXX
        return f"WFD-{formatted}"
```

## 9.3 Validación

```python
class LicenseValidator:
    def validate(key: str) -> LicenseStatus:
        # 1. Verificar formato: WFD-XXXX-XXXX-XXXX
        # 2. Extraer tipo, fecha de expiración, firma
        # 3. Verificar firma HMAC-SHA256
        # 4. Verificar que no haya expirado
        # 5. Retornar: valid, expired, invalid, trial

    def get_trial_status() -> TrialStatus:
        # Si no hay key, verificar fecha de primer inicio en config.db
        # Si han pasado < 7 días → trial activo
        # Si han pasado >= 7 días → trial expirado

    def get_license_info() -> LicenseInfo:
        # Retorna: tipo, cliente, fecha expiración, días restantes
```

## 9.4 Tipos de licencia

| Tipo | Precio | Máximo de instalaciones | Soporte incluido |
|---|---|---|---|
| `individual` | $399 | 1 servidor | 30 días |
| `reseller` | $1,499 | 10 servidores (clientes distintos) | 90 días |
| `enterprise` | $2,499 | Ilimitado | 1 año |

## 9.5 Modo Trial

- Sin License Key → el sistema funciona **30 días completos**
- Se guarda la fecha de primer inicio en la tabla `license` de la DB unificada
- A los 30 días, el sistema muestra pantalla de bloqueo:
  ```
  ⏳ Período de prueba expirado
  Ingresa tu License Key para seguir usando el sistema
  [ Comprar ahora — USDT TRC20 ]
  [________________] [ Validar ]
  ```
- Los datos NO se pierden al expirar el trial. Al ingresar una key válida, todo vuelve a funcionar.
- ✅ **Cambio v2.0:** El trial se extendió de 7 a 30 días porque los clientes necesitan tiempo para configurar y evaluar un sistema de automatización de negocio.

---

# 🔒 PARTE 11: SEGURIDAD

## 11.1 Seguridad del producto

| Aspecto | Implementación v2.0 (corregida) |
|---|---|
| **Contraseña admin** | ✅ Hasheada con **bcrypt** (cost=12). **NO** SHA-256. Almacenada en settings de la DB unificada |
| **Sesiones web** | ✅ Cookie firmada con **httpOnly, secure, sameSite=Lax**. Expira a las 24h. Secreto desde variable de entorno o generado aleatoriamente en instalación |
| **Puerto local** | ✅ Solo escucha en `127.0.0.1` (localhost), no accesible desde la red |
| **Webhooks** | ✅ **API Key OBLIGATORIA**. Sin key válida → 401 Unauthorized. Key configurable en Settings |
| **ConditionEvaluator** | ✅ NUNCA usa `eval()`. Usa **parser recursivo descendente** (o lark-parser como alternativa). Solo permite operadores listados: `==`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `contains`, `AND`, `OR` |
| **Rate limiting** | ✅ Login: 10 intentos cada 15 minutos. API general: 100 requests/15min |
| **Logs** | ✅ No guardan contraseñas ni License Keys. Audit_log tiene su propia tabla (no mezclada con config) |
| **Datos** | ✅ Todo queda en la computadora del cliente. Zero datos en nuestros servidores |

## 11.2 Seguridad del negocio

| Aspecto | Implementación |
|---|---|
| **License Keys** | Firmadas con HMAC-SHA256. Clave maestra conocida solo por nosotros |
| **Código fuente** | Empaquetado con PyInstaller/Nuitka. No es código abierto. Ofuscación opcional con `pyarmor` |
| **Wallet USDT** | Solo nosotros tenemos la clave privada. Cliente no toca la wallet |

## 11.3 Checklist de seguridad pre-lanzamiento

- [ ] Contraseñas hasheadas con bcrypt (cost ≥ 12)
- [ ] Cookies con httpOnly, secure, sameSite
- [ ] Rate limiting activo en login y API
- [ ] NUNCA usar `eval()` en ConditionEvaluator
- [ ] Logs sin datos sensibles (contraseñas, keys)
- [ ] Webhooks con API Key obligatoria
- [ ] Secretos guardados en variables de entorno, NO en código
- [ ] Prueba de penetración básica en el instalador
- [ ] Firma digital del .exe para evitar falsos positivos de antivirus

---

# 💰 PARTE 12: MODELO DE NEGOCIO

## 12.0 Versión gratuita limitada (Free Tier)

Para reducir la fricción de compra, ofrecemos una **versión gratuita limitada** que el cliente puede usar indefinidamente:

| Característica | Free | Individual ($399) |
|---|---|---|
| Workflows | Hasta 3 | Ilimitados |
| Herramientas | Solo CRM | Todas (6 en MVP) |
| Historial | 7 días | Ilimitado |
| Soport | — | 30 días incluido |
| License Key | No necesita | Sí |

> 💡 **Estrategia:** El free tier es el gancho. El cliente usa CRM gratis, se acostumbra, y cuando necesita automatizar, compra.

## 12.1 Precios

| Producto | Precio | Para quién |
|---|---|---|
| Workflow Determinista Free | **$0 USD** | Hasta 3 workflows, solo CRM |
| Licencia individual | **$399 USD** | Una empresa, un servidor, todas las herramientas |
| Soporte anual (opcional) | **$99 USD/año** | Actualizaciones + soporte técnico |
| Licencia revendedor (hasta 10 clientes) | **$1,499 USD** | Consultores TI |
| Licencia empresa (ilimitada) | **$2,499 USD** | Empresas grandes, múltiples instalaciones |

> 🛡️ **Garantía de 30 días:** Si el producto no cumple con tus expectativas, te devolvemos el 100%. Sin preguntas.

## 12.2 Proyección realista Año 1

| Mes | Clientes nuevos | Ingreso | Soporte anual | Total mes |
|---|---|---|---|---|
| Mes 1 | 0 (solo free) | $0 | $0 | $0 |
| Mes 2 | 1 | $399 | $0 | $399 |
| Mes 3 | 1 | $399 | $99 | $498 |
| Mes 4 | 2 | $798 | $99 | $897 |
| Mes 5 | 1 | $399 | $198 | $597 |
| Mes 6 | 2 | $798 | $198 | $996 |
| Mes 7 | 1 | $399 | $297 | $696 |
| Mes 8 | 2 | $798 | $297 | $1,095 |
| Mes 9 | 2 | $798 | $396 | $1,194 |
| Mes 10 | 1 | $399 | $495 | $894 |
| Mes 11 | 2 | $798 | $495 | $1,293 |
| Mes 12 | 3 | $1,197 | $594 | $1,791 |
| **TOTAL** | **18** | **$7,182** | **$3,168** | **$10,350** |

> Mes 1 sin ventas = el producto no está listo hasta semana 6-7. Los primeros usuarios serán del free tier.

## 12.3 Costos mensuales

| Concepto | Costo |
|---|---|
| Dominio (`workflowdeterminista.com`) | ~$0.67/mes ($8/año) |
| **TOTAL** | **~$0.67/mes** |

**No necesitas servidores, ni nube, ni nada.** El cliente instala en su máquina. La landing page puede ser Carrd o Netlify (gratis).

## 12.4 Beneficio por cliente

```
Costo de desarrollo (tu tiempo):   ~$0 (ya invertiste)
Costo por descarga (GitHub):        $0
Costo de transacción (USDT):        ~$0 (red TRC20 es ~$0.50)
Comisión NOWPayments:               $0 (no lo usas aún)

Tu ganancia por venta:              $398.50 ($399 - $0.50 de red)
Tu ganancia por soporte anual:      $99
```

---

# 🛠️ PARTE 13: PLAN DE IMPLEMENTACIÓN — 3 FASES

> ⏱️ **Nota sobre el cronograma:** 14 semanas asumen trabajo **full-time** (8h/día). Si es tiempo parcial, multiplica por 2x-3x.
>
> ✅ **v2.0:** Se agregaron 2 semanas de testing + se corrigió trial a 30 días.

## 📅 FASE 1: Núcleo Funcional (Semanas 1-4)

**Objetivo:** Tener un motor de workflows funcional con datos persistentes.

### Semana 1: WorkflowEngine

- [ ] `src/workflow/engine.py` → WorkflowEngine (ciclo de vida)
- [ ] `src/workflow/step_executor.py` → StepExecutor (ejecuta pasos, resuelve variables)
- [ ] `src/workflow/condition_evaluator.py` → ConditionEvaluator (parser seguro, sin eval())
- [ ] `src/workflow/branch_handler.py` → BranchHandler (if/else/switch)
- [ ] `src/workflow/loop_handler.py` → LoopHandler (for/while/for each)
- [ ] `src/workflow/error_handler.py` → ErrorHandler (retry, fallback, dead-letter)
- [ ] `src/workflow/repository.py` → WorkflowRepository (SQLite CRUD)

### Semana 2: EventSystem (sin APScheduler)

- [ ] `src/events/bus.py` → EventBus (pub/sub persistente con tabla event_queue)
- [ ] `src/events/file_watcher.py` → FileWatcher
- [ ] `src/events/webhook_server.py` → WebhookServer (API Key OBLIGATORIA)
- [ ] `src/events/schedule_worker.py` → ScheduleWorker (threading.Timer, cada 60s)
- [ ] `src/events/db_trigger.py` → DatabaseTrigger

### Semana 3: Tools (6 herramientas) + DB unificada

- [ ] `src/data/database_manager.py` → DatabaseManager (UNA sola DB: workflow_determinista.db)
- [ ] `src/data/backup_engine.py` → BackupEngine
- [ ] `src/tools/crm/` → CRM (models, repository, service)
- [ ] `src/tools/invoice/` → Invoice (models, repository, service)
- [ ] `src/tools/inventory/` → Inventory (models, repository, service)
- [ ] `src/tools/notification/` → Notification (send_email, SMTP config)
- [ ] `src/tools/autopilot/` → AutoPilot (templates)
- [ ] `src/tools/logic_gate/` → LogicGate (reglas)

### Semana 4: Licencias + NLP + Tests

- [ ] `src/nlp/intent_classifier.py` → IntentClassifier
- [ ] `src/nlp/entity_extractor.py` → EntityExtractor
- [ ] `src/nlp/templates.py` → Plantillas (10+ templates)
- [ ] `src/nlp/bilingual_router.py` → BilingualRouter ES/EN
- [ ] `src/license/generator.py` → LicenseGenerator (HMAC-SHA256)
- [ ] `src/license/validator.py` → LicenseValidator + trial 30 días
- [ ] `src/tests/conftest.py` → Fixtures compartidas
- [ ] `src/tests/test_engine.py` → Tests del WorkflowEngine
- [ ] `src/tests/test_condition_eval.py` → Tests del ConditionEvaluator
- [ ] `src/tests/test_event_bus.py` → Tests del EventBus

## 📅 FASE 2: Instalable + Usable (Semanas 5-8)

**Objetivo:** El cliente puede instalar y usar el producto solo.

### Semana 5: Web UI - Parte 1

- [ ] `src/web/app.py` → Servidor Flask con todas las rutas
- [ ] `src/web/templates/login.html` → Login (bcrypt + rate limiting + cookie flags)
- [ ] `src/web/templates/dashboard.html` → Dashboard con stats
- [ ] `src/web/templates/chat.html` → Chat → genera workflow
- [ ] `src/web/static/style.css` → Estilos
- [ ] `src/web/static/app.js` → Interactividad

### Semana 6: Web UI - Parte 2 + Editor Visual

- [ ] `src/web/templates/editor.html` → Editor visual de workflows (NUEVO)
- [ ] `src/web/static/editor.js` → Lógica del editor
- [ ] `src/web/templates/workflow_list.html` → Lista de workflows
- [ ] `src/web/templates/workflow_detail.html` → Detalle + historial
- [ ] `src/web/templates/settings.html` → Configuración

### Semana 7: One-Click Installer

- [ ] `installer/installer_main.py` → GUI de instalación
- [ ] `installer/build_pyinstaller.sh` → Script PyInstaller
- [ ] `installer/build_nuitka.sh` → Script Nuitka (alternativa, menos falsos positivos)
- [ ] Probar instalación en Windows 10/11 limpio (SIN Python)
- [ ] Probar instalación en Linux limpio
- [ ] Probar con antivirus activado (Windows Defender, Avast)

### Semana 8: Tests de integración

- [ ] `src/tests/test_crm.py` → Tests del CRM
- [ ] `src/tests/test_invoice.py` → Tests de Invoice
- [ ] `src/tests/test_inventory.py` → Tests de Inventory
- [ ] `src/tests/test_notification.py` → Tests de Notifications
- [ ] `src/tests/test_nlp.py` → Tests del NLP
- [ ] `src/tests/test_license.py` → Tests del License System
- [ ] `src/tests/test_api.py` → Tests de integración de API
- [ ] Cobertura mínima: 70%

## 📅 FASE 3: Vendible (Semanas 9-14)

**Objetivo:** El producto se puede vender.

### Semana 9: Landing page + Dominio

- [ ] Crear landing page en Carrd.co o Netlify (una página)
- [ ] Comprar dominio: `workflowdeterminista.com`
- [ ] Subir versión gratuita (Free Tier) a GitHub Releases

### Semana 10: Pagos + Delivery manual

- [ ] Colocar dirección USDT TRC20 en la landing page
- [ ] Subir el instalador completo a GitHub Releases
- [ ] Probar el flujo: transferir $1 a ti mismo → generar License Key → enviar email

### Semana 11: Material de ventas

- [ ] PDF de 1 página para WhatsApp
- [ ] Video de 2 minutos (grabar con celular mostrando el sistema)
- [ ] Escribir casos de uso específicos para LATAM

### Semanas 12-14: Vender

- [ ] Contactar 10 consultores TI locales
- [ ] Publicar en grupos de WhatsApp/Facebook de dueños de negocio
- [ ] Ofrecer free tier a los primeros 50 usuarios
- [ ] Recoger testimonios
- [ ] Iterar: corregir bugs, mejorar UI, agregar herramientas

---

# ⚠️ PARTE 14: RIESGOS

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| **NLP no entiende al cliente** | Alta | Editor visual de workflows como respaldo. El cliente siempre confirma antes de crear |
| **Bug en WorkflowEngine** | Media | Tests automatizados (cobertura 70%+). ErrorHandler con retry cubre fallos transitorios |
| **Pérdida de datos** | Media | SQLite con WAL mode. Backup automático configurable a USB. Un solo archivo .db |
| **Cliente no sabe instalar** | Alta | PyInstaller/Nuitka: doble clic, sin dependencias, sin terminal. Video de instalación |
| **Antivirus bloquea el .exe** | Alta | Probar ambos empaquetadores. Firmar digitalmente. Enviar a lista blanca de Microsoft |
| **Bajas ventas** | Media | Free tier como gancho. Trial 30 días. Garantía de devolución. Si no se vende, sirve para uso propio |
| **Clonación del producto** | Baja | License System con HMAC-SHA256. Ofuscación con pyarmor |
| **Cliente pide funciones que no tenemos** | Media | Ser claros en qué es MVP. Roadmap público. Las herramientas extra son actualizaciones gratuitas |
| **$399 es caro sin marca** | Alta | Free tier + trial 30 días + garantía reducen el riesgo de compra. Testimonios de early adopters |

---

# 📢 PARTE 15: ESTRATEGIA DE VENTAS

## 15.1 Canales de venta (ordenados por efectividad)

| Canal | Esfuerzo | Conversión esperada |
|---|---|---|
| **Consultores TI locales** | Medio (1-2 contactos/día) | Alta (tienen clientes esperando soluciones) |
| **Grupos de WhatsApp de PYMEs** | Bajo (publicar 1 vez/semana) | Media |
| **Foros self-hosted / local-first** | Bajo | Media-alta (público técnico que valora privacidad) |
| **Landing page + SEO** | Alto (configurar) | Baja al inicio, crece con el tiempo |

## 15.2 Guiones de venta

### Para consultores TI:
> *"Tengo un sistema de automatización para empresas que no necesita internet y se paga una sola vez. Tú lo instalas en tus clientes. Precio especial para consultores: $1,499 para instalarlo en hasta 10 clientes. Cada cliente te paga $399. Tu ganancia: ~$2,491 por cada 10 clientes. Además tiene versión gratuita para que tus clientes lo prueben."*

### Para dueños de PYME:
> *"Deja de pagar $600 al año por herramientas que dependen de internet. Este sistema lo instalas en tu computadora, pagas UNA VEZ ($399), y hace todo: clientes, facturas, inventario, automatizaciones. Funciona aunque se caiga internet. Tus datos quedan en tu máquina, no en la nube. Y puedes empezar GRATIS con la versión limitada."*

## 15.3 Objeciones y respuestas

| Objeción | Respuesta |
|---|---|
| "Está muy caro" | "$399 es lo que pagas en 4 meses de Zapier. Y esto es tuyo para siempre. Además, puedes usar la versión gratis para empezar." |
| "¿Y si necesito ayuda?" | "30 días de soporte incluidos. Después, $99/año si quieres. O sigues sin soporte, funciona igual." |
| "¿Y si no funciona?" | "30 días de garantía de devolución. Si no te sirve, te devolvemos el 100%. Sin riesgo." |
| "No sé de tecnología" | "Tienes versión gratis. La instalas, la pruebas, y ves qué fácil es. Como mandar un WhatsApp." |
| "¿Cómo pago?" | "USDT TRC20 desde Binance o Trust Wallet. Tarda 10 segundos." |
| "¿Tiene pruebas?" | "Sí, funciona 30 días completos sin License Key. Y hay versión gratuita limitada para siempre." |

---

# ✅ ANEXO A: CHECKLIST DE LANZAMIENTO (v2.0)

## FASE 1 — Núcleo Funcional

- [ ] WorkflowEngine ejecuta un workflow de principio a fin
- [ ] EventSystem dispara workflows por: schedule, webhook, file change
- [ ] NLP convierte texto en workflow (al menos 10 templates)
- [ ] Editor visual de workflows funcional (no solo chat)
- [ ] Datos persisten en SQLite (UNA sola DB) al reiniciar el sistema
- [ ] License System: trial 30 días, validación de keys
- [ ] Tests unitarios: cobertura mínima 70%
- [ ] ConditionEvaluator usa parser seguro (sin eval())

## FASE 2 — Alpha (probadores)

- [ ] Web UI funcional: login (bcrypt), dashboard, chat, editor, workflow list, historial, settings
- [ ] Contraseñas hasheadas con bcrypt (no SHA-256)
- [ ] Cookies con httpOnly, secure, sameSite
- [ ] Rate limiting activo en login
- [ ] Instalador probado en Windows 10/11 limpio (sin Python)
- [ ] Instalador probado con antivirus activado (Windows Defender)
- [ ] Instalador probado en Linux limpio
- [ ] Prueba completa: instalar → crear WF → ejecutar → ver logs
- [ ] Free tier funcional (3 workflows, solo CRM)

## FASE 3 — Público (Vendible)

- [ ] Landing page en línea con dominio propio
- [ ] Wallet USDT TRC20 lista y probada
- [ ] Instalador subido a GitHub Releases
- [ ] PDF de 1 página para WhatsApp
- [ ] Video de 2 minutos grabado
- [ ] 5 contactos para contactar el primer día
- [ ] Garantía de 30 días publicada en la landing page

## Post-venta

- [ ] Preguntar: "¿Qué fue lo más difícil de la instalación?"
- [ ] Preguntar: "¿Qué herramienta te gustaría que agreguemos?"
- [ ] Pedir: "¿Me das un testimonio de 2 líneas?"
- [ ] Preguntar: "¿Conoces a alguien que también necesite esto?"

---

# 📊 ANEXO B: MAPA COMPLETO DE ARCHIVOS A CREAR (v2.0)

| # | Archivo | Propósito | Fase |
|---|---|---|---|
| 1 | `src/main.py` | Entry point: inicia servidor + workers | 2 |
| 2 | `src/config.py` | Configuración global (puertos, rutas) | 1 |
| 3 | `src/workflow/engine.py` | WorkflowEngine (ciclo de vida) | 1 |
| 4 | `src/workflow/step_executor.py` | Ejecuta pasos + resuelve variables | 1 |
| 5 | `src/workflow/condition_evaluator.py` | Evalúa condiciones (parser seguro, sin eval) | 1 |
| 6 | `src/workflow/branch_handler.py` | Maneja if/else/switch | 1 |
| 7 | `src/workflow/loop_handler.py` | Maneja bucles for/while | 1 |
| 8 | `src/workflow/error_handler.py` | Retry + fallback + dead-letter | 1 |
| 9 | `src/workflow/repository.py` | SQLite CRUD de workflows | 1 |
| 10 | `src/events/bus.py` | EventBus pub/sub persistente | 1 |
| 11 | `src/events/file_watcher.py` | Monitoreo de archivos | 1 |
| 12 | `src/events/webhook_server.py` | HTTP triggers (API Key OBLIGATORIA) | 1 |
| 13 | `src/events/schedule_worker.py` | Worker cron (threading.Timer) | 1 |
| 14 | `src/events/db_trigger.py` | Trigger de cambios en SQLite | 1 |
| 15 | `src/tools/crm/__init__.py` | CRM package | 1 |
| 16 | `src/tools/crm/models.py` | Modelos de CRM | 1 |
| 17 | `src/tools/crm/repository.py` | SQLite CRUD de CRM | 1 |
| 18 | `src/tools/crm/service.py` | Lógica de CRM | 1 |
| 19 | `src/tools/invoice/__init__.py` | Invoice package | 1 |
| 20 | `src/tools/invoice/models.py` | Modelos de factura | 1 |
| 21 | `src/tools/invoice/repository.py` | SQLite CRUD de factura | 1 |
| 22 | `src/tools/invoice/service.py` | Lógica de factura | 1 |
| 23 | `src/tools/inventory/__init__.py` | Inventory package | 1 |
| 24 | `src/tools/inventory/models.py` | Modelos de inventario | 1 |
| 25 | `src/tools/inventory/repository.py` | SQLite CRUD de inventario | 1 |
| 26 | `src/tools/inventory/service.py` | Lógica de inventario | 1 |
| 27 | `src/tools/notification/__init__.py` | Notification package | 1 |
| 28 | `src/tools/notification/service.py` | Envío de notificaciones | 1 |
| 29 | `src/tools/autopilot/__init__.py` | AutoPilot package | 1 |
| 30 | `src/tools/autopilot/service.py` | Plantillas de automatización | 1 |
| 31 | `src/tools/logic_gate/__init__.py` | LogicGate package | 1 |
| 32 | `src/tools/logic_gate/service.py` | Evaluación de reglas | 1 |
| 33 | `src/nlp/intent_classifier.py` | Clasificador por keywords | 1 |
| 34 | `src/nlp/entity_extractor.py` | Extractor por regex | 1 |
| 35 | `src/nlp/templates.py` | Plantillas de intención (10+) | 1 |
| 36 | `src/nlp/bilingual_router.py` | Detector ES/EN | 1 |
| 37 | `src/data/database_manager.py` | Singleton SQLite (DB unificada) | 1 |
| 38 | `src/data/backup_engine.py` | Backup automático a USB | 1 |
| 39 | `src/license/generator.py` | Genera License Keys (HMAC-SHA256) | 1 |
| 40 | `src/license/validator.py` | Valida licencias + trial 30 días | 1 |
| 41 | `src/web/app.py` | Servidor Flask con todas las rutas | 2 |
| 42 | `src/web/templates/login.html` | Login (bcrypt + rate limiting) | 2 |
| 43 | `src/web/templates/dashboard.html` | Dashboard con stats | 2 |
| 44 | `src/web/templates/chat.html` | Chat asistente | 2 |
| 45 | `src/web/templates/editor.html` | Editor visual de workflows (NUEVO) | 2 |
| 46 | `src/web/templates/workflow_list.html` | Lista de workflows | 2 |
| 47 | `src/web/templates/workflow_detail.html` | Detalle + historial | 2 |
| 48 | `src/web/templates/settings.html` | Configuración | 2 |
| 49 | `src/web/static/style.css` | Estilos | 2 |
| 50 | `src/web/static/app.js` | Interactividad | 2 |
| 51 | `src/web/static/editor.js` | Lógica del editor visual (NUEVO) | 2 |
| 52 | `src/tests/conftest.py` | Fixtures compartidas (NUEVO) | 1 |
| 53 | `src/tests/test_engine.py` | Tests del WorkflowEngine (NUEVO) | 1 |
| 54 | `src/tests/test_step_executor.py` | Tests del StepExecutor (NUEVO) | 1 |
| 55 | `src/tests/test_condition_eval.py` | Tests del ConditionEvaluator (NUEVO) | 1 |
| 56 | `src/tests/test_event_bus.py` | Tests del EventBus (NUEVO) | 1 |
| 57 | `src/tests/test_schedule.py` | Tests del ScheduleWorker (NUEVO) | 1 |
| 58 | `src/tests/test_crm.py` | Tests del CRM (NUEVO) | 1 |
| 59 | `src/tests/test_invoice.py` | Tests de Invoice (NUEVO) | 1 |
| 60 | `src/tests/test_inventory.py` | Tests de Inventory (NUEVO) | 1 |
| 61 | `src/tests/test_notification.py` | Tests de Notifications (NUEVO) | 1 |
| 62 | `src/tests/test_nlp.py` | Tests del NLP (NUEVO) | 1 |
| 63 | `src/tests/test_license.py` | Tests del License System (NUEVO) | 1 |
| 64 | `src/tests/test_api.py` | Tests de integración de API (NUEVO) | 2 |
| 65 | `installer/installer_main.py` | GUI de instalación | 2 |
| 66 | `installer/build_pyinstaller.sh` | Build script PyInstaller | 2 |
| 67 | `installer/build_nuitka.sh` | Build script Nuitka (NUEVO) | 2 |
| 68 | `scripts/generate_license_key.py` | Generar License Keys manualmente (NUEVO) | 1 |
| 69 | `requirements.txt` | Dependencias Python (bcrypt, pytest, etc.) | 1 |

---

**Documento creado:** Junio 2026 — **Versión 2.0 (Corregida y auditada)**

**Este documento incluye:**
- Glosario completo de términos (Parte 0)
- Visión de negocio y mercado objetivo — ✅ Reframed (offline + pago único, no "sin AI") (Parte 1)
- Arquitectura general con diagramas (Parte 2)
- Tech stack con justificaciones — ✅ bcrypt, threading.Timer, Nuitka, pytest (Parte 3)
- Modelo de datos — ✅ Unificado en UNA sola DB con índices (Parte 4)
- Especificación de todos los componentes — ✅ Editor visual, parser seguro (Parte 5)
- APIs detalladas de las 10 herramientas, 6 en MVP (Parte 6)
- Especificación de UI con wireframes — ✅ Editor visual, login seguro (Parte 7)
- Instalador — ✅ Nuitka, antivirus, auto-update (Parte 8)
- Sistema de licencias — ✅ Trial 30 días (Parte 9)
- Pagos y delivery — ✅ Garantía de 30 días agregada (Parte 10)
- Seguridad — ✅ bcrypt, cookie flags, rate limiting, parser seguro (Parte 11)
- Modelo de negocio — ✅ Free tier + garantía agregados (Parte 12)
- Plan de implementación en 3 fases, **14 semanas con testing** (Parte 13)
- Riesgos y mitigaciones — ✅ Actualizados (antivirus, precio, trial) (Parte 14)
- Estrategia de ventas con guiones — ✅ Reframed (Parte 15)
- Checklist de lanzamiento — ✅ Actualizado con tests, bcrypt, trial 30d (Anexo A)
- Mapa completo de **69 archivos** a crear (Anexo B)

**Siguiente paso:** Fase 1, Semana 1 — Construir `src/workflow/engine.py` con tests desde el día 1
