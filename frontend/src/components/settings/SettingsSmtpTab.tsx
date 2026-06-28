import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { apiFetch } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Loader2, Save, Send } from "lucide-react"

interface SmtpData {
  smtp_server: string
  smtp_port: string
  email_user: string
  email_password?: string
}

export function SettingsSmtpTab() {
  const [settings, setSettings] = useState<SmtpData>({
    smtp_server: "",
    smtp_port: "587",
    email_user: "",
  })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    apiFetch<SmtpData>("/api/settings").then((d) => {
      if (d) setSettings(d)
      setLoaded(true)
    })
  }, [])

  const handleSave = async () => {
    setSaving(true)
    const res = await apiFetch("/api/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    })
    setSaving(false)
    if (res !== null) {
      toast({
        title: "Configuración guardada",
        description: "Los cambios en el servidor SMTP se guardaron correctamente",
        variant: "success",
      })
    }
  }

  const handleTest = async () => {
    setTesting(true)
    const res = await apiFetch<{ status: string; message: string }>("/api/settings/test-email", {
      method: "POST",
    })
    setTesting(false)
    if (res?.status === "ok") {
      toast({
        title: "Correo de prueba enviado",
        description: res.message || "Revisa la bandeja de entrada del correo configurado",
        variant: "success",
      })
    } else {
      toast({
        title: "Error al enviar correo de prueba",
        description: res?.message || "Revisa la configuración SMTP e inténtalo de nuevo",
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
          <div className="skeleton h-9 w-full mb-3" />
          <div className="skeleton h-9 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          Correo SMTP
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Configura el servidor de correo para enviar notificaciones y alertas
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3">
          <div className="grid gap-2">
            <Label htmlFor="smtp_server">Servidor SMTP</Label>
            <Input
              id="smtp_server"
              value={settings.smtp_server}
              onChange={(e) => setSettings({ ...settings, smtp_server: e.target.value })}
              placeholder="smtp.gmail.com"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label htmlFor="smtp_port">Puerto</Label>
              <Input
                id="smtp_port"
                value={settings.smtp_port}
                onChange={(e) => setSettings({ ...settings, smtp_port: e.target.value })}
                placeholder="587"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="email_user">Correo electrónico</Label>
              <Input
                id="email_user"
                value={settings.email_user}
                onChange={(e) => setSettings({ ...settings, email_user: e.target.value })}
                placeholder="tucorreo@empresa.com"
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="email_password">Contraseña de la cuenta</Label>
            <Input
              id="email_password"
              type="password"
              value={settings.email_password || ""}
              onChange={(e) => setSettings({ ...settings, email_password: e.target.value })}
              placeholder="••••••••"
            />
          </div>
        </div>

        <Separator />

        <div className="flex items-center gap-3">
          <Button onClick={handleSave} disabled={saving} className="h-8">
            {saving ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Save className="size-3.5 mr-1" />}
            {saving ? "Guardando..." : "Guardar cambios"}
          </Button>
          <Button
            variant="outline"
            onClick={handleTest}
            disabled={testing || !settings.smtp_server}
            className="h-8"
          >
            {testing ? (
              <Loader2 className="size-3.5 mr-1 animate-spin" />
            ) : (
              <Send className="size-3.5 mr-1" />
            )}
            {testing ? "Enviando..." : "Enviar correo de prueba"}
          </Button>
        </div>

        <p className="text-xs text-muted-foreground">
          El correo de prueba se envía a la dirección configurada. Si no lo recibes, revisa la configuración o las políticas de seguridad de tu servidor SMTP.
        </p>
      </CardContent>
    </Card>
  )
}
