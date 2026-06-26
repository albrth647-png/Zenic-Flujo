# Backup Connectivity Audit — Zenic-Flujo

**Task ID:** `zenic-1b`
**Agent:** EngineeringSeniorDeveloper (agency-agents collection)
**Date:** 2025-06-22
**Scope:** Verify whether the `BackupEngine` (and, by extension, all backend code) is reachable from the React frontend; flag orphan backend code, ghost frontend calls, and assess the legacy Flask UI.

---

## Executive Summary

| Metric | Count |
|---|---|
| Backend routes — Flask blueprints (`src/web/blueprints/*.py`) | **150** |
| Backend routes — Flask app-level (`src/web/app.py`) | **4** (`/app`, `/app/<path>`, `/<path:spa_route>`, `/metrics`) |
| Backend routes — FastAPI v2 (`src/api_v2/routers/*.py`) | **~96** (across 13 routers) |
| Backend routes — HAT (`src/hat/level1_orchestrator/api/routes.py`) | **1** (`/api/hat/chat`) |
| Backend routes — Mobile (`src/mobile/api.py`) | **15** (`/mobile/*`) |
| **Total backend HTTP routes** | **≈ 266** |
| Distinct API paths the React frontend calls | **~95** |
| React calls that map to a live backend route (CONNECTED) | **~92** |
| React calls to endpoints that don't exist (GHOST_FRONTEND, strict) | **0** |
| React calls that are functionally broken at deploy time (wiring ghost) | **2 pages, 5 paths** (`/api/v2/*` — see §3) |
| Backend routes orphan from the React frontend (ORPHAN_BACKEND) | **≈ 130** (mostly FastAPI v2 duplicates + mobile + the `/api/*` Flask routes that only the Jinja UI consumes) |
| Backend routes orphan from **all** UIs (TRULY_ORPHAN) | **≈ 35** |
| BackupEngine methods exposed & wired to React | **1 of 4** public methods (`backup_now`) |
| BackupEngine methods with zero callers anywhere in the repo | **2** (`stop_auto_backup`, `get_backup_info`) |
| BackupEngine methods that don't exist but compliance criteria demand | **1** (`restore`) |

**Headline answers (TL;DR):**

