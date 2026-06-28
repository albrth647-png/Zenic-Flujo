import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { apiFetch } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Key, Loader2, Copy, RefreshCw, Eye, EyeOff, CheckCircle2 } from "lucide-react"

export function SettingsApiKeyTab() {
  const [apiKey, setApiKey] = useState("")
  const [showKey, setShowKey] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    apiFetch<{ api_key: string }>("/api/settings/api-key").then((d) => {
      if (d) setApiKey(d.api_key)
      setLoaded(true)
    })
  }, [])

  const handleRegenerate = async () => {
    if (!confirm("¿Estás seguro? La API Key actual dejará de funcionar de inmediato. Los servicios que la usen se quedarán sin acceso hasta que la actualices.")) return

    setRegenerating(true)
    const res = await apiFetch<{ api_key: string; status: string }>("/api/settings/api-key", {
      method: "POST",
    })
    setRegenerating(false)
    if (res?.api_key) {
      setApiKey(res.api_key)
      setShowKey(true)
      toast({
        title: "API Key regenerada",
        description: "La nueva clave ya está activa. Copiala ahora, solo se muestra una vez",
        variant: "success",
      })
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(apiKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast({
        title: "Copiado al portapapeles",
        variant: "success",
      })
    } catch {
      toast({
        title: "No se pudo copiar",
        description: "Copia la clave manualmente desde el campo de texto",
        variant: "error",
      })
    }
  }

  if (!loaded) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="skeleton h-4 w-32 mb-4" />
          <div className="skeleton h-9 w-full mb-3" />
          <div className="skeleton h-8 w-32" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Key className="size-4" />
          API Key
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Esta clave se usa para autenticar llamadas entrantes de webhooks y servicios externos
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2">
          <Label htmlFor="api_key">Tu API Key</Label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                id="api_key"
                type={showKey ? "text" : "password"}
                value={apiKey || "Sin clave generada"}
                readOnly
                className="pr-10 font-mono text-xs"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label={showKey ? "Ocultar" : "Mostrar"}
              >
                {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              </button>
            </div>
            {apiKey && (
              <Button variant="outline" size="icon" className="size-9 shrink-0" onClick={handleCopy} aria-label={copied ? "API Key copiada" : "Copiar API Key al portapapeles"}>
                {copied ? <CheckCircle2 className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
              </Button>
            )}
          </div>
        </div>

        {apiKey && showKey && (
          <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
            <p className="font-medium">⚠️ Importante</p>
            <p className="mt-0.5 opacity-80">
              Esta clave solo se muestra ahora. Si la pierdes, tendrás que regenerarla y actualizar todos los servicios que la usan.
            </p>
          </div>
        )}

        <Separator />

        <div className="space-y-3">
          <Label className="text-sm font-medium">Regenerar clave</Label>
          <p className="text-xs text-muted-foreground">
            Si crees que tu clave fue comprometida, puedes generar una nueva. La anterior dejará de funcionar al instante.
          </p>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleRegenerate}
            disabled={regenerating}
            className="h-8"
          >
            {regenerating ? (
              <Loader2 className="size-3.5 mr-1 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5 mr-1" />
            )}
            {regenerating ? "Regenerando..." : "Regenerar API Key"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
