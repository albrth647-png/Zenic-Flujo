# 🎯 PLAN MAESTRO — Zenic-Flujo / Workflow Determinista
## Basado en: MiroFish_Analisis + Plan Estrategico ORBITAL

**Fecha:** Junio 2026  
**Duración estimada:** 19 semanas (~4.5 meses)  
**Objetivo:** Llevar el proyecto de estado actual a producto listo para venta  
**Referencia dual:** MiroFish_Analisis_Zenic-Flijo.pdf + MiroFish_Plan_Estrategico_ORBITAL.pdf

---

## 📊 Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| Fases totales | 8 (Fase 0 → Fase 7) |
| Semanas estimadas | 19 |
| Bugs críticos identificados | 7 |
| MCPs a utilizar | 11 |
| Skills a utilizar | 15+ |
| Tests existentes | ~238+ |
| Tests objetivo final | 500+ |

---

## 🗺️ Mapa General de Fases

```
FASE 0 (Sem 1-2)   ████████░░░░░░░░░░░░  Estabilización Crítica
FASE 1 (Sem 3)     ░░░░████░░░░░░░░░░░░  Limpieza de Código Muerto
FASE 2 (Sem 4)     ░░░░░░░░██░░░░░░░░░░  Testing y Cobertura
FASE 3 (Sem 5)     ░░░░░░░░░░██░░░░░░░░  Seguridad Hardening
FASE 4 (Sem 6-9)   ░░░░░░░░░░░░████████  UI/UX Moderna
FASE 5 (Sem 10-12) ░░░░░░░░░░░░░░░░████  API Pública y Marketplace
FASE 6 (Sem 13-15) ░░░░░░░░░░░░░░░░░░██  Orbital v3.2
FASE 7 (Sem 16-19) ░░░░░░░░░░░░░░░░░░██  Lanzamiento
```

---

## 📋 FASE 0: Estabilización Crítica (Semanas 1-2)

**Objetivo:** Eliminar los 7 bugs críticos identificados por MiroFish que impiden que el motor ORBITAL funcione correctamente.

**Prioridad:** 🔴 ABSOLUTA — Sin esto, nada más funciona

**Skills:** `debugging-and-error-recovery`, `test-driven-development`, `security-and-hardening`, `doubt-driven-development`

**MCPs:** `semgrep-mcp` (security audit), `expert-mcp` (code review), `analyzer` (linting), `sequential-thinking` (debugging)

### Tareas

| # | Bug | Severidad | Descripción | Archivos | Tests |
|---|-----|-----------|-------------|----------|-------|
| 0.1 | **Bug #1: OrbitalContext singleton** | 🔴 Crítica | Verificar que `id(ctx.ovc) == id(ctx.engine._ovc)` funciona correctamente. El código actual parece tener la corrección (pasa instancias al Engine), pero necesita validación. | `src/orbital/context.py` | ✅ `test_orbital_context_sharing.py` (20 tests — COMPLETADO) |
| 0.2 | **Bug #2: COD no converge con amplitudes grandes** | 🟠 Alta | El COD falla a converger cuando las amplitudes son grandes (>100) porque TOR satura `tanh`. Verificar que `_normalize_tension` y `_convergence_scale` resuelven esto. | `src/orbital/cod.py` | Tests con amplitudes 1, 10, 100, 1000 |
| 0.3 | **Bug #3: OrbitalAdapter/Compiler crean OVCs independientes** | 🟠 Alta | Verificar que `OrbitalAdapter` y `OrbitalCompiler` usan `OrbitalContext()` en lugar de crear instancias aisladas. | `src/orbital/orbital_adapter.py`, `src/orbital/orbital_compiler.py` | Test de sharing entre adapter/compiler y engine |
| 0.4 | **Bug #4: Secrets hardcodeados** | 🔴 Crítica | `config.py` tiene `SECRET_KEY = "REDACTED"`. Generar keys aleatorias con `secrets.token_urlsafe`. | `src/config.py` | Test de que SECRET_KEY no está hardcodeada |
| 0.5 | **Bug #5: Typo "sbridgeectrum"** | 🟡 Media | Buscar y corregir typos en EventBus o archivos orbitales. | Global | Verificación con grep |
| 0.6 | **Bug #6: OrbitalContext.engine y ovc no sincronizados** | 🟠 Alta | Verificar que los snapshots de `ctx.ovc` y `ctx.engine.ovc` muestran el mismo estado después de ticks. | `src/orbital/context.py` | Tests de sincronización post-tick |
| 0.7 | **Bug #7: BusinessTools usa eval()** | 🔴 Crítica | Escaneo completo del proyecto para eliminar cualquier uso de `eval()` fuera de tests. | Todo el proyecto | `semgrep-mcp` scan completo |

