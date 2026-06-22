import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { AuthProvider } from "@/contexts/AuthContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { AppLayout } from "@/components/AppLayout"
import Dashboard from "@/pages/Dashboard"
import Editor from "@/pages/Editor"
import Workflows from "@/pages/Workflows"
import Settings from "@/pages/Settings"
import Plugins from "@/pages/Plugins"
import Compliance from "@/pages/Compliance"
import SyncCloud from "@/pages/SyncCloud"
import Deployments from "@/pages/Deployments"
import LoginPage from "@/pages/LoginPage"
import NotFoundPage from "@/pages/NotFoundPage"
import ChatPage from "@/pages/ChatPage"
import AdminPage from "@/pages/AdminPage"
import IntegrationsPage from "@/pages/IntegrationsPage"
import CrmPage from "@/pages/CrmPage"
import InventoryPage from "@/pages/InventoryPage"
import InvoicesPage from "@/pages/InvoicesPage"
import ReportsPage from "@/pages/ReportsPage"
import OrbitalPage from "@/pages/OrbitalPage"
import PartnersPage from "@/pages/PartnersPage"
import AirgapPage from "@/pages/AirgapPage"
import MiNegocioPage from "@/pages/MiNegocioPage"

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
      <ThemeProvider>
      <AuthProvider>
        <Routes>
          {/* Ruta pública: Login */}
          <Route path="/login" element={<LoginPage />} />

          {/* Rutas protegidas */}
          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/app/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="editor" element={<Editor />} />
            <Route path="workflows" element={<Workflows />} />
            <Route path="plugins" element={<Plugins />} />
            <Route path="compliance" element={<Compliance />} />
            <Route path="sync" element={<SyncCloud />} />
            <Route path="deploy" element={<Deployments />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="integrations" element={<IntegrationsPage />} />
            <Route path="crm" element={<CrmPage />} />
            <Route path="inventory" element={<InventoryPage />} />
            <Route path="invoices" element={<InvoicesPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="orbital" element={<OrbitalPage />} />
            <Route path="partners" element={<PartnersPage />} />
            <Route path="airgap" element={<AirgapPage />} />
            <Route path="mi-negocio" element={<MiNegocioPage />} />
            <Route path="settings" element={<Settings />} />
          </Route>

          {/* Página 404 */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
      </ThemeProvider>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
