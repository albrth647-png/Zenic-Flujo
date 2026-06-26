/**
 * Tests de BUG-2-FE: AbortController signal pasado al fetch.
 *
 * Antes: 15 páginas creaban `const ac = new AbortController()` en el
 * useEffect cleanup, pero el signal nunca se pasaba al `fetch()`. Los
 * requests seguían vivos tras unmount (zombies) — el `.then` podía
 * ejecutar `setState` en componente desmontado y mostrar toasts spurious.
 *
 * Fix: cada `loadX` recibe `signal?: AbortSignal`, lo pasa a `api.get/post/...`
 * o `apiFetch(..., { signal })` o `fetch(..., { signal })`, y el useEffect
 * invoca `loadX(ac.signal)`. El catch de `loadX` identifica `AbortError`
 * por `e.name` o `signal?.aborted` y lo silencia.
 *
 * Este test verifica que las 15 páginas afectadas tienen el patrón completo
 * en su código fuente. Verifica con regex multilinea porque es la forma más
 * robusta de detectar el patrón sin acoplarse a detalles de implementación.
 */
import { describe, it, expect, vi } from "vitest"
import * as fs from "node:fs"
import * as path from "node:path"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Lista de las 15 páginas/componentes afectados por BUG-2-FE.
// Si se añade una nueva página con AbortController, debe incluirse aquí.
const PAGES_WITH_ABORT_CONTROLLER: Array<{ relPath: string; loadFn: string }> = [
  { relPath: "../contexts/AuthContext.tsx", loadFn: "checkAuth" },
  { relPath: "../pages/Plugins.tsx", loadFn: "loadData" },
  { relPath: "../pages/SyncCloud.tsx", loadFn: "loadData" },
  { relPath: "../pages/AirgapPage.tsx", loadFn: "loadData" },
  { relPath: "../pages/PartnersPage.tsx", loadFn: "loadData" },
  { relPath: "../pages/ReportsPage.tsx", loadFn: "loadData" },
  { relPath: "../pages/IntegrationsPage.tsx", loadFn: "loadData" },
  { relPath: "../pages/CrmPage.tsx", loadFn: "loadLeads" },
  { relPath: "../pages/InventoryPage.tsx", loadFn: "loadProducts" },
  { relPath: "../components/admin/UsersTab.tsx", loadFn: "loadUsers" },
  { relPath: "../pages/Compliance.tsx", loadFn: "loadData" },
  { relPath: "../pages/InvoicesPage.tsx", loadFn: "loadInvoices" },
  { relPath: "../components/admin/DeadLetterTab.tsx", loadFn: "loadData" },
  { relPath: "../pages/OrbitalPage.tsx", loadFn: "loadStatus" },
  { relPath: "../components/admin/QueueTab.tsx", loadFn: "loadData" },
]

// Helpers para leer el código fuente de un archivo como string plano.
function readSrc(relPath: string): string {
  const filePath = path.resolve(__dirname, relPath)
  return fs.readFileSync(filePath, "utf-8")
}