### Criterios de Aceptación Fase 0

- [ ] 7 bugs críticos corregidos con tests que los validan
- [ ] `semgrep-mcp` scan limpio (sin eval() en producción, sin secrets hardcodeados)
- [ ] Todos los tests de orbital pasan (existentes + nuevos)
- [ ] El OrbitalContext comparte OVC correctamente (ya verificado ✅)

---

## 📋 FASE 1: Limpieza de Código Muerto (Semana 3)

**Objetivo:** Eliminar código obsoleto que genera confusión y aumenta la superficie de mantenimiento.

**Skills:** `code-simplification`, `deprecation-and-migration`, `code-review-and-quality`

**MCPs:** `analyzer` (vulture dead code detection), `filesystem` (búsqueda), `expert-mcp` (refactoring review)

### Tareas

| # | Tarea | Descripción | Archivos |
|---|-------|-------------|----------|
| 1.1 | Eliminar `workflow/tools.py` obsoleto | Verificar si existe y tiene código no utilizado | `src/workflow/tools.py` |
| 1.2 | Consolidar `nlu/pipeline.py` vs `src/nlp/` | El módulo `src/nlp/` es legado. Verificar si `src/nlu/pipeline.py` lo reemplaza completamente y eliminar `nlp/` | `src/nlp/`, `src/nlu/pipeline.py` |
| 1.3 | Ejecutar vulture (dead code detection) | Identificar funciones, variables y módulos no utilizados | Todo el proyecto |
| 1.4 | Eliminar imports no utilizados | Limpiar imports muertos en todos los archivos | Todo el proyecto |
| 1.5 | Revisar archivos `config/` antiguos | Verificar si hay directorios de configuración obsoletos | `src/config/` |

### Criterios de Aceptación Fase 1

- [ ] vulture reporta 0 dead code significativo
- [ ] `src/nlp/` eliminado o marcado como deprecated
- [ ] No hay imports no utilizados
- [ ] Todos los tests siguen pasando

---

## 📋 FASE 2: Testing y Cobertura (Semana 4)

**Objetivo:** Aumentar cobertura de tests al 80%+ en el módulo ORBITAL y verificar integración con el sistema existente.

**Skills:** `test-driven-development`, `doubt-driven-development`, `code-review-and-quality`

**MCPs:** `analyzer` (cobertura), `expert-mcp` (edge cases), `sequential-thinking` (casos adversariales)

### Tareas

| # | Tarea | Descripción | Archivos |
|---|-------|-------------|----------|
| 2.1 | Ejecutar tests existentes | `test_orbital.py`, `test_orbital_fase3.py`, `test_orbital_context_sharing.py` | `src/tests/` |
| 2.2 | Tests de integración ORBITAL ↔ WorkflowEngine | Verificar que el motor orbital funciona correctamente con el workflow engine lineal existente | `src/tests/test_engine.py` |
| 2.3 | Tests de COD con amplitudes extremas | 1, 10, 100, 1000, 10000 — verificar convergencia siempre | `src/tests/test_orbital*.py` |
| 2.4 | Tests de OrbitalAdapter con tools mockeadas | Verificar que el adaptador orbital envuelve correctamente las herramientas de negocio | `src/tests/` |
| 2.5 | Tests de OrbitalCompiler con 50+ frases | Verificar compilación correcta de intención → workflow | `src/tests/` |
| 2.6 | Tests de EventBus orbital | Verificar que el bus de eventos funciona correctamente con OrbitalContext | `src/tests/test_event_bus.py` |
| 2.7 | Cobertura de código | Ejecutar `pytest --cov` y generar reporte | Todo el proyecto |

