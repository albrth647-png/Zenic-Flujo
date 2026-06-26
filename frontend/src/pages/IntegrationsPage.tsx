import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "@/components/ui/toast"
import { error as humanError } from "@/utils/humanize"
import {
  Mail,
  Table,
  MessageCircle,
  Loader2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Save,
  Send,
  Plug,
  Trash2,
  Eye,
  EyeOff,
  Unlink,
} from "lucide-react"

// ── Tipos ─────────────────────────────────────

type IntegrationField = {
  key: string
  label: string
  type: "text" | "password" | "textarea"
  required: boolean
}

type Integration = {
  name: string
  title: string
  icon: string
  description: string
  fields: IntegrationField[]
  configured: boolean
  has_token?: boolean
  connected?: boolean
}

const INTEGRATION_ICONS: Record<string, React.ElementType> = {
  gmail: Mail,
  sheets: Table,
  telegram: MessageCircle,
  slack: MessageCircle,
}

const INTEGRATION_COLORS: Record<string, { color: string; bg: string }> = {
  gmail: { color: "text-red-400", bg: "bg-red-500/10" },
  sheets: { color: "text-emerald-400", bg: "bg-emerald-500/10" },
  telegram: { color: "text-sky-400", bg: "bg-sky-500/10" },
  slack: { color: "text-violet-400", bg: "bg-violet-500/10" },
}

// ── Componente ─────────────────────────────────

