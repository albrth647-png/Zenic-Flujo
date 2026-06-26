# ⚙️ Zenic-Flujo v2.0.0 — HAT-ORBITAL

**Automatización offline para tu negocio. Sin internet, sin mensualidades.**

Zenic-Flujo es un sistema de automatización de procesos de negocio que instalas en tu propia computadora, pagas una sola vez, y funciona 100% offline. Incluye el motor ORBITAL, un sistema circular determinista con convergencia garantizada por el Teorema del Punto Fijo de Brouwer, y HAT, una arquitectura de orquestación de 5 niveles.

---

## 🏗️ Arquitectura HAT v2 — 5 Niveles

```
NIVEL 1 — HATRouter (Orquestador central Orbital)
           FSM + Anti-Dup (3 capas) + Ledger (3 tablas) + Routing RCC
    ↓
NIVEL 2 — 3 Sub-orquestadores independientes
           operaciones · comunicaciones · datos_auto
    ↓
NIVEL 3 — 9 Specialists (LA MAGIA — 1 responsabilidad cada uno)
           CRM · Invoice · Inventory · Notification · Email · Chat · Data · Api · Code
    ↓
NIVEL 4 — 101 Workers (auto-generados, circuit breaker per-worker)
    ↓
NIVEL 5 — 19 Tools ZF reales (base final)
           crm · invoice · inventory · notification · code_runner · data_keeper ·
           api_connector · logic_gate · autopilot · gmail · slack · telegram ·
           stripe · mercadopago · openai · ollama · sheets · drive · postgresql
```

### Características clave

| Componente | Descripción |
|---|---|
| **Motor ORBITAL** | 5 pilares deterministas (OVC → TOR → RCC → COD → Espectro) con convergencia garantizada |
| **HATRouter** | Orquestador central con routing por resonancia RCC, FSM de desambiguación, anti-doble-llamada |
| **3 Supervisores** | Sub-orquestadores independientes que no se conocen entre sí |
| **9 Specialists** | Cada uno con UNA sola responsabilidad, decide qué tool/worker llamar |
| **101 Workers** | Auto-generados por introspección de tools, con circuit breaker per-worker |
| **19 Tools** | Herramientas reales con side effects en SQLite, EventBus nativo |
| **Ledger** | 3 tablas SQLite (facts, hypotheses, progress) — memoria entre sesiones |
| **Anti-Dup** | 3 capas en cascada (exact_match → idempotency → ttl_freshness) |

Ver [docs/hat/QUICKSTART.md](docs/hat/QUICKSTART.md) para empezar.

---

## 🚀 Instalación Rápida

