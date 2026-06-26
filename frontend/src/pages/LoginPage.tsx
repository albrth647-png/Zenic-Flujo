import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import {
  LogIn,
  Workflow,
  Eye,
  EyeOff,
  Loader2,
  UserPlus,
  Mail,
  User,
  ArrowLeft,
} from "lucide-react"

export default function LoginPage() {
  const { login, register, authenticated } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // ── Login state ───────────────────────────────────────────
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [focusedField, setFocusedField] = useState<"user" | "pass" | null>(null)

  // ── Register state ────────────────────────────────────────
  const [isRegister, setIsRegister] = useState(false)
  const [regUsername, setRegUsername] = useState("")
  const [regPassword, setRegPassword] = useState("")
  const [regConfirm, setRegConfirm] = useState("")
  const [regDisplayName, setRegDisplayName] = useState("")
  const [regEmail, setRegEmail] = useState("")
  const [showRegPassword, setShowRegPassword] = useState(false)

  // ── Redirect ──────────────────────────────────────────────
  const redirectTo = searchParams.get("redirect") || "/app/dashboard"
  const sessionExpired = searchParams.get("expired") === "1"

  // BUG P1-7: antes se llamaba `navigate(redirectTo)` directamente durante el
  // render (if authenticated { navigate(...); return null }), lo que es un
  // anti-patrón React que puede causar warnings de "Cannot update a component
  // while rendering a different component". Ahora se hace en un useEffect.
  useEffect(() => {
    if (authenticated) {
      navigate(redirectTo, { replace: true })
    }
  }, [authenticated, navigate, redirectTo])

  if (authenticated) {
    return null
  }

  // ── Handlers ──────────────────────────────────────────────

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (!username.trim() || !password.trim()) return
    setLoading(true)
    const success = await login({ username: username.trim(), password })
    setLoading(false)
    if (success) {
      navigate(redirectTo, { replace: true })
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    // Validaciones
    if (!regUsername.trim() || !regPassword.trim()) {
      setError("Usuario y contraseña son requeridos")
      return
    }
    if (regUsername.trim().length < 3) {
      setError("El usuario debe tener al menos 3 caracteres")
      return
    }
    if (regPassword.length < 6) {
      setError("La contraseña debe tener al menos 6 caracteres")
      return
    }
    if (regPassword !== regConfirm) {
      setError("Las contraseñas no coinciden")
      return
    }

    setLoading(true)
    const result = await register({
      username: regUsername.trim(),
      password: regPassword,
      display_name: regDisplayName.trim() || undefined,
      email: regEmail.trim() || undefined,
    })
    setLoading(false)

    if (result.success) {
      navigate(redirectTo, { replace: true })
    } else {
      setError(result.error || "Error al crear la cuenta")
    }
  }

  const toggleMode = () => {
    setIsRegister(!isRegister)
    setError("")
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background via-background to-primary/5 p-4">
      <div className="w-full max-w-md">
        {/* Logo y título */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center size-16 rounded-2xl bg-primary shadow-lg shadow-primary/25 mb-4">
            <Workflow className="size-8 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Zenic Flujo</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Tu plataforma de automatización inteligente
          </p>
        </div>

        {/* Tarjeta */}
        <div className="rounded-2xl border bg-card shadow-xl shadow-black/5">
          <div className="p-6 space-y-6">
            {/* Header */}
            <div className="text-center">
              <h2 className="text-lg font-semibold">
                {isRegister ? "Crear cuenta nueva" : "Bienvenido de vuelta"}
              </h2>
              <p className="text-sm text-muted-foreground mt-1">
                {isRegister
                  ? "Regístrate para empezar a automatizar"
                  : "Ingresa tus datos para continuar"}
              </p>
            </div>

            {/* Aviso de sesión expirada */}
            {sessionExpired && (
              <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
                <p className="font-medium">Tu sesión expiró</p>
                <p className="text-xs mt-0.5 opacity-80">
                  Por seguridad, tu sesión se cerró automáticamente.
                  Inicia sesión de nuevo para continuar.
                </p>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
                <p>{error}</p>
              </div>
            )}

            {/* Login form */}
            {!isRegister ? (
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username" className="text-sm font-medium">
                    Usuario
                  </Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/50" />
                    <Input
                      id="username"
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      onFocus={() => setFocusedField("user")}
                      onBlur={() => setFocusedField(null)}
                      className={cn(
                        "h-10 pl-9 transition-all duration-200",
                        focusedField === "user" && "ring-2 ring-primary/20 border-primary"
                      )}
                      placeholder="Tu usuario"
                      autoComplete="username"
                      autoFocus={!isRegister}
                      disabled={loading}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm font-medium">
                    Contraseña
                  </Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      onFocus={() => setFocusedField("pass")}
                      onBlur={() => setFocusedField(null)}
                      className={cn(
                        "h-10 pl-3 pr-10 transition-all duration-200",
                        focusedField === "pass" && "ring-2 ring-primary/20 border-primary"
                      )}
                      placeholder="Tu contraseña"
                      autoComplete="current-password"
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      tabIndex={-1}
                      aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>

                <Button
                  type="submit"
                  className="w-full h-10 text-sm font-medium"
                  disabled={loading || !username.trim() || !password.trim()}
                >
                  {loading ? (
                    <>
                      <Loader2 className="size-4 mr-2 animate-spin" />
                      Entrando...
                    </>
                  ) : (
                    <>
                      <LogIn className="size-4 mr-2" />
                      Iniciar sesión
                    </>
                  )}
                </Button>
              </form>
            ) : (
              /* Register form */
              <form onSubmit={handleRegister} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="reg-user" className="text-sm font-medium">
                    Usuario <span className="text-red-500">*</span>
                  </Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/50" />
                    <Input
                      id="reg-user"
                      type="text"
                      value={regUsername}
                      onChange={(e) => setRegUsername(e.target.value)}
                      className="h-10 pl-9"
                      placeholder="Elige un nombre de usuario"
                      autoComplete="username"
                      disabled={loading}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reg-name" className="text-sm font-medium">
                    Nombre para mostrar
                  </Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/50" />
                    <Input
                      id="reg-name"
                      type="text"
                      value={regDisplayName}
                      onChange={(e) => setRegDisplayName(e.target.value)}
                      className="h-10 pl-9"
                      placeholder="Tu nombre (opcional)"
                      disabled={loading}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reg-email" className="text-sm font-medium">
                    Correo electrónico
                  </Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground/50" />
                    <Input
                      id="reg-email"
                      type="email"
                      value={regEmail}
                      onChange={(e) => setRegEmail(e.target.value)}
                      className="h-10 pl-9"
                      placeholder="tu@correo.com (opcional)"
                      autoComplete="email"
                      disabled={loading}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reg-password" className="text-sm font-medium">
                    Contraseña <span className="text-red-500">*</span>
                  </Label>
                  <div className="relative">
                    <Input
                      id="reg-password"
                      type={showRegPassword ? "text" : "password"}
                      value={regPassword}
                      onChange={(e) => setRegPassword(e.target.value)}
                      className="h-10 pl-3 pr-10"
                      placeholder="Mínimo 6 caracteres"
                      autoComplete="new-password"
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={() => setShowRegPassword(!showRegPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      tabIndex={-1}
                      aria-label={showRegPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    >
                      {showRegPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reg-confirm" className="text-sm font-medium">
                    Confirmar contraseña <span className="text-red-500">*</span>
                  </Label>
                  <Input
                    id="reg-confirm"
                    type="password"
                    value={regConfirm}
                    onChange={(e) => setRegConfirm(e.target.value)}
                    className="h-10 pl-3"
                    placeholder="Repite la contraseña"
                    autoComplete="new-password"
                    disabled={loading}
                  />
                </div>

                <Button
                  type="submit"
                  className="w-full h-10 text-sm font-medium"
                  disabled={
                    loading ||
                    !regUsername.trim() ||
                    !regPassword.trim() ||
                    !regConfirm.trim() ||
                    regPassword !== regConfirm
                  }
                >
                  {loading ? (
                    <>
                      <Loader2 className="size-4 mr-2 animate-spin" />
                      Creando cuenta...
                    </>
                  ) : (
                    <>
                      <UserPlus className="size-4 mr-2" />
                      Crear cuenta
                    </>
                  )}
                </Button>
              </form>
            )}
          </div>

          {/* Footer: toggle between login / register */}
          <div className="border-t px-6 py-4">
            <button
              type="button"
              onClick={toggleMode}
              className="w-full flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {isRegister ? (
                <>
                  <ArrowLeft className="size-3.5" />
                  ¿Ya tienes cuenta? Inicia sesión
                </>
              ) : (
                <>
                  <UserPlus className="size-3.5" />
                  ¿Primera vez? Crea tu cuenta
                </>
              )}
            </button>
          </div>
        </div>

        {/* Versión */}
        <p className="text-center text-[10px] text-muted-foreground/60 mt-6">
          Zenic Flujo v1.0 — Hecho con determinismo
        </p>
      </div>
    </div>
  )
}
