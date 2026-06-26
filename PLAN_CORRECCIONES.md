# Plan de Correcciones por Fases — Zenic-Flujo

> **Metodología**: skill `planning-and-task-breakdown` (vertical slicing, dependencias bottom-up, acceptance criteria por tarea)
> **Inventario**: consolidación de 4 sesiones de auditoría (ANALISIS_CONSOLIDADO, FRONTEND_ERRORS_REPORT, BACKUP_CONNECTIVITY_REPORT, FIXES_FINAL_REPORT, AUDITORIA_PROFUNDA)
> **Fecha**: 2026-06-22

---

## Estado actual (resumen)

### ✅ Ya corregido (sesiones 2 y 3) — NO se repite en este plan
- 4 bugs P0 frontend (OrbitalVisualizer type drift, MiNegocioPage, FacturacionElectronicaPage headers, ProtectedRoute RBAC)
- 7 bugs P1 frontend (useApi onClick, ThemeContext, LoginPage navigate, charts theme, setTimeout leaks, settings AbortController, i18n)
- 4 issues P2 (code-splitting, aria-label, htmlFor, i18n cleanup)
- 4 conectividad backup (BackupEngine.restore + rutas + UI, ghost calls nginx/Vite proxy, UI historial, Jinja redirects 301)
- ESLint extras (preserve-caught-error, unused type, unused eslint-disable)

### ⏸ Pendiente — objeto de este plan
| # | Hallazgo | Origen | Severidad |
|---|---|---|---|
| 1 | 3 symlinks rotos (`src/core/core`, `src/orbital/orbital`, `src/events/events`) | Auditoría sesión 1 | High (corrupción repo) |
| 2 | `src/api_v2/routers/nlu.py` (294 LOC) NO incluido en app.py | Auditoría sesión 4 | High (código muerto) |
| 3 | 13 templates Jinja legacy siguen en el repo (ya redirigidos 301) | Sesión 3 (decisión Jinja vs React) | Medium (confusión) |
| 4 | 5 archivos static legacy (app.js, chart.umd.min.js, editor.js, orbital-visualizer.js, style.css = ~285 KB) | Sesión 3 | Medium (peso muerto) |
| 5 | `src/hat/agents_legacy/` nombre engañoso (se usa en producción) | Auditoría sesión 4 | Low (higiene) |
| 6 | ~27 rutas Flask potencialmente huérfanas reales | Auditoría sesión 4 | Medium (superficie ataque) |
| 7 | FastAPI v2 no documentada como API pública | Auditoría sesión 4 | Medium (onboarding) |

---

## Fases del plan

### 📦 FASE 1 — Limpieza de corrupción y código muerto (quick wins, bajo riesgo)
**Objetivo**: eliminar archivos que no se ejecutan/sirven, reducir superficie de confusión.
**Esfuerzo estimado**: 2-3 horas | **Riesgo**: Bajo | **Dependencias**: ninguna

#### Tarea 1.1: Eliminar symlinks rotos
- **Archivos**: `src/core/core`, `src/orbital/orbital`, `src/events/events`
- **Acción**: `git rm` los 3 symlinks (apuntan a `/home/z/my-project/repos/Zenic-Flujo/src/...` que no existe)
- **Acceptance criteria**:
  - `find src -type l ! -exec test -e {} \; -print` devuelve 0 resultados
  - `git status` muestra 3 symlinks eliminados
  - Los imports `from src.core.X` siguen funcionando (los symlinks eran redundantes)
- **Verificación**: `python3 -c "import src.core, src.orbital, src.events; print('OK')"`

#### Tarea 1.2: Decidir sobre `src/api_v2/routers/nlu.py` (294 LOC)
- **Decisión binaria** (aplicar doubt-driven-development):
  - **Opción A — Incluirlo**: añadir `from src.api_v2.routers.nlu import router as nlu_router` + `app.include_router(nlu_router)` en `app.py`. Solo si hay un consumidor real de `/api/v2/nlu/*` (no hay ninguno identificado).
  - **Opción B — Eliminarlo** (recomendado): `git rm src/api_v2/routers/nlu.py`. El frontend usa `/api/nlu/*` (Flask), no la v2.
- **Acceptance criteria**:
  - Opción B: archivo eliminado, `grep -r 'routers.nlu' src/api_v2/` devuelve 0
  - `python3 -c "import ast; ast.parse(open('src/api_v2/app.py').read()); print('OK')"`
  - Build frontend sigue pasando (no hay imports de `/api/v2/nlu` en frontend)

