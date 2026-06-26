/**
 * useNlu — Hook para el pipeline NLU
 * ====================================
 *
 * Endpoints:
 *   POST /api/v2/nlu/understand   — Pipeline completo NLU
 *   POST /api/v2/nlu/compile      — Compilar workflow desde texto
 *   POST /api/v2/nlu/dry-run      — Simulación dry-run
 *   GET  /api/v2/nlu/intents      — Listar intenciones
 *   GET  /api/v2/nlu/entities     — Listar entidades
 *   POST /api/v2/nlu/train        — Disparar entrenamiento
 *   GET  /api/v2/nlu/status       — Estado del entrenamiento
 */

import { useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import type {
  NLUUnderstandRequest,
  NLUUnderstandResponse,
  NLUCompileRequest,
  NLUCompileResponse,
  NLUDryRunRequest,
  NLUDryRunResult,
  NLUIntentsResponse,
  NLUEntitiesResponse,
  NLUTrainRequest,
  NLUTrainResponse,
  NLUTrainingStatus,
} from "@/types/nlu"

const BASE = "/api/v2/nlu"

export function useNlu() {
  const { getApi } = useApi()

  const understand = useCallback(
    async (text: string, lang?: string): Promise<NLUUnderstandResponse> => {
      const api = getApi()
      return api.post(`${BASE}/understand`, { text, lang } as NLUUnderstandRequest)
    },
    [getApi],
  )

  const compile = useCallback(
    async (text: string, lang?: string): Promise<NLUCompileResponse> => {
      const api = getApi()
      return api.post(`${BASE}/compile`, { text, lang } as NLUCompileRequest)
    },
    [getApi],
  )

  const dryRun = useCallback(
    async (text: string, lang?: string, context?: Record<string, unknown>): Promise<NLUDryRunResult> => {
      const api = getApi()
      return api.post(`${BASE}/dry-run`, { text, lang, context } as NLUDryRunRequest)
    },
    [getApi],
  )

  const listIntents = useCallback(async (): Promise<NLUIntentsResponse> => {
    const api = getApi()
    return api.get(`${BASE}/intents`)
  }, [getApi])

  const listEntities = useCallback(async (): Promise<NLUEntitiesResponse> => {
    const api = getApi()
    return api.get(`${BASE}/entities`)
  }, [getApi])

  const train = useCallback(
    async (language: string): Promise<NLUTrainResponse> => {
      const api = getApi()
      return api.post(`${BASE}/train`, { language } as NLUTrainRequest)
    },
    [getApi],
  )

  const getTrainingStatus = useCallback(async (): Promise<NLUTrainingStatus> => {
    const api = getApi()
    return api.get(`${BASE}/status`)
  }, [getApi])

  return {
    understand,
    compile,
    dryRun,
    listIntents,
    listEntities,
    train,
    getTrainingStatus,
  }
}
