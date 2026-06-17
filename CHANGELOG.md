# Changelog

## v2.0.0 (2026-06-17) — Multi-entorno, Monitoreo y Visualizador Orbital

### Added — Sprint 9: Multi-entorno + Versioning
- Sistema de versiones de workflows (snapshot inmutable por cada UPDATE)
- Política de retención configurable (default: 20 versiones por workflow)
- Rollback a versión anterior sin perder el histórico (append-only)
- Tabla `workflow_versions` con auto-incremento de `version_number`
- Tabla `workflow_environments` con entornos `dev`, `staging`, `prod`
- Tabla `workflow_promotions` para auditoría de promociones
- Flujo de promoción lineal `dev → staging → prod` (no se puede saltar etapas)
- Cálculo automático de diff entre versiones (campos cambiados + summary)
- 8 endpoints nuevos en `/api/workflows/:id/{versions,environments,promotions}`
- Frontend: `EnvironmentsTab` con 3 secciones (entornos, versiones, histórico)
- Frontend: `PromotionDialog` con selector visual de promoción
- Frontend: tipos TS `versioning.ts` + helpers (`getAvailablePromotions`)
- 61 tests backend (18 versioning + 43 environments/promotions)

### Added — Sprint 11: Monitoreo + Alertas
- `AlertService` con reglas declarativas y cooldown configurable
- 4 reglas por defecto: workflow_failure_rate, dead_letter_depth, worker_pool, queue_depth
- 3 notificadores plugables: `EmailNotifier` (SMTP), `SlackNotifier` (webhook), `WebhookNotifier` (JSON POST)
- Tabla `alert_events` con persistencia y estados (active/resolved/suppressed)
- Thread daemon opcional para evaluación periódica (default: 60s)
- Endpoint `/api/admin/metrics` con métricas agregadas (cola, DLQ, timeline 24h, top slowest)
- Endpoint `/api/admin/metrics/prometheus` en formato Prometheus text
- 5 endpoints para gestión de alertas: list, resolve, stats, rules, evaluate
- Frontend: `MetricsTab` con KPIs live + stats por status + timeline 24h (auto-refresh 30s)
- Frontend: `AlertsTab` con resumen por severidad + alertas activas + histórico + reglas
- Integración en `AdminPage.tsx` (tabs "Métricas" y "Alertas")
- 37 tests backend de alerts

### Added — Sprint 12: Visualizador Orbital
- `OrbitalVisualizer` con Canvas 2D en tiempo real (sin dependencias WebGL)
- Variables orbitales renderizadas como partículas (color por grupo orbital)
- Mayor amplitud → partícula más cerca del centro (mayor energía)
- Líneas TOR entre partículas (verde = resonancia, rojo = anti-resonancia)
- COD (Colapso Orbital Determinista) renderizado como punto pulsante en el centro
- Auto-refresh cada 1s desde `/api/orbital/status`
- Controles: pausar/reproducir, tick manual, métricas live (cache hit, iteraciones)
- Integrado como tab "Visualizador" en `OrbitalPage.tsx` (default tab)
- Es el showcase del diferenciador competitivo ORBITAL

### Added — Fase 1: Pulido TypeScript
- Activado `strict: true` + 8 verificaciones strict adicionales en `tsconfig.app.json`
- 40 errores TS preexistentes corregidos (foundation: types/workflow.ts)
- Componentes editor migrados a API v12 de `@xyflow/react` (`NodeProps<Node<T, "type">`)
- `useSSE.ts` con refs tipados correctamente (`useRef<T | undefined>(undefined)`)
- Suite de tests frontend con vitest (4 suites, 39 tests)
- Tests `useApi` (previene BUG-FE-01), `CrmPage` (previene BUG-FE-02)
- CI/CD con GitHub Actions (jobs backend + frontend + summary)
- `Textarea` component shadcn añadido

### Fixed
- BUG-FE-01: `useApi` mismatch restaurando `getApi()` con métodos HTTP completos
- BUG-FE-02: `STAGES` definido como const en `CrmPage.tsx` (ahora importado de `types/crm`)
- BUG-FE-03,04,05: Eliminados 3 hooks muertos (`useToast`, `useConfirm`, `usePagination`)
- BUG-FE-06: Eliminado `App.css` con estilos residuales Vite
- BUG-FE-07: Popover/Tooltip shorthands verificados tras strict mode
- BUG-FE-08: `Editor.tsx` set-state-in-effect resuelto al tipar `useEdgesState<WorkflowEdge>`
- BUG-TS-01: Activado `strict: true` + `noImplicitAny` + `strictNullChecks`
- BUG-DOC-01: Re-calificación arquitectónica pendiente (tras Fase 6)

### Verified (already mitigated in repo)
- BUG-BE-01: `eval()` en `agents/memory.py` — ya no existe (usa `json.loads`)
- BUG-LOG-01: `token_tracking.py` ya usa `<redacted>` en logs
- BUG-SEC-01..09: SQL injection — mysql/postgres/data_keeper validan identifiers con regex
- BUG-SEC-10: CORS — ya usa `WFD_API_V2_CORS_ORIGINS` env var, deny por defecto
- BUG-SEC-11: `importlib.import_module` — ya tiene `ALLOWED_PACKAGES` whitelist

### Stats
- Score de calidad: 28.5% → 92.0% (gap al 95%: 3 puntos, cerrables con Fase 6)
- Tests backend: +98 nuevos (18 versioning + 43 env/promo + 37 alerts)
- Tests frontend: +39 nuevos (4 suites vitest)
- Bugs P0: 12/12 resueltos (100%)
- Bugs P1: 3/3 resueltos (100%)
- Bugs P3: 4/4 resueltos (100%)
- Endpoints API nuevos: 16 (8 versioning + 8 admin metrics/alerts)
- Tablas DB nuevas: 4 (workflow_versions, workflow_environments, workflow_promotions, alert_events)
- Componentes frontend nuevos: 7 (EnvironmentsTab, PromotionDialog, MetricsTab, AlertsTab, OrbitalVisualizer, textarea, versioning types)

## v1.0.0 (2026-06-10)

### Added
- Motor ORBITAL v3.2 completo (OVC, TOR, RCC, COD, Espectro)
- OrbitalContext singleton con OVC compartido
- Benchmarks del motor ORBITAL
- Sistema WebSocket para dashboard en tiempo real
- Tema oscuro/claro con persistencia localStorage
- Chat mejorado con markdown y sugerencias
- API documentada con OpenAPI 3.0
- API Key authentication system
- Webhooks de salida
- Rate limiting por API key y por IP
- RBAC (admin, editor, viewer)
- CI/CD con GitHub Actions
- Instalador Windows/Linux con GUI tkinter

### Fixed
- 7 bugs críticos de Fase 0 (OrbitalContext, COD, secrets, eval, etc.)
- Migración nlp → nlu completada
- 101+ tests nuevos para seguridad y testing
- SQL injection prevention (parameterized queries)
- XSS protection mejorada
- Cookie security (httpOnly, SameSite)
