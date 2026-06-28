import { BrowserRouter, Routes, Route } from "react-router-dom"
import { AuthProvider } from "@/contexts/AuthContext"
import { ThemeProvider } from "@/contexts/ThemeContext"
import { ProtectedRoute } from "@/components/ProtectedRoute"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { AppLayout } from "@/components/AppLayout"

// LoginPage y NotFoundPage se mantienen eager (primera pantalla + fallback)
import LoginPage from "@/pages/LoginPage"
import NotFoundPage from "@/pages/NotFoundPage"

// Config centralizada de rutas protegidas
import { protectedRoutes, type RouteConfig } from "@/router/routes"
import { PATH_LOGIN } from "@/router/paths"

// BUG-6-FE: estos exports son necesarios para tests de wiring
import { EnvironmentsTab } from "@/components/workflows/EnvironmentsTab"
import { PromotionDialog } from "@/components/workflows/PromotionDialog"
export { EnvironmentsTab, PromotionDialog }

/**
 * Renderiza una ruta protegida, opcionalmente con ProtectedRoute si requiere rol.
 */
function renderProtectedRoute(route: RouteConfig) {
  const content = route.element
  if (route.requiredRole) {
    return (
      <Route
        key={route.path}
        path={route.path}
        element={
          <ProtectedRoute requiredRole={route.requiredRole}>
            {content}
          </ProtectedRoute>
        }
      />
    )
  }
  return <Route key={route.path} path={route.path} element={content} />
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
      <ThemeProvider>
      <AuthProvider>
        <Routes>
          {/* Ruta pública: Login */}
          <Route path={PATH_LOGIN} element={<LoginPage />} />

          {/* Rutas protegidas — se renderizan desde la config centralizada */}
          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            {protectedRoutes.map(renderProtectedRoute)}
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
