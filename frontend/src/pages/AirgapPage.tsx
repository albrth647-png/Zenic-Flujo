import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  ShieldOff,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Loader2,
  CheckCircle2,
  XCircle,
  Server,
  Globe,
  Lock,
  Key,
  Copy,
  Wifi,
  WifiOff,
  Download,
  AlertTriangle,
  Clock,
} from "lucide-react"

import type { LicenseInfo, LicenseValidation } from "@/types/license"

import { error as humanError } from "@/utils/humanize"
import type { AirgapStatus, AirgapConfig } from "@/types/airgap"

// ── Componentes ────────────────────────────────

function CheckRow({
  name,
  passed,
  message,
}: {
  name: string
  passed: boolean
  message: string
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 transition-colors hover:border-zinc-700">
      <div className="flex items-center gap-3">
        {passed ? (
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400" />
        ) : (
          <XCircle className="h-5 w-5 shrink-0 text-red-400" />
        )}
        <div>
          <p className="text-sm font-medium text-zinc-200">{name}</p>
          <p className="text-xs text-zinc-500">{message}</p>
        </div>
      </div>
      <Badge
        variant="outline"
        className={
          passed
            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
            : "border-red-500/20 bg-red-500/10 text-red-400"
        }
      >
        {passed ? "Aprobado" : "Falló"}
      </Badge>
    </div>
  )
}

// ── Página principal ───────────────────────────

