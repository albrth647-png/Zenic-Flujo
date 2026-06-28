/**
 * UsersTab — Gestión de usuarios en el panel de administración.
 *
 * Sprint 4 (bug #59): extraído de AdminPage.tsx para reducir LOC.
 * Estado local: users, loading, showDialog, editingUser, form, saving, error.
 * API: GET /api/users, POST /api/users, PUT /api/users/:id, DELETE /api/users/:id.
 */
import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Users as UsersIcon,
  Trash2,
  Edit,
  Shield,
  UserPlus,
  Loader2,
} from "lucide-react"
import type { AdminUser as User } from "@/types/admin"

export function UsersTab() {
  const { getApi } = useApi()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [form, setForm] = useState({
    username: "",
    password: "",
    display_name: "",
    email: "",
    role: "editor" as string,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const loadUsers = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const data = await api.get("/api/users", { signal })
      if (signal?.aborted) return
      setUsers(data as User[])
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar usuarios", variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadUsers(ac.signal)
    return () => ac.abort()
  }, [loadUsers])

  async function handleSave() {
    setSaving(true)
    setError("")
    try {
      const api = getApi()
      if (editingUser) {
        await api.put(`/api/users/${editingUser.id}`, {
          display_name: form.display_name,
          email: form.email,
          role: form.role,
        })
      } else {
        await api.post("/api/users", form)
      }
      setShowDialog(false)
      setEditingUser(null)
      setForm({ username: "", password: "", display_name: "", email: "", role: "editor" })
      loadUsers()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error al guardar el usuario")
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(userId: number, username: string) {
    if (!confirm(`¿Estás seguro de eliminar a "${username}"? Esta acción no se puede deshacer.`)) return
    try {
      const api = getApi()
      await api.delete(`/api/users/${userId}`)
      loadUsers()
    } catch {
      toast({ title: "Error al eliminar usuario", variant: "error" })
    }
  }

  function openEdit(user: User) {
    setEditingUser(user)
    setForm({
      username: user.username,
      password: "",
      display_name: user.display_name || "",
      email: user.email || "",
      role: user.role,
    })
    setShowDialog(true)
  }

  const roleBadge = (role: string) => {
    const styles: Record<string, string> = {
      admin: "bg-red-500/10 text-red-400 border-red-500/20",
      editor: "bg-blue-500/10 text-blue-400 border-blue-500/20",
      viewer: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
    }
    const labels: Record<string, string> = {
      admin: "Administrador",
      editor: "Editor",
      viewer: "Solo lectura",
    }
    return (
      <Badge variant="outline" className={`border ${styles[role] || styles.viewer}`}>
        <Shield className="mr-1 h-3 w-3" />
        {labels[role] || role}
      </Badge>
    )
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-lg bg-zinc-800" />
        ))}
      </div>
    )
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-zinc-400">
          {users.length} usuario{users.length !== 1 ? "s" : ""} registrado{users.length !== 1 ? "s" : ""}
        </p>
        <Button
          onClick={() => {
            setEditingUser(null)
            setForm({ username: "", password: "", display_name: "", email: "", role: "editor" })
            setShowDialog(true)
          }}
          className="bg-indigo-600 text-white hover:bg-indigo-500"
        >
          <UserPlus className="mr-1.5 h-4 w-4" />
          Nuevo usuario
        </Button>
      </div>

      {users.length === 0 ? (
        <EmptyState
          icon={<UsersIcon className="h-12 w-12" />}
          title="No hay usuarios aún"
          description="Crea el primer usuario para empezar a trabajar en equipo."
        />
      ) : (
        <div className="space-y-2">
          {users.map((user) => (
            <div
              key={user.id}
              className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800 text-sm font-medium text-zinc-300">
                  {(user.display_name || user.username).charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-zinc-200">
                      {user.display_name || user.username}
                    </span>
                    {!user.is_active && (
                      <Badge variant="outline" className="border-red-500/20 bg-red-500/10 text-xs text-red-400">
                        Inactivo
                      </Badge>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-center gap-3 text-xs text-zinc-500">
                    <span>@{user.username}</span>
                    {user.email && <span>· {user.email}</span>}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {roleBadge(user.role)}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => openEdit(user)}
                  className="text-zinc-400 hover:text-zinc-200"
                >
                  <Edit className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(user.id, user.username)}
                  className="text-zinc-400 hover:text-red-400"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Diálogo de crear/editar usuario */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>{editingUser ? "Editar usuario" : "Nuevo usuario"}</DialogTitle>
            <DialogDescription className="text-zinc-400">
              {editingUser
                ? "Actualiza los datos del usuario"
                : "Crea una cuenta para que alguien más pueda usar la plataforma"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label htmlFor="user-username" className="mb-1 block text-sm text-zinc-300">Nombre de usuario</label>
              <Input
                id="user-username"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                disabled={!!editingUser}
                placeholder="Ej: maria.rodriguez"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>

            {!editingUser && (
              <div>
                <label htmlFor="user-password" className="mb-1 block text-sm text-zinc-300">Contraseña</label>
                <Input
                  id="user-password"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="Mínimo 6 caracteres"
                  className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
                />
              </div>
            )}

            <div>
              <label htmlFor="user-display-name" className="mb-1 block text-sm text-zinc-300">Nombre visible</label>
              <Input
                id="user-display-name"
                value={form.display_name}
                onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                placeholder="Ej: María Rodríguez"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>

            <div>
              <label htmlFor="user-email" className="mb-1 block text-sm text-zinc-300">Correo electrónico</label>
              <Input
                id="user-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="ejemplo@correo.com"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>

            <div>
              <label htmlFor="user-role" className="mb-1 block text-sm text-zinc-300">Rol</label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
                <SelectTrigger id="user-role" className="border-zinc-700 bg-zinc-800 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-700 bg-zinc-800 text-zinc-200">
                  <SelectItem value="admin">Administrador — acceso completo</SelectItem>
                  <SelectItem value="editor">Editor — puede crear y modificar</SelectItem>
                  <SelectItem value="viewer">Solo lectura — solo ver</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {error && (
              <div className="rounded-lg bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || (!editingUser && (!form.username || !form.password))}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Guardando…
                </>
              ) : editingUser ? (
                "Guardar cambios"
              ) : (
                "Crear usuario"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
