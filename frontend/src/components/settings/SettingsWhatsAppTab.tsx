import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Badge } from "@/components/ui/badge"
import { apiFetch } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { MessageCircle, Loader2, Save, Send, CheckCircle2, XCircle } from "lucide-react"

interface WhatsAppStatus {
  configured: boolean
  phone_number_id?: string
  connected?: boolean
}

export function SettingsWhatsAppTab() {
  const [token, setToken] = useState("")
  const [phoneNumberId, setPhoneNumberId] = useState("")
  const [testNumber, setTestNumber] = useState("")
  const [status, setStatus] = useState<WhatsAppStatus | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    apiFetch<WhatsAppStatus>("/api/settings/whatsapp").then((d) => {
      if (d) {
        setStatus(d)
        if (d.phone_number_id) setPhoneNumberId(d.phone_number_id)
      }
      setLoaded(true)
    })
  }, [])

  const handleSave = async () => {
    if (!token || !phoneNumberId) {
      toast({
        title: "Faltan datos",
        description: "Necesitas el token y el ID del número de teléfono",
        variant: "warning",
      })
      return
    }
    setSaving(true)
    const res = await apiFetch("/api/settings/whatsapp", {
      method: "PUT",
      body: JSON.stringify({ token, phone_number_id: phoneNumberId }),
    })
    setSaving(false)
    if (res !== null) {
      setStatus({ ...status, configured: true, phone_number_id: phoneNumberId })
      toast({
        title: "WhatsApp configurado",
        description: "La integración con WhatsApp se guardó correctamente",
        variant: "success",
      })
    }
  }

  const handleTest = async () => {
    if (!testNumber) {
      toast({
        title: "Falta el número de prueba",
        description: "Escribe un número de WhatsApp para recibir el mensaje de prueba",
        variant: "warning",
      })
      return
    }
    setTesting(true)
    const res = await apiFetch<{ status: string; message: string }>("/api/settings/whatsapp/test", {
      method: "POST",
      body: JSON.stringify({ test_number: testNumber }),
    })
    setTesting(false)
    if (res?.status === "sent" || res?.status === "ok") {
      toast({
        title: "Mensaje enviado",
        description: "Revisa WhatsApp en el número de prueba",
        variant: "success",
      })
    } else {
      toast({
        title: "Error al enviar",
        description: res?.message || "No se pudo enviar el mensaje de prueba",
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
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <MessageCircle className="size-4" />
              WhatsApp
            </CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Conecta tu bot de WhatsApp Business API para enviar mensajes
            </p>
          </div>
          <Badge variant={status?.configured ? "success" : "secondary"} className="gap-1">
            {status?.configured ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
            {status?.configured ? "Conectado" : "Sin conectar"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3">
          <div className="grid gap-2">
            <Label htmlFor="whatsapp_token">Token de acceso</Label>
            <Input
              id="whatsapp_token"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={status?.configured ? "•••••••• (token actual oculto)" : "Ingresa el token de WhatsApp Business"}
            />
            <p className="text-xs text-muted-foreground">
              El token de acceso permanente de tu cuenta de WhatsApp Business API
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="whatsapp_phone">ID del número de teléfono</Label>
            <Input
              id="whatsapp_phone"
              value={phoneNumberId}
              onChange={(e) => setPhoneNumberId(e.target.value)}
              placeholder="Ej: 123456789012345"
            />
            <p className="text-xs text-muted-foreground">
              El ID numérico del número de teléfono verificando en Meta Business
            </p>
          </div>
        </div>

        <Separator />

        <Button onClick={handleSave} disabled={saving} className="h-8">
          {saving ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Save className="size-3.5 mr-1" />}
          {saving ? "Guardando..." : "Guardar configuración"}
        </Button>

        <Separator />

        <div className="space-y-3">
          <Label className="text-sm font-medium">Probar conexión</Label>
          <div className="flex gap-2">
            <Input
              value={testNumber}
              onChange={(e) => setTestNumber(e.target.value)}
              placeholder="Ej: 521234567890"
              className="flex-1"
            />
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testing || !status?.configured}
              className="h-9 shrink-0"
            >
              {testing ? (
                <Loader2 className="size-3.5 mr-1 animate-spin" />
              ) : (
                <Send className="size-3.5 mr-1" />
              )}
              {testing ? "Enviando..." : "Enviar prueba"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Escribe un número de WhatsApp con código de país para recibir un mensaje de prueba
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
