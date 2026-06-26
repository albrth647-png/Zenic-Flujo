import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import type { AuthState, LoginCredentials, LoginResponse, User, AuthContextValue, RegisterData } from "@/types/auth"
import { toast } from "@/components/ui/toast"

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    authenticated: false,
    loading: true,
  })
  const checkInProgress = useRef(false)

  // ── Registrar nuevo usuario ────────────────────────────
  const register = useCallback(async (data: RegisterData): Promise<{ success: boolean; error?: string }> => {
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
        credentials: "include",
      })

      const result = await res.json()

      if (res.ok && result.status === "ok") {
        setState({
          user: {
            id: result.id,
            username: result.user,
            role: (result.role as User["role"]) || "editor",
            display_name: data.display_name,
            email: data.email,
          },
          authenticated: true,
          loading: false,
        })
        toast({
          title: "Cuenta creada",
          description: "Bienvenido a Zenic Flujo",
          variant: "success",
        })
        return { success: true }
      }

      return { success: false, error: result.message || result.error || "Error al crear la cuenta" }
    } catch {
      toast({
        title: "Error de conexión",
        description: "No pudimos conectar con el servidor",
        variant: "error",
      })
      return { success: false, error: "Error de conexión" }
    }
  }, [])

  // ── Verifica si hay sesión activa al cargar ──────────────────
  const checkAuth = useCallback(async (signal?: AbortSignal) => {
    if (checkInProgress.current) return
    checkInProgress.current = true
    try {
      const res = await fetch("/api/auth/status", { credentials: "include", signal })
      if (signal?.aborted) {
        checkInProgress.current = false
        return
      }
      if (res.ok) {
        const data = await res.json()
        if (signal?.aborted) {
          checkInProgress.current = false
          return
        }
        setState({
          user: data.user || null,
          authenticated: data.authenticated === true,
          loading: false,
        })
        checkInProgress.current = false
        return
      }
    } catch {
      // Si hay error de red, no pasa nada
    }
    if (signal?.aborted) {
      checkInProgress.current = false
      return
    }
    setState({ user: null, authenticated: false, loading: false })
    checkInProgress.current = false
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkAuth(ac.signal)
    return () => ac.abort()
  }, [checkAuth])

  // ── Iniciar sesión ───────────────────────────────────────────
  const login = useCallback(async (credentials: LoginCredentials): Promise<boolean> => {
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
        credentials: "include",
      })

      const data = await res.json() as LoginResponse

      if (res.ok && data.status === "ok") {
        // Fix Sprint 4 bug #57: antes hardcodeaba id:1 y default role:'admin'.
        // Ahora usa data.user_id real del backend (o fallback a 0 si no viene),
        // y default role:'viewer' (least-privilege) si el backend no envía role.
        setState({
          user: {
            id: (data as { user_id?: number }).user_id ?? 0,
            username: data.user,
            role: (data.role as User["role"]) || "viewer",
          },
          authenticated: true,
          loading: false,
        })
        return true
      }

      // Si las credenciales son inválidas
      if (res.status === 401) {
        toast({
          title: "Usuario o contraseña incorrectos",
          description: "Revisa tus datos e inténtalo de nuevo",
          variant: "error",
        })
        return false
      }

      // Si el usuario está desactivado
      if (res.status === 403) {
        toast({
          title: "Tu cuenta está desactivada",
          description: "Habla con tu administrador para recuperar el acceso",
          variant: "error",
        })
        return false
      }

      // Demasiados intentos
      if (res.status === 429) {
        toast({
          title: "Demasiados intentos fallidos",
          description: "Espera 15 minutos antes de volver a intentarlo",
          variant: "error",
        })
        return false
      }

      toast({
        title: "Algo salió mal",
        description: data.message || data.error || "No pudimos iniciar sesión",
        variant: "error",
      })
      return false
    } catch {
      toast({
        title: "Error de conexión",
        description: "Revisa tu conexión a internet y vuelve a intentarlo",
        variant: "error",
      })
      return false
    }
  }, [])

  // ── Cerrar sesión ────────────────────────────────────────────
  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
      })
    } catch {
      // Si falla el logout, igual limpiamos el estado
    }
    setState({ user: null, authenticated: false, loading: false })
  }, [])

  const value = useMemo(
    () => ({ ...state, login, register, logout, checkAuth }),
    [state, login, register, logout, checkAuth]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