#### Tarea 1.3: Eliminar templates Jinja legacy (13 archivos)
- **Contexto**: la sesión 3 convirtió las rutas Jinja en redirecciones 301 al SPA. Los `.html` ya no se renderizan.
- **Archivos a eliminar** (en `src/web/templates/`): `airgap.html`, `chat.html`, `compliance.html`, `dashboard.html`, `dead_letter.html`, `editor.html`, `login.html`, `navbar.html`, `orbital.html`, `partners.html`, `settings.html`, `workflow_detail.html`, `workflow_list.html`
- **Excepción**: `login.html` — verificar si `/login` (Flask, en `pages.py`) aún lo renderiza. Si sí, mantenerlo; si no, eliminarlo.
- **Acción**: `git rm` los 12-13 archivos
- **Acceptance criteria**:
  - `ls src/web/templates/` devuelve solo los que se mantengan (login.html si aplica)
  - `grep -r 'render_template' src/web/blueprints/` no referencia templates eliminados
  - Flask app arranca sin errores: `python3 -c "from src.web.app import create_app; app = create_app(); print('OK')"`

#### Tarea 1.4: Eliminar static legacy JS/CSS (5 archivos, ~285 KB)
- **Contexto**: la UI legacy Jinja usaba `app.js`, `editor.js`, `chart.umd.min.js`, `orbital-visualizer.js`, `style.css`. Tras las redirecciones 301, ya no se sirven.
- **Acción**: `git rm src/web/static/{app.js, chart.umd.min.js, editor.js, orbital-visualizer.js, style.css, manifest.json}`
- **Mantener**: `src/web/static/spa/` (el build del React SPA) y cualquier icono/asset que use el SPA
- **Acceptance criteria**:
  - `ls src/web/static/` solo muestra `spa/` (y assets del SPA si los hay)
  - Build frontend sigue funcionando (el SPA no referencia estos archivos legacy)
  - `grep -r 'app.js\|editor.js\|chart.umd' src/web/` devuelve 0 (excepto en `spa/` que es generado)

**Gate de Fase 1** (sandbox): `python3 ast.parse` + Flask app arranca + frontend tsc/eslint/build limpios + `find src -type l ! -exec test -e {} \;` devuelve 0.

---

### 🏷️ FASE 2 — Documentar estado deprecated de `agents_legacy` (Opción B)
**Objetivo**: documentar la deuda técnica en vez de renombrar (el módulo SÍ es legacy).
**Esfuerzo**: 30 min | **Riesgo**: Bajo (solo docs) | **Dependencias**: Fase 1 completada
**Decisión**: Opción B — ver ADR-0001. El plan original (renombrar a `agents_runtime`) se descartó porque el propio módulo se declara DEPRECATED en su `__init__.py`.

#### Tarea 2.1: Crear ADR-0001 documentando el estado deprecated
- **Acción**: crear `docs/adr/0001-agents-legacy-deprecated-status.md`
- **Contenido**: contexto (agents_legacy se usa en producción pero está marcado deprecated), decisión (NO renombrar), consecuencias, plan de migración futuro
- **Acceptance criteria**: ADR existe y sigue el formato standard

#### Tarea 2.2: Añadir note en `agents.py` referenciando el ADR
- **Acción**: añadir comment en el docstring de `src/api_v2/routers/agents.py` apuntando al ADR
- **Acceptance criteria**: el docstring menciona ADR-0001 y que el módulo es deprecated

**Gate de Fase 2**: ADR existe + agents.py tiene la referencia + imports siguen funcionando.

---

### 🔍 FASE 3 — Auditoría caso por caso de rutas huérfanas
**Objetivo**: decidir eliminar o documentar cada una de las ~27 rutas Flask potencialmente huérfanas.
**Esfuerzo**: 3-4 horas | **Riesgo**: Medio (eliminar rutas puede romper integraciones) | **Dependencias**: ninguna (paralela a Fase 2)

#### Tarea 3.1: Inventario detallado de las 27 rutas candidatas
- **Rutas a revisar** (de AUDITORIA_PROFUNDA.md Parte 8):
  - `sync/import`, `sync/receive` (¿usadas por sync cloud externo?)
  - `queue/enqueue`, `queue/<id>/retry`, `queue/cleanup` (¿usadas por admin internamente?)
  - `reports/audit/<fmt>` (¿usado por scripts de auditoría?)
  - `partners/benefits`, `partners/benefits/<id>/revoke` (¿UI de partners las llama dinámicamente?)
  - `dead-letter/notify/<id>` (¿webhook interno?)
  - `marketplace/stats` (¿dashboard de marketplace?)
  - 16 rutas compliance Type II/GDPR/HIPAA (¿gestión de compliance offline?)
  - 5 rutas `reports/<entity>/<fmt>` CSV/PDF (¿export desde UI?)
