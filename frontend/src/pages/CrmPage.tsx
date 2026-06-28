import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import { error as humanError } from "@/utils/humanize"
import {
  Users,
  UserPlus,
  Phone,
  Building2,
  Mail,
  MessageSquare,
  Edit,
  Trash2,
  ChevronRight,
  RefreshCw,
  Loader2,
  Search,
} from "lucide-react"

import type { Lead, StageCounts } from "@/types/crm"
import { STAGES } from "@/types/crm"

// ── Constantes ──────────────────────────────

// STAGES se importa desde @/types/crm (single source of truth).
// Esto evita el drift entre el frontend y el backend tools/crm/service.py:STAGES.

const STAGE_LABELS: Record<string, string> = {
  new: "Nuevo",
  contacted: "Contactado",
  qualified: "Calificado",
  proposal: "Propuesta",
  negotiation: "Negociación",
  closed_won: "Ganado",
  closed_lost: "Perdido",
}

const STAGE_COLORS: Record<string, string> = {
  new: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  contacted: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  qualified: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  proposal: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  negotiation: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  closed_won: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  closed_lost: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
}

const SOURCE_LABELS: Record<string, string> = {
  web_form: "Formulario web",
  referral: "Referido",
  call: "Llamada",
  email: "Correo",
  social: "Redes sociales",
  manual: "Manual",
  other: "Otro",
}

// ── Componente ─────────────────────────────────

