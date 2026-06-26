# Zenic-Flujo Frontend — Deep Code Review Report

**Task ID:** zenic-1a
**Agent:** Frontend Developer (agency-agents, engineering division)
**Scope:** `frontend/src/` — React 19 + Vite 8 + TypeScript 6 + Tailwind 4 + Radix UI + xyflow v12 + recharts v3
**Method:** Static review of all 22 pages, 40+ components, 4 hooks, 3 contexts. Read every file. Cross-referenced against sandbox results (ESLint 4/1, TS 12 errors, 1.34 MB bundle) and zenic-1b connectivity audit.
**Honesty note:** This is a static review — no tests run, no browser session. All `file:line` references were verified by reading the actual file. Where I inferred runtime behavior (e.g., "clicking works despite type error"), I traced the code paths explicitly.

---

## Executive Summary

| Severity | Count | Examples |
|----------|-------|----------|
| **Critical (P0)** | 4 | MiNegocioPage auth mismatch; FacturacionElectronicaPage /api/v2 broken in prod; OrbitalVisualizer type drift (TOR/COD never render); FacturacionElectronicaPage `headers` type error |
| **High (P1)** | 7 | useApi onClick pattern (11 instances); ThemeContext not memoized; charts read DOM during render; SettingsSystemTab/SmtpTab no AbortController; setTimeout leaks in Dashboard; `navigate()` during render in LoginPage |
| **Medium (P2)** | 4 | i18n abandoned (21/22 pages hardcoded Spanish); icon-only buttons without aria-label (8+); 1.34 MB bundle / no code splitting; ESLint 4 errors |
| **Low (P3)** | 3 | `key={i}` array-index keys (TorMatrix, TickHistoryCard); Toolbox `setTimeout(removeChild, 0)` fragile; `confirm()` for destructive actions |

### Top 5 issues to fix first

1. **P0 — OrbitalVisualizer type drift** (`components/orbital/OrbitalVisualizer.tsx:43-57`): declares its own `OrbitalStatus` with `tor_results` and `cod` as object, but the canonical `types/orbital.ts:44-54` uses `tor: TorEntry[]` and `cod: CodResult[]`. The visualizer never renders TOR lines or actual COD state — the showcase feature is silently broken.
2. **P0 — MiNegocioPage broken in production** (`pages/MiNegocioPage.tsx:37-44`): reads `localStorage.getItem('token')` (always null — app uses cookie auth) and hardcodes `VITE_API_URL || 'http://localhost:8000'`. All 3 `/api/v2/*` calls fail; page silently shows zeros.
3. **P0 — FacturacionElectronicaPage wiring bug** (`pages/FacturacionElectronicaPage.tsx:88,142`): calls `/api/v2/fiscal/countries` and `/api/v2/fiscal/issue` — NOT proxied by nginx in production (confirmed by zenic-1b). Also line 142 passes `{ headers }` to `api.post` whose options type is `{ signal?: AbortSignal }` → TS error.
4. **P1 — useApi onClick pattern** (11 instances across 10 files): loaders typed `(signal?: AbortSignal) => Promise<void>` are passed directly to `onClick`, which gives them a `MouseEvent`. **Type error only** — runtime works because `MouseEvent` has no `aborted` property and the optional chain `signal?.aborted` is `undefined` (falsy). Fix with `onClick={() => loadData()}` wrappers or by relaxing the loader signature.
5. **P2 — Bundle is 1.34 MB / 377 KB gzip, zero code splitting**: no `React.lazy`, no `Suspense`, no dynamic imports anywhere. Route-based splitting alone (22 pages) would cut initial load by ~60-70%.

---

## Section 1: Confirmed sandbox findings

### 1.1 ESLint (4 errors, 1 warning) — VERIFIED

| File:Line | Rule | Status |
|-----------|------|--------|
| `src/hooks/useApi.ts:114` | `preserve-caught-error` | ✅ Verified. `throw new Error(errMsg)` does not include `cause`. |
| `src/hooks/useApi.ts:124` | `preserve-caught-error` | ✅ Verified. Same as above. |
| `src/i18n.ts:51` | unused eslint-disable | ✅ Verified. Line 51 has `// eslint-disable-next-line no-console` but the next line (`return key;`) is not a console call. |
| `src/pages/FacturacionElectronicaPage.tsx:25` | unused `FiscalCountry` type | ✅ Verified. Interface declared at lines 25-30 but never referenced — the page uses inline casts instead. |
| `src/pages/FacturacionElectronicaPage.tsx:103` | `react-hooks/set-state-in-effect` | ✅ Verified. `useEffect(() => { loadCountries() }, [loadData])` — `loadCountries` calls `setSupportedCountries/setAvailableCountries/setLoading` (lines 93-98). No eslint-disable comment. |

### 1.2 TypeScript (12 errors) — VERIFIED and characterized

**Pattern A: useApi loader passed to onClick (11 of 12 errors)**

Loaders are typed `useCallback(async (signal?: AbortSignal) => Promise<void>, [...])` and assigned directly to `onClick`:

| File:Line (onClick) | Loader definition |
|---|---|
| `src/components/admin/DeadLetterTab.tsx:193` | `loadData` at line 35: `async (signal?: AbortSignal) =>` |
| `src/pages/AirgapPage.tsx:210` | `loadData` at line 102: `async (signal?: AbortSignal) =>` |
| `src/pages/AirgapPage.tsx:261` | (same `loadData`) |
| `src/pages/CrmPage.tsx:263` | `loadLeads` at line 87: `async (signal?: AbortSignal) =>` |
| `src/pages/IntegrationsPage.tsx:216` | `loadData` at line 74: `async (signal?: AbortSignal) =>` |
| `src/pages/InventoryPage.tsx:280` | `loadProducts` at line 60: `async (signal?: AbortSignal) =>` |
| `src/pages/InvoicesPage.tsx:290` | `loadInvoices` at line 70: `async (signal?: AbortSignal) =>` |
| `src/pages/OrbitalPage.tsx:160` | `loadStatus` at line 60: `async (signal?: AbortSignal) =>` |
| `src/pages/OrbitalPage.tsx:211` | (same `loadStatus`) |
| `src/pages/Plugins.tsx:189` | `loadData` at line 92: `async (signal?: AbortSignal) =>` |
| `src/pages/ReportsPage.tsx:231` | `loadData` at line 115: `async (signal?: AbortSignal) =>` |