1. **Is the BackupEngine connected to the React frontend?** Yes, but only the *manual* `backup_now` action. The React `Settings → Sistema` tab (`SettingsSystemTab.tsx`) calls `POST /api/system/backup`, which Flask routes to `BackupEngine().backup_now()` (`src/web/blueprints/auth.py:284-291`). `start_auto_backup` runs internally at startup (`src/main.py:39`). `stop_auto_backup` and `get_backup_info` are **dead code** (zero callers). A `restore` method **does not exist** — even though `src/compliance/__init__.py:192` explicitly tells auditors to "verify backup schedule, test restoration, check RTO/RPO targets".
2. **Is there orphan backend code?** Yes — significantly. The FastAPI v2 router surface (~96 routes) is almost entirely orphan from the React frontend: only 5 of those routes are called (all from two pages: `MiNegocioPage` and `FacturacionElectronicaPage`). The FastAPI `/api/hat/chat` endpoint is a duplicate of the Flask `/api/workflows/chat` route that React actually calls. ~35 Flask routes (compliance Type II, GDPR, HIPAA, reports CSV/PDF, queue/enqueue, sync/import, sync/receive, dead-letter/notify, partners/benefits, marketplace/stats, integrations status, workflows/history, workflows/export, workflows/import, workflows/execute) have no React caller — most are consumed by the legacy Jinja UI; a handful are truly dead.
3. **Is `src/web/` a "backup" of the old frontend?** No — it is **still live and mounted in parallel** with the React SPA. Flask serves Jinja templates at `/`, `/login`, `/dashboard`, `/chat`, `/editor`, `/workflows`, `/settings`, `/dead-letter`, `/compliance`, `/airgap`, `/partners`, `/orbital`; the React SPA is served at `/app/*` and via the catch-all `/<path:spa_route>` (`src/web/app.py:95-119`). Both UIs call the same `/api/*` Flask routes. This is a maintenance risk, not a backup.
4. **Are there ghost frontend calls?** In the strict sense (path string doesn't match any backend route), **no** — every React-called path resolves to a real backend route. *Functionally*, however, the React SPA's 5 calls to `/api/v2/*` paths are broken at deploy time in the default topology: only Flask port 8080 is exposed in `docker-compose.yml`/`Dockerfile`, FastAPI port 8000 is internal-only, and Flask returns 404 for `api/v2/*` paths (catch-all rule at `src/web/app.py:114`). Only `MiNegocioPage.tsx` uses `VITE_API_URL || 'http://localhost:8000'` to bypass this; `FacturacionElectronicaPage.tsx` uses a bare relative path and would 404 in production. **This is a wiring bug, not a missing endpoint.**

---

## Section 1 — BackupEngine Method-by-Method Trace

Source: `src/core/db/backup_engine.py:1-144`.

| # | Method | Visibility | Caller(s) in backend | Backend route(s) exposing it | React frontend caller | Verdict |
|---|---|---|---|---|---|---|
| 1 | `__init__()` | public | `src/main.py:38` (start_workers), `src/web/blueprints/auth.py:289` (per-request instantiation) | n/a | n/a | Internal — OK |
| 2 | `backup_now(dest_path=None) → str` | public | `src/web/blueprints/auth.py:290` | `POST /api/system/backup` (`src/web/blueprints/auth.py:284-291`) | `frontend/src/components/settings/SettingsSystemTab.tsx:34` (`apiFetch("/api/system/backup", {method:"POST"})`) | ✅ **CONNECTED** |
| 3 | `start_auto_backup(interval_hours=24) → None` | public | `src/main.py:39` only | none (no API route) | none | ⚠️ **Reachable only at startup**, not user-controllable from the UI. Not strictly orphan (it's used), but there is no UI to start/stop or change the interval. |
| 4 | `stop_auto_backup() → None` | public | **none** (zero callers repo-wide — confirmed by `rg 'stop_auto_backup' src/ tests/ frontend/ e2e/`) | none | none | ❌ **TRULY ORPHAN** — dead code. |
| 5 | `_schedule_next()` | private | `start_auto_backup`, `_auto_backup_tick` | n/a | n/a | Internal — OK |
| 6 | `_auto_backup_tick()` | private | `_schedule_next` (via `Timer`) | n/a | n/a | Internal — OK |
| 7 | `_cleanup_old_backups(backup_dir, max_backups=10)` | private | `_auto_backup_tick` | n/a | n/a | Internal — OK |
| 8 | `get_backup_info() → dict` | public | **none** (zero callers repo-wide) | none | none | ❌ **TRULY ORPHAN** — dead code. Was likely intended for a "list backups / view backup history" UI; that UI doesn't exist. |
| — | `restore(...)` | — | **does not exist** | none | none | ❌ **MISSING** — `src/compliance/__init__.py:192` defines a SOC 2 control (A1.3, risk_level: critical) whose test procedure is *"Verify backup schedule, test restoration, check RTO/RPO targets."* There is no restore method on `BackupEngine` and no restore route on Flask or FastAPI. The compliance dashboard will always report this control as failing. |

**Backup trace diagram:**

```
React: SettingsSystemTab.tsx:34
   └─> POST /api/system/backup        (Flask blueprint)
         └─> src/web/blueprints/auth.py:284  api_system_backup()
               └─> BackupEngine().backup_now()
                     └─> DatabaseManager.backup(dest)    (sqlite backup API)

src/main.py:39 (at process startup only, never again)
   └─> BackupEngine().start_auto_backup(interval_hours=24)
         └─> _schedule_next → threading.Timer(24h) → _auto_backup_tick
                                                                  │
                                                                  └─> _cleanup_old_backups(max=10)

BackupEngine.stop_auto_backup   — NO CALLERS (dead)
BackupEngine.get_backup_info    — NO CALLERS (dead; no UI lists backups)
BackupEngine.restore            — DOES NOT EXIST (compliance A1.3 demands it)
```

---

## Section 2 — ORPHAN_BACKEND: routes no React page calls

Two columns: "orphan from React only" (likely still consumed by the legacy Flask/Jinja UI or by non-React clients like Prometheus / mobile apps / server-to-server) vs "truly orphan" (no caller anywhere in this repo).

### 2a. FastAPI v2 routes (orphan from React — all of them, except 5)

FastAPI v2 exposes ~96 routes under `/api/v2/*`. The React frontend calls only these 5:

| React caller | Path |
|---|---|
| `frontend/src/pages/MiNegocioPage.tsx:42` | `GET /api/v2/crm/stats` |
| `frontend/src/pages/MiNegocioPage.tsx:43` | `GET /api/v2/inventory/stats` |
| `frontend/src/pages/MiNegocioPage.tsx:44` | `GET /api/v2/invoices/stats` |
| `frontend/src/pages/FacturacionElectronicaPage.tsx:88` | `GET /api/v2/fiscal/countries` |
| `frontend/src/pages/FacturacionElectronicaPage.tsx:142` | `POST /api/v2/fiscal/issue` |

The remaining ~91 FastAPI routes are **orphan from the React frontend**. By router:

| FastAPI router (prefix) | Routes total | React-called | Orphan from React |
|---|---:|---:|---:|
| `workflows` (`/api/v2/workflows`) | 11 | 0 | 11 |
| `connectors` (`/api/v2/connectors`) | 9 | 0 | 9 |
| `tenants` (`/api/v2/tenants`) | 9 | 0 | 9 |
| `marketplace` (`/api/v2/marketplace`) | 9 | 0 | 9 |
| `auth` (`/api/v2/auth`) | 8 | 0 | 8 |
| `agents` (`/api/v2/agents`) | 11 | 0 | 11 |
| `bpmn` (`/api/v2/bpmn`) | 7 | 0 | 7 |
| `compliance` (`/api/v2/compliance`) | 12 | 0 | 12 |
| `nlu` (`/api/v2/nlu`) | 7 | 0 | 7 |
| `crm` (`/api/v2/crm`) | 9 | 1 (stats) | 8 |
| `inventory` (`/api/v2/inventory`) | 5 | 1 (stats) | 4 |
| `invoices_v2` (`/api/v2/invoices`) | 7 | 1 (stats) | 6 |
| `fiscal` (`/api/v2/fiscal`) | 5 | 2 (countries, issue) | 3 |
| **Total FastAPI v2** | **~115** | **5** | **~110** |

Most of these are deliberate "API v2 mirrors" of the Flask `/api/*` routes (the React SPA still uses the Flask versions, e.g. `/api/workflows` not `/api/v2/workflows`). The mirror surface is technically orphan from React, but the underlying services (CRM, Inventory, Invoices, Compliance, etc.) are still exercised by React via the Flask routes. **Net assessment:** these are not dead code, they are an alternative public API surface that no UI consumes.

### 2b. HAT FastAPI route (orphan from React)

| Path | File:line | React caller | Notes |
|---|---|---|---|
| `POST /api/hat/chat` | `src/hat/level1_orchestrator/api/routes.py:32` | **none** | React's `ChatPage.tsx:75` calls the Flask route `POST /api/workflows/chat` (`src/web/blueprints/nlu.py:88`), which internally calls `get_hat_router()` and delegates to HAT. The FastAPI `/api/hat/chat` is therefore a redundant duplicate of the Flask route. It is reachable from the `start_hat_server.sh` deployment topology, but no browser path reaches it. |

### 2c. Mobile FastAPI routes (orphan from React, by design)

15 routes under `/mobile/*` (`src/mobile/api.py:48-597`). **None are called by the React web app.** These are intended for native Android/iOS clients (per the module docstring). Not dead — they have a different consumer.

### 2d. Flask routes orphan from React (consumed only by the legacy Jinja UI or non-React callers)

The Flask surface has ~150 routes. ~95 are called by React; the remaining ~55 fall into three categories:

**(i) HTML page routes** (`src/web/blueprints/pages.py:13-113`) — 11 routes that serve Jinja templates (`/`, `/login`, `/dashboard`, `/chat`, `/editor`, `/workflows`, `/workflows/<id>`, `/settings`, `/dead-letter`, `/compliance`, `/airgap`, `/partners`, `/orbital`). React doesn't call these as fetch endpoints (they return HTML), but the legacy Jinja UI lives here. See §4.

**(ii) Flask `/api/*` routes called only by the legacy Jinja UI** (`src/web/static/app.js`, `src/web/static/editor.js`, `src/web/templates/*.html`):

| Flask route | Called by (legacy Jinja) | Called by React? |
|---|---|---|
| `GET /api/workflows/<id>/history` | `workflow_detail.html:151`, `workflow_list.html:167`, `app.js:413` | ❌ no |
| `GET /api/workflows/<id>/history/<exec_id>` | `workflow_detail.html:198` | ❌ no |
| `GET /api/workflows/<id>/export` | `workflow_detail.html:267`, `workflow_list.html:187`, `app.js` (not present, only the templates) | ❌ no |
| `POST /api/workflows/import` | `workflow_list.html:214` | ❌ no |
| `POST /api/workflows/<id>/execute` | (no caller found — orphan even from legacy UI) | ❌ no |

**(iii) Truly orphan Flask routes (no caller anywhere in the repo — confirmed by grep):**

| # | Flask route | File:line | Status |
|---|---|---|---|
| 1 | `POST /api/workflows/<wf_id>/execute` | `src/web/blueprints/workflows.py:148` | Not called by React, not called by Jinja UI, not called by tests. Dead. |
| 2 | `GET /api/workflows/<wf_id>/versions/<version_number>` | `src/web/blueprints/workflows.py:245` | React calls only `.../rollback` (POST), not the GET. Dead from UI. |
| 3 | `POST /api/marketplace/stats` (GET) | `src/web/blueprints/marketplace.py:150` | No caller. |
| 4 | `POST /api/queue/enqueue` | `src/web/blueprints/admin.py:174` | No caller. |
| 5 | `POST /api/queue/<item_id>/retry` | `src/web/blueprints/admin.py:195` | No caller. |
| 6 | `POST /api/queue/cleanup` | `src/web/blueprints/admin.py:205` | No caller. |
| 7 | `POST /api/dead-letter/notify/<entry_id>` | `src/web/blueprints/admin.py:144` | No caller. |
| 8 | `GET /api/admin/metrics/prometheus` | `src/web/blueprints/admin.py:287` | Not called by React (Prometheus scraper is the intended consumer — verify against `deploy/grafana/`, `helm/`). Not strictly dead, but no in-repo caller. |
| 9 | `POST /api/sync/import` | `src/web/blueprints/sync.py:99` | Not called by React `SyncCloud.tsx` (which only does export/push). Possibly consumed by a peer server in a multi-node deployment (`/api/sync/receive` is the inbound side). |
| 10 | `POST /api/sync/receive` | `src/web/blueprints/sync.py:155` | Server-to-server endpoint (peer sync). No React caller. |
| 11 | `GET /api/integrations/<name>/status` | `src/web/blueprints/integrations.py:99` | React IntegrationsPage calls `configure`, `test`, `disconnect` — but not `status`. |
| 12 | `GET /api/partners/benefits` | `src/web/blueprints/partnership.py:127` | Not called by `PartnersPage.tsx`. |
| 13 | `POST /api/partners/benefits` | `src/web/blueprints/partnership.py:145` | Not called. |
| 14 | `POST /api/partners/benefits/<benefit_id>/revoke` | `src/web/blueprints/partnership.py:170` | Not called. |
| 15-26 | `GET/POST /api/compliance/typeii/periods`, `/typeii/periods/<id>/bridge-letter`, `/typeii/periods/<id>/tests`, `/typeii/subservices`, `/typeii/subservices/<id>` (DELETE), `/controls`, `/controls/<id>/status` (PUT), `/audit`, `/report`, `/policies`, `/gdpr/consents`, `/gdpr/dsars`, `/gdpr/stats`, `/hipaa/baas`, `/hipaa/phi`, `/hipaa/stats` | `src/web/blueprints/compliance.py:16-344` | React `Compliance.tsx:51` calls **only** `/api/compliance/overview`. Everything else in this blueprint is orphan from React. |
| 27-31 | `GET /api/reports/workflows/<fmt>`, `/reports/crm/<fmt>`, `/reports/inventory/<fmt>`, `/reports/invoices/<fmt>`, `/reports/audit/<fmt>` | `src/web/blueprints/reports.py:12-84` | No React caller. The React `ReportsPage.tsx` assembles its own report from `/api/dashboard/stats` + `/api/tools/crm/leads` + etc. — it does not use the CSV/PDF download endpoints. |

**Subtotal truly-orphan Flask routes: ~35** (item 1-14 above plus 12 compliance routes plus 5 reports routes minus overlaps).

---

## Section 3 — GHOST_FRONTEND: React calls to endpoints that don't exist

In the **strict** sense (the path string doesn't match any Flask/FastAPI route), there are **zero ghost calls**. Every path the React frontend requests resolves to a real backend route.

However, there is a **deployment-wiring ghost** that is just as broken in practice:

### 3a. `/api/v2/*` calls that fail in the default deployment

The React SPA makes 5 calls to `/api/v2/*`. They map to real FastAPI routes — but only `MiNegocioPage.tsx` constructs the URL with `import.meta.env.VITE_API_URL || 'http://localhost:8000'` (a different origin). `FacturacionElectronicaPage.tsx` uses a bare relative path, which the browser resolves against the SPA's origin (Flask port 8080 in production).

| React call | URL the browser produces | Result in default docker-compose topology |
|---|---|---|
| `MiNegocioPage.tsx:42` `fetch(`${base}/api/v2/crm/stats`)` | `http://localhost:8000/api/v2/crm/stats` (or `VITE_API_URL`) | FastAPI port 8000 is **not exposed** in `docker-compose.yml` (only 8080/8081). Works only when the user runs `start_hat_server.sh` locally and accesses the SPA at `localhost:8080/app/...`. ❌ broken in docker prod |
| `MiNegocioPage.tsx:43` `fetch(`${base}/api/v2/inventory/stats`)` | same | ❌ same |
| `MiNegocioPage.tsx:44` `fetch(`${base}/api/v2/invoices/stats`)` | same | ❌ same |
| `FacturacionElectronicaPage.tsx:88` `api.get("/api/v2/fiscal/countries")` | relative `/api/v2/fiscal/countries` (same origin as SPA) | Hits Flask → Flask catch-all (`src/web/app.py:114`) returns 404 for paths starting with `api/`. ❌ broken always, including dev |
| `FacturacionElectronicaPage.tsx:142` `api.post("/api/v2/fiscal/issue", ...)` | relative `/api/v2/fiscal/issue` | ❌ same — always 404 via Flask catch-all |

**Root cause:**
- `nginx/nginx.conf:50-58` reverse-proxies all `/` to `zenic-flijo:8080` (Flask only). There is no `location /api/v2/` block routing to FastAPI port 8000.
- `Dockerfile` only `EXPOSE 8080 8081`. Port 8000 is internal-only.
- `src/web/app.py:106-119` SPA catch-all returns 404 JSON for any path starting with `api/` that isn't already matched by a Flask blueprint.
- `frontend/vite.config.ts:21-29` Vite dev proxy sends all `/api` to `localhost:5000` (i.e. Flask in `start_server.sh` dev mode), which then 404s on `/api/v2/*` for the same reason.

**This is a bug.** Either:
1. Add an nginx `location /api/v2/ { proxy_pass http://zenic-flijo:8000; }` block (production fix), and/or
2. Add a separate Vite proxy entry for `/api/v2` → `localhost:8000` (dev fix), and/or
3. Make `FacturacionElectronicaPage.tsx` use the same `${base}` pattern as `MiNegocioPage.tsx`.

### 3b. No other ghost calls

I exhaustively grepped every `fetch(`/api/...`)`, `apiFetch("/api/...")`, `api.get/post/put/delete("/api/...")`, and `` api.get(`/api/...`) `` in `frontend/src/` (see Methodology). All non-v2 paths resolve to a real Flask blueprint route.

---

## Section 4 — Legacy Flask UI (`src/web/`) Assessment

**Is `src/web/` a backup of the old frontend?** No — it is **still live and mounted in parallel** with the React SPA, in the same Flask process. There is no "old vs new" toggling: both are served simultaneously from a single `create_app()` call.

**Evidence:**

1. `src/main.py:280` calls `create_web_app()` which calls `src/web/app.py:59 create_app()`.
2. `src/web/app.py:87` calls `register_blueprints(app)` which mounts all 13 blueprints in `src/web/blueprints/__init__.py:23-41` — including `pages.bp` (the Jinja HTML page routes) and `auth.bp` (which holds `/api/system/backup`).
3. `src/web/app.py:95-119` then mounts the React SPA at `/app` and `/<path:spa_route>` (catch-all). The catch-all explicitly skips `api/`, `static/`, `metrics` — so Jinja HTML page routes like `/dashboard`, `/settings` (which are more specific literal routes registered earlier) win over the SPA catch-all.
4. The Jinja templates exist and are non-trivial: 13 templates totalling ~3000 LOC, plus `src/web/static/app.js` (458 LOC), `editor.js` (519 LOC), `orbital-visualizer.js` (199 LOC). These templates have their own `api()` JS helper and call many of the same `/api/*` Flask routes the React SPA calls (plus some extras like `/api/workflows/<id>/history` that React doesn't call).

**Routing reality:**

| Browser URL | Served by | Renders |
|---|---|---|
| `http://host:8080/` | Flask `pages.index` (`src/web/blueprints/pages.py:13`) | Redirect → `/dashboard` |
| `http://host:8080/login` | Flask `pages.login_page` | Jinja `login.html` |
| `http://host:8080/dashboard` | Flask `pages.dashboard_page` | Jinja `dashboard.html` + `app.js` |
| `http://host:8080/settings` | Flask `pages.settings_page` | Jinja `settings.html` (570 LOC, includes a "Hacer backup ahora" button at line 130 — see `src/web/templates/settings.html:130`) |
| `http://host:8080/app` | Flask `spa_serve` (`src/web/app.py:95`) | React `index.html` (built into `src/web/static/spa/`) → React Router |
| `http://host:8080/app/dashboard` | Flask `spa_serve` (catch-all under `/app/<path>`) | React `Dashboard.tsx` |
| `http://host:8080/app/settings` | Flask `spa_serve` | React `Settings.tsx` → `SettingsSystemTab.tsx` (which calls `/api/system/backup`) |

**Maintenance risk:** Two parallel UIs targeting the same backend, both shipped. The Jinja UI calls some Flask routes the React UI doesn't (e.g. `/api/workflows/<id>/history`, `/api/workflows/import`, `/api/workflows/<id>/export`). If the team deletes those "orphan-from-React" routes thinking they're dead, the Jinja UI breaks. There is **no build-time or test-time guard** preventing this. The same `/api/system/backup` endpoint is currently called by **both** UIs: `src/web/templates/settings.html:323` (Jinja) and `frontend/src/components/settings/SettingsSystemTab.tsx:34` (React).

**Build artifact status:** `src/web/static/spa/` currently contains only `favicon.svg` and `icons.svg` — `index.html` is **not present**. This means the React SPA has not been built yet (`npm run build` not run). In this state, all `/app/*` and catch-all SPA routes return `503 {"error": "SPA not built yet. Run: cd frontend && npm run build"}` (`src/web/app.py:101`). So at this moment the React SPA is **not actually being served**; only the legacy Jinja UI is. After a `npm run build`, the SPA appears and both UIs coexist.

---

## Section 5 — Orphan Backend Modules Summary

Per-module reachability from the React frontend:

| Module | React-reachable routes | React-orphan routes | Notes |
|---|---|---|---|
| `src/core/db/backup_engine.py` (BackupEngine) | `backup_now` (via Flask `/api/system/backup`) | `stop_auto_backup`, `get_backup_info` (zero callers anywhere); `restore` doesn't exist | See §1. Auto-backup starts at process boot via `src/main.py:39` and is not user-controllable. |
| `src/hat/` (HAT 5-level orchestrator + ORBITAL) | ✅ via Flask `/api/workflows/chat` (`src/web/blueprints/nlu.py:88-112`, which calls `get_hat_router()`). React caller: `ChatPage.tsx:75`. | FastAPI `/api/hat/chat` (`src/hat/level1_orchestrator/api/routes.py:32`) is **orphan from React** — it's a duplicate entry point to the same HAT router. | HAT is wired through Flask, not through its own FastAPI route. |
| `src/marketplace/` | Flask `/api/marketplace/{connectors,categories,connectors/<name>,connectors/<name>/install,connectors/<name>/uninstall}` (5 routes) | FastAPI `/api/v2/marketplace/*` (9 routes) all orphan from React. Flask `/api/marketplace/stats` is orphan from all UIs. | The FastAPI v2 marketplace router is an unused alternative API. |
| `src/nlu/` | Flask `/api/nlu/understand` + `/api/nlu/ai-generate` (2 routes). React caller: `ChatPage.tsx:94,123`. | FastAPI `/api/v2/nlu/*` (7 routes: understand, compile, dry-run, intents, entities, train, status) all orphan from React. | The React chat page doesn't expose training/intent-management UI; only chat + ai-generate. |
| `src/compliance/` | Flask `/api/compliance/overview` only (1 route). React caller: `Compliance.tsx:51`. | FastAPI `/api/v2/compliance/*` (12 routes) all orphan from React. Flask `/api/compliance/{controls,controls/<id>/status,audit,report,policies,typeii/*,gdpr/*,hipaa/*}` (~16 routes) all orphan from React. | The React Compliance page is minimal — it only shows the overview. Type II periods, GDPR consents/DSARs, HIPAA BAAs/PHI, policy approval, audit trail, evidence collection — none of these have React UI. |
| `src/partnership/` | Flask `/api/partners/{overview,tiers,activity,register,<id>/approve,<id>/promote}` (6 routes). React caller: `PartnersPage.tsx`. | Flask `/api/partners/benefits` (GET/POST) + `/api/partners/benefits/<id>/revoke` (3 routes) orphan from React. | The benefits subsystem has no React UI. |
| `src/sync/` | Flask `/api/sync/{config(GET/PUT/DELETE),key/generate,export,push,history,stats}` (8 routes). React caller: `SyncCloud.tsx`. | Flask `/api/sync/import` + `/api/sync/receive` (2 routes) — these are server-to-server (peer sync inbound); no React caller by design. | Not dead — intended for multi-node sync topology. Verify with `deploy/` if a peer receiver is actually deployed. |
| `src/mobile/` (`src/mobile/api.py`) | **0 routes** | 15 routes under `/mobile/*` | By design — these are for native Android/iOS clients, not the React web app. Not dead. |
| `src/bpmn/` (via `src/api_v2/routers/bpmn.py`) | **0 routes** | 7 routes under `/api/v2/bpmn/*` | No React page for BPMN import/export/convert/validate/processes. The BPMN router is entirely orphan from React. |
| `src/api_v2/routers/agents.py` | **0 routes** | 11 routes under `/api/v2/agents/*` | No React page for agent spawn/list/run/pause/orchestrate/token-usage. The agents router is entirely orphan from React. |
| `src/api_v2/routers/tenants.py` | **0 routes** | 9 routes under `/api/v2/tenants/*` | No React page for tenant CRUD/suspend/activate/users/features. The tenants router is entirely orphan from React. |
| `src/api_v2/routers/connectors.py` | **0 routes** | 9 routes under `/api/v2/connectors/*` | React's `IntegrationsPage.tsx` uses the Flask `/api/integrations/*` routes instead. The FastAPI connectors router is an unused alternative API. |
| `src/api_v2/routers/auth_routes.py` | **0 routes** | 8 routes under `/api/v2/auth/*` (login, logout, refresh, api-keys CRUD, mfa/enable, mfa/verify) | React uses Flask `/api/auth/{login,logout,register,status}` instead. The FastAPI auth router — including the entire API-key and MFA subsystem — is orphan from React. No React UI for API keys or MFA. |
| `src/api_v2/routers/workflows.py` | **0 routes** | 11 routes under `/api/v2/workflows/*` | React uses Flask `/api/workflows/*` instead. |

---

## Section 6 — Recommendations

### 6a. BackupEngine — fix the dead/missing methods

1. **Implement `BackupEngine.restore(backup_path)`**. The SOC 2 control A1.3 (`src/compliance/__init__.py:192`) explicitly demands restoration testing; without a restore method, the compliance dashboard cannot truthfully report this control as passing. Add:
   - A public `restore(backup_path: str | Path) → str` method on `BackupEngine`.
   - A Flask route `POST /api/system/restore` (admin-gated, like `/api/system/backup`).
   - A button + file picker in `SettingsSystemTab.tsx` to upload/select a `.db` backup and call the restore endpoint.
2. **Wire `get_backup_info()` to the UI.** The method exists, returns a clean dict (list of backups with size/date), but has no caller. Add:
   - A Flask route `GET /api/system/backups` that returns `be.get_backup_info()`.
   - A "Backup history" list in `SettingsSystemTab.tsx` showing the last 20 backups with size and date.
3. **Either wire `stop_auto_backup()` or delete it.** Currently dead code. If you want users to pause auto-backups from the UI, add `POST /api/system/backup/auto-stop` and `POST /api/system/backup/auto-start?interval=24`. If not, delete the method (and `start_auto_backup`'s public surface — make it private `_start_auto_backup`).

### 6b. Fix the `/api/v2/*` deployment-wiring ghost (BUG)

The 5 React calls to `/api/v2/*` are functionally broken in production. Pick one:

- **Option A (recommended, smallest change):** Add an nginx `location /api/v2/ { proxy_pass http://zenic-flijo:8000; }` block to `nginx/nginx.conf` (between the `location /` and `location /ws` blocks). Also expose port 8000 in `docker-compose.yml` (or keep it internal and let nginx reach it via the internal network). Add a matching Vite proxy entry: `'/api/v2': { target: 'http://localhost:8000', changeOrigin: true }`.
- **Option B:** Migrate `MiNegocioPage.tsx` and `FacturacionElectronicaPage.tsx` to use the Flask `/api/*` equivalents (e.g. `/api/dashboard/stats` for the negocio stats; move fiscal issue to a Flask `/api/tools/fiscal/issue` mirror). This avoids the second port entirely.
- **Option C (highest consistency):** Migrate the entire React frontend from Flask `/api/*` to FastAPI `/api/v2/*` (this is the implicit long-term plan, see `MIGRATION_MAP.md`). Out of scope for this audit.

Also: `FacturacionElectronicaPage.tsx` should use `VITE_API_URL` like `MiNegocioPage.tsx` does, even if Option A is chosen, so the calls work in pure-Flask dev (no FastAPI running).

### 6c. Decide what to do with the legacy Flask Jinja UI

Two UIs shipping in parallel is a maintenance hazard. Options:

- **Option A (recommended):** Delete the legacy Jinja UI. Remove `src/web/templates/*.html`, `src/web/static/app.js` + `editor.js` + `orbital-visualizer.js` + `chart.umd.min.js`, and the `pages.py` blueprint. Keep only the React SPA at `/app/*` and the `/<path:spa_route>` catch-all. Before doing this, audit which `/api/*` routes are *only* called by the Jinja UI (`/api/workflows/<id>/history`, `/api/workflows/import`, `/api/workflows/<id>/export`) and either wire them into React or delete them too.
- **Option B:** Keep both but add a guard. Add a build-time test that asserts every `/api/*` Flask route has either a React caller OR a Jinja caller (a "route ownership" test). This prevents silently breaking one UI when refactoring the other.

### 6d. Decide what to do with the FastAPI v2 surface

~110 FastAPI v2 routes are orphan from React. Three sub-decisions:

1. **Tenants, BPMN, Agents routers (27 routes total, 0 React callers):** No React page exists for these features. Either build the React pages or accept that these are public-API-only (for external integrators). Document this explicitly in `ARCHITECTURE.md` so future devs don't think they're dead.
2. **Mirror routers (workflows, connectors, marketplace, nlu, auth, crm, inventory, invoices, compliance — ~80 routes):** These duplicate Flask `/api/*` routes that React actually uses. The React frontend should eventually migrate (Option C above). Until then, add a deprecation header on the Flask routes: `X-Migrate-To: /api/v2/workflows`.
3. **MFA + API keys (`/api/v2/auth/mfa/*`, `/api/v2/auth/api-keys` — 5 routes):** No React UI. Either build a Settings tab for MFA/API-key management (it's a common enterprise requirement) or document as API-only.

### 6e. Truly orphan Flask routes — delete or wire

The ~35 routes in §2d(iii) have no caller anywhere. Highest-priority candidates for deletion (or wiring, depending on intent):

- `POST /api/workflows/<wf_id>/execute` — React uses `/retry` instead. Delete unless you want a "run now" button distinct from "retry last execution".
- `GET /api/workflows/<wf_id>/versions/<version_number>` — React only calls the rollback POST. Delete the GET, or add a "view version diff" feature.
- `GET /api/marketplace/stats` — no caller. Delete or wire into `Plugins.tsx`.
- `POST /api/queue/enqueue`, `POST /api/queue/<item_id>/retry`, `POST /api/queue/cleanup` — admin queue management. Wire into `QueueTab.tsx` (which currently only shows status/workers) or delete.
- `POST /api/dead-letter/notify/<entry_id>` — no caller. Delete or wire into `DeadLetterTab.tsx` as a "notify" action.
- `/api/compliance/typeii/*`, `/api/compliance/gdpr/*`, `/api/compliance/hipaa/*` — 16 routes for SOC 2 Type II periods/bridge letters/subservices, GDPR consents/DSARs, HIPAA BAAs/PHI. None have React UI. Either build a Compliance Pro tab or delete (but they may be needed for the SOC 2 audit story — confirm with the compliance owner before deleting).
- `/api/reports/<entity>/<fmt>` (5 routes, CSV/PDF download) — no React caller. The React `ReportsPage.tsx` builds its own report. Either delete or wire a "Download CSV" button.

### 6f. Backup-specific summary

The user's literal question — *"is all the backup connected to the frontend?"* — answer:

- ✅ **Manual backup** (`backup_now`) is connected: `SettingsSystemTab.tsx` → `POST /api/system/backup` → `BackupEngine.backup_now()`.
- ⚠️ **Auto backup** (`start_auto_backup`) is connected only at process startup (`src/main.py:39`); there is no UI to start/stop it or change the interval.
- ❌ **Stop auto backup** (`stop_auto_backup`) is dead code.
- ❌ **Backup info / history** (`get_backup_info`) is dead code — no UI lists existing backups.
- ❌ **Restore** does not exist — neither the method, the route, nor the UI. Compliance control A1.3 cannot be satisfied.

So: **not all of the backup is connected to the frontend.** Two of the four public methods are dead code, and the most important missing piece (restore) is required by the compliance framework the project advertises.

---

## Methodology & Honest Notes

**What I did:**

1. Read `src/core/db/backup_engine.py` end-to-end and enumerated every method.
2. `rg --no-follow 'BackupEngine|backup_engine' src/` — found 5 backend usage sites (`main.py`, `compliance/__init__.py` string-only, `core/db/__init__.py` re-export, `web/blueprints/auth.py`, and the class definition itself).
3. `rg --no-follow 'backup' src/api_v2/` and `src/web/` — found the Flask `/api/system/backup` route. No FastAPI v2 backup route exists.
4. `rg --no-follow 'backup' frontend/src/` — found the single React caller (`SettingsSystemTab.tsx`).
5. `rg --no-follow '@bp\.route|@app\.route' src/web/` — extracted all 162 Flask route declarations.
6. `rg --no-follow '@router\.(get|post|put|delete|patch)' src/api_v2/routers/` — extracted all 116 FastAPI route declarations.
7. `rg --no-follow 'APIRouter\(' src/api_v2/routers/` — extracted all 13 router prefixes.
8. `rg --no-follow 'api\.(get|post|put|patch|delete)\(' frontend/src/` and `rg --no-follow 'apiFetch|fetch\(' frontend/src/` — extracted every API call site in the React frontend (TS/TSX).
9. Manually cross-referenced every React-called path against the Flask + FastAPI route lists.
10. Confirmed the deployment topology by reading `src/main.py`, `src/web/app.py`, `nginx/nginx.conf`, `docker-compose.yml`, `Dockerfile`, `start_server.sh`, `start_hat_server.sh`, `frontend/vite.config.ts`.
11. Confirmed the legacy Jinja UI is alive by reading `src/web/blueprints/pages.py`, listing `src/web/templates/`, and grepping `src/web/static/app.js` + `src/web/templates/*.html` for `api('/api/...')` calls.

**What I could not determine (honest notes):**

- **Whether `BackupEngine` is *configured* correctly at runtime.** I confirmed `start_auto_backup(interval_hours=24)` is called once at process startup (`src/main.py:39`), but I did not run the system to verify that the `threading.Timer` actually fires every 24h and produces `.db` files in `DATA_DIR/backups/`. The cleanup logic (`_cleanup_old_backups` keeps only 10) is also unverified at runtime.
- **Whether `dest_path=None` in `backup_now()` actually resolves to a writable directory in production.** It depends on `DATA_DIR` from `src/core/config`, which I did not trace to a concrete path.
- **Whether `/api/admin/metrics/prometheus` is scraped by an actual Prometheus instance.** I confirmed no in-repo caller, but the scrape config could live in `deploy/grafana/` or external k8s manifests. The `/metrics` unauthenticated endpoint (`src/web/app.py:128-151`) is likely the one Prometheus actually scrapes; the `/api/admin/metrics/prometheus` authenticated variant may be for internal dashboards only.
- **Whether `/api/sync/receive` is hit by a peer Zenic-Flujo node in a multi-instance deployment.** The route exists for server-to-server sync; whether such a topology is actually deployed is outside this audit.
- **Whether the FastAPI v2 routes are exercised by external API clients (third-party integrators, SDK users).** The "orphan from React" label is strictly about the in-repo React frontend; an external consumer could still hit `/api/v2/workflows` etc. via API key. The `WFD_API_V2_CORS_ORIGINS` env var suggests external browser clients are anticipated.
- **Whether the React SPA build artifact (`src/web/static/spa/index.html`) is intentionally absent** (i.e. the team never runs `npm run build` in this snapshot) or accidentally absent. Either way, until it's built, only the Jinja UI is actually served.
- I did not run any tests; I did not start the server. All findings are from static analysis (Read + Grep). I did not execute the test suite under `src/tests/` to confirm whether `stop_auto_backup`/`get_backup_info` are exercised by tests — I did grep them and found zero hits in `src/tests/`, but `src/tests/` is a large tree I did not exhaustively read.
- The `rg` failures on `src/core/core`, `src/orbital/orbital`, `src/events/events` are **broken symlinks** pointing to `/home/z/my-project/repos/Zenic-Flujo/src/{core,orbital,events}` which does not exist. These are pre-existing repo corruption, unrelated to the audit. I worked around them with `rg --no-follow`.

---

*End of report — `zenic-1b`.*
