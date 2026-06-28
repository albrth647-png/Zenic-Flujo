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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Users,
  UserPlus,
  Handshake,
  Award,
  TrendingUp,
  ShieldCheck,
  RefreshCw,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Star,
  Activity,
  Mail,
  Zap,
} from "lucide-react"

import type { Partner, TierDef, PartnerStats, ActivityEntry } from "@/types/partners"
import { error as humanError } from "@/utils/humanize"

// ── Helpers ────────────────────────────────────

const TIER_COLORS: Record<string, string> = {
  community: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
  silver: "bg-slate-300/10 text-slate-300 border-slate-300/20",
  gold: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  platinum: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
}

const STATUS_LABELS: Record<string, string> = {
  applicant: "Solicitante",
  active: "Activo",
  suspended: "Suspendido",
  terminated: "Terminado",
}

const STATUS_COLORS: Record<string, string> = {
  applicant: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  active: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  suspended: "bg-red-500/10 text-red-400 border-red-500/20",
  terminated: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
}

// ── Componentes ────────────────────────────────

function TierCard({
  tier,
  def,
  count,
}: {
  tier: string
  def: TierDef
  count: number
}) {
  const color = TIER_COLORS[tier] || TIER_COLORS.community
  return (
    <Card className="border-zinc-800 bg-zinc-900/50 transition-all hover:border-zinc-700">
      <CardContent className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Award className={`h-4 w-4 ${color.split(" ")[1] || "text-zinc-400"}`} />
            <span className="font-medium text-zinc-200">{def.display_name}</span>
          </div>
          <Badge variant="outline" className={color}>
            {count} socio{count !== 1 ? "s" : ""}
          </Badge>
        </div>
        <div className="space-y-1 text-xs text-zinc-500">
          <div className="flex justify-between">
            <span>Participación de ingresos</span>
            <span className="font-medium text-zinc-300">{(def.revenue_share * 100).toFixed(0)}%</span>
          </div>
          <div className="flex justify-between">
            <span>Conectores mínimos</span>
            <span className="font-medium text-zinc-300">{def.min_connectors}</span>
          </div>
          <div className="flex justify-between">
            <span>Instalaciones mínimas</span>
            <span className="font-medium text-zinc-300">{def.min_installs.toLocaleString()}</span>
          </div>
          <div className="flex justify-between">
            <span>Calificación mínima</span>
            <span className="font-medium text-zinc-300">{def.min_rating}</span>
          </div>
          {def.benefits.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {def.benefits.slice(0, 4).map((b) => (
                <span
                  key={b}
                  className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400"
                >
                  {b.replace(/_/g, " ")}
                </span>
              ))}
              {def.benefits.length > 4 && (
                <span className="text-[10px] text-zinc-600">+{def.benefits.length - 4}</span>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function PartnerRow({
  partner,
  onApprove,
  onPromote,
}: {
  partner: Partner
  onApprove: (id: string) => void
  onPromote: (id: string) => void
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="flex flex-1 items-center gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-sm font-medium text-zinc-300">
          {partner.name.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-zinc-200">{partner.name}</span>
            <Badge
              variant="outline"
              className={`border ${STATUS_COLORS[partner.status] || STATUS_COLORS.applicant}`}
            >
              {STATUS_LABELS[partner.status] || partner.status}
            </Badge>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
            <span className="flex items-center gap-1">
              <Mail className="h-3 w-3" />
              {partner.email}
            </span>
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3" />
              {partner.connectors_published} conectores
            </span>
            {partner.rating > 0 && (
              <span className="flex items-center gap-1">
                <Star className="h-3 w-3 text-amber-400" />
                {partner.rating.toFixed(1)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge
            variant="outline"
            className={`border ${TIER_COLORS[partner.tier] || TIER_COLORS.community}`}
          >
            {partner.tier.charAt(0).toUpperCase() + partner.tier.slice(1)}
          </Badge>
          {partner.status === "applicant" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onApprove(partner.partner_id)}
              className="text-emerald-400 hover:text-emerald-300"
              title="Aprobar socio"
              aria-label={`Aprobar socio ${partner.name}`}
            >
              <CheckCircle2 className="h-4 w-4" />
            </Button>
          )}
          {partner.status === "active" && partner.tier !== "platinum" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onPromote(partner.partner_id)}
              className="text-indigo-400 hover:text-indigo-300"
              title="Promocionar de tier"
              aria-label={`Promocionar de tier al socio ${partner.name}`}
            >
              <TrendingUp className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Página principal ───────────────────────────

export default function PartnersPage() {
  const { getApi } = useApi()
  const [partners, setPartners] = useState<Partner[]>([])
  const [stats, setStats] = useState<PartnerStats>({ total: 0, active: 0, by_tier: {} })
  const [tiers, setTiers] = useState<Record<string, TierDef>>({})
  const [activities, setActivities] = useState<ActivityEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState("partners")

  // Diálogo de registro
  const [showRegister, setShowRegister] = useState(false)
  const [regForm, setRegForm] = useState({ name: "", contact: "", email: "", website: "", description: "", country: "" })
  const [saving, setSaving] = useState(false)

  // Diálogo de promoción
  const [showPromote, setShowPromote] = useState(false)
  const [promotePartner, setPromotePartner] = useState<string>("")
  const [promoteTier, setPromoteTier] = useState("silver")
  const [promoting, setPromoting] = useState(false)

  const loadData = useCallback(async (signal?: AbortSignal) => {
    setError(null)
    try {
      const api = getApi()
      const [overviewRes, tiersRes, activityRes] = await Promise.all([
        api.get("/api/partners/overview", { signal }),
        api.get("/api/partners/tiers", { signal }),
        api.get("/api/partners/activity", { signal }),
      ])
      if (signal?.aborted) return
      const overview = overviewRes as { partners: Partner[]; stats: PartnerStats }
      const tiersData = tiersRes as { definitions: Record<string, TierDef> }
      const actData = activityRes as { activities: ActivityEntry[] }
      setPartners(overview.partners || [])
      setStats(overview.stats || { total: 0, active: 0, by_tier: {} })
      setTiers(tiersData.definitions || {})
      setActivities(actData.activities || [])
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar partners", description: humanError(e), variant: "error" })
      setError(humanError(e) || "No se pudo cargar el programa de partners. Verifica que el servidor esté corriendo.")
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

  async function handleRegister() {
    if (!regForm.name.trim() || !regForm.email.trim()) return
    setSaving(true)
    try {
      const api = getApi()
      await api.post("/api/partners/register", {
        name: regForm.name.trim(),
        contact: regForm.contact.trim() || regForm.name.trim(),
        email: regForm.email.trim(),
        website: regForm.website.trim(),
        description: regForm.description.trim(),
        country: regForm.country.trim(),
      })
      setShowRegister(false)
      setRegForm({ name: "", contact: "", email: "", website: "", description: "", country: "" })
      loadData()
    } catch (e) {
      toast({ title: "Error al registrar socio", description: humanError(e), variant: "error" })
    } finally {
      setSaving(false)
    }
  }

  async function handleApprove(partnerId: string) {
    try {
      const api = getApi()
      await api.post(`/api/partners/${partnerId}/approve`)
      loadData()
    } catch (e) {
      toast({ title: "Error al aprobar socio", description: humanError(e), variant: "error" })
    }
  }

  async function handlePromote() {
    if (!promotePartner || !promoteTier) return
    setPromoting(true)
    try {
      const api = getApi()
      await api.post(`/api/partners/${promotePartner}/promote`, { target_tier: promoteTier })
      setShowPromote(false)
      loadData()
    } catch (e) {
      toast({ title: "Error al promocionar socio", description: humanError(e), variant: "error" })
    } finally {
      setPromoting(false)
    }
  }

  // activePartners está disponible si se necesita filtrar
  const applicantPartners = partners.filter((p) => p.status === "applicant")

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
            <Handshake className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Programa de Partners</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Gestiona socios, tiers y beneficios del ecosistema
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
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-zinc-800" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
            <Handshake className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Programa de Partners</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Gestiona socios, tiers y beneficios del ecosistema
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadData()}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Recargar
          </Button>
          <Button
            onClick={() => setShowRegister(true)}
            className="bg-indigo-600 text-white hover:bg-indigo-500"
          >
            <UserPlus className="mr-1.5 h-4 w-4" />
            Registrar socio
          </Button>
        </div>
      </div>

      {/* Tarjetas de resumen */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-zinc-100">{stats.total}</p>
            <Users className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Total socios</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-emerald-400">{stats.active}</p>
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Activos</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-amber-400">{applicantPartners.length}</p>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Pendientes aprobación</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-indigo-400">{Object.keys(tiers).length}</p>
            <Award className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Tiers disponibles</p>
        </div>
      </div>

      {/* Tiers cards */}
      {Object.keys(tiers).length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(tiers).map(([tier, def]) => (
            <TierCard
              key={tier}
              tier={tier}
              def={def}
              count={stats.by_tier?.[tier] || 0}
            />
          ))}
        </div>
      )}

      {/* Tabs: Partners, Actividad */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="border-zinc-800 bg-zinc-900">
          <TabsTrigger
            value="partners"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Users className="mr-1.5 h-4 w-4" />
            Socios
          </TabsTrigger>
          <TabsTrigger
            value="activity"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Activity className="mr-1.5 h-4 w-4" />
            Actividad reciente
          </TabsTrigger>
        </TabsList>

        {/* ── Lista de partners ── */}
        <TabsContent value="partners" className="mt-4">
          {partners.length === 0 ? (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="flex flex-col items-center justify-center p-12">
                <Handshake className="h-12 w-12 text-zinc-600" />
                <h3 className="mt-4 text-sm font-medium text-zinc-300">No hay socios registrados</h3>
                <p className="mt-1 text-xs text-zinc-500">
                  Registra tu primer partner para empezar a construir el ecosistema
                </p>
                <Button
                  onClick={() => setShowRegister(true)}
                  className="mt-4 bg-indigo-600 text-white hover:bg-indigo-500"
                >
                  <UserPlus className="mr-1.5 h-4 w-4" />
                  Registrar socio
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-0">
                <div className="divide-y divide-zinc-800">
                  {partners.map((partner) => (
                    <PartnerRow
                      key={partner.partner_id}
                      partner={partner}
                      onApprove={handleApprove}
                      onPromote={(id) => {
                        setPromotePartner(id)
                        setPromoteTier("silver")
                        setShowPromote(true)
                      }}
                    />
                  ))}
                </div>
                <div className="border-t border-zinc-800 px-4 py-2 text-xs text-zinc-600">
                  {partners.length} socio{partners.length !== 1 ? "s" : ""} registrado{partners.length !== 1 ? "s" : ""}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Actividad reciente ── */}
        <TabsContent value="activity" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Historial de actividad
              </CardTitle>
            </CardHeader>
            <CardContent>
              {activities.length === 0 ? (
                <div className="flex h-24 items-center justify-center text-sm text-zinc-500">
                  Sin actividad reciente
                </div>
              ) : (
                <div className="space-y-3">
                  {activities.slice(0, 30).map((act, i) => {
                    const partner = partners.find((p) => p.partner_id === act.partner_id)
                    return (
                      <div key={i} className="flex items-start gap-3">
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-800">
                          <div className="h-2 w-2 rounded-full bg-indigo-400" />
                        </div>
                        <div className="flex-1">
                          <p className="text-sm text-zinc-200">
                            <span className="font-medium">{partner?.name || act.partner_id}</span>
                            {" — "}
                            {act.description || act.activity_type.replace(/_/g, " ")}
                          </p>
                          <p className="text-xs text-zinc-600">
                            {new Date(act.performed_at).toLocaleString("es-MX")}
                          </p>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Diálogo registrar socio ── */}
      <Dialog open={showRegister} onOpenChange={setShowRegister}>
        <DialogContent className="max-w-lg border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Registrar nuevo socio</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Ingresa los datos de la empresa que se une al programa de partners
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor="partner-name" className="mb-1 block text-sm text-zinc-300">
                Empresa <span className="text-red-400">*</span>
              </label>
              <Input
                id="partner-name"
                value={regForm.name}
                onChange={(e) => setRegForm({ ...regForm, name: e.target.value })}
                placeholder="Nombre de la empresa"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="partner-contact" className="mb-1 block text-sm text-zinc-300">Persona de contacto</label>
              <Input
                id="partner-contact"
                value={regForm.contact}
                onChange={(e) => setRegForm({ ...regForm, contact: e.target.value })}
                placeholder="Nombre del contacto"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="partner-email" className="mb-1 block text-sm text-zinc-300">
                Correo electrónico <span className="text-red-400">*</span>
              </label>
              <Input
                id="partner-email"
                type="email"
                value={regForm.email}
                onChange={(e) => setRegForm({ ...regForm, email: e.target.value })}
                placeholder="contacto@empresa.com"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="partner-website" className="mb-1 block text-sm text-zinc-300">Sitio web</label>
              <Input
                id="partner-website"
                value={regForm.website}
                onChange={(e) => setRegForm({ ...regForm, website: e.target.value })}
                placeholder="https://empresa.com"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="partner-country" className="mb-1 block text-sm text-zinc-300">País</label>
              <Input
                id="partner-country"
                value={regForm.country}
                onChange={(e) => setRegForm({ ...regForm, country: e.target.value })}
                placeholder="Ej: México"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="partner-description" className="mb-1 block text-sm text-zinc-300">Descripción</label>
              <textarea
                id="partner-description"
                value={regForm.description}
                onChange={(e) => setRegForm({ ...regForm, description: e.target.value })}
                placeholder="Breve descripción de la empresa y su experiencia…"
                rows={2}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowRegister(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleRegister}
              disabled={saving || !regForm.name.trim() || !regForm.email.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Registrando…
                </>
              ) : (
                "Registrar socio"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Diálogo promocionar tier ── */}
      <Dialog open={showPromote} onOpenChange={setShowPromote}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Promocionar socio</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Selecciona el nuevo tier para este socio. Debe cumplir los requisitos mínimos.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label htmlFor="partner-promote-tier" className="mb-1 block text-sm text-zinc-300">Nuevo tier</label>
              <Select value={promoteTier} onValueChange={setPromoteTier}>
                <SelectTrigger id="partner-promote-tier" className="border-zinc-700 bg-zinc-800 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-700 bg-zinc-800 text-zinc-200">
                  {Object.entries(tiers).map(([tier, def]) => (
                    <SelectItem key={tier} value={tier}>
                      <span className="flex items-center gap-2">
                        <Award className={`h-4 w-4 ${(TIER_COLORS[tier] || "").split(" ")[1] || "text-zinc-400"}`} />
                        {def.display_name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {promoteTier && tiers[promoteTier] && (
              <div className="rounded-lg bg-zinc-800/30 p-3 text-xs text-zinc-400">
                <p>Requisitos para {tiers[promoteTier].display_name}:</p>
                <ul className="mt-1 space-y-0.5">
                  <li>• Mín. {tiers[promoteTier].min_connectors} conectores publicados</li>
                  <li>• Mín. {tiers[promoteTier].min_installs.toLocaleString()} instalaciones</li>
                  <li>• Calificación mínima: {tiers[promoteTier].min_rating}</li>
                  <li>• Participación de ingresos: {(tiers[promoteTier].revenue_share * 100).toFixed(0)}%</li>
                </ul>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowPromote(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handlePromote}
              disabled={promoting}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {promoting ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Promocionando…
                </>
              ) : (
                "Promocionar"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