- **Acción**: para cada ruta, leer el código del handler y buscar callers en:
  1. Frontend (grep en `frontend/src/`)
  2. Backend (otros módulos Python que la llamen internamente)
  3. Scripts (`scripts/`, `cli/`)
  4. Tests (para distinguir "ruta de test" de "ruta muerta")
  5. e2e (`e2e/`)
- **Output**: tabla `RUTA | CALLERS | DECISIÓN (eliminar/documentar/mantener)`

#### Tarea 3.2: Eliminar rutas confirmadas huérfanas
- **Acción**: para cada ruta marcada "eliminar" en 3.1, `git rm` el handler correspondiente en `src/web/blueprints/*.py`
- **Cuidado**: no eliminar rutas que tengan tests activos (significa que son parte del contrato)
- **Acceptance criteria**:
  - Cada ruta eliminada tiene justificación documentada en el commit message
  - `grep -r 'def api_<ruta>' src/web/` confirma la eliminación
  - Flask app arranca sin errores
  - Tests siguen pasando (si una ruta tenía tests, no se elimina)

#### Tarea 3.3: Documentar rutas que se mantienen
- **Acción**: para rutas marcadas "mantener" (legítimamente para integraciones/scripts), añadir un comment en el handler explicando el consumidor
- **Acceptance criteria**: cada ruta mantenida tiene un `# Consumer: <descripción>` en su handler

**Gate de Fase 3**: tabla de inventario completa + rutas eliminadas con justificación + Flask app arranca + tests pasan.

---

### 📚 FASE 4 — Documentación de API pública
**Objetivo**: clarificar qué es API pública (FastAPI v2) vs API interna del SPA (Flask).
**Esfuerzo**: 2 horas | **Riesgo**: Bajo (solo docs) | **Dependencias**: Fase 3 completada

#### Tarea 4.1: Actualizar ARCHITECTURE.md con sección "API Layers"
- **Acción**: añadir a `ARCHITECTURE.md` una sección que explique:
  - **Flask (`/api/*`, puerto 8080)**: API interna consumida por el SPA React. 139 rutas.
  - **FastAPI v2 (`/api/v2/*`, puerto 8000)**: API pública para integraciones externas (SDK, móvil, partners). 43 rutas efectivas (tras Fase 1).
  - **SSE (`/api/events/stream`)**: streaming de eventos en tiempo real.
  - Tabla de routers v2 con su propósito y consumidores conocidos.
- **Acceptance criteria**: ARCHITECTURE.md tiene la sección "API Layers" con la tabla

#### Tarea 4.2: Añadir header de documentación a cada router FastAPI v2
- **Acción**: en cada `src/api_v2/routers/*.py`, verificar que el docstring del router explique su propósito y audiencia (externa/interna)
- **Acceptance criteria**: los 12 routers v2 (tras Fase 1) tienen docstring con `# Audience: external|internal` y `# Purpose: ...`

#### Tarea 4.3: Documentar la decisión Jinja vs React (ADR)
- **Acción**: crear `docs/adr/0001-jinja-to-spa-migration.md` (Architecture Decision Record) registrando:
  - Contexto: coexistencia de UI Jinja y SPA React
  - Decisión: SPA React como UI principal, rutas Jinja → 301 redirects, templates eliminados (Fase 1)
  - Consecuencias: mantenimiento simplificado, `/login` aún en Jinja por lógica de trial
- **Acceptance criteria**: ADR existe y sigue el formato standard

**Gate de Fase 4**: ARCHITECTURE.md actualizado + routers documentados + ADR creado.

---

### ✅ FASE 5 — Verificación final con sandbox
**Objetivo**: confirmar que todo el plan se ejecutó sin regressiones.
**Esfuerzo**: 1 hora | **Riesgo**: N/A (verificación) | **Dependencias**: Fases 1-4 completadas