export default function AirgapPage() {
  const { getApi } = useApi()
  const [status, setStatus] = useState<AirgapStatus | null>(null)
  const [config, setConfig] = useState<AirgapConfig | null>(null)
  const [licenseInfo, setLicenseInfo] = useState<LicenseInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState("status")

  // Diálogo crear licencia
  const [showLicenseDialog, setShowLicenseDialog] = useState(false)
  const [licenseForm, setLicenseForm] = useState({ client: "", days: "365" })
  const [licenseResult, setLicenseResult] = useState<{ license_key: string; signature: string } | null>(null)
  const [creating, setCreating] = useState(false)

  // Diálogo verificar licencia
  const [showVerifyDialog, setShowVerifyDialog] = useState(false)
  const [verifyKey, setVerifyKey] = useState("")
  const [verifyResult, setVerifyResult] = useState<{ valid: boolean; customer?: string; days_remaining?: number } | null>(null)
  const [verifying, setVerifying] = useState(false)

  // Diálogo validar licencia online
  const [showValidateDialog, setShowValidateDialog] = useState(false)
  const [validateKey, setValidateKey] = useState("")
  const [validateResult, setValidateResult] = useState<LicenseValidation | null>(null)
  const [validating, setValidating] = useState(false)

  const loadData = useCallback(async (signal?: AbortSignal) => {
    setError(null)
    try {
      const api = getApi()
      const [statusRes, configRes, licenseRes] = await Promise.all([
        api.get("/api/airgap/status", { signal }),
        api.get("/api/airgap/config", { signal }),
        api.get("/api/license/info", { signal }),
      ])
      if (signal?.aborted) return
      setStatus(statusRes as AirgapStatus)
      setConfig(configRes as AirgapConfig)
      setLicenseInfo(licenseRes as LicenseInfo)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar datos", description: humanError(e), variant: "error" })
      setError("No se pudo conectar con el servidor. Verifica que esté corriendo.")
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

  async function handleCreateLicense() {
    if (!licenseForm.client.trim()) return
    setCreating(true)
    setLicenseResult(null)
    try {
      const api = getApi()
      const res = await api.post("/api/airgap/license", {
        client: licenseForm.client.trim(),
        days: parseInt(licenseForm.days) || 365,
      })
      setLicenseResult(res as { license_key: string; signature: string })
    } catch (e) {
      toast({ title: "Error al crear licencia", description: humanError(e), variant: "error" })
    } finally {
      setCreating(false)
    }
  }

  async function handleVerifyLicense() {
    if (!verifyKey.trim()) return
    setVerifying(true)
    setVerifyResult(null)
    try {
      const api = getApi()
      const res = await api.post("/api/airgap/license/verify", { license_key: verifyKey.trim() })
      setVerifyResult(res as { valid: boolean; customer?: string; days_remaining?: number })
    } catch (e) {
      toast({ title: "Error al verificar licencia", description: humanError(e), variant: "error" })
    } finally {
      setVerifying(false)
    }
  }

  async function handleValidateLicense() {
    if (!validateKey.trim()) return
    setValidating(true)
    setValidateResult(null)
    try {
      const api = getApi()
      const res = await api.post("/api/license/validate", { key: validateKey.trim() })
      setValidateResult(res as LicenseValidation)
      loadData()
    } catch (e) {
      toast({ title: "Error al validar licencia", description: humanError(e), variant: "error" })
    } finally {
      setValidating(false)
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
  }

  const allChecks = status?.checks ? Object.entries(status.checks) : []
  const passedChecks = allChecks.filter(([, c]) => c.passed).length
  const totalChecks = allChecks.length

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
            <ShieldOff className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Modo Air-Gapped</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Entornos aislados sin conexión a internet
            </p>
          </div>
        </div>
        <Card className="border-red-800 bg-red-900/20">
          <CardContent className="flex flex-col items-center justify-center p-12">
            <XCircle className="h-12 w-12 text-red-400" />
            <h3 className="mt-4 text-sm font-medium text-zinc-300">Error de conexión</h3>
            <p className="mt-2 text-sm text-zinc-500 text-center max-w-md">{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadData()}
              className="mt-4 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              <RefreshCw className="mr-1.5 h-4 w-4" />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 bg-zinc-800" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 rounded-lg bg-zinc-800" />
          ))}
        </div>
        <Skeleton className="h-48 rounded-lg bg-zinc-800" />
      </div>
    )
  }

  const isAirgap = config?.mode === "airgap"
  const isOnline = config?.mode === "online"

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
            {isAirgap ? (
              <ShieldOff className="h-5 w-5 text-indigo-400" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-indigo-400" />
            )}
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Modo Air-Gapped</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Entornos aislados sin conexión a internet — seguridad máxima
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadData()}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Recargar
        </Button>
      </div>

      {/* Tarjetas de estado */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            {isAirgap ? (
              <ShieldOff className="h-5 w-5 text-amber-400" />
            ) : (
              <Globe className="h-5 w-5 text-emerald-400" />
            )}
          </div>
          <p className="mt-2 text-lg font-bold text-zinc-100">
            {isAirgap ? "Aislado" : "En línea"}
          </p>
          <p className="mt-1 text-xs text-zinc-500">Modo de operación</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            {status?.all_passed ? (
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-red-400" />
            )}
          </div>
          <p className="mt-2 text-lg font-bold text-zinc-100">
            {passedChecks}/{totalChecks}
          </p>
          <p className="mt-1 text-xs text-zinc-500">Validaciones aprobadas</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <Lock className="h-5 w-5 text-zinc-600" />
          </div>
          <p className="mt-2 text-lg font-bold text-zinc-100">
            {licenseInfo?.type || "Free"}
          </p>
          <p className="mt-1 text-xs text-zinc-500">Tipo de licencia</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            {isOnline ? (
              <Wifi className="h-5 w-5 text-emerald-400" />
            ) : (
              <WifiOff className="h-5 w-5 text-zinc-500" />
            )}
          </div>
          <p className="mt-2 text-lg font-bold text-zinc-100">{config?.version || "—"}</p>
          <p className="mt-1 text-xs text-zinc-500">Versión del sistema</p>
        </div>
      </div>

      {/* Tabs: Validación, Configuración, Licencias */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="border-zinc-800 bg-zinc-900 flex-wrap">
          <TabsTrigger
            value="status"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <ShieldCheck className="mr-1.5 h-4 w-4" />
            Estado de validación
          </TabsTrigger>
          <TabsTrigger
            value="config"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Server className="mr-1.5 h-4 w-4" />
            Configuración
          </TabsTrigger>
          <TabsTrigger
            value="license"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Key className="mr-1.5 h-4 w-4" />
            Licencias
          </TabsTrigger>
        </TabsList>

        {/* ── Estado de validación ── */}
        <TabsContent value="status" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4" />
                Verificaciones
                {totalChecks > 0 && (
                  <span className="text-xs font-normal text-zinc-600">
                    ({passedChecks}/{totalChecks} aprobados)
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {totalChecks === 0 ? (
                <div className="flex h-32 flex-col items-center justify-center text-sm text-zinc-500">
                  <ShieldOff className="mb-2 h-8 w-8 text-zinc-600" />
                  <p>El modo air-gapped no está habilitado</p>
                  <p className="text-xs text-zinc-600">
                    Activa el modo en la configuración para ver las validaciones
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {allChecks.map(([name, check]) => (
                    <CheckRow key={name} name={name} passed={check.passed} message={check.message} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Configuración ── */}
        <TabsContent value="config" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                  <Globe className="h-4 w-4" />
                  Conectores cloud ({config?.cloud_connectors.length || 0})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {!config?.cloud_connectors || config.cloud_connectors.length === 0 ? (
                  <p className="text-sm text-zinc-500">No hay conectores cloud configurados</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {config.cloud_connectors.map((name) => (
                      <Badge
                        key={name}
                        variant="outline"
                        className="border-zinc-700 bg-zinc-800 text-zinc-400"
                      >
                        {name}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                  <Server className="h-4 w-4" />
                  Conectores locales ({config?.local_connectors.length || 0})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {!config?.local_connectors || config.local_connectors.length === 0 ? (
                  <p className="text-sm text-zinc-500">No hay conectores locales configurados</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {config.local_connectors.map((name) => (
                      <Badge
                        key={name}
                        variant="outline"
                        className="border-zinc-700 bg-zinc-800 text-zinc-400"
                      >
                        {name}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {config?.internal_dns && (
              <Card className="md:col-span-2 border-zinc-800 bg-zinc-900/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                    <Server className="h-4 w-4" />
                    DNS interno
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <code className="rounded bg-zinc-800 px-3 py-1.5 text-sm text-zinc-300">
                    {config.internal_dns}
                  </code>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* ── Licencias ── */}
        <TabsContent value="license" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Licencia actual */}
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                  <Key className="h-4 w-4" />
                  Licencia actual
                </CardTitle>
              </CardHeader>
              <CardContent>
                {licenseInfo ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between text-zinc-400">
                      <span>Tipo</span>
                      <span className="font-medium text-zinc-200 capitalize">
                        {licenseInfo.type || "Free"}
                      </span>
                    </div>
                    <div className="flex justify-between text-zinc-400">
                      <span>Cliente</span>
                      <span className="font-medium text-zinc-200">
                        {licenseInfo.client_name || "—"}
                      </span>
                    </div>
                    <div className="flex justify-between text-zinc-400">
                      <span>Workflows máx.</span>
                      <span className="font-medium text-zinc-200">
                        {licenseInfo.max_workflows && licenseInfo.max_workflows > 0
                          ? licenseInfo.max_workflows
                          : "Ilimitados"}
                      </span>
                    </div>
                    {licenseInfo.is_free && (
                      <div className="mt-3 rounded-lg bg-amber-500/10 p-3 text-xs text-amber-400">
                        <AlertTriangle className="mr-1 inline h-3 w-3" />
                        Estás usando el plan gratuito. Algunas funciones están limitadas.
                      </div>
                    )}
                    {licenseInfo.is_trial && licenseInfo.expires_at && (
                      <div className="mt-3 rounded-lg bg-blue-500/10 p-3 text-xs text-blue-400">
                        <Clock className="mr-1 inline h-3 w-3" />
                        Periodo de prueba — vence el{" "}
                        {new Date(licenseInfo.expires_at).toLocaleDateString("es-MX")}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-zinc-500">Cargando información de licencia…</p>
                )}

                <div className="mt-4 flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setValidateKey("")
                      setValidateResult(null)
                      setShowValidateDialog(true)
                    }}
                    className="flex-1 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <Key className="mr-1.5 h-3.5 w-3.5" />
                    Validar licencia
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Licencia offline */}
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                  <ShieldOff className="h-4 w-4" />
                  Licencia offline
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-3 text-sm text-zinc-500">
                  Crea licencias para entornos air-gapped sin conexión a internet.
                  La licencia incluye una firma criptográfica para verificación offline.
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setLicenseForm({ client: "", days: "365" })
                      setLicenseResult(null)
                      setShowLicenseDialog(true)
                    }}
                    className="flex-1 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <Download className="mr-1.5 h-3.5 w-3.5" />
                    Crear licencia
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setVerifyKey("")
                      setVerifyResult(null)
                      setShowVerifyDialog(true)
                    }}
                    className="flex-1 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
                    Verificar
                  </Button>
                </div>

                {licenseResult && (
                  <div className="mt-3 space-y-2 rounded-lg bg-emerald-500/10 p-3">
                    <p className="text-xs font-medium text-emerald-400">Licencia creada exitosamente</p>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-zinc-500">Key:</span>
                        <button
                          onClick={() => copyToClipboard(licenseResult.license_key)}
                          className="flex items-center gap-1 text-[10px] text-zinc-300 hover:text-zinc-100"
                        >
                          <code className="truncate max-w-[180px] block">{licenseResult.license_key}</code>
                          <Copy className="h-3 w-3 shrink-0" />
                        </button>
                      </div>
                      {licenseResult.signature && (
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] text-zinc-500">Firma:</span>
                          <code className="text-[10px] text-zinc-400 truncate max-w-[200px] block">
                            {licenseResult.signature.substring(0, 32)}…
                          </code>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      {/* ── Diálogo crear licencia offline ── */}
      <Dialog open={showLicenseDialog} onOpenChange={setShowLicenseDialog}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>            Crear licencia sin conexión</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Genera una licencia firmada para entornos sin conexión
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label htmlFor="airgap-license-client" className="mb-1 block text-sm text-zinc-300">
                Cliente <span className="text-red-400">*</span>
              </label>
              <Input
                id="airgap-license-client"
                value={licenseForm.client}
                onChange={(e) => setLicenseForm({ ...licenseForm, client: e.target.value })}
                placeholder="Nombre del cliente o empresa"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="airgap-license-days" className="mb-1 block text-sm text-zinc-300">Días de validez</label>
              <Input
                id="airgap-license-days"
                type="number"
                min={1}
                value={licenseForm.days}
                onChange={(e) => setLicenseForm({ ...licenseForm, days: e.target.value })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Por defecto 365 días (1 año)
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowLicenseDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleCreateLicense}
              disabled={creating || !licenseForm.client.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {creating ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Creando…
                </>
              ) : (
                <>
                  <Download className="mr-1.5 h-4 w-4" />
                  Crear licencia
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Diálogo verificar licencia ── */}
      <Dialog open={showVerifyDialog} onOpenChange={setShowVerifyDialog}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Verificar licencia offline</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Verifica una licencia air-gapped existente
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label htmlFor="airgap-verify-key" className="mb-1 block text-sm text-zinc-300">Clave de licencia</label>
              <Input
                id="airgap-verify-key"
                value={verifyKey}
                onChange={(e) => setVerifyKey(e.target.value)}
                placeholder="ag-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>

            {verifyResult && (
              <div
                className={`rounded-lg p-3 text-sm ${
                  verifyResult.valid
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-red-500/10 text-red-400"
                }`}
              >
                <div className="flex items-center gap-2">
                  {verifyResult.valid ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  <span className="font-medium">
                    {verifyResult.valid ? "Licencia válida" : "Licencia inválida"}
                  </span>
                </div>
                {verifyResult.valid && verifyResult.customer && (
                  <p className="mt-1 text-xs opacity-80">
                    Cliente: {verifyResult.customer}
                    {verifyResult.days_remaining !== undefined && (
                      <> · {verifyResult.days_remaining} días restantes</>
                    )}
                  </p>
                )}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowVerifyDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cerrar
            </Button>
            <Button
              onClick={handleVerifyLicense}
              disabled={verifying || !verifyKey.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {verifying ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Verificando…
                </>
              ) : (
                "Verificar"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Diálogo validar licencia online ── */}
      <Dialog open={showValidateDialog} onOpenChange={setShowValidateDialog}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Validar licencia</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Ingresa tu clave de licencia para activar el producto
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label htmlFor="airgap-validate-key" className="mb-1 block text-sm text-zinc-300">Clave de licencia</label>
              <Input
                id="airgap-validate-key"
                value={validateKey}
                onChange={(e) => setValidateKey(e.target.value)}
                placeholder="WFD-XXXX-XXXX-XXXX-XXXX"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>

            {validateResult && (
              <div
                className={`rounded-lg p-3 text-sm ${
                  validateResult.valid
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-red-500/10 text-red-400"
                }`}
              >
                <div className="flex items-center gap-2">
                  {validateResult.valid ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  <span className="font-medium">
                    {validateResult.valid ? "Licencia activada" : "Clave inválida"}
                  </span>
                </div>
                {validateResult.valid && (
                  <p className="mt-1 text-xs opacity-80">
                    Tipo: {validateResult.type}
                    {validateResult.client_name && <> · {validateResult.client_name}</>}
                  </p>
                )}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowValidateDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleValidateLicense}
              disabled={validating || !validateKey.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {validating ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Validando…
                </>
              ) : (
                "Validar"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