### Opción 1: Ejecutable (Windows/Linux)
1. Descarga el instalador desde [GitHub Releases](https://github.com/albrth647-png/Zenic-Flujo/releases)
2. Haz doble clic en `ZenicFlujo_v2.0.exe`
3. Sigue las instrucciones del instalador
4. Abre `http://localhost:8080` en tu navegador

### Opción 2: Desde código fuente (Python)

**Requisitos:** Python 3.10+

```bash
# Clonar
git clone https://github.com/albrth647-png/Zenic-Flujo.git
cd Zenic-Flujo

# Instalar dependencias
pip install -r requirements.txt

# Iniciar
python src/main.py
```

El servidor lanza:
- **Flask** en puerto 8080 (Web UI + API v1)
- **FastAPI** en puerto 8000 (API v2 + HAT `/api/hat/chat`)

---

## 🖥️ Uso

1. Abre `http://localhost:8080` en tu navegador
2. Inicia sesión con tu contraseña de administrador
3. Usa el **Chat** para interactuar con HAT en lenguaje natural
4. Monitorea tus automatizaciones en el **Dashboard**
5. Configura SMTP, webhooks y más en **Configuración**

### Chat con HAT

El chat usa el sistema HAT de 5 niveles. Ejemplos:

```
Usuario: "listar leads"
→ HATRouter rutea a "operaciones" → CrmSpecialist → list_leads → SQLite

Usuario: "enviar email a cliente@example.com"
→ HATRouter rutea a "comunicaciones" → NotificationSpecialist → send_email

Usuario: "ejecutar código python"
→ HATRouter rutea a "datos_auto" → CodeSpecialist → run_python
```

### API REST

```bash
# HAT API (FastAPI, port 8000)
curl -X POST http://localhost:8000/api/hat/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","session_id":"s1","message":"listar leads"}'

# Health check
curl http://localhost:8000/api/hat/health

# Prometheus metrics
curl http://localhost:8080/metrics
```

---

## 🧰 Herramientas incluidas (Nivel 5)

| Categoría | Herramientas |
|---|---|
| **Business** | CRM, Invoice, Inventory |
| **Payments** | Stripe, MercadoPago |
| **Communications** | Notification (email+WhatsApp), Gmail, Slack, Telegram |
| **Data** | DataKeeper, ApiConnector, Sheets, Drive, PostgreSQL |
| **Automation** | CodeRunner, LogicGate, Autopilot, OpenAI, Ollama |

---

## 📁 Estructura del proyecto

```
zenic-flujo/
├── src/
│   ├── core/                    ← Infraestructura base (config, db, security, observability)
│   ├── orbital/                 ← Motor determinista ORBITAL (5 pilares)
│   ├── hat/                     ← Arquitectura HAT 5 niveles
│   │   ├── level1_orchestrator/ ← NIVEL 1: HATRouter + FSM + Anti-Dup + Ledger
│   │   ├── level2_supervisors/  ← NIVEL 2: 3 supervisores independientes
│   │   ├── level3_specialists/  ← NIVEL 3: 9 specialists (1 responsabilidad cada uno)
│   │   ├── level4_workers/      ← NIVEL 4: 101 workers auto-generados
│   │   ├── level5_tools/        ← NIVEL 5: 19 tools ZF reales
│   │   ├── agents_legacy/       ← Framework de agentes heredado
│   │   └── bootstrap.py         ← Inicializa los 5 niveles al startup
│   ├── events/                  ← Sistema de eventos (EventBus, watchers, triggers)
│   ├── nlu/                     ← NLU determinista (pipeline, entidades, guardrails)
│   ├── workflow/                ← Motor de workflows multi-step
│   ├── connectors/              ← 40+ conectores externos (Salesforce, HubSpot, Jira, etc.)
│   ├── sdk/                     ← SDK para construir tools/conectores
│   ├── bpmn/                    ← BPMN 2.0 import/export
│   ├── tenant/                  ← Multi-tenant
│   ├── license/                 ← Licencias (pago único, Ed25519)
│   ├── compliance/              ← HIPAA, GDPR, SOC2
│   ├── marketplace/             ← Marketplace de tools/workflows
│   ├── web/                     ← Web UI (Flask + Jinja2)
│   ├── api_v2/                  ← API REST v2 (FastAPI + HAT)
│   ├── mobile/                  ← API mobile companion
│   ├── cli/                     ← CLI para desarrollo
│   ├── installer/               ← Instalador end-user
│   └── main.py                  ← Entry point (lanza Flask + FastAPI)
├── frontend/                    ← SPA React (TypeScript)
├── scripts/                     ← Scripts de ops
├── deploy/                      ← Helm + k8s + istio + grafana
├── docs/                        ← Documentación
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🔧 Desarrollo

### Inicializar HAT

```python
from src.events.bus import EventBus
from src.hat import bootstrap_hat

# Inicializa los 5 niveles
hat_router = bootstrap_hat(event_bus=EventBus())

# Procesar un mensaje
result = hat_router.handle(
    user_id="user1",
    session_id="session1",
    message="listar leads",
)
print(result["domain"])    # "operaciones"
print(result["status"])    # "completed"
print(result["response"])  # "[{'id': 1, 'name': 'Juan', ...}]"
```

### Añadir una tool nueva

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
3. Reiniciar — WorkerFactory genera workers automáticamente, SpecialistFactory crea specialist

### Tests

```bash
# Tests E2E de HAT
pytest src/tests/hat/e2e/ -v

# Tests de workers
pytest src/tests/hat/test_workers.py -v

# Tests de tools
pytest src/tests/test_crm.py src/tests/test_invoice.py src/tests/test_inventory.py -v

# Benchmarks
python scripts/benchmark_hat.py --n 20
```

---

## 🛡️ Seguridad

- Contraseñas hasheadas con bcrypt (cost=12)
- Cookies con httpOnly, secure, sameSite
- License Keys firmadas con Ed25519
- Parser seguro (sin eval())
- CSRF protection (flask-wtf)
- Registro de usuarios cerrado a admins
- Todo local, zero datos en la nube

---

## 📊 Métricas y Observabilidad

- **Prometheus**: `GET /metrics` (sin auth, para scrape)
- **OpenTelemetry**: DispatchTracer con spans por dispatch_id
- **Métricas HAT**: workflow, NLU, auth, agent execution
- **Alertas**: Reglas declarativas con notificadores email/Slack/webhook

---

## 🔑 Licencias

| Tipo | Precio | Descripción |
|---|---|---|
| **Free** | $0 | Hasta 3 workflows, solo CRM |
| **Individual** | $399 | Ilimitado, todas las herramientas |
| **Revendedor** | $1,499 | Hasta 10 clientes |
| **Empresa** | $2,499 | Ilimitado |

---

## 📦 Build desde código

```bash
# Con PyInstaller
bash installer/build_pyinstaller.sh

# Con Nuitka (alternativo)
bash installer/build_nuitka.sh
```

---

## 📄 Licencia

Propietaria — Pago Único.

---

## 🔗 Links

- **Repositorio**: [GitHub](https://github.com/albrth647-png/Zenic-Flujo)
- **Quickstart HAT**: [docs/hat/QUICKSTART.md](docs/hat/QUICKSTART.md)
- **Arquitectura**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Plan de migración**: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
