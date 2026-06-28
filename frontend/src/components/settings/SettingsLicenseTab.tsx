import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { apiFetch } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Award, Loader2, CheckCircle2, AlertTriangle, XCircle } from "lucide-react"
import type { LicenseInfo, LicenseValidation } from "@/types/license"

export function SettingsLicenseTab() {
  const [info, setInfo] = useState<LicenseInfo | null>(null)
  const [licenseKey, setLicenseKey] = useState("")
  const [validating, setValidating] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    apiFetch<LicenseInfo>("/api/license/info").then((d) => {
      if (d) setInfo(d)
      setLoaded(true)
    })
  }, [])

  const handleValidate = async () => {
    if (!licenseKey.trim()) return
    setValidating(true)
    const res = await apiFetch<LicenseValidation>(
      "/api/license/validate",
      { method: "POST", body: JSON.stringify({ key: licenseKey.trim() }) }
    )
    setValidating(false)

    if (res?.valid) {
      toast({
        title: "¡Licencia activada!",
        description: res.client_name
          ? `Licencia ${res.type} para ${res.client_name}`
          : "Tu licencia se activó correctamente",
        variant: "success",
      })
      setLicenseKey("")
      // Recargar info
      apiFetch<LicenseInfo>("/api/license/info").then((d) => {
        if (d) setInfo(d)
      })
    } else {
      toast({
        title: "Licencia inválida",
        description: res?.message || res?.error || "La clave que ingresaste no es válida. Verifícala e inténtalo de nuevo",
        variant: "error",
      })
    }
  }

  if (!loaded) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="skeleton h-4 w-32 mb-4" />
          <div className="skeleton h-8 w-48 mb-2" />
          <div className="skeleton h-4 w-full" />
        </CardContent>
      </Card>
    )
  }

  const isTrial = info?.is_trial || info?.type === "trial"
  const isFree = info?.is_free || info?.type === "free"
  const isActive = !isTrial && !isFree && info?.type !== "invalid"

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Award className="size-4" />
            Estado de la licencia
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-4">
            <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 shrink-0">
              {isActive ? (
                <CheckCircle2 className="size-6 text-emerald-500" />
              ) : isTrial ? (
                <AlertTriangle className="size-6 text-amber-500" />
              ) : (
                <XCircle className="size-6 text-red-500" />
              )}
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold capitalize">
                  {isActive ? "Licencia activa" : isTrial ? "Modo de prueba" : "Sin licencia"}
                </span>
                <Badge
                  variant={isActive ? "success" : isTrial ? "warning" : "destructive"}
                  className="text-[10px]"
                >
                  {info?.type || "free"}
                </Badge>
              </div>

              {info?.client_name && (
                <p className="text-sm text-muted-foreground">
                  Cliente: <span className="font-medium text-foreground">{info.client_name}</span>
                </p>
              )}

              {info?.expires_at && (
                <p className="text-sm text-muted-foreground">
                  Vence:{" "}
                  {new Date(info.expires_at).toLocaleDateString("es-ES", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </p>
              )}

              {isTrial && info && (
                <div className="mt-2">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Días restantes:</span>
                    <span
                      className={`font-semibold ${
                        (info.days_left ?? 0) <= 7
                          ? "text-red-500"
                          : (info.days_left ?? 0) <= 15
                            ? "text-amber-500"
                            : ""
                      }`}
                    >
                      {info.days_left ?? 0}
                    </span>
                  </div>
                  {(info.days_left ?? 0) <= 7 && (
                    <p className="text-xs text-red-500 mt-1">
                      Tu periodo de prueba está por terminar. Ingresa una licencia para seguir usando el sistema sin interrupciones.
                    </p>
                  )}
                </div>
              )}

              <div className="flex items-center gap-4 mt-3 text-sm text-muted-foreground">
                <span>Workflows: <strong className="text-foreground">{info?.max_workflows === -1 ? "Ilimitados" : info?.max_workflows}</strong></span>
                <span>Herramientas: <strong className="text-foreground">{info?.allowed_tools?.includes("all") ? "Todas" : `${info?.allowed_tools?.length || 0} disponibles`}</strong></span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Activar licencia</CardTitle>
          <p className="text-sm text-muted-foreground">
            Ingresa tu clave de licencia para activar todas las funciones del sistema
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <Input
              value={licenseKey}
              onChange={(e) => setLicenseKey(e.target.value)}
              placeholder="WFD-XXXX-XXXX-XXXX-XXXX"
              className="flex-1 font-mono text-sm"
              onKeyDown={(e) => e.key === "Enter" && handleValidate()}
            />
            <Button onClick={handleValidate} disabled={validating || !licenseKey.trim()} className="shrink-0">
              {validating ? (
                <Loader2 className="size-3.5 mr-1 animate-spin" />
              ) : (
                <Award className="size-3.5 mr-1" />
              )}
              {validating ? "Validando..." : "Activar"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            ¿No tienes licencia? Puedes seguir usando el sistema en modo de prueba con funciones limitadas.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