export default function IntegrationsPage() {
  const { getApi } = useApi()
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<string>("gmail")
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [showDisconnect, setShowDisconnect] = useState<string | null>(null)
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})
  const [formValues, setFormValues] = useState<Record<string, Record<string, string>>>({})

  const loadData = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const data = await api.get("/api/integrations", { signal })
      if (signal?.aborted) return
      const list = (data as Integration[]) || []
      setIntegrations(list)

      // Inicializar formValues con valores vacíos
      const initial: Record<string, Record<string, string>> = {}
      for (const integ of list) {
        initial[integ.name] = {}
        for (const field of integ.fields) {
          initial[integ.name][field.key] = ""
        }
      }
      setFormValues((prev) => ({ ...initial, ...prev }))
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar integraciones", description: humanError(e), variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(ac.signal)
    return () => ac.abort()
  }, [loadData])

  async function handleSave(name: string) {
    setSaving(true)
    try {
      const api = getApi()
      const integ = integrations.find((i) => i.name === name)
      // No enviar campos vacíos si ya hay credenciales guardadas
      const payload = { ...(formValues[name] || {}) }
      if (integ?.configured) {
        for (const key of Object.keys(payload)) {
          if (!payload[key]) delete payload[key]
        }
      }
      const res = await api.post(`/api/integrations/${name}/configure`, payload)
      const r = res as { status?: string; message?: string }
      if (r?.status === "configured") {
        toast({ title: `✅ ${name} configurado`, variant: "success" })
        loadData()
      } else {
        toast({ title: `Error al configurar ${name}`, variant: "error" })
      }
    } catch (e) {
      toast({ title: `Error al configurar ${name}`, description: humanError(e), variant: "error" })
    } finally {
      setSaving(false)
    }
  }

  async function handleTest(name: string) {
    setTesting(name)
    try {
      const api = getApi()
      const res = await api.post(`/api/integrations/${name}/test`)
      const r = res as { status?: string; message?: string }
      if (r?.status === "ok" || r?.status === "sent") {
        toast({ title: `✅ Conexión exitosa: ${r.message || "Todo en orden"}`, variant: "success" })
      } else {
        toast({ title: `❌ ${r?.message || "Error de conexión"}`, variant: "error" })
      }
    } catch (e) {
      toast({ title: "Error al probar conexión", description: humanError(e), variant: "error" })
    } finally {
      setTesting(null)
    }
  }

  async function handleDisconnect(name: string) {
    try {
      const api = getApi()
      await api.post(`/api/integrations/${name}/disconnect`)
      toast({ title: `❌ ${name} desconectado`, variant: "success" })
      setShowDisconnect(null)
      setFormValues((prev) => ({
        ...prev,
        [name]: Object.keys(prev[name] || {}).reduce((acc, k) => ({ ...acc, [k]: "" }), {}),
      }))
      loadData()
    } catch (e) {
      toast({ title: "Error al desconectar", description: humanError(e), variant: "error" })
    }
  }

  function setFormValue(integ: string, key: string, value: string) {
    setFormValues((prev) => ({
      ...prev,
      [integ]: { ...(prev[integ] || {}), [key]: value },
    }))
  }

  function togglePassword(integ: string) {
    setShowPasswords((prev) => ({ ...prev, [integ]: !prev[integ] }))
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-8 w-48 bg-zinc-800" />
          <Skeleton className="mt-1 h-4 w-64 bg-zinc-800" />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-5">
                <Skeleton className="h-5 w-32 bg-zinc-800" />
                <Skeleton className="mt-2 h-3 w-full bg-zinc-800" />
                <Skeleton className="mt-4 h-9 w-full bg-zinc-800" />
                <Skeleton className="mt-2 h-9 w-24 bg-zinc-800" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  const current = integrations.find((i) => i.name === activeTab)

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Integraciones</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Conecta tus servicios favoritos para usarlos directamente desde tus workflows
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadData()}
          disabled={loading}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Recargar
        </Button>
      </div>

      {/* Resumen rápido */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {integrations.map((integ) => {
          const Icon = INTEGRATION_ICONS[integ.name] || Plug
          const colors = INTEGRATION_COLORS[integ.name] || { color: "text-zinc-400", bg: "bg-zinc-500/10" }
          return (
            <button
              key={integ.name}
              onClick={() => setActiveTab(integ.name)}
              className={`rounded-lg border p-4 text-left transition-all ${
                activeTab === integ.name
                  ? "border-indigo-500/50 bg-indigo-500/10"
                  : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${colors.bg}`}>
                  <Icon className={`h-5 w-5 ${colors.color}`} />
                </div>
                {integ.configured ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                ) : (
                  <XCircle className="h-4 w-4 text-zinc-600" />
                )}
              </div>
              <p className="mt-2 text-sm font-medium text-zinc-200">{integ.title}</p>
              <p className="mt-0.5 text-[10px] text-zinc-500">
                {integ.configured ? "Conectado" : "Sin conectar"}
              </p>
            </button>
          )
        })}
      </div>

      {/* Panel de configuración */}
      {current && (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                    INTEGRATION_COLORS[current.name]?.bg || "bg-zinc-500/10"
                  }`}
                >
                  {(() => {
                    const Icon = INTEGRATION_ICONS[current.name] || Plug
                    return (
                      <Icon
                        className={`h-5 w-5 ${INTEGRATION_COLORS[current.name]?.color || "text-zinc-400"}`}
                      />
                    )
                  })()}
                </div>
                <div>
                  <CardTitle className="text-lg text-zinc-100">{current.title}</CardTitle>
                  <p className="text-sm text-zinc-400">{current.description}</p>
                </div>
              </div>
              <Badge
                variant="outline"
                className={
                  current.configured
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                    : "border-zinc-700 text-zinc-400"
                }
              >
                {current.configured ? (
                  <>
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    Conectado
                  </>
                ) : (
                  <>
                    <XCircle className="mr-1 h-3 w-3" />
                    Sin configurar
                  </>
                )}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Campos del formulario */}
            {current.fields.map((field) => (
              <div key={field.key}>
                <label htmlFor={`integration-field-${current.name}-${field.key}`} className="mb-1.5 block text-sm font-medium text-zinc-300">
                  {field.label}
                  {field.required && <span className="ml-1 text-red-400">*</span>}
                </label>
                {field.type === "textarea" ? (
                  <textarea
                    id={`integration-field-${current.name}-${field.key}`}
                    value={formValues[current.name]?.[field.key] || ""}
                    onChange={(e) => setFormValue(current.name, field.key, e.target.value)}
                    placeholder={`Pega el contenido del archivo de configuración aquí…`}
                    rows={4}
                    className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono"
                  />
                ) : (
                  <div className="relative">
                    <Input
                      id={`integration-field-${current.name}-${field.key}`}
                      type={field.type === "password" && !showPasswords[current.name] ? "password" : "text"}
                      value={formValues[current.name]?.[field.key] || ""}
                      onChange={(e) => setFormValue(current.name, field.key, e.target.value)}
                      placeholder={`Ingresa tu ${field.label.toLowerCase()}…`}
                      className="border-zinc-700 bg-zinc-800 pr-9 text-zinc-200 placeholder:text-zinc-500"
                    />
                    {field.type === "password" && (
                      <button
                        type="button"
                        onClick={() => togglePassword(current.name)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                        aria-label={showPasswords[current.name] ? `Ocultar ${field.label}` : `Mostrar ${field.label}`}
                      >
                        {showPasswords[current.name] ? (
                          <EyeOff className="h-4 w-4" />
                        ) : (
                          <Eye className="h-4 w-4" />
                        )}
                      </button>
                    )}
                  </div>
                )}
                {current.configured && !formValues[current.name]?.[field.key] && (
                  <p className="mt-1 text-xs text-zinc-600">
                    Ya hay credenciales guardadas. Deja en blanco para mantener las actuales.
                  </p>
                )}
              </div>
            ))}

            {/* Botones de acción */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Button
                onClick={() => handleSave(current.name)}
                disabled={saving}
                className="bg-indigo-600 text-white hover:bg-indigo-500"
              >
                {saving ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    Guardando…
                  </>
                ) : (
                  <>
                    <Save className="mr-1.5 h-4 w-4" />
                    Guardar configuración
                  </>
                )}
              </Button>

              <Button
                variant="outline"
                onClick={() => handleTest(current.name)}
                disabled={testing === current.name || !current.configured}
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                {testing === current.name ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    Probando…
                  </>
                ) : (
                  <>
                    <Send className="mr-1.5 h-4 w-4" />
                    Probar conexión
                  </>
                )}
              </Button>

              {current.configured && (
                <Button
                  variant="ghost"
                  onClick={() => setShowDisconnect(current.name)}
                  className="ml-auto text-zinc-500 hover:text-red-400"
                >
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  Desconectar
                </Button>
              )}
            </div>

            {/* Ayuda contextual */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-800/20 p-3">
              <p className="text-xs text-zinc-500">
                {current.name === "gmail" &&
                  "Necesitas un proyecto en Google Cloud Console con la API de Gmail activada. Las credenciales OAuth2 se guardan cifradas en la base de datos local."}
                {current.name === "sheets" &&
                  "Crea una service account en Google Cloud Console, activa la API de Sheets y descarga el JSON. Comparte tus hojas con el email de la service account."}
                {current.name === "telegram" &&
                  "Crea un bot con @BotFather en Telegram y copia el token HTTP API. El token se guarda cifrado en la base de datos local."}
                {current.name === "slack" &&
                  "Crea una app en api.slack.com, agrega el scope 'chat:write' y 'channels:read', instala la app en tu workspace y copia el Bot Token."}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diálogo de confirmación para desconectar */}
      <Dialog open={!!showDisconnect} onOpenChange={() => setShowDisconnect(null)}>
        <DialogContent className="max-w-sm border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>¿Desconectar {showDisconnect}?</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Los workflows que usen esta integración dejarán de funcionar. Puedes volver a configurarla después.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDisconnect(null)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => showDisconnect && handleDisconnect(showDisconnect)}
              className="bg-red-600 text-white hover:bg-red-500"
            >
              <Unlink className="mr-1.5 h-4 w-4" />
              Desconectar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
