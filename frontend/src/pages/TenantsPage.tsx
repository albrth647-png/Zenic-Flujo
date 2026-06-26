/**
 * TenantsPage — Gestión de Multi-tenancy
 * ========================================
 *
 * 10 endpoints del backend expuestos en una UI completa:
 *   CRUD tenants + Suspend/Activate + Users + Features
 */

import { useState, useEffect, useCallback } from "react"
import { useTenants } from "@/hooks/useTenants"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Building2,
  Plus,
  Loader2,
  Users,
  Flag,
  ShieldCheck,
  ShieldOff,
  Trash2,
  CheckCircle2,
  XCircle,
  UserPlus,
  ToggleLeft,
  ToggleRight,
  Eye,
  ArrowLeft,
} from "lucide-react"
import { error as humanError } from "@/utils/humanize"
import type {
  TenantResponse,
  TenantUserResponse,
  TenantFeature,
} from "@/types/tenants"

type View = "list" | "detail" | "create" | "edit"

export default function TenantsPage() {
  const { createTenant, getTenant, updateTenant, deleteTenant, suspendTenant, activateTenant, listUsers, addUser, listFeatures, toggleFeature } = useTenants()
  const [view, setView] = useState<View>("list")
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null)
  const [tenants, setTenants] = useState<TenantResponse[]>([])
  const [tenant, setTenant] = useState<TenantResponse | null>(null)
  const [users, setUsers] = useState<TenantUserResponse[]>([])
  const [features, setFeatures] = useState<TenantFeature[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)

  // Resetea loading al cambiar de vista
  useEffect(() => {
    setLoading(false)
  }, [view])

  // Form states
  const [form, setForm] = useState({
    name: "",
    slug: "",
    plan: "free" as const,
  })
  const [userForm, setUserForm] = useState({
    username: "",
    password: "",
    role: "editor" as const,
    display_name: "",
    email: "",
  })

  // ── Load all tenants (list view uses mock — real API would have /list endpoint) ──
  // The API has GET /{id} but no list-all endpoint. We manage tenants from
  // the detail/create flow. The list is populated from user entries.

  const handleCreate = async () => {
    if (!form.name.trim() || !form.slug.trim()) {
      toast({ title: "Nombre y slug requeridos", variant: "error" })
      return
    }
    setCreating(true)
    try {
      const newTenant = await createTenant({
        name: form.name,
        slug: form.slug,
        plan: form.plan,
      })
      setTenants((prev) => [...prev, newTenant])
      setTenant(newTenant)
      setSelectedTenantId(newTenant.id)
      setView("detail")
      setForm({ name: "", slug: "", plan: "free" })
      toast({ title: `Tenant "${newTenant.name}" creado`, variant: "success" })
    } catch (err) {
      toast({ title: "Error creando tenant", description: humanError(err), variant: "error" })
    } finally {
      setCreating(false)
    }
  }

  const loadTenant = useCallback(async (id: string) => {
    setLoading(true)
    try {
      const [t, u, f] = await Promise.all([
        getTenant(id),
        listUsers(id),
        listFeatures(id),
      ])
      setTenant(t)
      setUsers(u)
      setFeatures(f.features)
    } catch (err) {
      toast({ title: "Error cargando tenant", description: humanError(err), variant: "error" })
    } finally {
      setLoading(false)
    }
  }, [getTenant, listUsers, listFeatures])

  const handleSelectTenant = (id: string) => {
    setSelectedTenantId(id)
    setView("detail")
  }

  const handleSuspend = async () => {
    if (!selectedTenantId) return
    try {
      await suspendTenant(selectedTenantId)
      toast({ title: "Tenant suspendido", variant: "success" })
      loadTenant(selectedTenantId)
    } catch (err) {
      toast({ title: "Error suspendiendo", description: humanError(err), variant: "error" })
    }
  }

  const handleActivate = async () => {
    if (!selectedTenantId) return
    try {
      await activateTenant(selectedTenantId)
      toast({ title: "Tenant activado", variant: "success" })
      loadTenant(selectedTenantId)
    } catch (err) {
      toast({ title: "Error activando", description: humanError(err), variant: "error" })
    }
  }

  const handleDelete = async () => {
    if (!selectedTenantId) return
    if (!confirm("¿Eliminar este tenant? Esta acción es irreversible.")) return
    try {
      await deleteTenant(selectedTenantId)
      setTenants((prev) => prev.filter((t) => t.id !== selectedTenantId))
      setSelectedTenantId(null)
      setTenant(null)
      setView("list")
      toast({ title: "Tenant eliminado", variant: "success" })
    } catch (err) {
      toast({ title: "Error eliminando", description: humanError(err), variant: "error" })
    }
  }

  const handleAddUser = async () => {
    if (!selectedTenantId || !userForm.username.trim() || !userForm.password.trim()) {
      toast({ title: "Usuario y contraseña requeridos", variant: "error" })
      return
    }
    try {
      await addUser(selectedTenantId, userForm)
      toast({ title: `Usuario "${userForm.username}" agregado`, variant: "success" })
      setUserForm({ username: "", password: "", role: "editor", display_name: "", email: "" })
      const updatedUsers = await listUsers(selectedTenantId)
      setUsers(updatedUsers)
    } catch (err) {
      toast({ title: "Error agregando usuario", description: humanError(err), variant: "error" })
    }
  }

  const handleToggleFeature = async (feature: string, currentEnabled: boolean) => {
    if (!selectedTenantId) return
    // Optimistic update: toggle local state inmediatamente
    setFeatures((prev) => prev.map((f) => (f.name === feature ? { ...f, enabled: !currentEnabled } : f)))
    try {
      await toggleFeature(selectedTenantId, feature, !currentEnabled)
      toast({ title: `Feature "${feature}" ${!currentEnabled ? "activada" : "desactivada"}`, variant: "success" })
    } catch (err) {
      // Revertir en caso de error
      setFeatures((prev) => prev.map((f) => (f.name === feature ? { ...f, enabled: currentEnabled } : f)))
      toast({ title: "Error al cambiar funcionalidad", description: humanError(err), variant: "error" })
    }
  }

  // Load tenant data when selecting for detail
  useEffect(() => {
    if (view === "detail" && selectedTenantId) {
      loadTenant(selectedTenantId)
    }
  }, [view, selectedTenantId, loadTenant])

  // ── Render: List ────────────────────────────────

  const renderList = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-300">
          {tenants.length} organizaci{tenants.length !== 1 ? "ones" : "ón"} registrada{tenants.length !== 1 ? "s" : ""}
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setView("create")}>
            <Plus className="h-4 w-4 mr-1" /> Nuevo tenant
          </Button>
        </div>
      </div>

      {tenants.length === 0 ? (
        <EmptyState
          icon={<Building2 className="h-12 w-12" />}
          title="Sin organizaciones"
          description="Crea la primera organización para empezar con multi-tenancy."
          action={
            <Button onClick={() => setView("create")}>
              <Plus className="h-4 w-4 mr-2" /> Crear primera organización
            </Button>
          }
        />
      ) : (
        <div className="grid gap-3">
          {tenants.map((t) => (
            <Card key={t.id} className="cursor-pointer hover:border-zinc-500 transition-colors" onClick={() => handleSelectTenant(t.id)}>
              <CardContent className="p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Building2 className="h-5 w-5 text-blue-400 shrink-0" />
                  <div>
                    <div className="text-sm font-medium text-zinc-200">{t.name}</div>
                    <div className="text-xs text-zinc-500 font-mono">{t.slug} · {t.id.slice(0, 8)}...</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">{t.plan}</Badge>
                  <Badge
                    variant={t.status === "active" ? "default" : "secondary"}
                    className="text-[10px]"
                  >
                    {t.status}
                  </Badge>
                  <Eye className="h-4 w-4 text-zinc-500" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )

  // ── Render: Create ──────────────────────────────

  const renderCreate = () => (
    <div className="max-w-lg mx-auto space-y-4">
      <Button variant="ghost" size="sm" onClick={() => setView("list")}>
        <ArrowLeft className="h-4 w-4 mr-1" /> Volver
      </Button>
      <Card>
        <CardContent className="p-5 space-y-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Plus className="h-4 w-4 text-blue-400" />
            Nueva organización
          </h2>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Nombre</label>
              <Input
                placeholder="Ej: Acme Corp"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Identificador único</label>
              <Input
                placeholder="Ej: acme-corp"
                value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })}
                className="font-mono text-xs"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-400 mb-1 block">Plan</label>
              <select
                value={form.plan}
                onChange={(e) => setForm({ ...form, plan: e.target.value as "free" | "smb" | "enterprise" })}
                className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-3 text-sm"
              >
                <option value="free">Free</option>
                <option value="smb">SMB</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <Button onClick={handleCreate} disabled={creating} className="w-full">
              {creating ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Building2 className="h-4 w-4 mr-2" />}
              {creating ? "Creando..." : "Crear organización"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )

  // ── Render: Detail ──────────────────────────────

  const renderDetail = () => {
    if (loading && !tenant) {
      return <div className="space-y-4"><Skeleton className="h-12 w-1/3" /><Skeleton className="h-48 w-full" /></div>
    }
    if (!tenant) {
      return          <EmptyState icon={<Building2 className="h-12 w-12" />} title="Selecciona una organización" description="Selecciona una organización de la lista o crea una nueva." />
    }

    return (
      <div className="space-y-6">
        {/* Back button + actions */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={() => setView("list")}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Volver
          </Button>
          <div className="flex gap-2">
            {tenant.status === "active" ? (
              <Button variant="outline" size="sm" onClick={handleSuspend}>
                <ShieldOff className="h-4 w-4 mr-1" /> Suspender
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={handleActivate}>
                <ShieldCheck className="h-4 w-4 mr-1" /> Activar
              </Button>
            )}
            <Button variant="destructive" size="sm" onClick={handleDelete}>
              <Trash2 className="h-4 w-4 mr-1" /> Eliminar
            </Button>
          </div>
        </div>

        {/* Tenant info */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Building2 className="h-5 w-5 text-blue-400" />
                  <h2 className="text-lg font-semibold text-zinc-100">{tenant.name}</h2>
                </div>
                <div className="flex items-center gap-3 mt-2 text-xs text-zinc-400">
                  <span className="font-mono">{tenant.slug}</span>
                  <span>·</span>
                  <span className="font-mono">ID: {tenant.id}</span>
                </div>
              </div>
              <div className="flex gap-2">
                <Badge variant="outline" className="text-xs">{tenant.plan}</Badge>
                <Badge
                  variant={tenant.status === "active" ? "default" : "secondary"}
                  className="text-xs"
                >
                  {tenant.status}
                </Badge>
              </div>
            </div>
            {tenant.domain && (
              <div className="mt-2 text-xs text-zinc-500">Dominio: {tenant.domain}</div>
            )}
            <div className="mt-3 text-[10px] text-zinc-600">
              Creado: {tenant.created_at ? new Date(tenant.created_at).toLocaleString() : "—"}
              {tenant.updated_at && ` · Actualizado: ${new Date(tenant.updated_at).toLocaleString()}`}
            </div>
          </CardContent>
        </Card>

        {/* Users section */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Users className="h-4 w-4 text-blue-400" />
                Usuarios ({users.length})
              </h3>
            </div>

            {/* Add user form */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mb-4">
              <Input
                placeholder="Usuario"
                value={userForm.username}
                onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                className="text-xs"
              />
              <Input
                type="password"
                placeholder="Contraseña"
                value={userForm.password}
                onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                className="text-xs"
              />
              <select
                value={userForm.role}
                onChange={(e) => setUserForm({ ...userForm, role: e.target.value as "admin" | "editor" | "viewer" })}
                className="h-9 bg-zinc-900 border border-zinc-700 rounded-md px-2 text-xs"
              >
                <option value="admin">Admin</option>
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
              <Input
                placeholder="Email"
                value={userForm.email}
                onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                className="text-xs"
              />
              <Button size="sm" onClick={handleAddUser} className="h-9">
                <UserPlus className="h-3.5 w-3.5 mr-1" /> Agregar
              </Button>
            </div>

            {/* Users list */}
            {users.length === 0 ? (
              <div className="text-xs text-zinc-500 text-center py-4">Sin usuarios registrados</div>
            ) : (
              <div className="space-y-1">
                {users.map((u) => (
                  <div key={u.id} className="flex items-center justify-between p-2 rounded-md bg-zinc-900/50 border border-zinc-800">
                    <div className="flex items-center gap-2">
                      <div className="size-7 rounded-full bg-blue-500/10 text-blue-400 flex items-center justify-center text-xs font-bold">
                        {u.display_name?.charAt(0)?.toUpperCase() || u.username.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="text-xs text-zinc-200">{u.display_name || u.username}</div>
                        <div className="text-[10px] text-zinc-500">{u.email || "—"}</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[9px]">{u.role}</Badge>
                      <Badge
                        variant={u.is_active ? "default" : "secondary"}
                        className="text-[9px]"
                      >
                        {u.is_active ? "Activo" : "Inactivo"}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Features section */}
        <Card>
          <CardContent className="p-5">
            <h3 className="text-sm font-semibold flex items-center gap-2 mb-4">
              <Flag className="h-4 w-4 text-blue-400" />
              Funcionalidades ({features.length})
            </h3>

            {features.length === 0 ? (
              <div className="text-xs text-zinc-500 text-center py-4">              Sin funcionalidades configuradas</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {features.map((f) => (
                  <div key={f.name} className="flex items-center justify-between p-3 rounded-md border border-zinc-700 bg-zinc-900/50">
                    <div className="flex items-center gap-2">
                      {f.enabled
                        ? <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                        : <XCircle className="h-4 w-4 text-zinc-600" />
                      }
                      <span className="text-xs font-mono text-zinc-200">{f.name}</span>
                    </div>
                    <button
                      onClick={() => handleToggleFeature(f.name, f.enabled)}
                      className="text-zinc-400 hover:text-zinc-200 transition-colors"
                      title={f.enabled ? "Desactivar" : "Activar"}
                    >
                      {f.enabled
                        ? <ToggleRight className="h-5 w-5 text-emerald-400" />
                        : <ToggleLeft className="h-5 w-5 text-zinc-600" />
                      }
                    </button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  // ── Main render ─────────────────────────────────

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Building2 className="h-7 w-7 text-blue-400" />
          Tenants — Multi-tenancy
        </h1>
        <p className="text-sm text-zinc-400 mt-1">
          Organizaciones, usuarios, roles y funcionalidades. Administración multi-tenant.
        </p>
      </div>

      {view === "list" && renderList()}
      {view === "create" && renderCreate()}
      {view === "detail" && renderDetail()}
    </div>
  )
}
