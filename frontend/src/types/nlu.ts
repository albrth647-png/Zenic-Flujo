/**
 * Types — NLU (Natural Language Understanding)
 * =============================================
 *
 * Tipos para los 7 endpoints del pipeline NLU:
 *   POST /api/v2/nlu/understand
 *   POST /api/v2/nlu/compile
 *   POST /api/v2/nlu/dry-run
 *   GET  /api/v2/nlu/intents
 *   GET  /api/v2/nlu/entities
 *   POST /api/v2/nlu/train
 *   GET  /api/v2/nlu/status
 */

// ── Understand ───────────────────────────────────────────────────────

export interface NLUUnderstandRequest {
  text: string
  lang?: string
}

export interface NLUToken {
  text: string
  lemma: string
  pos: string
  start: number
  end: number
}

export interface NLUEntity {
  type: string
  value: string
  span: [number, number]
}

export interface NLUIntent {
  intent: string
  score: number
}

export interface NLUSlot {
  name: string
  value: string
}

export interface NLUUnderstandResponse {
  text: string
  lang: string
  tokens: NLUToken[]
  entities: NLUEntity[]
  intents: NLUIntent[]
  slots: NLUSlot[]
  confidence: number
  trace: string[]
}

// ── Compile ──────────────────────────────────────────────────────────

export interface NLUCompileRequest {
  text: string
  lang?: string
}

export interface NLUCompileResponse {
  workflow: Record<string, unknown>
  explanation: string
  missing_slots: string[]
  status: "valid" | "partial" | "invalid"
}

// ── Dry Run ──────────────────────────────────────────────────────────

export interface NLUDryRunRequest {
  text: string
  lang?: string
  context?: Record<string, unknown>
}

export interface NLUDryRunResult {
  workflow_name: string
  trigger_type: string
  total_steps: number
  steps_that_would_succeed: number
  steps_that_would_fail: number
  warnings: string[]
  overall_feasible: boolean
  summary: string
}

// ── Intents / Entities ───────────────────────────────────────────────

export interface NLUIntentInfo {
  name: string
  source: "database" | "classifier"
}

export interface NLUIntentsResponse {
  intents: NLUIntentInfo[]
  total: number
}

export interface NLUEntityType {
  name: string
  description: string
  patterns: string[]
}

export interface NLUEntitiesResponse {
  entities: NLUEntityType[]
  total: number
}

// ── Training ─────────────────────────────────────────────────────────

export interface NLUTrainRequest {
  language: string
}

export interface NLUTrainResponse {
  job_id: string
  status: "queued" | "training" | "completed" | "failed"
  message: string
}

export interface NLUTrainingStatus {
  job_id: string
  status: "idle" | "queued" | "training" | "completed" | "failed"
  progress: number
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
}
