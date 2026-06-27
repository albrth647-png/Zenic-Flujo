import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"
import { LazyRoute } from "@/components/LazyRoute"
import { PATH_DASHBOARD } from "@/router/paths"

/**
 * RouteConfig — cada objeto define una ruta protegida bajo /app.
 * Elimina el boilerplate de Suspense y centraliza la config.
 */
export interface RouteConfig {
  path: string
  element: ReactNode
  /** Rol requerido (opcional). Si se omite,任何 usuario autenticado accede. */
  requiredRole?: "admin" | "editor" | "viewer"
}

/**
 * Las rutas protegidas se definen aquí como datos, no como JSX repetitivo.
 * El AppLayout se encarga de wrappear cada una con LazyRoute y
 * opcionalmente con ProtectedRoute si requiredRole está definido.
 */
export const protectedRoutes: RouteConfig[] = [
  { path: "", element: <Navigate to={PATH_DASHBOARD} replace /> },
  { path: "dashboard", element: <LazyRoute loader={() => import("@/pages/Dashboard")} /> },
  { path: "editor", element: <LazyRoute loader={() => import("@/pages/Editor")} /> },
  { path: "workflows", element: <LazyRoute loader={() => import("@/pages/Workflows")} /> },
  { path: "plugins", element: <LazyRoute loader={() => import("@/pages/Plugins")} /> },
  { path: "compliance", element: <LazyRoute loader={() => import("@/pages/Compliance")} /> },
  { path: "sync", element: <LazyRoute loader={() => import("@/pages/SyncCloud")} /> },
  { path: "deploy", element: <LazyRoute loader={() => import("@/pages/Deployments")} /> },
  { path: "chat", element: <LazyRoute loader={() => import("@/pages/ChatPage")} /> },
  { path: "integrations", element: <LazyRoute loader={() => import("@/pages/IntegrationsPage")} /> },
  { path: "crm", element: <LazyRoute loader={() => import("@/pages/CrmPage")} /> },
  { path: "inventory", element: <LazyRoute loader={() => import("@/pages/InventoryPage")} /> },
  { path: "invoices", element: <LazyRoute loader={() => import("@/pages/InvoicesPage")} /> },
  { path: "reports", element: <LazyRoute loader={() => import("@/pages/ReportsPage")} /> },
  { path: "orbital", element: <LazyRoute loader={() => import("@/pages/OrbitalPage")} /> },
  { path: "partners", element: <LazyRoute loader={() => import("@/pages/PartnersPage")} /> },
  { path: "airgap", element: <LazyRoute loader={() => import("@/pages/AirgapPage")} /> },
  { path: "mi-negocio", element: <LazyRoute loader={() => import("@/pages/MiNegocioPage")} /> },
  { path: "facturacion-electronica", element: <LazyRoute loader={() => import("@/pages/FacturacionElectronicaPage")} /> },
  { path: "agents", element: <LazyRoute loader={() => import("@/pages/AgentsPage")} /> },
  { path: "bpmn", element: <LazyRoute loader={() => import("@/pages/BpmnPage")} /> },
  { path: "nlu", element: <LazyRoute loader={() => import("@/pages/NluPage")} /> },
  { path: "tenants", element: <LazyRoute loader={() => import("@/pages/TenantsPage")} /> },
  { path: "settings", element: <LazyRoute loader={() => import("@/pages/Settings")} /> },
  {
    path: "admin",
    requiredRole: "admin" as const,
    element: <LazyRoute loader={() => import("@/pages/AdminPage")} />,
  },
]