**Runtime behavior**: ✅ clicking the button DOES work. React passes the `MouseEvent` as the first argument; it lands in `signal`. Inside the loader, every guard is `signal?.aborted` — `MouseEvent` has no `aborted` property so this evaluates to `undefined` (falsy). The fetch proceeds normally without an AbortSignal. **The bug is a TypeScript type error, not a runtime failure.** The page refetches on click as intended; the only consequence is that click-triggered fetches cannot be aborted (which doesn't matter — they're triggered by user action, not by a cleanup path).

**Not in the sandbox list but worth noting**: `src/components/admin/AlertsTab.tsx:136` and `src/pages/FacturacionElectronicaPage.tsx:191` also pass `loadAll`/`loadCountries` to onClick, but those loaders are typed `async () => {...}` (no args). TypeScript's bivariance for function parameters allows assigning a 0-arg function to a slot expecting `(event) => void`, so no TS error. Functionally equivalent pattern.

**Pattern B: FacturacionElectronicaPage headers (1 of 12 errors)**

`src/pages/FacturacionElectronicaPage.tsx:142`:
```ts
const data = (await api.post("/api/v2/fiscal/issue", payload, { headers })) as FiscalResponse
```
`api.post`'s third argument is typed `{ signal?: AbortSignal }` (see `hooks/useApi.ts:133`). Passing `{ headers }` is a type error and **also a runtime bug**: the `headers` object is silently dropped, so the `X-License-Key` header is never sent. The license check on the backend will fail or fall back to default tier.

### 1.3 Bundle size — VERIFIED

- `vite.config.ts:14-18`: no `manualChunks`, no `rollupOptions`. `build.sourcemap: true` (adds .map files but not to the bundle).
- Grep for `lazy\(|Suspense|React\.lazy` → **0 matches**. Zero code splitting.
- Heaviest deps (from `package.json`):
  - `@xyflow/react ^12.11.0` (~250 KB min) — only used in `/app/editor`
  - `recharts ^3.8.1` (~200 KB min) — used in Dashboard + ReportsPage only
  - 14 `@radix-ui/react-*` packages (~30-60 KB total, tree-shaken)
  - `lucide-react ^1.17.0` (~5 KB per icon × ~50 icons used ≈ 50 KB)
  - `react 19 + react-dom 19` (~140 KB min)
- Total reported by sandbox: **1.34 MB raw / 377 KB gzip** — consistent with no splitting.
- **Recommended initial split**: lazy-load `Editor` (xyflow), `ReportsPage` + `Dashboard` (recharts), `OrbitalPage` (canvas + orbital subcomponents), `AdminPage` (5 sub-tabs). Estimated 60-70% reduction in initial bundle.

---

## Section 2: useApi pattern deep-dive

### Root cause

`useApi.ts` exports a `getApi()` factory that returns an object with `get/post/put/patch/delete` methods, all accepting an optional `{ signal?: AbortSignal }` as the LAST argument. This was added in "BUG-2-FE" (per the code comment at `useApi.ts:62-65`) to allow `useEffect` cleanup to abort in-flight requests.

Page authors then wrote loaders as `useCallback(async (signal?: AbortSignal) => { ... }, [deps])` so the SAME loader can be called from:
1. The `useEffect` body with `loadData(ac.signal)` (correct — passes AbortSignal).
2. The `onClick` of a "Recargar" button as `onClick={loadData}` (type error — passes MouseEvent).

### Why the type error doesn't surface as a runtime bug

```ts
// useApi.ts:131
get: <T = unknown>(path: string, options?: { signal?: AbortSignal }) =>
  request<T>("GET", path, undefined, options),
```
Inside `request` (line 83): `signal: options?.signal`. When called via onClick, `options` is a `MouseEvent`. `options?.signal` is `undefined` (MouseEvent has no `.signal`). The fetch is made without a signal — fine.

Inside the loader body, the guards `if (signal?.aborted) return` (e.g., `CrmPage.tsx:92`) evaluate `MouseEvent?.aborted` → `undefined` → falsy. The loader proceeds normally. ✅ Works.

The only real loss: clicking "Recargar" 5 times rapidly fires 5 concurrent fetches with no abort. Mild perf/race concern, not a correctness bug.

### Fix options (pick one)

**Option A — Wrapper at the call site (minimal, preserves the abort pattern):**
```tsx
<Button onClick={() => loadData()} ...>Recargar</Button>
```
Fixes all 11 instances with one-line changes each. Loaders keep their abort capability.

**Option B — Relax the loader signature:**
```ts
const loadData = useCallback(async (signal?: AbortSignal | unknown) => {
  const ac = signal instanceof AbortSignal ? signal : undefined
  ...
}, [deps])
```
Type-compatible with both `loadData(ac.signal)` and `onClick={loadData}`. Less safe (loses type-checking on signal usage).

**Recommendation**: Option A. It's the standard pattern, costs nothing, and keeps the abort capability intact for effect-driven calls.

### The 11 affected call sites (all listed in Section 1.2)

---

## Section 3: React bugs

### 3.1 Rules of Hooks violations
**No issues found in this category.** All hooks are called at the top level of components/custom hooks. No conditional hooks, no hooks in loops. Verified across all 22 pages and 40+ components.

### 3.2 Missing useEffect cleanup / AbortController

