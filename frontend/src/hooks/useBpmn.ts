/**
 * useBpmn — React hook for BPMN API (/api/v2/bpmn/*)
 *
 * 7 endpoints:
 *   importBpmn, exportBpmn, convertToWorkflow, validate,
 *   listProcesses, getProcess, deleteProcess
 */
import { useState, useCallback } from "react"
import { apiFetch } from "@/hooks/useApi"
import { error as humanError } from "@/utils/humanize"
import type {
  BPMNImportResponse,
  BPMNExportResponse,
  BPMNConvertResponse,
  BPMNValidateResponse,
  BPMNProcessSummary,
  BPMNListResponse,
  BPMNProcess,
} from "@/types/bpmn"

const BASE = "/api/v2/bpmn"

export function useBpmn() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleError = useCallback((err: unknown) => {
    const msg = err instanceof Error ? humanError(err.message) : "Error desconocido"
    setError(msg)
    return null
  }, [])

  /** POST /import — Importar un XML BPMN 2.0 */
  const importBpmn = useCallback(async (xmlContent: string, validate = true): Promise<BPMNImportResponse | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<BPMNImportResponse>(`${BASE}/import?validate=${validate}`, {
        method: "POST", body: JSON.stringify({ xml_content: xmlContent, validate }),
      })
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** POST /export/{process_id} — Exportar proceso como XML */
  const exportBpmn = useCallback(async (processId: string): Promise<BPMNExportResponse | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<BPMNExportResponse>(`${BASE}/export/${processId}`, { method: "POST" })
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** POST /convert/{process_id} — Convertir BPMN a workflow */
  const convertToWorkflow = useCallback(async (processId: string): Promise<BPMNConvertResponse | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<BPMNConvertResponse>(`${BASE}/convert/${processId}`, { method: "POST" })
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** POST /validate — Validar XML BPMN sin importar */
  const validate = useCallback(async (xmlContent: string): Promise<BPMNValidateResponse | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<BPMNValidateResponse>(`${BASE}/validate`, {
        method: "POST", body: JSON.stringify({ xml_content: xmlContent }),
      })
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /processes — Listar procesos BPMN */
  const listProcesses = useCallback(async (): Promise<BPMNProcessSummary[] | null> => {
    setLoading(true); setError(null)
    try {
      const data = await apiFetch<BPMNListResponse>(`${BASE}/processes`)
      return data?.processes ?? null
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /processes/{process_id} — Obtener detalle de proceso */
  const getProcess = useCallback(async (processId: string): Promise<BPMNProcess | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<BPMNProcess>(`${BASE}/processes/${processId}`)
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** DELETE /processes/{process_id} — Eliminar proceso */
  const deleteProcess = useCallback(async (processId: string): Promise<boolean> => {
    setLoading(true); setError(null)
    try {
      await apiFetch(`${BASE}/processes/${processId}`, { method: "DELETE" })
      return true
    } catch (e) { handleError(e); return false } finally { setLoading(false) }
  }, [handleError])

  const clearError = useCallback(() => setError(null), [])

  return {
    loading, error, clearError,
    importBpmn, exportBpmn, convertToWorkflow, validate,
    listProcesses, getProcess, deleteProcess,
  }
}
