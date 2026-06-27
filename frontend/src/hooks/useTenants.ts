/**
 * useTenants — Hook para gestión de Tenants (multi-tenancy)
 * ==========================================================
 *
 * Endpoints:
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

import { useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import type {
  TenantCreate,
  TenantUpdate,
  TenantResponse,
  TenantStatusResponse,
  TenantUserCreate,
  TenantUserResponse,
  TenantFeaturesResponse,
  TenantFeatureToggle,
  TenantFeatureToggleResponse,
} from "@/types/tenants"

const BASE = "/api/v2/tenants"

export function useTenants() {
  const { getApi } = useApi()

  const createTenant = useCallback(
    async (data: TenantCreate): Promise<TenantResponse | null> => {
      const api = getApi()
      return api.post(BASE, data)
    },
    [getApi],
  )

  const getTenant = useCallback(
    async (tenantId: string): Promise<TenantResponse | null> => {
      const api = getApi()
      return api.get(`${BASE}/${tenantId}`)
    },
    [getApi],
  )

  const updateTenant = useCallback(
    async (tenantId: string, data: TenantUpdate): Promise<TenantResponse | null> => {
      const api = getApi()
      return api.put(`${BASE}/${tenantId}`, data)
    },
    [getApi],
  )

  const deleteTenant = useCallback(
    async (tenantId: string): Promise<null> => {
      const api = getApi()
      return api.delete(`${BASE}/${tenantId}`)
    },
    [getApi],
  )

  const suspendTenant = useCallback(
    async (tenantId: string): Promise<TenantStatusResponse | null> => {
      const api = getApi()
      return api.post(`${BASE}/${tenantId}/suspend`, {})
    },
    [getApi],
  )

  const activateTenant = useCallback(
    async (tenantId: string): Promise<TenantStatusResponse | null> => {
      const api = getApi()
      return api.post(`${BASE}/${tenantId}/activate`, {})
    },
    [getApi],
  )

  const listUsers = useCallback(
    async (tenantId: string): Promise<TenantUserResponse[] | null> => {
      const api = getApi()
      return api.get(`${BASE}/${tenantId}/users`)
    },
    [getApi],
  )

  const addUser = useCallback(
    async (tenantId: string, data: TenantUserCreate): Promise<TenantUserResponse | null> => {
      const api = getApi()
      return api.post(`${BASE}/${tenantId}/users`, data)
    },
    [getApi],
  )

  const listFeatures = useCallback(
    async (tenantId: string): Promise<TenantFeaturesResponse | null> => {
      const api = getApi()
      return api.get(`${BASE}/${tenantId}/features`)
    },
    [getApi],
  )

  const toggleFeature = useCallback(
    async (tenantId: string, feature: string, enabled: boolean): Promise<TenantFeatureToggleResponse | null> => {
      const api = getApi()
      return api.put(`${BASE}/${tenantId}/features/${feature}`, { enabled } as TenantFeatureToggle)
    },
    [getApi],
  )

  return {
    createTenant,
    getTenant,
    updateTenant,
    deleteTenant,
    suspendTenant,
    activateTenant,
    listUsers,
    addUser,
    listFeatures,
    toggleFeature,
  }
}
