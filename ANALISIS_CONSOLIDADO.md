# Zenic-Flujo — Análisis Consolidado (Frontend + Conectividad Backup)

> **Flujo de trabajo aplicado:** 3 capas (Skills + Personas + Sandbox)
> - **Layer 1 (Skills)**: `planning-and-task-breakdown` → `frontend-ui-engineering` → `debugging-and-error-recovery`
> - **Layer 2 (Personas)**: Frontend Developer (análisis profundo) + Senior Developer (conectividad)
> - **Layer 3 (Sandbox)**: ESLint + tsc + Vite build ejecutados sobre el frontend
> - **Fecha**: 2026-06-22

## Reportes detallados (leer para contexto completo)
- [`FRONTEND_ERRORS_REPORT.md`](./FRONTEND_ERRORS_REPORT.md) — análisis de errores del frontend (42 KB, 9 secciones)
- [`BACKUP_CONNECTIVITY_REPORT.md`](./BACKUP_CONNECTIVITY_REPORT.md) — conectividad frontend ↔ backup (37 KB, 6 secciones)

---

## 1. Respuesta directa a las 2 preguntas del usuario

### Pregunta 1: "Análisis completo del frontend y buscar errores"
**Sí, hay errores.** El frontend compila (Vite build funciona) pero tiene **12 errores de TypeScript, 4 de ESLint, y 4 bugs críticos de runtime** que el sandbox no puede detectar pero el análisis manual sí encontró.

### Pregunta 2: "Verificar frontend vs código del backup para ver si todo el backup está conectado al frontend"
**No, no todo está conectado.** De los 5 métodos públicos de `BackupEngine`, solo **1** (`backup_now`) está conectado al frontend. Hay **2 métodos muertos** (`stop_auto_backup`, `get_backup_info`), **1 método interno** sin UI (`start_auto_backup`), y **`restore` ni siquiera existe** (pero una control SOC 2 lo requiere).

---

## 2. Hallazgos CRÍTICOS (P0 — arreglar ya)

| # | Bug | Archivo:línea | Impacto |
|---|---|---|---|
| 1 | `OrbitalVisualizer` declara su propio `OrbitalStatus` con `tor_results`/`cod` (objeto) pero el tipo canónico `types/orbital.ts` usa `tor: TorEntry[]`/`cod: CodResult[]` | `components/orbital/OrbitalVisualizer.tsx:43-57` vs `types/orbital.ts:44-54` | **Las líneas TOR y el indicador COD nunca renderizan** — la visualización estrella está silenciosamente rota |
| 2 | `MiNegocioPage` usa `localStorage.getItem('token')` (siempre null — la app usa cookies) + URL hardcoded `localhost:8000` | `pages/MiNegocioPage.tsx:37-44` | **Las 3 llamadas `/api/v2/*` fallan en producción** — la página muestra ceros |
| 3 | `FacturacionElectronicaPage` pasa `{ headers }` a `api.post` cuyo tipo de options es `{ signal?: AbortSignal }` | `pages/FacturacionElectronicaPage.tsx:142` | TS error + **el header `X-License-Key` se pierde en runtime** |
| 4 | `ProtectedRoute` se usa sin `requiredRole` en ninguna ruta | `App.tsx:52-58` | **Cualquier usuario `viewer` puede acceder a `/app/admin`** — bypass de RBAC |

## 3. Hallazgos HIGH (P1)

| # | Bug | Archivo | Impacto |
|---|---|---|---|
| 5 | Patrón `useApi` onClick: el hook devuelve `(signal?: AbortSignal) => Promise<void>` y se pasa directo a `onClick` | 11 instancias en 10 archivos (DeadLetterTab, AirgapPage×2, CrmPage, IntegrationsPage, InventoryPage, InvoicesPage, OrbitalPage×2, Plugins, ReportsPage) | **Type error** (MouseEvent no es AbortSignal). Runtime funciona por suerte (`event.aborted` es undefined) pero es frágil. Fix: envolver con `() => loadData()` |
| 6 | `ThemeContext` no memoizado | `contexts/ThemeContext.tsx` | Re-renders innecesarios en toda la app al cambiar tema |
| 7 | Charts leen DOM durante el render (no re-renderizan al cambiar tema) | dashboard charts | Theme toggle no actualiza los gráficos |
| 8 | Fetch sin AbortController en 4 componentes | SettingsSystemTab, SettingsSmtpTab, SettingsApiKeyTab, MiNegocioPage | Race conditions en montaje/desmontaje rápido |
| 9 | `setTimeout` leaks en handlers SSE del Dashboard | `pages/Dashboard.tsx` | Memory leak potencial |
| 10 | `navigate()` durante render en LoginPage | `pages/LoginPage.tsx` | Anti-patrón React, puede causar warnings/errores |

