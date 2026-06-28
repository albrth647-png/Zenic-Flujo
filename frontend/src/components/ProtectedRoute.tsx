import { useEffect, type ReactNode } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"
import { Loader2 } from "lucide-react"

interface ProtectedRouteProps {
  children: ReactNode
  requiredRole?: "admin" | "editor" | "viewer"
}

export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { authenticated, loading, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!loading && !authenticated) {
      // Guarda la ruta a la que quería ir para redirigir después del login
      navigate(`/login?redirect=${encodeURIComponent(location.pathname)}`, {
        replace: true,
      })
    }
  }, [loading, authenticated, navigate, location.pathname])

  // Verifica el rol si es necesario
  useEffect(() => {
    if (!loading && authenticated && requiredRole && user) {
      const roleHierarchy: Record<string, number> = {
        admin: 3,
        editor: 2,
        viewer: 1,
      }
      const userLevel = roleHierarchy[user.role] ?? 0
      const requiredLevel = roleHierarchy[requiredRole] ?? 0
      if (userLevel < requiredLevel) {
        navigate("/app/dashboard", { replace: true })
      }
    }
  }, [loading, authenticated, requiredRole, user, navigate])

  // Mientras carga la autenticación, muestra un placeholder
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center space-y-3">
          <Loader2 className="size-8 animate-spin text-primary mx-auto" />
          <p className="text-sm text-muted-foreground">Cargando...</p>
        </div>
      </div>
    )
  }

  // Si no está autenticado, no renderiza nada (el useEffect redirige)
  if (!authenticated) return null

  return <>{children}</>
}