### Criterios de Aceptación Fase 2

- [ ] Todos los tests pasan (existentes + nuevos)
- [ ] Cobertura ORBITAL > 80%
- [ ] Cobertura total del proyecto > 70%
- [ ] Tests de integración ORBITAL ↔ WorkflowEngine pasan

---

## 📋 FASE 3: Seguridad Hardening (Semana 5)

**Objetivo:** Eliminar vulnerabilidades de seguridad y establecer baseline de seguridad con semgrep.

**Skills:** `security-and-hardening`, `doubt-driven-development`, `code-review-and-quality`

**MCPs:** `semgrep-mcp` (AST analysis, security rules), `analyzer` (linting), `expert-mcp` (security review)

### Tareas

| # | Tarea | Descripción | Archivos |
|---|-------|-------------|----------|
| 3.1 | Auditoría semgrep completa | Ejecutar semgrep con reglas de seguridad (Python) | Todo el proyecto |
| 3.2 | Eliminar eval() restante | Verificar que NO hay eval() en código de producción | Todo el proyecto |
| 3.3 | Secrets management | Verificar que todos los secrets usan variables de entorno o `secrets.token_urlsafe` | `src/config.py`, `src/license/` |
| 3.4 | Rate limiting | Verificar rate limiting en todos los endpoints públicos | `src/web/app.py` |
| 3.5 | SQL injection prevention | Verificar que todas las queries SQL usan parámetros (no string formatting) | `src/data/database_manager.py` |
| 3.6 | XSS protection | Verificar escaping en templates HTML | `src/web/templates/` |
| 3.7 | CSRF tokens | Verificar protección CSRF en formularios | `src/web/app.py` |
| 3.8 | Cookie security | Verificar httpOnly, secure, sameSite en cookies | `src/web/app.py` |
| 3.9 | Sandbox code_runner | Verificar que el sandbox de Python bloquea imports peligrosos | `src/tools/code_runner/sandbox.py` |

### Criterios de Aceptación Fase 3

- [ ] semgrep scan limpio (0 findings críticos)
- [ ] No hay eval() en código de producción
- [ ] No hay secrets hardcodeados
- [ ] Rate limiting funciona en endpoints críticos
- [ ] Cookie flags configurados correctamente

---

## 📋 FASE 4: UI/UX Moderna (Semanas 6-10)

**Objetivo:** Crear una interfaz moderna y profesional que compita con n8n y Zapier visualmente.

**Skills:** `frontend-ui-engineering`, `api-and-interface-design`, `browser-testing-with-devtools`

**MCPs:** `browser-use` (testing visual), `expert-mcp` (UI review), `filesystem` (assets)

### Fase 4a: Core UI (Semanas 6-7)

| # | Tarea | Semana | Descripción | Archivos |
|---|-------|--------|-------------|----------|
| 4.1 | Dashboard WebSocket en tiempo real | 6 | Dashboard con actualizaciones en tiempo real vía WebSocket | `src/web/app.py`, `src/web/templates/dashboard.html` |
| 4.2 | UI de chat mejorada | 6 | Chat con soporte para markdown, código, y sugerencias | `src/web/templates/chat.html`, `src/web/static/app.js` |
| 4.3 | Tema oscuro/claro | 7 | Toggle de tema con persistencia en localStorage | `src/web/static/style.css` |
| 4.4 | Responsive design base | 7 | Adaptar las vistas principales para móvil | `src/web/templates/` |

### Fase 4b: Features Avanzadas (Semanas 8-10)

| # | Tarea | Semana | Descripción | Archivos |
|---|-------|--------|-------------|----------|
| 4.5 | Editor visual de workflows (drag & drop) | 8-9 | Editor visual tipo n8n con nodos arrastrables | `src/web/static/editor.js`, `src/web/templates/editor.html` |
| 4.6 | Micro-interacciones | 9 | Hover states, transiciones, loading states | `src/web/static/style.css` |
| 4.7 | Panel de integraciones | 9-10 | UI para configurar Gmail, Sheets, Telegram, Slack | `src/web/templates/settings.html` |
| 4.8 | Visualizador de espectro orbital | 10 | Visualización animada del ciclo ORBITAL en tiempo real | `src/web/static/orbital.js` (nuevo) |

