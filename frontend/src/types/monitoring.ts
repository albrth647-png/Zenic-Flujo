/**
 * Tipos para Sprint 11 — Monitoreo + Alertas.
 *
 * Refleja las estructuras que devuelve el backend en:
 * - src/observability/alerts.py
 * - src/web/blueprints/admin.py (endpoints /api/admin/*)
 */

// ─── Métricas ──────────────────────────────────────────────────────────

/** Métricas de la cola de workflows. */
export interface WorkQueueMetrics {
  depth?: number
  throughput_per_minute?: number
  processing?: number
  failed?: number
  completed?: number
  [key: string]: unknown
}

/** Métricas de la dead letter queue. */
export interface DeadLetterStats {
  total?: number
  by_status?: Record<string, number>
  top_workflows?: Array<{ workflow_id: number; count: number }>
  [key: string]: unknown
}

/** Estadísticas de ejecución de workflows por status. */
export interface WorkflowStatusStats {
  count: number
  avg_duration_ms: number | null
  max_duration_ms: number | null
}

/** Respuesta de GET /api/admin/metrics */
export interface AdminMetricsResponse {
  workqueue: WorkQueueMetrics
  dead_letter: DeadLetterStats
  workflow_stats_1h: Record<string, WorkflowStatusStats>
  slowest_workflows_1h: Array<{
    workflow_id: number
    workflow_name: string
    duration_ms: number
    status: string
    started_at: string
  }>
  timeline_24h: Array<{
    hour: string
    status: string
    count: number
  }>
  timestamp: string
}

// ─── Alertas ───────────────────────────────────────────────────────────

export type AlertSeverity = "info" | "warning" | "critical"
export type AlertStatus = "active" | "resolved" | "suppressed"

export interface AlertEvent {
  id: number
  rule_name: string
  severity: AlertSeverity
  metric_value: number
  threshold: number
  message: string
  channels_notified: string[]
  created_at: string
  resolved_at: string | null
  status: AlertStatus
}

export interface AlertRule {
  name: string
  description: string
  metric_name: string
  threshold: number
  comparison: "gt" | "lt" | "gte" | "lte" | "eq"
  severity: AlertSeverity
  enabled: boolean
  channels: string[]
  cooldown_seconds: number
}

export interface AlertStats {
  by_severity: Record<string, Record<string, number>>
  total_active: number
  total_resolved: number
  rules_count: number
}

/** Respuesta de GET /api/admin/alerts */
export interface AlertListResponse {
  total: number
  limit: number
  offset: number
  alerts: AlertEvent[]
}

/** Respuesta de GET /api/admin/alerts/rules */
export interface AlertRulesResponse {
  rules: AlertRule[]
  total: number
}

/** Respuesta de POST /api/admin/alerts/evaluate */
export interface EvaluateAlertsResponse {
  triggered_count: number
  alerts: AlertEvent[]
}

// ─── Helpers ───────────────────────────────────────────────────────────

export const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  info: "Info",
  warning: "Advertencia",
  critical: "Crítica",
}

export const SEVERITY_BADGE_COLORS: Record<AlertSeverity, string> = {
  info: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  warning: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  critical: "bg-red-500/10 text-red-400 border-red-500/20",
}

export const SEVERITY_ICONS: Record<AlertSeverity, string> = {
  info: "ℹ️",
  warning: "⚠️",
  critical: "🚨",
}

export const STATUS_LABELS: Record<AlertStatus, string> = {
  active: "Activa",
  resolved: "Resuelta",
  suppressed: "Suprimida",
}

export const STATUS_BADGE_COLORS: Record<AlertStatus, string> = {
  active: "bg-red-500/10 text-red-400 border-red-500/20",
  resolved: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  suppressed: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
}

/** Formatea una comparación para mostrar en UI. */
export function formatComparison(
  comparison: AlertRule["comparison"],
  threshold: number
): string {
  const symbols: Record<AlertRule["comparison"], string> = {
    gt: ">",
    lt: "<",
    gte: "≥",
    lte: "≤",
    eq: "=",
  }
  return `${symbols[comparison]} ${threshold}`
}