| File:Line | Issue | Severity |
|---|---|---|
| `src/components/settings/SettingsSystemTab.tsx:21-30` | `useEffect` calls `apiFetch` (which returns a Promise) with no AbortController. If user navigates away from Settings while fetch is in flight, `setStatus/setLogs/setLoading` fire on unmounted component. | Medium |
| `src/components/settings/SettingsSmtpTab.tsx:28-33` | Same pattern — `apiFetch("/api/settings").then(...)` with no abort. | Medium |
| `src/pages/MiNegocioPage.tsx:34-64` | `useEffect` with 3 concurrent `fetch()` calls and no AbortController. `setStats/setLoading` fire on unmounted component if user navigates away. | Medium |
| `src/components/settings/SettingsApiKeyTab.tsx:18-23` | Same pattern. | Low (single fetch) |
| `src/pages/Dashboard.tsx:120, 133` | `setTimeout(() => loadData(), 500)` inside SSE event handlers — not cleared in cleanup. If component unmounts within 500ms of an SSE event, `loadData()` fires; `cancelledRef.current` is true so it returns early (line 71), but the timer itself leaks. | Low (mitigated) |
| `src/pages/Deployments.tsx:82` | `setTimeout(() => setCopiedId(null), 2000)` — leaks if unmounted within 2s. | Low |
| `src/components/settings/SettingsApiKeyTab.tsx:48` | `setTimeout(() => setCopied(false), 2000)` — leaks if unmounted within 2s. | Low |

**Properly cleaned up (verified ✓):** `useSSE.ts:112-120` (EventSource.close + reconnectRef.clear), `useApi.ts` AbortController pattern in `DeadLetterTab/QueueTab/UsersTab/CrmPage/InventoryPage/InvoicesPage/OrbitalPage/AirgapPage/IntegrationsPage/Plugins/ReportsPage`, `OrbitalVisualizer.tsx:120` (clearInterval), `MetricsTab.tsx:52` (clearInterval), `LiveExecutionFeed.tsx:34` (removeEventListener), `AnimatedCounter.tsx:53-57` (cancelAnimationFrame).

### 3.3 Missing `key` props in `.map()` renders

| File:Line | Issue |
|---|---|
| `src/components/orbital/TorMatrix.tsx:24` | `key={i}` — array index. Acceptable here because the list is read-only and never reordered, but not best practice. |
| `src/components/orbital/TickHistoryCard.tsx:25` | `key={i}` — array index. History is reversed then mapped; `h.tick` would be a better key. |
| `src/pages/Compliance.tsx:324-325` | `key={i}` for recommendations list. OK because list is static from server. |

**All other `.map()` renders use stable IDs** (verified: `entry.id`, `wf.id`, `lead.id`, `connector.name`, `version.id`, `promo.id`, `alert.id`, `rule.name`, `user.id`, `item.label`, `card.title`, `code` (country), `section.id`, `envName`, `cat.name`, etc.).

### 3.4 Stale closures in event handlers
**No issues found in this category.** All async handlers use `getApi()` to obtain a fresh API client (which itself is wrapped in `useCallback([])` with no deps because it only uses `setLoading/setError` which are stable). Loaders correctly declare deps: e.g., `CrmPage.tsx:107` `[getApi, stageFilter]`, `DeadLetterTab.tsx:52` `[getApi, filter]`. No stale closures detected.

### 3.5 Race conditions in async data fetching
**All major data-fetching pages use the AbortController pattern correctly**: `useEffect(() => { const ac = new AbortController(); loadData(ac.signal); return () => ac.abort() }, [loadData])`. This is the correct race-free pattern — if `loadData` changes (because a dep like `filter` changes), the previous request is aborted.

**One exception**: `src/pages/Workflows.tsx:48-53` uses a `cancelledRef` pattern instead of AbortController:
```ts
useEffect(() => {
  cancelledRef.current = false
  load()
  return () => { cancelledRef.current = true }
}, [])
```
The empty dep array `[]` means this effect runs ONCE on mount. The `load` function is not in deps, so if it closes over stale state, that's a bug — but `load` only uses `apiFetch` (module-level) and `setWorkflows` (stable), so no stale closure. The `cancelledRef` correctly guards `setWorkflows` after unmount. No race condition, but no abort either — the in-flight request is wasted if the user navigates away. **Low severity.**

### 3.6 Memory leaks (intervals/timeouts without cleanup)

Already covered in Section 3.2. The two `setInterval` instances (`OrbitalVisualizer.tsx:116`, `MetricsTab.tsx:51`) are both properly cleaned up with `clearInterval` in the effect return. The `setTimeout` instances in `Dashboard.tsx`, `Deployments.tsx`, `SettingsApiKeyTab.tsx`, `Toolbox.tsx` are not cleaned up but are short-lived (500ms-2000ms) and the state-setter calls they make are either guarded by `cancelledRef` (Dashboard) or harmless (Deployments/SettingsApiKeyTab just toggle a "copied" flag).

---

## Section 4: Routing

### 4.1 Route inventory — all 22 routes verified

`src/App.tsx:47-85`:

| Path | Element | File exists? | Notes |
|---|---|---|---|
| `/login` | `<LoginPage />` | ✅ | Public route. |
| `/app` | `<ProtectedRoute><AppLayout /></ProtectedRoute>` | ✅ | Index redirects to `/app/dashboard`. |
| `/app/dashboard` | `<Dashboard />` | ✅ | |
| `/app/editor` | `<Editor />` | ✅ | |
| `/app/workflows` | `<Workflows />` | ✅ | |
| `/app/plugins` | `<Plugins />` | ✅ | |
| `/app/compliance` | `<Compliance />` | ✅ | |
| `/app/sync` | `<SyncCloud />` | ✅ | |
| `/app/deploy` | `<Deployments />` | ✅ | |
| `/app/chat` | `<ChatPage />` | ✅ | |
| `/app/admin` | `<AdminPage />` | ✅ | |
| `/app/integrations` | `<IntegrationsPage />` | ✅ | |
| `/app/crm` | `<CrmPage />` | ✅ | |
| `/app/inventory` | `<InventoryPage />` | ✅ | |
| `/app/invoices` | `<InvoicesPage />` | ✅ | |
| `/app/reports` | `<ReportsPage />` | ✅ | |
| `/app/orbital` | `<OrbitalPage />` | ✅ | |
| `/app/partners` | `<PartnersPage />` | ✅ | |
| `/app/airgap` | `<AirgapPage />` | ✅ | |
| `/app/mi-negocio` | `<MiNegocioPage />` | ✅ | **Broken in prod — see Section 5.** |
| `/app/facturacion-electronica` | `<FacturacionElectronicaPage />` | ✅ | **Broken in prod — see zenic-1b.** |
| `/app/settings` | `<Settings />` | ✅ | |
| `*` | `<NotFoundPage />` | ✅ | 404 fallback. |

