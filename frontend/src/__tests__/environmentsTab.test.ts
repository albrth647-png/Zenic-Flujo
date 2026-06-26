/**
 * Tests de BUG-6-FE: EnvironmentsTab y PromotionDialog cableados.
 *
 * Sprint 9 construyó EnvironmentsTab (373 LOC) y PromotionDialog (236 LOC)
 * para el sistema de multi-entorno + versioning + rollback. Pero ningún
 * componente los importaba, así que estaban huérfanos — el backend de
 * versioning.py (718 LOC) no se usaba desde la UI.
 *
 * Fix:
 * 1. App.tsx importa EnvironmentsTab y PromotionDialog (y los re-exporta
 *    para asegurar que estén en el bundle graph).
 * 2. Workflows.tsx añade un botón "Entornos" en cada workflow que abre
 *    un diálogo con EnvironmentsTab (que internamente usa PromotionDialog).
 *
 * Este test verifica que:
 * 1. App.tsx referencia ambos componentes (import + re-export).
 * 2. Workflows.tsx usa EnvironmentsTab en su render.
 * 3. Los componentes existen y exportan lo esperado.
 */
import { describe, it, expect } from "vitest"
import * as fs from "node:fs"
import * as path from "node:path"
import { fileURLToPath } from "node:url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

describe("BUG-6-FE: EnvironmentsTab y PromotionDialog cableados en la UI", () => {
  it("App.tsx importa EnvironmentsTab", () => {
    const appPath = path.resolve(__dirname, "../App.tsx")
    const content = fs.readFileSync(appPath, "utf-8")

    expect(content).toMatch(/import\s+\{[^}]*EnvironmentsTab[^}]*\}\s+from\s+["']@\/components\/workflows\/EnvironmentsTab["']/)
  })

  it("App.tsx importa PromotionDialog", () => {
    const appPath = path.resolve(__dirname, "../App.tsx")
    const content = fs.readFileSync(appPath, "utf-8")

    expect(content).toMatch(/import\s+\{[^}]*PromotionDialog[^}]*\}\s+from\s+["']@\/components\/workflows\/PromotionDialog["']/)
  })

  it("App.tsx re-exporta ambos componentes para asegurar bundle graph", () => {
    const appPath = path.resolve(__dirname, "../App.tsx")
    const content = fs.readFileSync(appPath, "utf-8")

    expect(content).toMatch(/export\s+\{\s*EnvironmentsTab,?\s*PromotionDialog\s*\}/)
  })

  it("Workflows.tsx usa EnvironmentsTab en su render", () => {
    const wfPath = path.resolve(__dirname, "../pages/Workflows.tsx")
    const content = fs.readFileSync(wfPath, "utf-8")

    // Importa EnvironmentsTab
    expect(content).toMatch(/import\s+\{[^}]*EnvironmentsTab[^}]*\}\s+from\s+["']@\/components\/workflows\/EnvironmentsTab["']/)
    // Usa el componente en el JSX
    expect(content).toMatch(/<EnvironmentsTab\s/)
  })

  it("Workflows.tsx tiene un trigger para abrir el dialogo de entornos", () => {
    const wfPath = path.resolve(__dirname, "../pages/Workflows.tsx")
    const content = fs.readFileSync(wfPath, "utf-8")

    // Hay un estado para el workflow seleccionado y un setEnvDialogWf
    expect(content).toMatch(/envDialogWf/)
    expect(content).toMatch(/setEnvDialogWf/)
  })

  it("los componentes existen y exportan sus nombres", async () => {
    const envModule = await import("@/components/workflows/EnvironmentsTab")
    const promoModule = await import("@/components/workflows/PromotionDialog")

    expect(envModule.EnvironmentsTab).toBeDefined()
    expect(typeof envModule.EnvironmentsTab).toBe("function")
    expect(promoModule.PromotionDialog).toBeDefined()
    expect(typeof promoModule.PromotionDialog).toBe("function")
  })

  it("PromotionDialog se renderiza dentro de EnvironmentsTab (uso interno)", () => {
    const envPath = path.resolve(__dirname, "../components/workflows/EnvironmentsTab.tsx")
    const content = fs.readFileSync(envPath, "utf-8")

    // EnvironmentsTab importa y usa PromotionDialog
    expect(content).toMatch(/import\s+\{[^}]*PromotionDialog[^}]*\}\s+from\s+["']@\/components\/workflows\/PromotionDialog["']/)
    expect(content).toMatch(/<PromotionDialog\s/)
  })

  it("App.tsx o routes.tsx mantienen el route /app/workflows apuntando a Workflows", () => {
    // Sanity check: acepta ruta definida en App.tsx (legacy) o en routes.tsx (refactor)
    const appPath = path.resolve(__dirname, "../App.tsx")
    const routesPath = path.resolve(__dirname, "../router/routes.tsx")
    const appContent = fs.readFileSync(appPath, "utf-8")
    const routesContent = fs.readFileSync(routesPath, "utf-8")

    // Workflows está referenciado en App.tsx (import) o en routes.tsx (lazy route)
    if (appContent.includes("Workflows")) {
      // Legacy: App.tsx tiene el lazy import directo
      expect(appContent).toMatch(/path="workflows"/)
      expect(appContent).toMatch(/Workflows/)
    } else {
      // Refactor: routes.tsx tiene la config
      expect(routesContent).toMatch(/path: ["']workflows["']/)
      expect(routesContent).toMatch(/Workflows/)
    }
  })
})