### Criterios de Aceptación Fase 4

- [ ] Dashboard WebSocket funciona con actualizaciones en tiempo real
- [ ] Editor visual permite crear workflows con drag & drop
- [ ] UI funciona correctamente en móvil (responsive)
- [ ] Tema oscuro/claro funciona
- [ ] No hay errores en consola del navegador (browser-use test)

---

## 📋 FASE 5: API Pública y Marketplace (Semanas 10-12)

**Objetivo:** Crear una API REST documentada y un sistema de plugins/marketplace.

**Skills:** `api-and-interface-design`, `source-driven-development`, `security-and-hardening`

**MCPs:** `context7` (OpenAPI docs), `expert-mcp` (API design review), `semgrep-mcp` (API security)

### Tareas

| # | Tarea | Semana | Descripción | Archivos |
|---|-------|--------|-------------|----------|
| 5.1 | API REST documentada (OpenAPI 3.0) | 10 | Documentación automática de endpoints | `src/web/app.py` |
| 5.2 | Autenticación API (API keys) | 10 | Sistema de API keys para acceso externo | `src/web/app.py`, `src/data/database_manager.py` |
| 5.3 | Rate limiting por API key | 10 | Límites diferenciados por tier de licencia | `src/web/app.py` |
| 5.4 | Webhooks de salida | 11 | Enviar eventos a URLs externas cuando ocurren eventos | `src/events/webhook_server.py` |
| 5.5 | Sistema de plugins | 11-12 | Arquitectura de plugins para extensiones de terceros | `src/plugins/` (nuevo) |
| 5.6 | Marketplace de templates | 12 | Repositorio de workflows pre-construidos | `src/web/templates/marketplace.html` (nuevo) |
| 5.7 | SDK Python | 12 | Cliente Python para la API pública | `sdk/` (nuevo) |

### Criterios de Aceptación Fase 5

- [ ] API documentada con OpenAPI 3.0
- [ ] Autenticación por API key funciona
- [ ] Rate limiting por tier funciona
- [ ] Webhooks de salida envían eventos correctamente
- [ ] Al menos 3 plugins de ejemplo funcionan

---

## 📋 FASE 6: Orbital v3.2 (Semanas 13-15)

**Objetivo:** Optimizar el motor ORBITAL, crear benchmarks y preparar documentación técnica.

**Skills:** `performance-optimization`, `documentation-and-adrs`, `source-driven-development`

**MCPs:** `sequential-thinking` (optimization strategy), `analyzer` (performance profiling), `context7` (benchmarks)

### Tareas

| # | Tarea | Semana | Descripción | Archivos |
|---|-------|--------|-------------|----------|
| 6.1 | Benchmarks del motor ORBITAL | 13 | Medir tiempo de ejecución, memoria, throughput | `src/orbital/benchmarks.py` (nuevo) |
| 6.2 | Optimización de COD | 13 | Reducir iteraciones del colapso con pre-computación | `src/orbital/cod.py` |
| 6.3 | Cache de tensiones TOR | 14 | Evitar recalcular TOR para parejas sin cambio de fase | `src/orbital/tor.py` |
| 6.4 | Documentación técnica ORBITAL | 14 | Documentación completa de la arquitectura circular | `docs/orbital-technical.md` (nuevo) |
| 6.5 | Whitepaper ORBITAL | 15 | Documento técnico para validación independiente | `docs/orbital-whitepaper.md` (nuevo) |
| 6.6 | Validación independiente | 15 | Preparar caso para validación por expertos externos | `docs/validation-guide.md` (nuevo) |
| 6.7 | Comparativa con sistemas lineales | 15 | Benchmark vs n8n, Zapier (workflow lineal) | `docs/benchmark-report.md` (nuevo) |

### Criterios de Aceptación Fase 6

- [ ] Benchmarks documentados con métricas claras
- [ ] COD converge en <100 iteraciones para amplitudes hasta 10000
- [ ] Documentación técnica completa
- [ ] Whitepaper listo para revisión independiente

---