**All 22 page imports resolve. No orphan routes. No missing pages.**

### 4.2 ProtectedRoute logic

`src/components/ProtectedRoute.tsx:11-57`:
- Reads `authenticated, loading, user` from `useAuth()`.
- While `loading === true`: shows a spinner. ✅
- When `loading === false && !authenticated`: `useEffect` calls `navigate("/login?redirect=...", { replace: true })`. ✅
- When `authenticated && requiredRole` set: checks role hierarchy `admin=3, editor=2, viewer=1`. If `userLevel < requiredLevel`, redirects to `/app/dashboard`. ✅
- **Returns `null` while unauthenticated** (line 54) — the redirect is via useEffect, so there's a brief moment where children are not rendered. ✅ No auth bypass.

**Auth bypass check**: ✅ No bypass found. The `if (!authenticated) return null` at line 54 ensures children never render without auth. The only way to reach `<AppLayout />` is via `<ProtectedRoute>` which always gates on `authenticated`.

**Role check gap**: `requiredRole` is never passed by `App.tsx` — line 52-58 of App.tsx uses `<ProtectedRoute>` without `requiredRole`. So **all protected routes are accessible to all authenticated users regardless of role**. The `AdminPage` is not protected by `requiredRole="admin"` — any `viewer` can see it. **Medium severity** — the role-check code exists but is unused.

### 4.3 Lazy loading
**None.** All 22 pages are statically imported at the top of `App.tsx:7-28`. Zero `React.lazy()`, zero `Suspense`, zero dynamic `import()`. The 1.34 MB bundle is the direct consequence.

### 4.4 404 handling
`src/App.tsx:84`: `<Route path="*" element={<NotFoundPage />} />`. ✅ Catches all unmatched routes including non-`/app` paths. `NotFoundPage` has a "Volver atrás" button (`window.history.back()`) and a "Ir al inicio" link to `/app/dashboard`. ✅

---

## Section 5: Auth

### 5.1 Token storage

`src/contexts/AuthContext.tsx`:
- Login: `fetch("/api/auth/login", { credentials: "include" })` — **cookie-based auth, no token in JS**. ✅ Good — httpOnly cookies are not XSS-readable.
- All subsequent requests use `credentials: "include"` (see `useApi.ts:21, 81, 154`). ✅
- `checkAuth` calls `/api/auth/status` to verify session on mount. ✅

**Exception — `src/pages/MiNegocioPage.tsx:37-38`**:
```ts
const token = localStorage.getItem('token')
const headers = { Authorization: `Bearer ${token}` }
```
This is the ONLY place in the codebase that reads a token from localStorage. The key `'token'` is never set anywhere — `AuthContext` doesn't store a token. So `token` is always `null`, and the header becomes `Authorization: Bearer null`. The 3 `/api/v2/*` calls (lines 42-44) are sent to FastAPI v2 with an invalid Bearer header.

**This is a fundamental auth pattern mismatch**: the rest of the app uses cookie auth, but MiNegocioPage was written assuming JWT-in-localStorage. The page is broken in two independent ways:
1. Auth header is always `Bearer null` (cookie not sent because `credentials: "include"` is missing from these `fetch` calls too — line 42-44 has no `credentials` option, so cookies are NOT sent).
2. The target URLs `/api/v2/*` are not proxied by nginx (zenic-1b finding).

**Severity**: P0 — page silently fails, shows all-zeros, no error to user.

### 5.2 Token refresh logic
**Not implemented.** The app uses session cookies; when they expire, the next API call returns 401, and `useApi.ts:24-28` / `85-89` redirects to `/login?expired=1`. There's no proactive refresh. ✅ Acceptable for cookie auth, but means users lose work mid-session without warning.

### 5.3 Logout cleanup

`src/contexts/AuthContext.tsx:184-194`:
```ts
const logout = useCallback(async () => {
  try { await fetch("/api/auth/logout", { method: "POST", credentials: "include" }) } catch {}
  setState({ user: null, authenticated: false, loading: false })
}, [])
```
✅ Clears `user`, `authenticated`, `loading`. Server-side session cookie is invalidated by the POST. The `useMemo` value (line 196-199) recomputes because `state` changed, so all consumers re-render.

**Gap**: `useSSE` EventSource connections are NOT closed on logout. If the Dashboard is mounted and the user clicks "Cerrar sesión" in AppLayout, the EventSource to `/api/events/stream` stays open until the Dashboard unmounts (which happens when the route changes to `/login`). In practice this is fine because logout navigates to `/login` which unmounts everything. **Low severity.**

### 5.4 Race conditions on initial load

`src/contexts/AuthContext.tsx:102-107`:
```ts
useEffect(() => {
  const ac = new AbortController()
  checkAuth(ac.signal)
  return () => ac.abort()
}, [checkAuth])
```
✅ Correct. If `checkAuth` changes (it won't — it's `useCallback([])`), the previous request is aborted. The `checkInProgress` ref (line 22, 69-70) prevents double-calls if StrictMode double-invokes the effect. ✅

`checkAuth` itself checks `signal?.aborted` at 3 points (lines 73, 79, 94) before calling `setState`. ✅ No setState-on-aborted-signal race.

