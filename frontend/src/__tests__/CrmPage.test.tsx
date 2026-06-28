/**
 * Tests del módulo CRM (CrmPage).
 *
 * Previenen BUG-FE-02: STAGES debe estar definido como array de 7 etapas
 * que coincida con tools/crm/service.py:STAGES.
 *
 * Si este test falla, la línea `STAGES.map(...)` en CrmPage lanzará
 * ReferenceError en runtime.
 */
import { describe, it, expect } from "vitest"
import { STAGES as EXPECTED_BACKEND_STAGES } from "@/types/crm"

describe("CrmPage STAGES contract", () => {
  it("el backend expone las 7 etapas esperadas", () => {
    expect(EXPECTED_BACKEND_STAGES).toBeDefined()
    expect(Array.isArray(EXPECTED_BACKEND_STAGES)).toBe(true)
    expect(EXPECTED_BACKEND_STAGES).toHaveLength(7)
  })

  it("las etapas coinciden con tools/crm/service.py:STAGES", () => {
    // El orden debe coincidir con el pipeline del backend
    expect(EXPECTED_BACKEND_STAGES).toEqual([
      "new",
      "contacted",
      "qualified",
      "proposal",
      "negotiation",
      "closed_won",
      "closed_lost",
    ])
  })
})