## 4. Hallazgos MEDIUM (P2)

| # | Issue | Detalle |
|---|---|---|
| 11 | i18n abandonado | Solo 1 de 22 páginas usa `t()`. 25 claves muertas en `es.json` |
| 12 | 8 botones solo-icono sin `aria-label` | WCAG 4.1.2 — lectores de pantalla no los anuncian |
| 13 | ~20 form labels sin `htmlFor` | WCAG 1.3.1 |
| 14 | Bundle de 1.34 MB sin code-splitting | `React.lazy`/`Suspense`/dynamic import inexistentes. Route-based lazy loading reduciría 60-70% |

## 5. Conectividad Backup — detalle completo

### BackupEngine: 5 métodos, solo 1 conectado al frontend

| Método | Estado | Evidencia |
|---|---|---|
| `backup_now` | ✅ Conectado | `SettingsSystemTab.tsx:34` → `POST /api/system/backup` (Flask `auth.py:284-291`) → `BackupEngine.backup_now()` |
| `start_auto_backup` | ⚠️ Solo interno | Llamado una vez en `src/main.py:39` al arrancar. Sin UI para iniciar/detener/cambiar intervalo |
| `stop_auto_backup` | ❌ Código muerto | Cero callers en todo el repo |
| `get_backup_info` | ❌ Código muerto | Cero callers; no existe UI de "historial de backups" |
| `restore` | ❌ No existe | Sin método, sin ruta, sin UI. **Pero** `compliance/__init__.py:192` define el control SOC 2 A1.3 (critical) cuyo procedimiento es "Verify backup schedule, test restoration, check RTO/RPO" — **incumplible como está** |

### Otros hallazgos de conectividad

- **Ghost frontend (BUG de despliegue):** 5 llamadas React a `/api/v2/*` (3 en `MiNegocioPage`, 2 en `FacturacionElectronicaPage`) fallan en producción porque `nginx.conf` solo proxyea a Flask:8080; FastAPI:8000 es interno. Fix: añadir `location /api/v2/ { proxy_pass http://zenic-flijo:8000; }` + entrada de proxy en Vite.
- **UI Flask legacy NO es backup:** está viva, montada en paralelo con el SPA React en el mismo proceso Flask (`src/web/app.py:87-119`). 13 templates Jinja (~3000 LOC) + 1100 LOC de JS legacy. Ambas UIs pegan a `/api/system/backup`. Riesgo de mantenimiento: borrar rutas "huérfanas desde React" rompería silenciosamente la UI Jinja.
- **FastAPI v2:** ~96 rutas, solo 5 llamadas desde React. ~110 rutas FastAPI v2 + 1 HAT + 15 móviles son huérfanas desde React.
- **Rutas Flask realmente huérfanas (sin caller en ninguna UI):** ~35 — `workflows/execute`, `marketplace/stats`, `queue/enqueue`/`<id>/retry`/`cleanup`, `dead-letter/notify/<id>`, 16 rutas compliance Type II/GDPR/HIPAA, 5 rutas `reports/<entity>/<fmt>`, 3 rutas `partners/benefits*`, `integrations/<name>/status`, `workflows/versions/<n>`, `sync/import`, `sync/receive`.
- **Corrupción preexistente del repo:** symlinks rotos en `src/{core,orbital,events}/{core,orbital,events}` apuntando a `/home/z/my-project/repos/Zenic-Flujo/src/...` (ruta inexistente).