#### Tarea 5.1: Gates del sandbox
- **Backend**:
  - `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['src/api_v2/app.py', 'src/web/app.py', 'src/core/db/backup_engine.py']]; print('OK')"`
  - `python3 -c "from src.web.app import create_app; app = create_app(); print('Flask OK')"`
  - Smoke test BackupEngine: `python3 -c "from src.core.db.backup_engine import BackupEngine; be = BackupEngine(); print(be.get_auto_backup_status())"`
- **Frontend**:
  - `cd frontend && npx tsc -b --noEmit` → 0 errores
  - `npx eslint .` → 0 errores, 0 warnings
  - `npx vite build` → exitoso
- **Sandbox self-tests**: `python -m pytest sandbox/tests/ -q` → 65 passed
- **Sinergia**: `find src -type l ! -exec test -e {} \; -print` → 0 symlinks rotos
- **Nomenclatura**: `grep -r 'agents_legacy' src/` → 0 resultados

#### Tarea 5.2: Reporte de cierre
- **Acción**: actualizar `FIXES_FINAL_REPORT.md` (o crear `PLAN_EJECUCION_REPORT.md`) con:
  - Estado final de cada hallazgo del inventario
  - Métricas finales (LOC eliminados, rutas reducidas, archivos limpiados)
  - Confirmación de gates
- **Acceptance criteria**: reporte existe, todos los hallazgos marcados ✅ o justificados

**Gate de Fase 5**: los 4 gates (Python syntax, tsc, eslint, build) + sandbox 65 tests + smoke tests pasan.

---

## Resumen del plan

| Fase | Objetivo | Tareas | Esfuerzo | Riesgo | Depende de |
|---|---|---|---|---|---|
| 1 | Limpieza corrupción + código muerto | 4 | 2-3h | Bajo | — |
| 2 | Renombrar agents_legacy | 1 | 1h | Medio | Fase 1 |
| 3 | Auditar 27 rutas huérfanas | 3 | 3-4h | Medio | — (paralela) |
| 4 | Documentar API pública | 3 | 2h | Bajo | Fase 3 |
| 5 | Verificación sandbox | 2 | 1h | — | Fases 1-4 |
| **Total** | | **13 tareas** | **9-11h** | | |

## Orden de ejecución recomendado

```
Fase 1 (limpieza) ──→ Fase 2 (rename) ──┐
                                         ├──→ Fase 4 (docs) ──→ Fase 5 (verify)
Fase 3 (rutas huérfanas) ────────────────┘
```

- **Fase 1 y Fase 3 pueden ir en paralelo** (no se tocan)
- **Fase 2 depende de Fase 1** (mejor limpiar antes de renombrar)
- **Fase 4 depende de Fase 3** (la docs de API debe reflejar las rutas que quedan)
- **Fase 5 al final** (verifica todo)

## Principios aplicados (skill planning-and-task-breakdown)
- **Vertical slicing**: cada fase entrega valor completo (no "todo el backend, luego todo el frontend")
- **Bottom-up dependencies**: fases foundation (limpieza) antes que fases derivadas (docs)
- **Acceptance criteria explícitos**: cada tarea tiene criterios verificables
- **Esfuerzo estimado**: cada fase tiene estimación de horas
- **Risk assessment**: cada fase tiene riesgo clasificado

## Cuándo activar Code-Forge (Layer 3)
- **Fase 1, 2, 3**: NO activar Code-Forge (son eliminaciones/renames, no implementación con gates)
- **Fase 4**: NO activar (solo docs)
- **Fase 5**: NO activar (verificación)
- Si en Fase 3 se decide **implementar UI para rutas huérfanas** (en vez de eliminarlas), ahí sí activar Code-Forge con hard gates para la nueva UI.

## Notas de honestidad
- **~27 rutas huérfanas** es una estimación; el número real puede variar tras la revisión caso por caso de Fase 3. Algunas resultarán legítimas (scripts internos), otras serán eliminables.
- **`login.html`**: la excepción de Fase 1.3 requiere verificación. Si `/login` (Flask) aún lo renderiza (tiene lógica de trial), se mantiene; si no, se elimina.
- **Renombrar `agents_legacy`** (Fase 2) puede romper imports si hay referencias dinámicas (string imports). El grep exhaustivo las detectará, pero hay que revisar manualmente.
- **FastAPI v2 como "API pública"**: si NO hay consumidores externos reales (SDK, móvil, partners), la recomendación correcta es **eliminar los routers v2 no usados** en vez de documentarlos. La Fase 4 asume que sí hay consumidores; si no, convertiría en "eliminar routers v2 huérfanos".
