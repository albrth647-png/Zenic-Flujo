import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import { error as humanError } from "@/utils/humanize"
import {
  FileText,
  RefreshCw,
  Loader2,
  Send,
  Globe,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldCheck,
  Key,
} from "lucide-react"

// ── Types ──────────────────────────────────────

interface FiscalResponse {
  success: boolean
  country: string
  action: string
  country_tracking_id: string
  xml: string
  pdf_base64: string
  government_response: Record<string, unknown>
  reject_code: string
  reject_message: string
  error: string
  dispatched_at: string
}

// ── Country labels ─────────────────────────────

const COUNTRY_LABELS: Record<string, { name: string; authority: string }> = {
  AR: { name: "Argentina", authority: "AFIP" },
  MX: { name: "México", authority: "SAT" },
  BR: { name: "Brasil", authority: "SEFAZ" },
  CL: { name: "Chile", authority: "SII" },
  CO: { name: "Colombia", authority: "DIAN" },
  PE: { name: "Perú", authority: "SUNAT" },
  EC: { name: "Ecuador", authority: "SRI" },
}

// ── Componente ─────────────────────────────────

export default function FacturacionElectronicaPage() {
  const { getApi } = useApi()
  const [loading, setLoading] = useState(true)
  const [issuing, setIssuing] = useState(false)
  const [supportedCountries, setSupportedCountries] = useState<string[]>([])
  const [availableCountries, setAvailableCountries] = useState<string[]>([])
  const [lastResult, setLastResult] = useState<FiscalResponse | null>(null)
  const [licenseKey, setLicenseKey] = useState("")
  const [form, setForm] = useState({
    country: "MX",
    action: "issue",
    emisor_rfc: "",
    emisor_name: "",
    receptor_rfc: "",
    receptor_name: "",
    concepto_clave: "01010101",
    concepto_cantidad: 1,
    concepto_precio: 100,
    concepto_descripcion: "Servicio de prueba",
    cert_path: "",
    cert_password: "",
  })

  // ── Load supported countries ─────────────────

  const loadCountries = useCallback(async () => {
    try {
      const api = getApi()
      const data = (await api.get("/api/v2/fiscal/countries")) as {
        supported: string[]
        available: string[]
        unavailable: string[]
      }
      setSupportedCountries(data.supported)
      setAvailableCountries(data.available)
    } catch (e) {
      toast({ title: "Error al cargar países", description: humanError(e), variant: "error" })
    } finally {
      setLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    // Carga inicial de países soportados. `loadCountries` es async y los
    // setState ocurren tras `await api.get(...)` (no sincrónicos), pero la
    // regla react-hooks/set-state-in-effect no puede ver eso a través del
    // useCallback. Es un falso positivo legítimo para carga inicial de datos.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCountries()
  }, [loadCountries])

  // ── Issue fiscal document ────────────────────

  const handleIssue = async () => {
    setIssuing(true)
    setLastResult(null)
    try {
      const api = getApi()
      const payload = {
        country: form.country,
        action_params: {
          emisor: { rfc: form.emisor_rfc, razon_social: form.emisor_name },
          receptor: { rfc: form.receptor_rfc, razon_social: form.receptor_name },
          conceptos: [
            {
              clave_prod_serv: form.concepto_clave,
              cantidad: Number(form.concepto_cantidad),
              valor_unitario: Number(form.concepto_precio),
              descripcion: form.concepto_descripcion,
            },
          ],
          forma_pago: "01",
          metodo_pago: "PUE",
          uso_cfdi: "G03",
        },
        credentials: {
          rfc: form.emisor_rfc,
          cert_path: form.cert_path,
          cert_password: form.cert_password,
          environment: "homologacion",
        },
      }
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      }
      if (licenseKey) headers["X-License-Key"] = licenseKey

      const data = (await api.post("/api/v2/fiscal/issue", payload, { headers })) as FiscalResponse
      setLastResult(data)
      if (data.success) {
        toast({
          title: `Comprobante emitido en ${COUNTRY_LABELS[data.country]?.name || data.country}`,
          description: `ID: ${data.country_tracking_id || "(sin tracking id)"}`,
          variant: "success",
        })
      } else {
        toast({
          title: "Envío falló",
          description: data.reject_message || data.error || "Error desconocido",
          variant: "error",
        })
      }
    } catch (err) {
      toast({ title: "Error al emitir", description: humanError(err), variant: "error" })
    } finally {
      setIssuing(false)
    }
  }

  // ── Render ───────────────────────────────────

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      {/* ── Header ─────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-emerald-400" />
            Facturación Electrónica LATAM
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Conectores fiscales para Argentina, México, Brasil, Chile, Colombia, Perú y Ecuador.
            Firma digital certificada para cada país.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadCountries}>
          <RefreshCw className="h-4 w-4 mr-1" />
          Refrescar países
        </Button>
      </div>

      {/* ── Países soportados ──────────────────── */}
      <Card>
        <CardContent className="p-5">
          <h2 className="text-sm font-semibold flex items-center gap-2 mb-3">
            <Globe className="h-4 w-4 text-blue-400" />
            Países soportados
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
            {supportedCountries.map((code) => {
              const label = COUNTRY_LABELS[code]
              const isAvailable = availableCountries.includes(code)
              return (
                <div
                  key={code}
                  className={`p-2 rounded-md border text-center ${
                    isAvailable
                      ? "border-emerald-500/30 bg-emerald-500/5"
                      : "border-zinc-700 bg-zinc-900/50 opacity-50"
                  }`}
                  title={label?.authority || code}
                >
                  <div className="text-xs font-bold">{code}</div>
                  <div className="text-[10px] text-zinc-400 truncate">
                    {label?.name || code}
                  </div>
                  <Badge
                    variant="outline"
                    className={`mt-1 text-[9px] px-1 py-0 ${
                      isAvailable
                        ? "border-emerald-500/40 text-emerald-400"
                        : "border-zinc-700 text-zinc-500"
                    }`}
                  >
                    {isAvailable ? "OK" : "N/D"}
                  </Badge>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── License tier banner ────────────────── */}
      <Card className="border-amber-500/30 bg-amber-500/5">
        <CardContent className="p-4 flex items-start gap-3">
          <Key className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
          <div className="flex-1">
            <div className="text-sm font-medium text-amber-300">
              Requisito de licencia: tier Reseller o Enterprise
            </div>
            <div className="text-xs text-zinc-400 mt-1">
              La facturación electrónica requiere una licencia Reseller o Enterprise.
              Los planes gratuitos no tienen acceso a esta función.
            </div>
          </div>
          <Input
            placeholder="WFD-XXXX-XXXX-XXXX-XXXX (opcional)"
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            className="w-72 font-mono text-xs"
          />
        </CardContent>
      </Card>

      {/* ── Formulario de emisión ──────────────── */}
      <Card>
        <CardContent className="p-5 space-y-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Send className="h-4 w-4 text-blue-400" />
            Emitir comprobante fiscal
          </h2>

          {/* Selector país + acción */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label htmlFor="fiscal-country" className="text-xs text-zinc-400 mb-1 block">País</label>
              <select
                id="fiscal-country"
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
                className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-3 text-sm"
              >
                {supportedCountries.map((code) => (
                  <option key={code} value={code}>
                    {code} — {COUNTRY_LABELS[code]?.name || code}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="fiscal-action" className="text-xs text-zinc-400 mb-1 block">Acción</label>
              <select
                id="fiscal-action"
                value={form.action}
                onChange={(e) => setForm({ ...form, action: e.target.value })}
                className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-3 text-sm"
              >
                <option value="issue">Emitir comprobante</option>
                <option value="cancel">Cancelar comprobante</option>
                <option value="verify">Consultar estado</option>
                <option value="get_pdf">Descargar PDF</option>
              </select>
            </div>
            <div>
              <label htmlFor="fiscal-environment" className="text-xs text-zinc-400 mb-1 block">Ambiente</label>
              <Input id="fiscal-environment" value="homologación" disabled className="bg-zinc-900/50" />
            </div>
          </div>

          {/* Emisor + Receptor */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className="text-xs font-semibold text-zinc-300">Emisor</div>
              <Input
                placeholder="RFC del emisor"
                value={form.emisor_rfc}
                onChange={(e) => setForm({ ...form, emisor_rfc: e.target.value })}
                className="font-mono text-xs"
              />
              <Input
                placeholder="Razón social emisor"
                value={form.emisor_name}
                onChange={(e) => setForm({ ...form, emisor_name: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <div className="text-xs font-semibold text-zinc-300">Receptor</div>
              <Input
                placeholder="RFC del receptor"
                value={form.receptor_rfc}
                onChange={(e) => setForm({ ...form, receptor_rfc: e.target.value })}
                className="font-mono text-xs"
              />
              <Input
                placeholder="Razón social receptor"
                value={form.receptor_name}
                onChange={(e) => setForm({ ...form, receptor_name: e.target.value })}
              />
            </div>
          </div>

          {/* Concepto (CFDI 4.0) */}
          <div className="space-y-2">
            <div className="text-xs font-semibold text-zinc-300">Concepto</div>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
              <Input
                placeholder="ClaveProdServ"
                value={form.concepto_clave}
                onChange={(e) => setForm({ ...form, concepto_clave: e.target.value })}
                className="font-mono text-xs"
              />
              <Input
                type="number"
                placeholder="Cantidad"
                value={form.concepto_cantidad}
                onChange={(e) => setForm({ ...form, concepto_cantidad: Number(e.target.value) })}
              />
              <Input
                type="number"
                placeholder="Precio unitario"
                value={form.concepto_precio}
                onChange={(e) => setForm({ ...form, concepto_precio: Number(e.target.value) })}
              />
              <Input
                placeholder="Descripción"
                value={form.concepto_descripcion}
                onChange={(e) => setForm({ ...form, concepto_descripcion: e.target.value })}
              />
            </div>
          </div>

          {/* Certificado digital */}
          <div className="space-y-2">
            <div className="text-xs font-semibold text-zinc-300">
              Certificado digital
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <Input
                placeholder="Ruta del certificado digital"
                value={form.cert_path}
                onChange={(e) => setForm({ ...form, cert_path: e.target.value })}
                className="font-mono text-xs"
              />
              <Input
                type="password"
                placeholder="Contraseña del certificado"
                value={form.cert_password}
                onChange={(e) => setForm({ ...form, cert_password: e.target.value })}
              />
            </div>
            <div className="text-[10px] text-zinc-500">
              El certificado se carga de forma segura en memoria durante la operación.
              Nunca se guarda en la base de datos.
            </div>
          </div>

          {/* Botón emitir */}
          <div className="flex justify-end pt-2">
            <Button onClick={handleIssue} disabled={issuing}>
              {issuing ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Send className="h-4 w-4 mr-2" />
              )}
              {issuing ? "Emitiendo..." : "Emitir comprobante"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── Resultado ──────────────────────────── */}
      {lastResult && (
        <Card>
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold flex items-center gap-2">
                <FileText className="h-4 w-4 text-blue-400" />
                Resultado del envío
              </h2>
              <Badge
                variant="outline"
                className={
                  lastResult.success
                    ? "border-emerald-500/40 text-emerald-400"
                    : "border-red-500/40 text-red-400"
                }
              >
                {lastResult.success ? (
                  <CheckCircle2 className="h-3 w-3 mr-1 inline" />
                ) : (
                  <XCircle className="h-3 w-3 mr-1 inline" />
                )}
                {lastResult.success ? "ÉXITO" : "FALLÓ"}
              </Badge>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div>
                <div className="text-zinc-500">País</div>
                <div className="font-mono">{lastResult.country}</div>
              </div>
              <div>
                <div className="text-zinc-500">Acción</div>
                <div className="font-mono">{lastResult.action}</div>
              </div>
              <div className="col-span-2">
                <div className="text-zinc-500">Folio de seguimiento</div>
                <div className="font-mono truncate">
                  {lastResult.country_tracking_id || "(sin tracking id)"}
                </div>
              </div>
              <div className="col-span-2">
                <div className="text-zinc-500">Enviado el</div>
                <div className="font-mono">{lastResult.dispatched_at}</div>
              </div>
              <div className="col-span-2">
                <div className="text-zinc-500">Código de rechazo</div>
                <div className="font-mono">{lastResult.reject_code || "—"}</div>
              </div>
            </div>

            {lastResult.reject_message && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-red-500/5 border border-red-500/20">
                <AlertTriangle className="h-4 w-4 text-red-400 mt-0.5 shrink-0" />
                <div className="text-xs text-red-300">
                  <div className="font-medium">Mensaje del gobierno:</div>
                  <div className="font-mono mt-1">{lastResult.reject_message}</div>
                </div>
              </div>
            )}

            {lastResult.xml && (
              <details className="text-xs">
                <summary className="cursor-pointer text-blue-400 hover:underline">
                  Ver comprobante (XML)
                </summary>
                <pre className="mt-2 p-3 bg-zinc-950 border border-zinc-800 rounded-md overflow-auto max-h-96 font-mono text-[10px]">
                  {lastResult.xml}
                </pre>
              </details>
            )}

            {Object.keys(lastResult.government_response).length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-blue-400 hover:underline">
                  Ver respuesta del gobierno
                </summary>
                <pre className="mt-2 p-3 bg-zinc-950 border border-zinc-800 rounded-md overflow-auto max-h-96 font-mono text-[10px]">
                  {JSON.stringify(lastResult.government_response, null, 2)}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Empty state inicial ────────────────── */}
      {!lastResult && !issuing && (
        <EmptyState
          icon={<FileText className="h-12 w-12" />}
          title="Listo para emitir"
          description="Complete el formulario de arriba y presione 'Emitir comprobante' para enviarlo al gobierno."
        />
      )}
    </div>
  )
}