## 6. Lo que está VERIFICADO LIMPIO (honestidad)

- Las 22 rutas importan páginas que existen; hay catch-all 404.
- Cero violaciones de Rules of Hooks en toda la app.
- `useSSE.ts` cleanup correcto (EventSource + reconnectRef).
- `AuthContext.tsx` value memoizado; `checkAuth` tiene 3 abort-check points.
- Patrón AbortController de `useApi` correctamente aplicado en 11 page loaders.
- `AnimatedCounter` cancela `requestAnimationFrame` en cleanup.

## 7. Top 5 recomendaciones prioritizadas

1. **Fix OrbitalVisualizer type drift** (P0) — cambiar `tor_results`/`cod` → `tor`/`cod` para que coincida con `types/orbital.ts`. Sin esto, la visualización estrella no funciona.
2. **Fix MiNegocioPage roto en producción** (P0) — 3 bugs independientes: quitar `localStorage.getItem('token')`, usar `VITE_API_URL` en vez de `localhost:8000`, arreglar el proxy nginx para `/api/v2/`.
3. **Fix FacturacionElectronicaPage headers + wiring `/api/v2/`** (P0) — el wrapper `api.post` no acepta `headers`; ampliar el tipo o usar el fetch nativo. Y el proxy nginx.
4. **Fix patrón useApi onClick** (P1) — 11 wrappers mecánicos `() => loadData()` en 10 archivos. O cambiar la firma del hook.
5. **Route-based lazy loading** (P2) — añadir `React.lazy` + `Suspense` en `App.tsx` para las 22 páginas. Reduciría el bundle de 1.34 MB a ~400-500 KB por ruta.

## 8. Recomendaciones de conectividad backup

1. **Implementar `BackupEngine.restore(backup_path)`** + ruta `POST /api/system/restore` + botón UI en `SettingsSystemTab.tsx`. Sin esto, el control SOC 2 A1.3 no puede pasar.
2. **Añadir UI de historial de backups** que use `get_backup_info` (hoy muerto) — lista de backups con fecha, tamaño, opción de descargar/restaurar.
3. **Añadir UI de configuración de auto-backup** que use `start_auto_backup`/`stop_auto_backup` con intervalo configurable (hoy hardcoded en `main.py:39`).
4. **Decidir Jinja vs React:** o borrar el legacy `src/web/templates/*` + `static/{app,editor}.js` + el blueprint `pages.py`, o añadir un test de "route ownership" que afirme que toda ruta Flask tiene caller en al menos una UI.
5. **Borrar las ~35 rutas Flask realmente huérfanas** (lista completa en `BACKUP_CONNECTIVITY_REPORT.md` Sección 2d) — son superficie de ataque muerta.

## 9. Métricas del análisis

| Métrica | Valor |
|---|---|
| Archivos frontend analizados | ~100 (22 páginas + 60 componentes + 18 tipos/hooks/contexts) |
| Líneas de frontend | ~12,000 LOC TS/TSX |
| Errores TypeScript | 12 |
| Errores ESLint | 4 (+1 warning) |
| Bugs críticos runtime (P0) | 4 |
| Bugs high (P1) | 7 |
| Issues medium (P2) | 4 |
| Issues low (P3) | 3 |
| Métodos BackupEngine | 5 (1 conectado, 2 muertos, 1 interno, 1 inexistente) |
| Rutas backend | ~150 (Flask + FastAPI v2 + HAT + mobile) |
| Rutas huérfanas (sin caller React) | ~145 |
| Rutas realmente huérfanas (sin caller en cualquier UI) | ~35 |
| Ghost frontend (frontend llama, backend no sirve en prod) | 5 |
| Bundle size | 1.34 MB (377 KB gzip) — sin code-splitting |

---

*Análisis ejecutado siguiendo el flujo: dispatcher unificado de 3 capas → skills (planning/frontend-ui/debugging) → personas (Frontend Developer + Senior Developer como subagentes) → sandbox (ESLint + tsc + Vite build). Layer 3 (Code-Forge loop) no se activó porque es análisis, no implementación con hard gates.*
