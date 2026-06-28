# ADR-0002: Migración Jinja UI → React SPA

**Estado**: Aceptado
**Fecha**: 2026-06-22 (decisión inicial sesión 3, formalizado en sesión 7)
**Fase del plan**: Fase 4.3 del PLAN_CORRECCIONES

## Contexto

Zenic-Flujo tenía históricamente **dos UIs coexistiendo**:

1. **UI Jinja legacy** (`src/web/templates/*.html` + `src/web/static/{app.js, editor.js, chart.umd.min.js, orbital-visualizer.js, style.css}`) — Flask server-rendered, ~3000 LOC de templates + ~1100 LOC de JS legacy
2. **SPA React** (`frontend/` + build en `src/web/static/spa/`) — React 19 + Vite + TypeScript, ~12,000 LOC

Ambas UIs se servían desde el mismo proceso Flask (`src/web/app.py`):
- Rutas Jinja raíz (`/dashboard`, `/chat`, `/editor`, `/workflows`, `/settings`, etc.) renderizaban templates HTML
- Rutas SPA (`/app/*`) servían el `index.html` del build React
- Ambas UIs pegaban a los mismos endpoints `/api/*` (Flask)

**Problemas de la coexistencia**:
- Mantenimiento duplicado: cada feature requería implementarse en ambas UIs
- Riesgo de desincronización: cambios en Flask `/api/*` podían romper una UI pero no la otra
- Superficie de ataque ampliada: rutas "huérfanas del React" podían seguir siendo usadas por la UI Jinja
- Confusión para nuevos desarrolladores: ¿qué UI es la "oficial"?
- Peso muerto: ~285 KB de assets legacy que el SPA no usaba

## Decisión

**SPA React es la UI principal y única**. Las rutas Jinja raíz se convierten en redirecciones 301 al SPA, y los templates/assets legacy se eliminan.

### Acciones ejecutadas

#### Sesión 3 (decisión inicial)
- `src/web/blueprints/pages.py` reescrito: 10 rutas Jinja raíz (`/dashboard`, `/chat`, `/editor`, `/workflows`, `/settings`, `/dead-letter`, `/compliance`, `/airgap`, `/partners`, `/orbital`) convertidas en redirecciones 301 a `/app/*`
- `/workflows/<int:id>` redirige a `/app/workflows?id=<id>` (301)
- `/login` se mantiene en Jinja porque tiene lógica de trial (`LicenseValidator.get_trial_status()`) que el SPA maneja de forma diferente al arranque

#### Sesión 5 (Fase 1 del PLAN_CORRECCIONES — ejecución de la limpieza)
- **Eliminados 12 templates Jinja legacy**: `airgap.html`, `chat.html`, `compliance.html`, `dashboard.html`, `dead_letter.html`, `editor.html`, `navbar.html`, `orbital.html`, `partners.html`, `settings.html`, `workflow_detail.html`, `workflow_list.html`
- **Mantenido `login.html`** porque `/login` (Flask) aún lo renderiza
- **Eliminados 5 assets legacy**: `app.js` (19KB), `chart.umd.min.js` (209KB), `editor.js` (21KB), `orbital-visualizer.js` (7KB), `style.css` (31KB) — total ~285 KB
- **Eliminado `sw.js` inicialmente** (referenciaba assets legacy), luego **restaurado y reparado** en sesión 6 para soporte PWA offline real

#### Sesión 6 (PWA offline reparada)
- `sw.js` reescrito para cachear assets del SPA (`/static/spa/*`) con estrategia stale-while-revalidate
- `manifest.json` actualizado: `start_url=/app/dashboard`, 9 iconos (incluido maskable), 3 shortcuts
- 10 iconos PNG generados (72, 96, 128, 144, 152, 192, 384, 512, maskable-512, badge-72)
- `frontend/index.html` actualizado con manifest link + theme-color + apple-touch-icon + apple-mobile-web-app meta tags
- `frontend/src/main.tsx` actualizado con registro de service worker (solo en PROD)

## Consecuencias

### Positivas
- **Una sola UI** que mantener: el SPA React
- **Sin riesgo de desincronización**: los cambios en `/api/*` solo afectan al SPA
- **Superficie de ataque reducida**: las rutas "huérfanas del React" ahora son candidatas claras a eliminación (ver `ORPHAN_ROUTES_INVENTORY.md`)
- **PWA offline funcional**: la app ahora funciona offline de verdad (antes el service worker nunca se registraba)
- **~285 KB de assets legacy eliminados** del repo
- **Onboarding simplificado**: nuevos desarrolladores solo aprenden React, no Flask+Jinja+React

### Negativas
- **`/login` sigue en Jinja**: requiere migrar la lógica de `LicenseValidator.get_trial_status()` al `AuthContext` del SPA para completar la transición
- **Bookmarks viejos** redirigen 301 (latencia mínima, pero no instantánea)
- **Pérdida de server-rendering** para `/login` (peor SEO/first-paint en esa ruta, pero irrelevante porque es pantalla de auth)

## Migración futura de `/login` (deuda técnica residual)

Para eliminar completamente la dependencia Jinja:

1. Mover `LicenseValidator.get_trial_status()` a un endpoint API (`GET /api/license/trial-status`)
2. Llamarlo desde `AuthContext` al inicializar
3. Crear `LoginPage` del SPA que use ese dato (en vez de pasarlo vía template context)
4. Eliminar `/login` Flask route + `login.html` + el `render_template` en `pages.py:53`
5. Eliminar la dependencia de Jinja2/Flask templating si no se usa en ningún otro sitio

## Referencias

- `src/web/blueprints/pages.py` — redirecciones 301 al SPA (sesión 3)
- `src/web/templates/login.html` — único template Jinja restante
- `src/web/static/sw.js` — service worker PWA reparado (sesión 6)
- `src/web/static/manifest.json` — manifiesto PWA (sesión 6)
- `frontend/index.html` — tags PWA + manifest link (sesión 6)
- `frontend/src/main.tsx` — registro de service worker (sesión 6)
- `ORPHAN_ROUTES_INVENTORY.md` — rutas candidatas a eliminación tras esta migración
- `ADR-0001` — estado deprecated de agents_legacy (relacionado pero independiente)