export default function CrmPage() {
  const { getApi } = useApi()
  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(true)
  const [stageFilter, setStageFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [showDialog, setShowDialog] = useState(false)
  const [editingLead, setEditingLead] = useState<Lead | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [stageStats, setStageStats] = useState<StageCounts>({})
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    company: "",
    source: "manual",
    notes: "",
  })

  const loadLeads = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const query = stageFilter !== "all" ? `?stage=${stageFilter}` : ""
      const data = (await api.get(`/api/tools/crm/leads${query}`, { signal })) as Lead[]
      if (signal?.aborted) return

      // Calcular estadísticas por etapa
      const stats: StageCounts = {}
      for (const lead of data) {
        stats[lead.stage] = (stats[lead.stage] || 0) + 1
      }
      setStageStats(stats)
      setLeads(data)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar clientes", description: humanError(e), variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi, stageFilter])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadLeads(ac.signal)
    return () => ac.abort()
  }, [loadLeads])

  const filteredLeads = leads.filter((lead) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      lead.name.toLowerCase().includes(q) ||
      (lead.email || "").toLowerCase().includes(q) ||
      (lead.company || "").toLowerCase().includes(q) ||
      (lead.phone || "").toLowerCase().includes(q)
    )
  })

  async function handleSave() {
    if (!form.name.trim()) return
    setSaving(true)
    setError("")
    try {
      const api = getApi()
      if (editingLead) {
        await api.put(`/api/tools/crm/leads/${editingLead.id}`, form)
      } else {
        await api.post("/api/tools/crm/leads", form)
      }
      setShowDialog(false)
      setEditingLead(null)
      setForm({ name: "", email: "", phone: "", company: "", source: "manual", notes: "" })
      loadLeads()
    } catch (err: unknown) {
      setError(humanError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(leadId: number, name: string) {
    if (!confirm(`¿Eliminar a "${name}"? Esta acción no se puede deshacer.`)) return
    try {
      const api = getApi()
      await api.delete(`/api/tools/crm/leads/${leadId}`)
      loadLeads()
    } catch (e) {
      toast({ title: "Error al eliminar cliente", description: humanError(e), variant: "error" })
    }
  }

  async function handleAdvanceStage(leadId: number) {
    try {
      const api = getApi()
      await api.post(`/api/tools/crm/leads/${leadId}/advance`)
      loadLeads()
    } catch (e) {
      toast({ title: "Error al avanzar etapa", description: humanError(e), variant: "error" })
    }
  }

  function openEdit(lead: Lead) {
    setEditingLead(lead)
    setForm({
      name: lead.name,
      email: lead.email || "",
      phone: lead.phone || "",
      company: lead.company || "",
      source: lead.source,
      notes: lead.notes || "",
    })
    setShowDialog(true)
  }

  function openNew() {
    setEditingLead(null)
    setForm({ name: "", email: "", phone: "", company: "", source: "manual", notes: "" })
    setShowDialog(true)
  }

  const stageBadge = (stage: string) => (
    <Badge variant="outline" className={`border ${STAGE_COLORS[stage] || STAGE_COLORS.new}`}>
      {STAGE_LABELS[stage] || stage}
    </Badge>
  )

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 bg-zinc-800" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 rounded-lg bg-zinc-800" />
          ))}
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-zinc-800" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Encabezado */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-100">Mis Clientes</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Gestiona tus clientes potenciales y da seguimiento a cada etapa de la venta
        </p>
      </div>

      {/* Estadísticas por etapa */}
      <div className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {STAGES.map((stage) => {
          const count = stageStats[stage] || 0
          return (
            <button
              key={stage}
              onClick={() => setStageFilter(stageFilter === stage ? "all" : stage)}
              className={`rounded-lg border p-3 text-left transition-all ${
                stageFilter === stage
                  ? "border-indigo-500/50 bg-indigo-500/10"
                  : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
              }`}
            >
              <p className={`text-lg font-bold ${STAGE_COLORS[stage]?.split(" ")[1] || "text-zinc-300"}`}>
                {count}
              </p>
              <p className="mt-0.5 text-xs text-zinc-500">{STAGE_LABELS[stage]}</p>
            </button>
          )
        })}
      </div>

      {/* Barra de búsqueda y acciones */}
      <Card className="mb-4 border-zinc-800 bg-zinc-900/50">
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar por nombre, correo, empresa o teléfono…"
                className="border-zinc-700 bg-zinc-800 pl-9 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadLeads()}
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                <RefreshCw className="mr-1.5 h-4 w-4" />
                Actualizar
              </Button>
              <Button
                onClick={openNew}
                className="bg-indigo-600 text-white hover:bg-indigo-500"
              >
                <UserPlus className="mr-1.5 h-4 w-4" />
                Nuevo cliente
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Lista de leads */}
      {filteredLeads.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-12">
            <EmptyState
              icon={<Users className="h-12 w-12 text-zinc-600" />}
              title={leads.length === 0 ? "Aún no tienes clientes" : "Sin resultados"}
              description={
                leads.length === 0
                  ? "Agrega tu primer cliente potencial para empezar a dar seguimiento."
                  : "Ningún cliente coincide con tu búsqueda. Prueba con otro término."
              }
            />
          </CardContent>
        </Card>
      ) : (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-0">
            <div className="divide-y divide-zinc-800">
              {filteredLeads.map((lead) => (
                <div
                  key={lead.id}
                  className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-zinc-800/30"
                >
                  <div className="flex flex-1 items-center gap-4">
                    {/* Avatar */}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-sm font-medium text-zinc-300">
                      {lead.name.charAt(0).toUpperCase()}
                    </div>

                    {/* Info principal */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-200">{lead.name}</span>
                        {lead.company && (
                          <span className="flex items-center gap-1 text-xs text-zinc-500">
                            <Building2 className="h-3 w-3" />
                            {lead.company}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
                        {lead.email && (
                          <span className="flex items-center gap-1">
                            <Mail className="h-3 w-3" />
                            {lead.email}
                          </span>
                        )}
                        {lead.phone && (
                          <span className="flex items-center gap-1">
                            <Phone className="h-3 w-3" />
                            {lead.phone}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <MessageSquare className="h-3 w-3" />
                          {SOURCE_LABELS[lead.source] || lead.source}
                        </span>
                        {lead.created_at && (
                          <span>
                            · {new Date(lead.created_at).toLocaleDateString("es-MX")}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Etapa y acciones */}
                    <div className="flex items-center gap-2 shrink-0">
                      {stageBadge(lead.stage)}
                      {lead.stage !== "closed_won" && lead.stage !== "closed_lost" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleAdvanceStage(lead.id)}
                          className="text-zinc-500 hover:text-indigo-400"
                          title="Avanzar a siguiente etapa"
                          aria-label={`Avanzar a ${lead.name} a la siguiente etapa`}
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEdit(lead)}
                        className="text-zinc-500 hover:text-zinc-200"
                        title="Editar"
                        aria-label={`Editar cliente ${lead.name}`}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(lead.id, lead.name)}
                        className="text-zinc-500 hover:text-red-400"
                        title="Eliminar"
                        aria-label={`Eliminar cliente ${lead.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Total */}
            <div className="border-t border-zinc-800 px-4 py-2 text-xs text-zinc-600">
              {filteredLeads.length} de {leads.length} cliente{leads.length !== 1 ? "s" : ""}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diálogo crear/editar */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-lg border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>{editingLead ? "Editar cliente" : "Nuevo cliente"}</DialogTitle>
            <DialogDescription className="text-zinc-400">
              {editingLead
                ? "Actualiza los datos de tu cliente potencial"
                : "Registra un nuevo cliente para darle seguimiento"}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor="crm-lead-name" className="mb-1 block text-sm text-zinc-300">
                Nombre <span className="text-red-400">*</span>
              </label>
              <Input
                id="crm-lead-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Ej: María García"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="crm-lead-email" className="mb-1 block text-sm text-zinc-300">Correo electrónico</label>
              <Input
                id="crm-lead-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="cliente@correo.com"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="crm-lead-phone" className="mb-1 block text-sm text-zinc-300">Teléfono</label>
              <Input
                id="crm-lead-phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+52 55 1234 5678"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="crm-lead-company" className="mb-1 block text-sm text-zinc-300">Empresa</label>
              <Input
                id="crm-lead-company"
                value={form.company}
                onChange={(e) => setForm({ ...form, company: e.target.value })}
                placeholder="Nombre de la empresa"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="crm-lead-source" className="mb-1 block text-sm text-zinc-300">Origen</label>
              <Select
                value={form.source}
                onValueChange={(v) => setForm({ ...form, source: v })}
              >
                <SelectTrigger id="crm-lead-source" className="border-zinc-700 bg-zinc-800 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-700 bg-zinc-800 text-zinc-200">
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="web_form">Formulario web</SelectItem>
                  <SelectItem value="referral">Referido</SelectItem>
                  <SelectItem value="call">Llamada</SelectItem>
                  <SelectItem value="email">Correo</SelectItem>
                  <SelectItem value="social">Redes sociales</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="crm-lead-notes" className="mb-1 block text-sm text-zinc-300">Notas</label>
              <textarea
                id="crm-lead-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Información relevante sobre este cliente…"
                rows={3}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            {error && (
              <div className="sm:col-span-2 rounded-lg bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
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
              disabled={saving || !form.name.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Guardando…
                </>
              ) : editingLead ? (
                "Guardar cambios"
              ) : (
                "Crear cliente"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
