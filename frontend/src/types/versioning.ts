/**
 * Tipos para Sprint 9 — Versioning + Multi-entorno + Promoción.
 *
 * Estos tipos reflejan exactamente las estructuras que devuelve el backend
 * en src/workflow/versioning.py. Si cambias el backend, actualiza también aquí.
 */

// ─── Tipos atómicos ───────────────────────────────────────────────────

export type Environment = "dev" | "staging" | "prod"

/** Tupla ordenada de entornos válidos (definir el flujo de promoción). */
export const ENVIRONMENTS: readonly Environment[] = ["dev", "staging", "prod"] as const

/** Mapeo origen → destino permitido en promociones. */
export const PROMOTION_FLOW: Record<Environment, Environment | null> = {
  dev: "staging",
  staging: "prod",
  prod: null, // desde prod no se puede promover
}

// ─── Versiones ────────────────────────────────────────────────────────

/** Snapshot inmutable de un workflow en un momento dado. */
export interface WorkflowVersion {
  id: number
  workflow_id: number
  version_number: number
  name: string
  description: string
  trigger_type: string
  trigger_config: Record<string, unknown>
  steps: Array<Record<string, unknown>>
  change_summary: string
  created_by: number
  created_at: string
}

/** Respuesta de GET /api/workflows/:id/versions */
export interface WorkflowVersionListResponse {
  workflow_id: number
  total: number
  limit: number
  offset: number
  versions: WorkflowVersion[]
}

// ─── Entornos ─────────────────────────────────────────────────────────

/** Asociación de un workflow con un entorno. */
export interface WorkflowEnvironment {
  id: number
  workflow_id: number
  environment: Environment
  promoted_from: string | null
  promoted_at: string | null
  promoted_by: number
  is_current: boolean
  notes: string
  created_at: string
  updated_at: string
}

/** Respuesta de GET /api/workflows/:id/environments */
export interface WorkflowEnvironmentListResponse {
  workflow_id: number
  environments: WorkflowEnvironment[]
}

/** Body de POST /api/workflows/:id/environments/:env */
export interface AssignEnvironmentRequest {
  notes?: string
  promoted_from?: string
}

// ─── Promociones ──────────────────────────────────────────────────────

/** Registro de auditoría de una promoción entre entornos. */
export interface WorkflowPromotion {
  id: number
  workflow_id: number
  source_env: Environment
  target_env: Environment
  source_version: number | null
  target_version: number | null
  diff_summary: string
  status: string
  promoted_by: number
  created_at: string
}

/** Respuesta de GET /api/workflows/:id/promotions */
export interface WorkflowPromotionListResponse {
  workflow_id: number
  total: number
  promotions: WorkflowPromotion[]
  summary_by_target_env: Record<string, { count: number; last_at: string }>
}

/** Body de POST /api/workflows/:id/promote */
export interface PromoteWorkflowRequest {
  source_env: Environment
  target_env: Environment
  notes?: string
}

/** Respuesta de POST /api/workflows/:id/versions/:version/rollback */
export interface RollbackResponse {
  status: "ok"
  message: string
  workflow: Record<string, unknown>
}

// ─── Helpers ──────────────────────────────────────────────────────────

/** Etiquetas legibles para cada entorno. */
export const ENVIRONMENT_LABELS: Record<Environment, string> = {
  dev: "Desarrollo",
  staging: "Staging",
  prod: "Producción",
}

/** Colores (clases Tailwind) para badges de entorno. */
export const ENVIRONMENT_BADGE_COLORS: Record<Environment, string> = {
  dev: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  staging: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  prod: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
}

/** Iconos emoji para cada entorno. */
export const ENVIRONMENT_ICONS: Record<Environment, string> = {
  dev: "🛠️",
  staging: "🧪",
  prod: "🚀",
}

/**
 * Determina el siguiente entorno al que se puede promover.
 * Retorna null si no se puede promover más (ya está en prod).
 */
export function getNextEnvironment(env: Environment): Environment | null {
  return PROMOTION_FLOW[env]
}

/**
 * Verifica si una promoción de source a target es válida según el flujo.
 */
export function isValidPromotion(source: Environment, target: Environment): boolean {
  return PROMOTION_FLOW[source] === target
}

/**
 * Lista de promociones válidas para un workflow basado en los entornos donde está presente.
 * Retorna un array de {source, target} tuples para todas las promociones posibles.
 */
export function getAvailablePromotions(
  currentEnvironments: Environment[]
): Array<{ source: Environment; target: Environment }> {
  const available: Array<{ source: Environment; target: Environment }> = []
  const envSet = new Set(currentEnvironments)

  for (const source of ENVIRONMENTS) {
    const target = PROMOTION_FLOW[source]
    if (target === null) continue
    // Solo ofrecer la promoción si el workflow está en source pero no en target
    if (envSet.has(source) && !envSet.has(target)) {
      available.push({ source, target })
    }
  }
  return available
}