## 📋 FASE 7: Lanzamiento (Semanas 16-19)

**Objetivo:** Preparar todo para el lanzamiento comercial: CI/CD, documentación, instalador, soporte.

**Skills:** `shipping-and-launch`, `ci-cd-and-automation`, `documentation-and-adrs`

**MCPs:** `github` (releases), `semgrep-mcp` (final security scan), `expert-mcp` (launch review)

### Tareas

| # | Tarea | Semana | Descripción | Archivos |
|---|-------|--------|-------------|----------|
| 7.1 | CI/CD pipeline completo | 16 | GitHub Actions: lint, test, build, release | `.github/workflows/` |
| 7.2 | Instalador Windows | 16 | Instalador PyInstaller/Nuitka para Windows | `installer/` |
| 7.3 | Instalador Linux | 17 | Script de instalación para Linux/Mac | `installer/` |
| 7.4 | Documentación de usuario | 17 | README, guías de inicio rápido, FAQ | `docs/`, `README.md` |
| 7.5 | Videos de demostración | 18 | Screencasts de las features principales | `docs/videos/` |
| 7.6 | Landing page actualizada | 18 | Página de ventas con features, pricing, testimonials | `docs/landing-page.html` |
| 7.7 | Auditoría de seguridad final | 19 | semgrep + expert-mcp review completo | Todo el proyecto |
| 7.8 | Release v1.0.0 | 19 | Tag, changelog, release notes | Git |

### Criterios de Aceptación Fase 7

- [ ] CI/CD funciona end-to-end
- [ ] Instalador funciona en Windows y Linux
- [ ] Documentación completa y actualizada
- [ ] Landing page actualizada con pricing
- [ ] Auditoría de seguridad final limpia
- [ ] Release v1.0.0 publicada

---

## 🔧 MCPs Disponibles — Mapa de Uso por Fase

| MCP | Fase 0 | Fase 1 | Fase 2 | Fase 3 | Fase 4 | Fase 5 | Fase 6 | Fase 7 |
|-----|--------|--------|--------|--------|--------|--------|--------|--------|
| `semgrep-mcp` | ✅ | — | — | ✅ | — | ✅ | — | ✅ |
| `expert-mcp` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| `analyzer` | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | — |
| `sequential-thinking` | ✅ | — | ✅ | — | — | — | ✅ | — |
| `filesystem` | — | ✅ | — | — | ✅ | — | — | — |
| `browser-use` | — | — | — | — | ✅ | — | — | — |
| `context7` | — | — | — | — | — | ✅ | ✅ | — |
| `memory` | — | — | — | — | — | ✅ | — | — |
| `sqlite` | — | — | ✅ | — | — | ✅ | — | — |
| `github` | — | — | — | — | — | — | — | ✅ |
| `syke` | — | — | ✅ | — | — | — | ✅ | — |

---

## 🛠️ Skills Disponibles — Mapa de Uso por Fase

| Skill | Fase 0 | Fase 1 | Fase 2 | Fase 3 | Fase 4 | Fase 5 | Fase 6 | Fase 7 |
|-------|--------|--------|--------|--------|--------|--------|--------|--------|
| `debugging-and-error-recovery` | ✅ | — | — | — | — | — | — | — |
| `test-driven-development` | ✅ | — | ✅ | — | — | — | — | — |
| `security-and-hardening` | ✅ | — | — | ✅ | — | ✅ | — | — |
| `doubt-driven-development` | ✅ | — | ✅ | ✅ | — | — | — | — |
| `code-simplification` | — | ✅ | — | — | — | — | — | — |
| `deprecation-and-migration` | — | ✅ | — | — | — | — | — | — |
| `code-review-and-quality` | — | ✅ | ✅ | ✅ | — | — | — | — |
| `frontend-ui-engineering` | — | — | — | — | ✅ | — | — | — |
| `browser-testing-with-devtools` | — | — | — | — | ✅ | — | — | — |
| `api-and-interface-design` | — | — | — | — | — | ✅ | — | — |
| `source-driven-development` | — | — | — | — | — | ✅ | ✅ | — |
| `performance-optimization` | — | — | — | — | — | — | ✅ | — |
| `documentation-and-adrs` | — | — | — | — | — | — | ✅ | ✅ |
| `shipping-and-launch` | — | — | — | — | — | — | — | ✅ |
| `ci-cd-and-automation` | — | — | — | — | — | — | — | ✅ |

