/**
 * Paths — Constantes de ruta del frontend.
 * Centraliza todas las rutas para eliminar strings mágicos.
 * Importar desde aquí en vez de escribir strings literales.
 */

// ── Rutas públicas ───────────────────────────────────────────────────
export const PATH_LOGIN = "/login"

// ── Rutas protegidas (bajo /app) ─────────────────────────────────────
export const PATH_APP = "/app"
export const PATH_DASHBOARD = "/app/dashboard"
export const PATH_EDITOR = "/app/editor"
export const PATH_WORKFLOWS = "/app/workflows"
export const PATH_PLUGINS = "/app/plugins"
export const PATH_COMPLIANCE = "/app/compliance"
export const PATH_SYNC = "/app/sync"
export const PATH_DEPLOY = "/app/deploy"
export const PATH_CHAT = "/app/chat"
export const PATH_ADMIN = "/app/admin"
export const PATH_INTEGRATIONS = "/app/integrations"
export const PATH_CRM = "/app/crm"
export const PATH_INVENTORY = "/app/inventory"
export const PATH_INVOICES = "/app/invoices"
export const PATH_REPORTS = "/app/reports"
export const PATH_ORBITAL = "/app/orbital"
export const PATH_PARTNERS = "/app/partners"
export const PATH_AIRGAP = "/app/airgap"
export const PATH_MI_NEGOCIO = "/app/mi-negocio"
export const PATH_FACTURACION_ELECTRONICA = "/app/facturacion-electronica"
export const PATH_AGENTS = "/app/agents"
export const PATH_BPMN = "/app/bpmn"
export const PATH_NLU = "/app/nlu"
export const PATH_TENANTS = "/app/tenants"
export const PATH_SETTINGS = "/app/settings"

// ── Agrupaciones útiles ──────────────────────────────────────────────
export const PROTECTED_PATHS = [
  PATH_DASHBOARD,
  PATH_EDITOR,
  PATH_WORKFLOWS,
  PATH_PLUGINS,
  PATH_COMPLIANCE,
  PATH_SYNC,
  PATH_DEPLOY,
  PATH_CHAT,
  PATH_ADMIN,
  PATH_INTEGRATIONS,
  PATH_CRM,
  PATH_INVENTORY,
  PATH_INVOICES,
  PATH_REPORTS,
  PATH_ORBITAL,
  PATH_PARTNERS,
  PATH_AIRGAP,
  PATH_MI_NEGOCIO,
  PATH_FACTURACION_ELECTRONICA,
  PATH_AGENTS,
  PATH_BPMN,
  PATH_NLU,
  PATH_TENANTS,
  PATH_SETTINGS,
] as const

export const ADMIN_PATHS = [PATH_ADMIN] as const