**One concern**: `loading` starts as `true` (line 20). If `checkAuth` is aborted before any setState, `loading` stays `true` forever and `ProtectedRoute` shows a spinner forever. However, the abort only happens on unmount, which means the user navigated away — the spinner is never seen. ✅ Not a real bug.

---

## Section 6: i18n

### 6.1 Usage audit

**Grep for `useTranslation` → 1 match: `src/pages/MiNegocioPage.tsx`.**

Of the 22 pages, **only MiNegocioPage uses `react-i18next`**. The other 21 pages (Dashboard, Workflows, Editor, Settings, AdminPage, CrmPage, InventoryPage, InvoicesPage, ReportsPage, OrbitalPage, PartnersPage, AirgapPage, FacturacionElectronicaPage, ChatPage, IntegrationsPage, Plugins, Compliance, SyncCloud, Deployments, LoginPage, NotFoundPage) use **hardcoded Spanish strings**.

Examples of hardcoded Spanish that should be i18n keys:
- `Dashboard.tsx:205`: `<h1>Dashboard</h1>`
- `CrmPage.tsx:217`: `<h1>Mis Clientes</h1>`
- `InventoryPage.tsx:206`: `<h1>Inventario</h1>`
- `OrbitalPage.tsx:200`: `<h1>Monitor ORBITAL</h1>`
- `Plugins.tsx:181`: `<h1>Plugins</h1>`
- `AppLayout.tsx:44-61`: All 18 nav item labels are hardcoded Spanish ("Panel", "Editor", "Workflows", "CRM", etc.)
- Toast messages: `DeadLetterTab.tsx:48` "Error al cargar buzón", `CrmPage.tsx:103` "Error al cargar leads", etc. (~50+ hardcoded toast strings)
- Form labels: `CrmPage.tsx:407` "Nombre", `CrmPage.tsx:418` "Correo electrónico", etc.

**i18n is effectively abandoned** despite the infrastructure (`i18n.ts`, 3 locale files, `changeLanguage()` helper, `parseMissingKeyHandler` dev warning) being in place. The `i18n.ts:8` comment even says "BUG-31 (frontend-bugs.md): 'No i18n en frontend' — resuelto por este archivo" — but the bug is only partially resolved (infrastructure added, strings not migrated).

### 6.2 Locale key completeness

| Locale | Keys | Status |
|---|---|---|
| `src/locales/es.json` | 228 | Baseline (default language) |
| `src/locales/en.json` | 203 | **Missing 25 keys** |
| `src/locales/pt_br.json` | 203 | **Missing 25 keys** (same as en) |

**Missing from `en.json` and `pt_br.json`** (vs `es.json`):
- 21 `fiscal.*` keys: `fiscal.title`, `fiscal.dispatch_success`, `fiscal.dispatch_error`, `fiscal.license_denied`, `fiscal.country_not_supported`, `fiscal.connector_unavailable`, `fiscal.creds_missing`, `fiscal.connect_failed`, `fiscal.issue_success`, `fiscal.cancel_success`, `fiscal.verify_success`, `fiscal.pdf_success`, `fiscal.pdf_unavailable`, `fiscal.tracking_id_label`, `fiscal.country_ar/mx/br/cl/co/pe/ec` (7 keys)
- 4 `mi_negocio.*` keys: `mi_negocio.title`, `mi_negocio.dashboard`, `mi_negocio.pipeline`, `mi_negocio.stock_critical`

**Note**: The 4 `mi_negocio.*` keys appear to be DEAD code — `MiNegocioPage` uses `minegocio.*` (underscore vs no underscore), not `mi_negocio.*`. And the 21 `fiscal.*` keys are also dead code — `FacturacionElectronicaPage` uses hardcoded Spanish strings ("Facturación Electrónica LATAM", "Comprobante emitido en...") not `t('fiscal.title')`.

**So the actual user-facing impact of the missing 25 keys is zero** — they're dead keys in `es.json` that should either be removed or the corresponding pages should be migrated to use them.

### 6.3 `parseMissingKeyHandler` behavior

`src/i18n.ts:48-55`: in dev mode, missing keys log a `console.warn` and return the key itself. In production, missing keys silently return the key string (e.g., `minegocio.title` would render as the literal text "minegocio.title"). Since only MiNegocioPage uses `t()` and all its keys exist in all 3 locales, no production breakage. ✅

---

## Section 7: Accessibility (WCAG 2.1 AA)

### 7.1 Form inputs without associated Label

**LoginPage** (`src/pages/LoginPage.tsx`): ✅ All inputs use `<Label htmlFor="...">` + `<Input id="...">` (lines 159-180, 184-202, 237-252, 256-269, 273-290, 293-316, 319-333). Excellent.

**SettingsSmtpTab** (`src/components/settings/SettingsSmtpTab.tsx`): ✅ All inputs use `<Label htmlFor>` + `<Input id>` (lines 98-104, 109-115, 118-124, 129-136).

**SettingsApiKeyTab**: ✅ `<Label htmlFor="api_key">` (line 87).

**However**, many pages use raw `<label>` (lowercase, not the Radix `<Label>` component) WITHOUT `htmlFor`:
- `src/pages/CrmPage.tsx:407, 418, 428, 437, 446, 465` — `<label className="...">` with no `htmlFor`, and the `<Input>` has no `id`. The label is a sibling, not associated. **WCAG 1.3.1 / 4.1.2 issue.**
- `src/pages/InventoryPage.tsx` — same pattern (verified at lines around the dialog, ~similar to CrmPage).
- `src/pages/InvoicesPage.tsx` — same pattern.
- `src/pages/FacturacionElectronicaPage.tsx:272, 286, 299` — `<label className="text-xs text-zinc-400 mb-1 block">País</label>` with no `htmlFor`, `<select>` with no `id`.
- `src/pages/AirgapPage.tsx` — license dialog forms.
- `src/components/orbital/VariableDialog.tsx:83, 95, 105, 115` — `<label>` with no `htmlFor`, `<Input>` with no `id`.
- `src/components/orbital/CycleDialog.tsx:83, 94, 108` — same.
- `src/pages/SyncCloud.tsx:293, 302` — uses raw `<label>` for checkboxes without `htmlFor` (but the `<input type="checkbox">` is inside the label, which IS a valid association pattern). ✅ OK.

