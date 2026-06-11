# 🚀 Roadmap Competitivo — Workflow Determinista

## Objetivo
Llevar el proyecto al nivel de n8n, Zapier y Make en 3 meses (12 sprints).

## Estado Actual vs Objetivo

| Dimensión | HOY | META 3 meses |
|-----------|-----|--------------|
| Integraciones | 4 | 50+ (vía HTTP node + adapters) |
| Workflow complexity | 3-5 pasos lineales | 100+ pasos con DAG |
| Escalabilidad | ~10 wf/s | ~1000 wf/s (Redis queue) |
| Enterprise | Básico | RBAC, SSO, multi-entorno |
| Diferenciación | ORBITAL (único) | ORBITAL + DAG + AI |

---

## 🏗️ Sprint 1: HTTP Request + Wait + Schedule Nodes
**Semana 1-2 — 10 tareas**

### Tareas:
1.1. Registrar APIConnectorService en WorkflowEngine (tool `api_connector`)
1.2. Crear HTTP Request step type con auth bearer/basic/api-key
1.3. Agregar validación de respuesta HTTP (status code matching)
1.4. Crear nodo Wait (delay fijo: segundos, minutos, horas)
1.5. Crear nodo WaitUntil (fecha/hora absoluta)
1.6. Mejorar Schedule Worker con CRON avanzado (5-field, timezone)
1.7. Agregar Schedule con intervalos (cada X minutos/horas/días)
1.8. Tests: HTTP request con mock server
1.9. Tests: Wait nodes con timeout
1.10. Tests: Schedule con CRON edge cases

**Skills:** `source-driven-development`, `test-driven-development`
**MCPs:** `expert-mcp` (code review)

---

## 🏗️ Sprint 2: Workflows en Paralelo (DAG Fork/Join)
**Semana 3-4 — 8 tareas**

### Tareas:
2.1. Crear modelo de DAG execution (fork + join)
2.2. Implementar ForkHandler: bifurcación en N ramas paralelas
2.3. Implementar JoinHandler: esperar a que todas las ramas terminen
2.4. Agregar step type `parallel` con timeout global
2.5. Actualizar WorkflowEngine para ejecutar pasos en paralelo
2.6. Agregar merge strategies: `all`, `any`, `race`
2.7. Tests: fork/join con 2, 5, 10 ramas paralelas
2.8. Tests: timeout en paralelo

**Skills:** `test-driven-development`, `performance-optimization`
**MCPs:** `expert-mcp`, `sequential-thinking`

---

## 🏗️ Sprint 3: Workflow Variables + Contexto Mejorado
**Semana 5 — 6 tareas**

### Tareas:
3.1. Crear sistema de variables de workflow (set, get, math, string ops)
3.2. Agregar $trigger, $steps, $env, $now, $random en contexto
3.3. Agregar transform functions: upper, lower, trim, replace, slice
3.4. Agregar agregadores: sum, avg, count, max, min sobre arrays
3.5. Actualizar editor visual con variables autocompletadas
3.6. Tests: todas las funciones de variables y transformaciones

**Skills:** `api-and-interface-design`, `test-driven-development`
**MCPs:** `expert-mcp`

---

## 🏗️ Sprint 4: Error Handling + Retry + Dead Letter
**Semana 6 — 6 tareas**

### Tareas:
4.1. Mejorar retry con backoff exponencial configurable por step
4.2. Agregar dead letter queue persistente en SQLite
4.3. Agregar notificación en dead letter (email/alert)
4.4. UI para ver/reintentar/descartar dead letter entries
4.5. Agregar `continue_on_error` flag en workflow
4.6. Tests: retry, dead letter, continue_on_error

**Skills:** `security-and-hardening`, `code-review-and-quality`
**MCPs:** `semgrep-mcp`

---

## 🏗️ Sprint 5: Integraciones Top 10 — HTTP Request Genérico
**Semana 7 — 8 tareas**

### Tareas:
5.1. Mejorar APIConnectorService con rate limiting por dominio
5.2. Agregar paginación automática (cursor, page, offset)
5.3. Agregar caching de respuestas (TTL configurable)
5.4. Agregar webhook receiver para callbacks asíncronos
5.5. Agregar transform JSON → dict automática
5.6. Agregar XML support (parse + generate)
5.7. Tests: rate limiting, pagination, caching
5.8. Tests: XML parse/generate roundtrip

**Skills:** `api-and-interface-design`, `security-and-hardening`
**MCPs:** `expert-mcp`, `semgrep-mcp`

---

## 🏗️ Sprint 6: Integraciones Específicas
**Semana 8-9 — 12 tareas**

### Tareas:
6.1. OpenAI connector (chat completion, embeddings)
6.2. Ollama connector (LLM local)
6.3. PostgreSQL connector (query, insert, update)
6.4. Google Drive connector (upload, list, download)
6.5. Dropbox connector (upload, list, download)
6.6. Stripe connector (create payment, list customers)
6.7. MercadoPago connector (create preference, webhook)
6.8. Mailchimp connector (add subscriber, send campaign)
6.9. Airtable connector (list, create, update records)
6.10. Tests: cada conector con mock server
6.11. Tests: error handling por conector
6.12. Tests: autenticación por conector

