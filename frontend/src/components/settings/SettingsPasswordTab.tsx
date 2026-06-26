import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { apiFetch } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Lock, Loader2, Eye, CheckCircle2 } from "lucide-react"

export function SettingsPasswordTab() {
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPasswords, setShowPasswords] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!currentPassword || !newPassword) {
      toast({
        title: "Faltan campos",
        description: "Completa todos los campos para cambiar la contraseña",
        variant: "warning",
      })
      return
    }

    if (newPassword.length < 6) {
      toast({
        title: "Contraseña muy corta",
        description: "La nueva contraseña debe tener al menos 6 caracteres",
        variant: "error",
      })
      return
    }

    if (newPassword !== confirmPassword) {
      toast({
        title: "Las contraseñas no coinciden",
        description: "La nueva contraseña y su confirmación deben ser iguales",
        variant: "error",
      })
      return
    }

    setSaving(true)
    const res = await apiFetch<{ status: string; error?: string; message?: string }>("/api/settings/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    })
    setSaving(false)

    if (res?.status === "ok") {
      toast({
        title: "Contraseña actualizada",
        description: "Tu contraseña se cambió correctamente",
        variant: "success",
      })
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
    } else {
      toast({
        title: "Error al cambiar la contraseña",
        description: res?.message || res?.error || "Verifica que la contraseña actual sea correcta",
        variant: "error",
      })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Lock className="size-4" />
          Cambiar contraseña
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          Actualiza tu contraseña de acceso al sistema
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="current_password">Contraseña actual</Label>
            <Input
              id="current_password"
              type={showPasswords ? "text" : "password"}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Tu contraseña actual"
              autoComplete="current-password"
            />
          </div>

          <Separator />

          <div className="grid gap-2">
            <Label htmlFor="new_password">Nueva contraseña</Label>
            <Input
              id="new_password"
              type={showPasswords ? "text" : "password"}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Mínimo 6 caracteres"
              autoComplete="new-password"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="confirm_password">Confirmar nueva contraseña</Label>
            <Input
              id="confirm_password"
              type={showPasswords ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Repite la nueva contraseña"
              autoComplete="new-password"
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={showPasswords}
                onChange={(e) => setShowPasswords(e.target.checked)}
                className="rounded"
              />
              <Eye className="size-3.5" />
              Mostrar contraseñas
            </label>
          </div>

          <Separator />

          <Button
            type="submit"
            disabled={saving || !currentPassword || !newPassword || !confirmPassword}
            className="h-8"
          >
            {saving ? (
              <Loader2 className="size-3.5 mr-1 animate-spin" />
            ) : (
              <CheckCircle2 className="size-3.5 mr-1" />
            )}
            {saving ? "Actualizando..." : "Cambiar contraseña"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
