/**
 * useAgents — React hook for Agents API (/api/v2/agents/*)
 *
 * 12 endpoints:
 *   spawn, list, getStatus, run, pause, resume, terminate,
 *   orchestrate, getStats, getTokenSummary, getDailyUsage, setBudget
 */
import { useState, useCallback } from "react"
import { apiFetch } from "@/hooks/useApi"
import { error as humanError } from "@/utils/humanize"
import type {
  AgentConfig,
  AgentStatus,
  AgentListResponse,
  AgentRunResponse,
  AgentOrchestrationPlan,
  AgentOrchestrationResult,
  TokenUsageSummary,
  DailyTokenUsage,
  RuntimeStats,
} from "@/types/agents"

const BASE = "/api/v2/agents"

export function useAgents() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleError = useCallback((err: unknown) => {
    const msg = err instanceof Error ? humanError(err.message) : "Error desconocido"
    setError(msg)
    return null
  }, [])

  /** POST /spawn — Crear un nuevo agente */
  const spawn = useCallback(async (config: AgentConfig): Promise<AgentStatus | null> => {
    setLoading(true); setError(null)
    try {
      const data = await apiFetch<AgentStatus>(`${BASE}/spawn`, { method: "POST", body: JSON.stringify(config) })
      return data
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /list — Listar agentes activos */
  const list = useCallback(async (state?: string, capability?: string): Promise<AgentListResponse | null> => {
    setLoading(true); setError(null)
    try {
      const params = new URLSearchParams()
      if (state) params.set("state", state)
      if (capability) params.set("capability", capability)
      const qs = params.toString()
      const data = await apiFetch<AgentListResponse>(`${BASE}/list${qs ? `?${qs}` : ""}`)
      return data
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /{agent_id} — Obtener estado de un agente */
  const getStatus = useCallback(async (agentId: string): Promise<AgentStatus | null> => {
    setLoading(true); setError(null)
    try {
      const data = await apiFetch<AgentStatus>(`${BASE}/${agentId}`)
      return data
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** POST /{agent_id}/run — Ejecutar un agente */
  const run = useCallback(async (agentId: string, input?: Record<string, unknown>): Promise<AgentRunResponse | null> => {
    setLoading(true); setError(null)
    try {
      const data = await apiFetch<AgentRunResponse>(`${BASE}/${agentId}/run`, { method: "POST", body: input !== undefined ? JSON.stringify(input) : undefined })
      return data
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** POST /{agent_id}/pause — Pausar un agente */
  const pause = useCallback(async (agentId: string): Promise<boolean> => {
    setLoading(true); setError(null)
    try {
      await apiFetch(`${BASE}/${agentId}/pause`, { method: "POST" })
      return true
    } catch (e) { handleError(e); return false } finally { setLoading(false) }
  }, [handleError])

  /** POST /{agent_id}/resume — Reanudar un agente */
  const resume = useCallback(async (agentId: string): Promise<boolean> => {
    setLoading(true); setError(null)
    try {
      await apiFetch(`${BASE}/${agentId}/resume`, { method: "POST" })
      return true
    } catch (e) { handleError(e); return false } finally { setLoading(false) }
  }, [handleError])

  /** DELETE /{agent_id} — Terminar un agente */
  const terminate = useCallback(async (agentId: string, force = false): Promise<boolean> => {
    setLoading(true); setError(null)
    try {
      await apiFetch(`${BASE}/${agentId}?force=${force}`, { method: "DELETE" })
      return true
    } catch (e) { handleError(e); return false } finally { setLoading(false) }
  }, [handleError])

  /** POST /orchestrate — Orquestación multi-agente */
  const orchestrate = useCallback(async (plan: AgentOrchestrationPlan): Promise<AgentOrchestrationResult | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<AgentOrchestrationResult>(`${BASE}/orchestrate`, { method: "POST", body: JSON.stringify(plan) })
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /runtime/stats — Estadísticas del runtime */
  const getStats = useCallback(async (): Promise<RuntimeStats | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<RuntimeStats>(`${BASE}/runtime/stats`)
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /token-usage/summary — Resumen de tokens */
  const getTokenSummary = useCallback(async (tenantId = "default"): Promise<TokenUsageSummary | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<TokenUsageSummary>(`${BASE}/token-usage/summary?tenant_id=${tenantId}`)
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** GET /token-usage/daily — Uso diario de tokens */
  const getDailyUsage = useCallback(async (tenantId = "default", days = 30): Promise<DailyTokenUsage[] | null> => {
    setLoading(true); setError(null)
    try {
      return await apiFetch<DailyTokenUsage[]>(`${BASE}/token-usage/daily?tenant_id=${tenantId}&days=${days}`)
    } catch (e) { return handleError(e) } finally { setLoading(false) }
  }, [handleError])

  /** POST /token-usage/budget — Fijar presupuesto de tokens */
  const setBudget = useCallback(async (tenantId: string, opts: { daily_limit?: number; monthly_limit?: number; total_limit?: number }): Promise<boolean> => {
    setLoading(true); setError(null)
    try {
      const params = new URLSearchParams({ tenant_id: tenantId })
      if (opts.daily_limit !== undefined) params.set("daily_limit", String(opts.daily_limit))
      if (opts.monthly_limit !== undefined) params.set("monthly_limit", String(opts.monthly_limit))
      if (opts.total_limit !== undefined) params.set("total_limit", String(opts.total_limit))
      await apiFetch(`${BASE}/token-usage/budget?${params}`, { method: "POST" })
      return true
    } catch (e) { handleError(e); return false } finally { setLoading(false) }
  }, [handleError])

  const clearError = useCallback(() => setError(null), [])

  return {
    loading, error, clearError,
    spawn, list, getStatus, run, pause, resume, terminate,
    orchestrate, getStats, getTokenSummary, getDailyUsage, setBudget,
  }
}