**Severity**: Medium — screen reader users won't get label-to-input association for ~20+ form fields across CRM/Inventory/Invoices/Orbital dialogs. Functional impact is real.

### 7.2 Icon-only buttons without accessible names

| File:Line | Button | Has `aria-label`? | Has `title`? |
|---|---|---|---|
| `src/components/editor/NodeConfigPanel.tsx:66-68` | Close (X icon) | ❌ | ❌ |
| `src/components/settings/SettingsApiKeyTab.tsx:107-109` | Copy API key | ❌ | ❌ |
| `src/pages/SyncCloud.tsx:347-348` | Copy encryption key | ❌ | ❌ |
| `src/pages/SyncCloud.tsx:350-351` | Hide key | ❌ | ❌ |
| `src/pages/Deployments.tsx:152-163` | Copy deployment command | ❌ | ❌ |
| `src/components/AppLayout.tsx:180-191` | Collapse sidebar (ChevronRight/Left) | ❌ | ❌ |
| `src/components/admin/DeadLetterTab.tsx:190-197` | Refresh (RefreshCw) | ❌ | ❌ |
| `src/pages/ChatPage.tsx:461-471` | Send message (Send icon) | ❌ | ❌ |

**Icon-only buttons WITH `title` (acceptable but `aria-label` is better)**:
- `src/components/AppLayout.tsx:171-179` — theme toggle, has `title={isDark ? "Modo claro" : "Modo oscuro"}`.
- `src/pages/Editor.tsx:326-334` — toggle toolbox, has `title`.
- `src/pages/Editor.tsx:377-386` — toggle config panel, has `title`.
- `src/components/orbital/VariableCard.tsx:26-34` — delete variable, has `title="Eliminar variable"`.
- `src/components/admin/DeadLetterTab.tsx:236-244` — retry, has `title="Reintentar"`.
- `src/components/admin/DeadLetterTab.tsx:245-253` — discard, has `title="Descartar"`.
- `src/components/admin/UsersTab.tsx` — edit and delete buttons, no `title` (verified at line ~204-219 — actually these have no title either).

**WCAG 2.1 AA 4.1.2 (Name, Role, Value) violation** for the 8 buttons in the first table. **Severity**: Medium — icon-only buttons are unnamed to screen readers.

### 7.3 Dialog focus trap

