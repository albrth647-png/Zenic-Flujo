/**
 * Types — Tenants (Multi-tenancy)
 * ================================
 *
 * Tipos para los 10 endpoints del router de tenants:
 *   POST   /api/v2/tenants                          — Crear tenant
 *   GET    /api/v2/tenants/{id}                     — Obtener tenant
 *   PUT    /api/v2/tenants/{id}                     — Actualizar tenant
 *   DELETE /api/v2/tenants/{id}                     — Eliminar tenant
 *   POST   /api/v2/tenants/{id}/suspend             — Suspender
 *   POST   /api/v2/tenants/{id}/activate            — Activar
 *   GET    /api/v2/tenants/{id}/users               — Listar usuarios
 *   POST   /api/v2/tenants/{id}/users               — Agregar usuario
 *   GET    /api/v2/tenants/{id}/features            — Listar features
 *   PUT    /api/v2/tenants/{id}/features/{feature}  — Toggle feature
 */

// ── Tenant CRUD ──────────────────────────────────────────────────────

export interface TenantCreate {
  name: string
  slug: string
  plan?: "free" | "smb" | "enterprise"
  config?: Record<string, unknown>
}

export interface TenantUpdate {
  name?: string
  domain?: string
  plan?: "free" | "smb" | "enterprise"
  config?: Record<string, unknown>
}

export interface TenantResponse {
  id: string
  name: string
  slug: string
  domain: string | null
  plan: string
  status: "active" | "suspended" | "deleted"
  config: Record<string, unknown>
  features: Record<string, boolean>
  settings: Record<string, string>
  created_at: string | null
  updated_at: string | null
}

// ── Suspend / Activate ───────────────────────────────────────────────

export interface TenantStatusResponse {
  status: "suspended" | "active"
  tenant_id: string
}

// ── Users ────────────────────────────────────────────────────────────

export interface TenantUserCreate {
  username: string
  password: string
  role: "admin" | "editor" | "viewer"
  display_name?: string
  email?: string
}

export interface TenantUserResponse {
  id: number
  username: string
  role: string
  display_name: string
  email: string
  is_active: number
  created_at: string | null
}

// ── Features ─────────────────────────────────────────────────────────

export interface TenantFeature {
  name: string
  enabled: boolean
}

export interface TenantFeaturesResponse {
  tenant_id: string
  features: TenantFeature[]
  total: number
}

export interface TenantFeatureToggle {
  enabled: boolean
}

export interface TenantFeatureToggleResponse {
  tenant_id: string
  feature: string
  enabled: boolean
}
