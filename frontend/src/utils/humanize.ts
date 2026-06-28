/**
 * humanize — Traduce respuestas del backend a español humano
 * ============================================================
 *
 * El backend devuelve valores como "completed", "failed", "idle",
 * "timestamp_wins", etc. Esta utilidad los traduce antes de que
 * lleguen a la UI, para que el usuario vea texto natural.
 *
 * Uso:
 *   import { h } from "@/utils/humanize"
 *   <Badge>{h.status(agent.state)}</Badge>
 *   toast({ title: h.error(err) })
 */

// ── Status ──────────────────────────────────────────────────────────

const STATUS_MAP: Record<string, string> = {
  // Workflow / Execution
  active: "Activo",
  paused: "Pausado",
  archived: "Archivado",
  completed: "Completado",
  failed: "Falló",
  running: "Ejecutando",
  idle: "En espera",
  pending: "Pendiente",
  error: "Error",
  queued: "En cola",
  terminated: "Terminado",
  // Generic
  success: "Éxito",
  ok: "Correcto",
  warning: "Advertencia",
  healthy: "Saludable",
  degraded: "Degradado",
  unhealthy: "No saludable",
  // Sync
  synced: "Sincronizado",
  syncing: "Sincronizando",
  never: "Nunca",
  // Training
  training: "Entrenando",
  // Install
  installed: "Instalado",
  already_installed: "Ya instalado",
  uninstalled: "Desinstalado",
  // Config
  configured: "Configurado",
  not_configured: "Sin configurar",
  connected: "Conectado",
  disconnected: "Desconectado",
}

export function status(value: string): string {
  return STATUS_MAP[value.toLowerCase()] || value
}

// ── Error messages ──────────────────────────────────────────────────

const ERROR_MAP: Record<string, string> = {
  not_found: "No se encontró el recurso solicitado",
  forbidden: "No tienes permiso para realizar esta acción",
  unauthorized: "Debes iniciar sesión para continuar",
  bad_request: "La solicitud no es válida. Revisa los datos ingresados",
  conflict: "Ya existe un recurso con los mismos datos",
  internal_error: "Ocurrió un error interno del servidor",
  timeout: "La operación tardó demasiado y se canceló",
  rate_limited: "Demasiadas solicitudes. Espera unos segundos",
  validation_error: "Algunos campos no son válidos",
  connection_refused: "No se pudo conectar con el servidor",
  network_error: "Error de conexión. Verifica tu red",
  aborted: "La operación fue cancelada",
}

export function error(msg: string | Error | unknown): string {
  if (msg instanceof Error) {
    const key = msg.message.toLowerCase()
    return ERROR_MAP[key] || msg.message
  }
  if (typeof msg === "string") {
    const key = msg.toLowerCase()
    return ERROR_MAP[key] || msg
  }
  return "Error desconocido"
}

// ── Enum values ─────────────────────────────────────────────────────

const ENUM_MAP: Record<string, string> = {
  // Trigger types
  manual: "Manual",
  schedule: "Programado",
  webhook: "Webhook",
  event: "Evento",
  // Workflow status
  active: "Activo",
  paused: "Pausado",
  archived: "Archivado",
  // Agent states
  idle: "En espera",
  running: "Ejecutando",
  // paused: "Pausado" — duplicado de workflow status (línea 97)
  terminated: "Terminado",
  error: "Error",
  // Agent config capabilities
  chat: "Chat",
  analyze: "Analizar",
  generate: "Generar",
  transform: "Transformar",
  // NLU compile status
  valid: "Válido",
  partial: "Parcial",
  invalid: "Inválido",
  ready: "Listo",
  needs_clarification: "Necesita aclaración",
  ambiguous: "Ambiguo",
  unknown: "Desconocido",
  validation_error: "Error de validación",
  // NLU training status
  // idle: "Inactivo" — duplicado de agent states (línea 100)
  queued: "En cola",
  training: "Entrenando",
  completed: "Completado",
  failed: "Falló",
  // Tenant status
  // active: "Activo" — duplicado de workflow status (línea 96)
  suspended: "Suspendido",
  deleted: "Eliminado",
  // Tenant plans
  free: "Gratuito",
  smb: "PyME",
  enterprise: "Empresarial",
  // Partner status
  applicant: "Solicitante",
  // active: "Activo" — duplicado de workflow status (línea 96)
  // suspended: "Suspendido" — duplicado de tenant status (línea 127)
  // terminated: "Terminado" — duplicado de agent states (línea 103)
  // Conflict strategies
  timestamp_wins: "Gana el más reciente",
  version_wins: "Gana versión mayor",
  keep_both: "Mantener ambos",
  // Sync
  export: "Exportación",
  import: "Importación",
  push: "Envío",
  pull: "Descarga",
  // Risk levels
  critical: "Crítico",
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
  // BPMN
  // valid: "Válido" — duplicado de NLU compile status (línea 111)
  // invalid: "Inválido" — duplicado de NLU compile status (línea 113)
  // Fiscal
  issue: "Emitir",
  cancel: "Cancelar",
  verify: "Verificar",
  get_pdf: "Descargar PDF",
  // Environments
  dev: "Desarrollo",
  staging: "Pruebas",
  prod: "Producción",
}

export function enumVal(value: string): string {
  return ENUM_MAP[value.toLowerCase()] || value
}

// ── Dates ───────────────────────────────────────────────────────────

export function date(value: string | number | Date | null | undefined): string {
  if (!value) return "—"
  try {
    const d = new Date(value)
    return d.toLocaleDateString("es-ES", {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return String(value)
  }
}

export function shortDate(value: string | number | Date | null | undefined): string {
  if (!value) return "—"
  try {
    const d = new Date(value)
    return d.toLocaleDateString("es-ES", {
      day: "numeric",
      month: "short",
    })
  } catch {
    return String(value)
  }
}

// ── Numbers ─────────────────────────────────────────────────────────

export function number(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return value.toLocaleString("es-ES")
}

export function percentage(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return `${(value * 100).toFixed(0)}%`
}

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—"
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

// ── IDs ─────────────────────────────────────────────────────────────

export function shortId(id: string | null | undefined): string {
  if (!id) return "—"
  if (id.length <= 12) return id
  return `${id.slice(0, 8)}...`
}

// ── Aggregated helper ───────────────────────────────────────────────

/**
 * h() — shorthand para humanizar objetos de API.
 * Convierte campos conocidos (status, state, plan, etc.) a español.
 */
export function h(obj: Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!obj) return {}
  const result = { ...obj }
  for (const key of ["status", "state", "plan", "tier", "role", "type"]) {
    if (typeof result[key] === "string") {
      result[key] = enumVal(result[key] as string)
    }
  }
  return result
}

// ── Convenience re-export ───────────────────────────────────────────

const humanize = { status, error, enumVal, date, shortDate, number, percentage, duration, shortId, h }
export default humanize