**Skills:** `source-driven-development`, `security-and-hardening`
**MCPs:** `gravity_index` (discovery), `expert-mcp`

---

## 🏗️ Sprint 7-8: Redis Queue + Workers
**Semana 10-11 — 10 tareas**

### Tareas:
7.1. Integrar Redis (redis-py) para cola de ejecución
7.2. Crear WorkQueue: publish + subscribe para workers
7.3. Crear WorkerManager: N workers, health check, restart
7.4. Migrar ejecución de workflows a cola asíncrona
7.5. Agregar execution status polling para el frontend
7.6. Manejar worker failure: re-encolar después de timeout
7.7. Agregar métricas: queue depth, processing time, error rate
7.8. Tests: worker procesa N jobs concurrentes
7.9. Tests: failover de worker caído
7.10. Tests: throughput benchmark

**Skills:** `performance-optimization`, `shipping-and-launch`
**MCPs:** `sequential-thinking`, `analyzer`

---

## 🏗️ Sprint 9: Multi-entorno + Versioning
**Semana 12 — 6 tareas**

### Tareas:
9.1. Agregar tabla workflow_versions en SQLite
9.2. UI para crear/activar/rollback versiones
9.3. Diferencia visual entre versiones (diff)
9.4. Export workflow con version history
9.5. Import con validación de versión
9.6. Tests: version CRUD + rollback

**Skills:** `git-workflow-and-versioning`, `api-and-interface-design`
**MCPs:** `expert-mcp`

---

## 🏗️ Sprint 10: SSO + OAuth + Enterprise Auth
**Semana 13 — 5 tareas**

### Tareas:
10.1. Google OAuth login (usando google-auth)
10.2. Azure AD / Microsoft OAuth login
10.3. API tokens con scopes (read, write, admin)
10.4. Audit log mejorado con IP, user agent, timestamp
10.5. Tests: OAuth flow, token validation, audit

**Skills:** `security-and-hardening`, `api-and-interface-design`
**MCPs:** `semgrep-mcp`, `expert-mcp`

---

## 🏗️ Sprint 11: Monitoreo + Alertas + Dashboard Admin
**Semana 14 — 6 tareas**

### Tareas:
11.1. Dashboard de health: uptime, memory, queue, errors
11.2. Alertas: email/Slack cuando workflow falla N veces
11.3. Historial de alertas con resolución
11.4. Export metrics para Prometheus / Grafana
11.5. Health check endpoint para load balancer
11.6. Tests: alert generation, metrics export

**Skills:** `shipping-and-launch`, `documentation-and-adrs`
**MCPs:** `expert-mcp`, `analyzer`

---

## 🏗️ Sprint 12: Polish + Documentación + Lanzamiento
**Semana 15 — 8 tareas**

### Tareas:
12.1. Visualizador de espectro orbital en tiempo real
12.2. Documentación de todas las APIs y componentes
12.3. Guía de migración para usuarios de n8n/Zapier
12.4. Video de demostración (screencast)
12.5. Landing page con testimonios
12.6. Optimización final de benchmarks
12.7. semgrep scan final (0 críticos)
12.8. Release v2.0.0

**Skills:** `shipping-and-launch`, `documentation-and-adrs`
**MCPs:** `browser-use`, `semgrep-mcp`

---

## 📊 Costo Estimado Total

| Sprint | Semanas | Tareas | Esfuerzo |
|--------|---------|--------|----------|
| 1 | 1-2 | 10 | ~40h |
| 2 | 3-4 | 8 | ~32h |
| 3 | 5 | 6 | ~24h |
| 4 | 6 | 6 | ~24h |
| 5 | 7 | 8 | ~32h |
| 6 | 8-9 | 12 | ~48h |
| 7-8 | 10-11 | 10 | ~40h |
| 9 | 12 | 6 | ~24h |
| 10 | 13 | 5 | ~20h |
| 11 | 14 | 6 | ~24h |
| 12 | 15 | 8 | ~32h |
| **Total** | **15** | **85** | **~340h** |

---

## 📋 Checklist de Progreso

### Sprint 1 ✅
- [ ] 1.1 APIConnectorService registrado
- [ ] 1.2 HTTP Request step type
- [ ] 1.3 Validación de respuesta HTTP
- [ ] 1.4 Wait node (delay fijo)
- [ ] 1.5 WaitUntil node (fecha absoluta)
- [ ] 1.6 Schedule CRON avanzado
- [ ] 1.7 Schedule intervalos
- [ ] 1.8-1.10 Tests

### Sprint 2
- [ ] 2.1 DAG model
- [ ] 2.2 ForkHandler
- [ ] 2.3 JoinHandler
- [ ] 2.4 Parallel step type
- [ ] 2.5 WorkflowEngine parallel
- [ ] 2.6 Merge strategies
- [ ] 2.7-2.8 Tests

### Sprint 3
- [ ] ...

*(Continuar actualizando)*

---

## ⚠️ Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Redis no disponible en entornos sin Docker | Media | Alto | Fallback a SQLite queue |
| OAuth requiere internet | Baja | Alto | Mantener login local como fallback |
| Integraciones cambian APIs | Alta | Medio | Tests de integración automatizados |
| Orquestación paralela introduce bugs | Media | Alto | Tests de estrés + checkoutpoints |