describe("BUG-2-FE: AbortController signal pasado al fetch", () => {
  describe("analisis estatico — todas las paginas afectadas", () => {
    PAGES_WITH_ABORT_CONTROLLER.forEach(({ relPath, loadFn }) => {
      it(`${relPath} pasa signal al fetch y aborta en cleanup`, () => {
        const content = readSrc(relPath)

        // 1. Crea un AbortController
        expect(content).toMatch(/new AbortController\(\)/)

        // 2. Llama ac.abort() en el cleanup del useEffect
        expect(content).toMatch(/ac\.abort\(\)/)

        // 3. La función de carga acepta un parámetro signal (opcional o requerido)
        //    Ej: `loadData = useCallback(async (signal?: AbortSignal) => {` o
        //    `const loadData = async (signal?: AbortSignal) => {`
        const signalParamRegex = new RegExp(
          `${loadFn}\\b[^=]*=\\s*(?:useCallback\\()?(?:async\\s*)?\\([^)]*signal\\s*\\?\\s*:\\s*AbortSignal`,
        )
        expect(content).toMatch(signalParamRegex)

        // 4. El useEffect pasa ac.signal a la función de carga
        const passSignalRegex = new RegExp(`${loadFn}\\(ac\\.signal\\)`)
        expect(content).toMatch(passSignalRegex)

        // 5. El signal se pasa al fetch — cualquiera de estas formas:
        //    - `{ signal }` (shorthand)
        //    - `{ signal: ... }` (explicito)
        //    - `{ credentials: "include", signal }` (con otras props)
        //    - `api.get(path, { signal })`
        //    - `apiFetch(path, { signal })`
        //    - `fetch(url, { ..., signal })`
        const passesSignalToFetch =
          /\{\s*[^}]*\bsignal\b[^}]*\}/.test(content) ||
          /signal:\s*ac\.signal/.test(content)
        expect(passesSignalToFetch).toBe(true)

        // 6. El catch identifica AbortError y/o signal.aborted y lo silencia
        const handlesAbortError =
          /AbortError/.test(content) || /signal\?\.aborted/.test(content)
        expect(handlesAbortError).toBe(true)
      })
    })
  })

  describe("paginas representativas — verificacion detallada del patron", () => {
    it("AirgapPage.tsx: loadData acierta el patron completo", () => {
      const content = readSrc("../pages/AirgapPage.tsx")

      // Tiene el callback con signal
      expect(content).toMatch(/loadData\s*=\s*useCallback\(\s*async\s*\(signal\?:\s*AbortSignal\)/)
      // Pasa signal a las 3 llamadas api.get
      expect(content).toMatch(/api\.get\(["']\/api\/airgap\/status["'],\s*\{\s*signal\s*\}\)/)
      expect(content).toMatch(/api\.get\(["']\/api\/airgap\/config["'],\s*\{\s*signal\s*\}\)/)
      expect(content).toMatch(/api\.get\(["']\/api\/license\/info["'],\s*\{\s*signal\s*\}\)/)
      // Llama loadData(ac.signal)
      expect(content).toMatch(/loadData\(ac\.signal\)/)
    })

    it("CrmPage.tsx: loadLeads acierta el patron completo", () => {
      const content = readSrc("../pages/CrmPage.tsx")

      expect(content).toMatch(/loadLeads\s*=\s*useCallback\(\s*async\s*\(signal\?:\s*AbortSignal\)/)
      // Pasa signal al api.get
      expect(content).toMatch(/api\.get\(`\/api\/tools\/crm\/leads\$\{query\}`,\s*\{\s*signal\s*\}\)/)
      // Llama loadLeads(ac.signal)
      expect(content).toMatch(/loadLeads\(ac\.signal\)/)
    })

    it("InvoicesPage.tsx: loadInvoices acierta el patron completo", () => {
      const content = readSrc("../pages/InvoicesPage.tsx")

      expect(content).toMatch(/loadInvoices\s*=\s*useCallback\(\s*async\s*\(signal\?:\s*AbortSignal\)/)
      // Pasa signal al api.get
      expect(content).toMatch(/api\.get\(`\/api\/tools\/invoice\/list\$\{query\}`,\s*\{\s*signal\s*\}\)/)
      // Llama loadInvoices(ac.signal)
      expect(content).toMatch(/loadInvoices\(ac\.signal\)/)
    })

    it("AuthContext.tsx: checkAuth pasa signal al fetch nativo", () => {
      const content = readSrc("../contexts/AuthContext.tsx")

      // checkAuth acepta signal
      expect(content).toMatch(/checkAuth\s*=\s*useCallback\(\s*async\s*\(signal\?:\s*AbortSignal\)/)
      // fetch nativo con signal
      expect(content).toMatch(/fetch\(["']\/api\/auth\/status["'],\s*\{\s*credentials:\s*["']include["'],\s*signal\s*\}\)/)
      // Llama checkAuth(ac.signal)
      expect(content).toMatch(/checkAuth\(ac\.signal\)/)
    })
  })

  describe("getApi acepta signal (BUG-2-FE habilitador)", () => {
    it("useApi.ts: getApi().get/post/put/patch/delete aceptan options.signal", async () => {
      // Behavior test: mockear fetch y verificar que signal llega al fetch subyacente
      const mockFetch = vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
      vi.stubGlobal("fetch", mockFetch)

      try {
        const { useApi } = await import("../hooks/useApi")
        const { renderHook, act } = await import("@testing-library/react")
        const { result } = renderHook(() => useApi())

        const controller = new AbortController()
        const signal = controller.signal

        await act(async () => {
          await result.current.getApi().get("/api/test", { signal })
        })

        expect(mockFetch).toHaveBeenCalledTimes(1)
        const [, init] = mockFetch.mock.calls[0]
        expect(init).toMatchObject({ method: "GET", signal })
      } finally {
        vi.unstubAllGlobals()
      }
    })
  })
})