The app uses `@radix-ui/react-dialog` (see `src/components/ui/dialog.tsx`) which provides focus trapping, Escape-to-close, and click-outside-to-close out of the box. ✅ All dialogs in the app use this component (verified: CrmPage, InventoryPage, InvoicesPage, IntegrationsPage, Plugins, AirgapPage, Workflows, VariableDialog, CycleDialog, PromotionDialog, LoginPage's no dialog).

**No custom dialogs found.** ✅ No focus-trap concerns.

### 7.4 Color contrast

The app uses a dark-mode-first design with `zinc-900`/`zinc-800` backgrounds and `zinc-100`/`zinc-200` text — these pass WCAG AA contrast (ratio > 4.5:1).

**Low-contrast concerns**:
- `text-zinc-500` on `bg-zinc-900` (used for secondary text in DeadLetterTab, QueueTab, etc.): contrast ratio ~5.0:1 — passes AA for normal text, but fails for small text (< 18px). Many of these are `text-xs text-zinc-500` (12px) which would need 4.5:1 — borderline.
- `text-zinc-600` on `bg-zinc-900` (used in `DeadLetterTab.tsx:228`, `QueueTab.tsx:90`, `TorMatrix.tsx:46`): contrast ratio ~3.5:1 — **fails AA for normal text**.
- `text-[10px] text-zinc-600` (used for "Mostrando 25 de N parejas" in TorMatrix): 10px + zinc-600 = **fails AA**.
- `text-zinc-400` on `bg-zinc-900` (used for placeholder text): ratio ~6.3:1 — passes.

**Severity**: Low-Medium — minor contrast issues with `text-zinc-600` on small text. Not a P0 but worth fixing for AA compliance.

### 7.5 Images without alt

**Grep for `<img ` → 0 matches** in `src/`. The app uses SVG icons (lucide-react) and inline SVG, no `<img>` tags. ✅

The `<canvas>` in `OrbitalVisualizer.tsx:323-329` has no `role="img"` or `aria-label`. Screen readers will announce it as nothing. **Severity**: Medium — the canvas conveys real-time ORBITAL state but is invisible to AT users. Should have `role="img"` and a dynamic `aria-label` like `"ORBITAL visualizer: 5 variables, 8 TOR connections, COD converged"`.

### 7.6 ARIA misuse

`src/components/ui/progress.tsx:25` uses `role="progressbar"` — correct usage. ✅

`src/components/dashboard/LiveExecutionFeed.tsx` uses `<span className="...">EN VIVO</span>` with a pulsing dot — purely decorative, no `role="status"` or `aria-live="polite"`. Real-time events are added to the list below but not announced to AT. **Severity**: Medium — live regions should use `aria-live`.

**No misuse of ARIA found** (no `role="button"` on `<div>`, no `aria-label` on already-named elements, etc.).

---

## Section 8: Performance

### 8.1 Bundle analysis

**Total: 1.34 MB raw / 377 KB gzip** (per sandbox). No code splitting (`React.lazy`/`Suspense`/dynamic `import` = 0 matches).

**Heaviest dependencies** (from `package.json`):

| Dependency | Estimated size (min) | Used in |
|---|---|---|
| `@xyflow/react ^12.11.0` | ~250 KB | `Editor.tsx` + 4 editor components — single route `/app/editor` |
| `recharts ^3.8.1` | ~200 KB | `Dashboard.tsx` (3 charts) + `ReportsPage.tsx` (3 charts) — 2 routes |
| `react 19 + react-dom 19` | ~140 KB | All routes (unavoidable) |
| 14 × `@radix-ui/react-*` | ~40 KB total (tree-shaken) | Spread across dialogs, selects, etc. |
| `lucide-react ^1.17.0` | ~5 KB × ~50 icons ≈ 50 KB | All routes (icons used everywhere) |
| `i18next + react-i18next` | ~25 KB | Only used by MiNegocioPage (per Section 6) |
| `react-router-dom ^7.17.0` | ~20 KB | All routes (unavoidable) |
| `tailwindcss` (CSS) | ~30 KB (purged) | All routes |

### 8.2 Recommended code-split points

**Route-based lazy loading** (highest impact, easiest to implement):

```tsx
// App.tsx — replace static imports with lazy
const Editor = lazy(() => import("@/pages/Editor"))
const OrbitalPage = lazy(() => import("@/pages/OrbitalPage"))
const ReportsPage = lazy(() => import("@/pages/ReportsPage"))
const Dashboard = lazy(() => import("@/pages/Dashboard"))
const AdminPage = lazy(() => import("@/pages/AdminPage"))
// ... wrap <Route> elements in <Suspense fallback={<Skeleton/>}>
```

**Estimated impact**:
- Initial bundle (login page): ~250 KB (react + react-dom + react-router + radix-dialog + lucide icons) — down from 1.34 MB.
- Dashboard route: +200 KB (recharts) — loads on first visit to `/app/dashboard`.
- Editor route: +250 KB (xyflow) — loads on first visit to `/app/editor`.
- All other routes: +20-40 KB each.

**Initial load improvement: ~70%** (from 1.34 MB to ~400 KB).

**Other split opportunities**:
- `PromotionDialog` and `EnvironmentsTab` are already lazy candidates (only used when user clicks "Entornos" in Workflows) — but they're small.
- `i18n.ts` + 3 locale JSON files (~30 KB) could be loaded on demand if i18n is ever actually adopted.

### 8.3 Unmemoized list renders

**Workflow nodes** (`src/pages/Editor.tsx`): uses `useNodesState`/`useEdgesState` from xyflow, which are designed for this. `ActionNode` and `TriggerNode` are both `memo()`'d (`ActionNode.tsx:86`, `TriggerNode.tsx:48`). ✅

**Dashboard charts** (`TimelineChart`, `SuccessChart`, `ToolsChart`): receive `data` prop. Not memoized, but they're cheap re-renders (recharts handles internal memoization). The parent `Dashboard` re-renders on every SSE event (because `loadData` is called after each event). **Medium** — could memoize chart components with `React.memo` and stable data references.

**Admin tables** (`UsersTab`, `DeadLetterTab`, `QueueTab`): list renders with `.map()` and `key={id}`. ✅ Correct. No memoization needed because they only re-render when `users`/`entries`/`items` state changes.

**CrmPage lead list** (`CrmPage.tsx:300-382`): `.map()` over `filteredLeads` (computed inline at line 116-125). `filteredLeads` is recomputed on every render even if `leads` and `searchQuery` haven't changed. **Low severity** — list is typically < 100 items. Could `useMemo` the filter.

### 8.4 Unnecessary re-renders

| File:Line | Issue | Severity |
|---|---|---|
| `src/contexts/ThemeContext.tsx:27-30` | `value` object is NOT memoized. Every render of `ThemeProvider` (which happens when `theme` changes) creates a new value object, causing ALL consumers of `useTheme()` to re-render. Since `theme` only changes on toggle, this is rare — but `AppLayout` (which uses `useTheme`) re-renders on every route change because `useLocation` triggers re-render, and ThemeProvider's value prop change cascades. **Fix**: `useMemo(() => ({ theme, toggleTheme, setTheme, isDark }), [theme])`. | Low |
| `src/contexts/AuthContext.tsx:196-199` | ✅ `value` IS memoized with `useMemo([state, login, register, logout, checkAuth])`. Good. | — |
| `src/hooks/useSSE.ts:123-126` | ✅ Return value IS memoized. Good. | — |
| `src/pages/Dashboard.tsx:151-180` | `cards` array is recomputed on every render. Not memoized. Low impact (4 items). | Low |
| `src/pages/ReportsPage.tsx:178-196` | `moduleData`, `statusData`, `invoiceStatusData` arrays recomputed every render. Low impact. | Low |
| `src/pages/Compliance.tsx:103-109` | `filteredControls` recomputed every render even if filters unchanged. Low impact. | Low |
| Inline objects in props: `src/pages/OrbitalPage.tsx:364, 366, 380, 382` pass inline arrow functions `() => setShowVarDialog(true)` etc. to `VariablesTab`/`RccTab`. These create new function identities every render, but since the children don't use `React.memo`, it doesn't cause extra re-renders. | Low |

### 8.5 DOM reads during render (anti-pattern)

| File:Line | Issue |
|---|---|
| `src/components/dashboard/ToolsChart.tsx:29` | `const isDark = document.documentElement.classList.contains("dark")` — called during render. If user toggles theme, the chart does NOT re-render (no state change in the component). Charts stay with old colors until a prop changes. |
| `src/components/dashboard/SuccessChart.tsx:15` | Same. |
| `src/components/dashboard/TimelineChart.tsx:18` | Same. |
| `src/pages/ReportsPage.tsx:173` | Same. |

**Fix**: read theme via `useTheme()` hook, which subscribes to ThemeContext and triggers re-render on toggle.

**Severity**: Medium — visual bug where charts don't follow theme toggles.

---

## Section 9: Recommendations prioritized

### P0 — Critical (fix before any production deploy)

1. **`src/pages/MiNegocioPage.tsx:37-44`**: Remove the `localStorage.getItem('token')` + Bearer header. Use `apiFetch` (which sends cookies) and either proxy `/api/v2/*` through nginx OR migrate the page to use the existing `/api/dashboard/stats` endpoint that the rest of the app uses. Page is currently 100% broken in production.

2. **`src/pages/FacturacionElectronicaPage.tsx:88,142`**: Either proxy `/api/v2/fiscal/*` through nginx or migrate to a Flask `/api/fiscal/*` route. Fix the `api.post(..., { headers })` type error by extending `useApi.ts`'s `post` options type to accept `headers`, or use raw `fetch` with credentials:"include".

3. **`src/components/orbital/OrbitalVisualizer.tsx:43-57`**: Delete the local `OrbitalStatus` interface and import from `@/types/orbital`. Update all references: `status.tor_results` → `status.tor`, `status.cod?.converged` → `status.cod?.[0]?.converged ?? true`, `status.cod?.iterations` → `status.cod?.[0]?.iterations ?? 0`. Currently the TOR lines and COD indicator NEVER render.

4. **`src/App.tsx`**: Add `requiredRole="admin"` to the `<ProtectedRoute>` wrapping `/app/admin` route. Currently any `viewer` can access the admin panel.

### P1 — High (fix in next sprint)

5. **useApi onClick pattern** (11 instances in Section 1.2): wrap each `onClick={loadData}` with `onClick={() => loadData()}`. Mechanical fix, ~15 minutes of work.

6. **`src/contexts/ThemeContext.tsx:27-30`**: Memoize the `value` object with `useMemo`.

7. **`src/components/dashboard/{ToolsChart,SuccessChart,TimelineChart}.tsx` and `src/pages/ReportsPage.tsx:173`**: Replace `document.documentElement.classList.contains("dark")` with `useTheme()` to make charts follow theme toggles.

8. **`src/components/settings/SettingsSystemTab.tsx:21-30` and `SettingsSmtpTab.tsx:28-33`**: Add AbortController pattern (copy from DeadLetterTab.tsx:54-59). Same for `src/pages/MiNegocioPage.tsx:34-64` and `src/components/settings/SettingsApiKeyTab.tsx:18-23`.

9. **`src/pages/LoginPage.tsx:46-49`**: Move `if (authenticated) { navigate(redirectTo, ...); return null }` into a `useEffect`. Calling `navigate()` during render is a React Router anti-pattern (works but logs a warning in dev).

10. **`src/pages/Dashboard.tsx:120, 133`**: Store the `setTimeout` id in a ref and clear it in the SSE effect cleanup. Currently the timer leaks on unmount.

11. **`src/hooks/useApi.ts:114, 124`**: Add `{ cause: e }` to the thrown errors to satisfy `preserve-caught-error` lint rule.

### P2 — Medium (technical debt)

12. **i18n migration**: Either commit to i18n (migrate all 21 hardcoded pages to use `t()`) or remove the i18n infrastructure. The current state (infrastructure present, only 1 page uses it, 25 dead keys in `es.json`) is the worst of both worlds.

13. **Accessibility — icon-only buttons**: Add `aria-label` to the 8 buttons listed in Section 7.2. ~30 minutes of work.

14. **Accessibility — form labels**: Migrate `<label>` (lowercase) to `<Label htmlFor>` (Radix) in CrmPage, InventoryPage, InvoicesPage, FacturacionElectronicaPage, AirgapPage, VariableDialog, CycleDialog. ~1 hour.

15. **Bundle splitting**: Implement route-based lazy loading per Section 8.2. ~1 hour, 60-70% initial bundle reduction.

16. **`src/pages/FacturacionElectronicaPage.tsx:25-30`**: Remove unused `FiscalCountry` interface.

17. **`src/pages/FacturacionElectronicaPage.tsx:102-104`**: Add `// eslint-disable-next-line react-hooks/set-state-in-effect` (matching the pattern used in 9 other pages) OR refactor to use the AbortController pattern.

18. **`src/i18n.ts:51`**: Remove the stale `// eslint-disable-next-line no-console` comment.

### P3 — Low (cleanup)

19. **`src/components/orbital/TorMatrix.tsx:24` and `TickHistoryCard.tsx:25`**: Use `key={`${entry.variable_i}-${entry.variable_j}`}` and `key={h.tick}` instead of `key={i}`.

20. **`src/components/editor/Toolbox.tsx:39`**: Replace `setTimeout(() => document.body.removeChild(el), 0)` with a `requestAnimationFrame` callback or store the ref and remove in `onDragEnd`.

21. **`text-zinc-600` on small text** (Section 7.4): Bump to `text-zinc-500` for AA compliance.

22. **`<canvas>` in `OrbitalVisualizer.tsx:323-329`**: Add `role="img"` and a dynamic `aria-label`.

23. **`src/pages/Compliance.tsx:32`**: `text-gray-400` — minor, but the rest of the app uses `zinc` scale. Standardize.

---

## Methodology and honesty notes

- **Read every file**: 22 pages, 40+ components, 4 hooks, 3 contexts, 3 locale files, 3 config files (vite, eslint, package.json). ~4500 LOC total reviewed.
- **No tests run**: this is a static review. Runtime claims (e.g., "clicking works despite type error") are inferred from tracing the code paths, not from executing them.
- **No browser session**: accessibility findings are based on code inspection, not axe-core or screen reader testing.
- **Bundle size**: accepted the sandbox's 1.34 MB / 377 KB gzip figures without re-running `vite build`.
- **Cross-references**: zenic-1b connectivity report (`BACKUP_CONNECTIVITY_REPORT.md`) was read for the `/api/v2/*` nginx proxy issue; not re-verified independently.
- **What I did NOT check**: backend code (Flask/FastAPI), test files (`__tests__/`), the `docs/TECH_DEBT.md` file, CSS animations, Service Workers (none found), PWA manifest (none found).
- **What I might have missed**: subtle race conditions that only manifest under specific timing; visual bugs that only appear with real data; mobile responsive issues (only checked class-based responsive design, not tested in mobile viewport).