---

## 📈 Progresión de Tests

```
Estado actual:    ~238 tests ✅
Fase 0:           +15 tests (bugs críticos)       → ~253
Fase 1:           +5 tests (limpieza)              → ~258
Fase 2:           +60 tests (cobertura ORBITAL)    → ~318
Fase 3:           +20 tests (seguridad)            → ~338
Fase 4:           +30 tests (UI/visual)            → ~368
Fase 5:           +40 tests (API/plugins)          → ~408
Fase 6:           +30 tests (benchmarks/orbital)   → ~438
Fase 7:           +62 tests (integración final)    → 500+
```

---

## 📅 Cronograma Visual (Gantt Simplificado)

```
SEMANA  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19
        ─────────────────────────────────────────────────────────────
Fase 0  ████████
Fase 1            ████
Fase 2                 ████
Fase 3                      ████
Fase 4                           ████████████████████
Fase 5                                                  ████████████
Fase 6                                                               ████████████
Fase 7                                                                        ████████████
```

**Nota:** Las fases se ejecutan secuencialmente. Si una fase se extiende, las siguientes se retrasan proporcionalmente. Se recomienda un buffer de 1-2 semanas por fase.

---

## ⚠️ Riesgos y Mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| OrbitalContext no comparte OVC correctamente | Baja (ya verificado) | Crítico | Tests de identity en Fase 0 |
| COD no converge con amplitudes extremas | Media | Alto | Normalización de amplitud + tests extremos |
| UI toma más tiempo del estimado | Alta | Medio | Priorizar funcionalidad sobre polish. Si Fase 4 se extiende >2 semanas, recortar features avanzadas (4.6-4.8) |
| API pública expone vulnerabilidades | Media | Crítico | semgrep scan en cada PR |
| Competencia (n8n, Zapier) lanza features similares | Alta | Medio | Enfocar en diferenciación ORBITAL (circular vs lineal) |
| Validación independiente falla | Baja | Crítico | Documentación transparente + benchmarks publicados |
| Fase se extiende más del estimado | Media | Medio | Buffer de 1-2 semanas por fase. Si una fase se extiende >3 semanas, evaluar si recortar alcance |
| `src/nlp/` tiene dependencias ocultas | Baja | Bajo | Migrar imports a `src/nlu/` antes de eliminar. Verificar con `grep -r 'from src.nlp'` |

---

## 🎯 Recomendación Inmediata

El análisis MiroFish dice: **"La prioridad absoluta es fixear el OrbitalContext singleton"**.

**Estado actual de Fase 0:**
- ✅ Bug #1: OrbitalContext singleton — VERIFICADO con 20 tests
- ⏳ Bug #2: COD no converge con amplitudes grandes — PENDIENTE
- ⏳ Bug #3: OrbitalAdapter/Compiler crean OVCs independientes — PENDIENTE
- ⏳ Bug #4: Secrets hardcodeados — PENDIENTE
- ⏳ Bug #5: Typo "sbridgeectrum" — PENDIENTE
- ⏳ Bug #6: OrbitalContext.engine y ovc no sincronizados — PENDIENTE
- ⏳ Bug #7: BusinessTools usa eval() — PENDIENTE

**Siguiente paso inmediato:** Bug #4 (secrets hardcodeados) — es rápido de fixear y elimina una vulnerabilidad crítica. Luego Bug #7 (eval()) por la misma razón.

---

## 📚 Documentos Relacionados

- `docs/DDE-V3-IMPLEMENTATION-PLAN.md` — Plan de sprints NLU (ya completado)
- `docs/SPRINT-PLAN-POST-MASTERPLAN.md` — Sprints 5-7 completados
- `MiroFish_Analisis_Zenic-Flijo.pdf` — Análisis completo del proyecto
- `MiroFish_Plan_Estrategico_ORBITAL.pdf` — Plan estratégico con simulaciones

---

*Última actualización: Junio 2026 — Plan Maestro MiroFish*
