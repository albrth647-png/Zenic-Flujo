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
import { OrbitalVisualizer } from "@/components/orbital/OrbitalVisualizer"
import {
  Activity,
  RefreshCw,
  Play,
  RotateCcw,
  Plus,
  Trash2,
  Loader2,
  Zap,
  Radio,
  BarChart3,
  History,
  Cpu,
  Layers,
  CircleDot,
  CheckCircle2,
  XCircle,
} from "lucide-react"

import type {
  OrbitalVariable,
  TorEntry,
  RccCycle,
  CodResult,
  TickHistory,
  OrbitalStatus,
} from "@/types/orbital"

// ── Helpers ────────────────────────────────────

function degrees(rad: number) {
  return ((rad * 180) / Math.PI) % 360
}

function torColor(value: number): string {
  const abs = Math.abs(value)
  if (abs < 0.1) return "text-zinc-500"
  if (value > 0) return "text-emerald-400"
  return "text-red-400"
}

function torBg(value: number): string {
  const abs = Math.min(Math.abs(value) / 100, 1)
  if (value > 0) return `rgba(52,211,153,${abs * 0.2})`
  if (value < 0) return `rgba(248,113,113,${abs * 0.2})`
  return "transparent"
}

// ── Componentes ────────────────────────────────

function VariableCard({
  name,
  varData,
  onDelete,
}: {
  name: string
  varData: OrbitalVariable
  onDelete: (name: string) => void
}) {
  const deg = degrees(varData.theta)
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CircleDot className="h-4 w-4 text-indigo-400" />
          <span className="font-medium text-zinc-200">{name}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-zinc-500 hover:text-red-400"
          onClick={() => onDelete(name)}
          title="Eliminar variable"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Fase visual */}
      <div className="mb-3 flex items-center justify-center">
        <div className="relative flex h-16 w-16 items-center justify-center">
          <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
            <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
            <circle
              cx="32"
              cy="32"
              r="28"
              fill="none"
              stroke="#6366f1"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${(deg / 360) * 176} 176`}
              className="transition-all duration-500"
            />
            <circle
              cx={32 + 28 * Math.sin(varData.theta)}
              cy={32 - 28 * Math.cos(varData.theta)}
              r="4"
              fill="#6366f1"
              className="transition-all duration-500"
            />
          </svg>
        </div>
      </div>

      {/* Métricas */}
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between text-zinc-400">
          <span>θ</span>
          <span className="font-mono text-zinc-200">{deg.toFixed(1)}°</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Amplitud</span>
          <span className="font-mono text-zinc-200">{varData.amplitude.toFixed(1)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Velocidad</span>
          <span className="font-mono text-zinc-200">{varData.velocity.toFixed(3)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Valor</span>
          <span className="font-mono text-zinc-200">{varData.value.toFixed(4)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Grupo</span>
          <span className="text-zinc-500">{varData.orbit_group || "default"}</span>
        </div>
      </div>
    </div>
  )
}

function TorMatrix({ entries }: { entries: TorEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        Sin datos TOR — ejecuta un tick primero
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {entries.slice(0, 25).map((entry, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-zinc-800/30"
          style={{ backgroundColor: torBg(entry.tor_value) }}
        >
          <span className="text-zinc-300">
            <span className="text-indigo-400">{entry.variable_i}</span>
            {" ↔ "}
            <span className="text-indigo-400">{entry.variable_j}</span>
          </span>
          <div className="flex items-center gap-3">
            <span className={`font-mono text-xs ${torColor(entry.tor_value)}`}>
              {entry.tor_value.toFixed(4)}
            </span>
            <span className={`text-[10px] ${entry.alignment > 0 ? "text-emerald-500" : "text-red-500"}`}>
              {entry.alignment > 0 ? "resonante" : "opuesta"}
            </span>
          </div>
        </div>
      ))}
      {entries.length > 25 && (
        <p className="pt-1 text-center text-[10px] text-zinc-600">
          Mostrando 25 de {entries.length} parejas
        </p>
      )}
    </div>
  )
}

function CycleCard({ cycle, cod }: { cycle: RccCycle; cod?: CodResult }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio className={`h-4 w-4 ${cycle.is_resonant ? "text-emerald-400" : "text-zinc-500"}`} />
          <span className="text-sm font-medium text-zinc-200">{cycle.cycle_name}</span>
        </div>
        <Badge
          variant="outline"
          className={
            cycle.is_resonant
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
              : "border-zinc-700 bg-zinc-800 text-zinc-400"
          }
        >
          {cycle.is_resonant ? "Resonante" : "Silencio"}
        </Badge>
      </div>
      <div className="space-y-1 text-xs text-zinc-500">
        <div className="flex justify-between">
          <span>ID: {cycle.cycle_id}</span>
          <span>Fuerza: {cycle.strength.toFixed(4)}</span>
        </div>
        {cod && (
          <div className="flex justify-between pt-1 border-t border-zinc-800">
            <span className="flex items-center gap-1">
              {cod.converged ? (
                <CheckCircle2 className="h-3 w-3 text-emerald-400" />
              ) : (
                <XCircle className="h-3 w-3 text-red-400" />
              )}
              {cod.converged ? "Convergió" : "No convergió"}
            </span>
            <span>{cod.iterations} iteraciones</span>
            <span>Δ: {cod.convergence_delta.toExponential(2)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function TickHistoryCard({ history }: { history: TickHistory[] }) {
  if (history.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-sm text-zinc-500">
        Aún no hay ticks ejecutados
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {[...history].reverse().map((h, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-zinc-800/30"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/10 text-[10px] font-bold text-indigo-400">
              #{h.tick}
            </span>
            <span className="text-zinc-400">{h.variables} variables</span>
          </div>
          <span className="font-mono text-xs text-zinc-500">{h.duration_ms}ms</span>
        </div>
      ))}
    </div>
  )
}

// ── Página principal ───────────────────────────

export default function OrbitalPage() {
  const { getApi } = useApi()
  const [status, setStatus] = useState<OrbitalStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ticking, setTicking] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [activeTab, setActiveTab] = useState("visualizer")

  // Diálogo nueva variable
  const [showVarDialog, setShowVarDialog] = useState(false)
  const [varForm, setVarForm] = useState({ name: "", theta: "0", amplitude: "10", velocity: "0.1" })
  const [savingVar, setSavingVar] = useState(false)

  // Diálogo nuevo ciclo
  const [showCycleDialog, setShowCycleDialog] = useState(false)
  const [cycleForm, setCycleForm] = useState({ name: "", variables: "", threshold: "0.5" })
  const [savingCycle, setSavingCycle] = useState(false)

  const loadStatus = useCallback(async () => {
    try {
      const api = getApi()
      const data = await api.get("/api/orbital/status")
      setStatus(data as OrbitalStatus)
      setError(null)
    } catch {
      toast({ title: "Error al cargar estado ORBITAL", variant: "error" })
      setError("No se pudo conectar con el motor ORBITAL. Verifica que el servidor esté corriendo.")
    } finally {
      setLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadStatus()
    return () => ac.abort()
  }, [loadStatus])

  async function handleTick() {
    setTicking(true)
    try {
      const api = getApi()
      await api.post("/api/orbital/tick")
      await loadStatus()
    } catch {
      toast({ title: "Error al ejecutar tick", variant: "error" })
    } finally {
      setTicking(false)
    }
  }

  async function handleReset() {
    if (!confirm("¿Resetear el motor ORBITAL? Se perderán todas las variables y ciclos.")) return
    setResetting(true)
    try {
      const api = getApi()
      await api.post("/api/orbital/reset")
      await loadStatus()
    } catch {
      toast({ title: "Error al resetear", variant: "error" })
    } finally {
      setResetting(false)
    }
  }

  async function handleCreateVariable() {
    if (!varForm.name.trim()) return
    setSavingVar(true)
    try {
      const api = getApi()
      await api.post("/api/orbital/variable", {
        name: varForm.name.trim(),
        theta: parseFloat(varForm.theta) || 0,
        amplitude: parseFloat(varForm.amplitude) || 10,
        velocity: parseFloat(varForm.velocity) || 0.1,
      })
      setShowVarDialog(false)
      setVarForm({ name: "", theta: "0", amplitude: "10", velocity: "0.1" })
      await loadStatus()
    } catch {
      toast({ title: "Error al crear variable", variant: "error" })
    } finally {
      setSavingVar(false)
    }
  }

  async function handleDeleteVariable(name: string) {
    if (!confirm(`¿Eliminar la variable "${name}"?`)) return
    try {
      const api = getApi()
      await api.delete(`/api/orbital/variable/${name}`)
      await loadStatus()
    } catch {
      toast({ title: "Error al eliminar variable", variant: "error" })
    }
  }

  async function handleCreateCycle() {
    if (!cycleForm.name.trim() || !cycleForm.variables.trim()) return
    setSavingCycle(true)
    try {
      const api = getApi()
      await api.post("/api/orbital/cycle", {
        name: cycleForm.name.trim(),
        variables: cycleForm.variables.split(",").map((v) => v.trim()).filter(Boolean),
        threshold: parseFloat(cycleForm.threshold) || 0.5,
      })
      setShowCycleDialog(false)
      setCycleForm({ name: "", variables: "", threshold: "0.5" })
      await loadStatus()
    } catch {
      toast({ title: "Error al crear ciclo", variant: "error" })
    } finally {
      setSavingCycle(false)
    }
  }

  const variableNames = status ? Object.keys(status.variables) : []
  const variableCount = status?.variable_count || 0
  const cycleCount = status?.cycle_count || 0
  const currentTick = status?.tick || 0

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
            <Cpu className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-zinc-100">Monitor ORBITAL</h1>
            <p className="mt-1 text-sm text-zinc-400">
              Visualiza y controla el motor determinista circular en tiempo real
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
              onClick={loadStatus}
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
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48 rounded-lg bg-zinc-800" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10">
              <Cpu className="h-5 w-5 text-indigo-400" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-zinc-100">Monitor ORBITAL</h1>
              <p className="mt-1 text-sm text-zinc-400">
                Visualiza y controla el motor determinista circular en tiempo real
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadStatus}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Recargar
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={resetting}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            {resetting ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <RotateCcw className="mr-1.5 h-4 w-4" />
            )}
            Reset
          </Button>
          <Button
            onClick={handleTick}
            disabled={ticking}
            className="bg-indigo-600 text-white hover:bg-indigo-500"
          >
            {ticking ? (
              <>
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                Ejecutando…
              </>
            ) : (
              <>
                <Play className="mr-1.5 h-4 w-4" />
                Run Tick
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Tarjetas de resumen */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-indigo-400">{currentTick}</p>
            <Activity className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Tick actual</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-zinc-100">{variableCount}</p>
            <CircleDot className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Variables orbitales</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-zinc-100">{cycleCount}</p>
            <Radio className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Ciclos orbitales</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-emerald-400">
              {status?.tor_cache.hit_rate ? `${(status.tor_cache.hit_rate * 100).toFixed(0)}%` : "—"}
            </p>
            <BarChart3 className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Cache TOR (hit rate)</p>
        </div>
      </div>

      {/* Controles de creación */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowVarDialog(true)}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          Nueva variable
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowCycleDialog(true)}
          disabled={variableNames.length < 2}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <Layers className="mr-1.5 h-4 w-4" />
          Nuevo ciclo
        </Button>
      </div>

      {/* Paneles con tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="border-zinc-800 bg-zinc-900 flex-wrap">
          <TabsTrigger
            value="visualizer"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Activity className="mr-1.5 h-4 w-4" />
            Visualizador
          </TabsTrigger>
          <TabsTrigger
            value="variables"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <CircleDot className="mr-1.5 h-4 w-4" />
            Variables
          </TabsTrigger>
          <TabsTrigger
            value="tor"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Zap className="mr-1.5 h-4 w-4" />
            Matriz TOR
          </TabsTrigger>
          <TabsTrigger
            value="rcc"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Radio className="mr-1.5 h-4 w-4" />
            Ciclos RCC
          </TabsTrigger>
          <TabsTrigger
            value="cache"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <BarChart3 className="mr-1.5 h-4 w-4" />
            Cache TOR
          </TabsTrigger>
          <TabsTrigger
            value="history"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <History className="mr-1.5 h-4 w-4" />
            Historial
          </TabsTrigger>
        </TabsList>

        {/* ── Visualizador (Sprint 12) ── */}
        <TabsContent value="visualizer" className="mt-4">
          <OrbitalVisualizer size={480} />
        </TabsContent>

        {/* ── Variables ── */}
        <TabsContent value="variables" className="mt-4">
          {variableNames.length === 0 ? (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="flex flex-col items-center justify-center p-12">
                <CircleDot className="h-12 w-12 text-zinc-600" />
                <h3 className="mt-4 text-sm font-medium text-zinc-300">No hay variables orbitales</h3>
                <p className="mt-1 text-xs text-zinc-500">
                  Crea tu primera variable para empezar a orbitar
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowVarDialog(true)}
                  className="mt-4 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                >
                  <Plus className="mr-1.5 h-4 w-4" />
                  Crear variable
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {variableNames.map((name) => (
                <VariableCard
                  key={name}
                  name={name}
                  varData={status!.variables[name]}
                  onDelete={handleDeleteVariable}
                />
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Matriz TOR ── */}
        <TabsContent value="tor" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <Zap className="h-4 w-4" />
                Tensiones Orbitales Recíprocas
                <span className="text-xs text-zinc-600 font-normal">
                  ({status?.tor.length || 0} parejas)
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TorMatrix entries={status?.tor || []} />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Ciclos RCC ── */}
        <TabsContent value="rcc" className="mt-4">
          {!status?.rcc || status.rcc.length === 0 ? (
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="flex flex-col items-center justify-center p-12">
                <Radio className="h-12 w-12 text-zinc-600" />
                <h3 className="mt-4 text-sm font-medium text-zinc-300">No hay ciclos orbitales</h3>
                <p className="mt-1 text-xs text-zinc-500">
                  Crea un ciclo con al menos 2 variables para ver resonancia
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCycleDialog(true)}
                  disabled={variableNames.length < 2}
                  className="mt-4 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                >
                  <Layers className="mr-1.5 h-4 w-4" />
                  Crear ciclo
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {status.rcc.map((cycle) => {
                const cod = status.cod?.find((c) => c.cycle_id === cycle.cycle_id)
                return <CycleCard key={cycle.cycle_id} cycle={cycle} cod={cod} />
              })}
            </div>
          )}
        </TabsContent>

        {/* ── Cache TOR ── */}
        <TabsContent value="cache" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Estadísticas del Cache TOR
              </CardTitle>
            </CardHeader>
            <CardContent>
              {status?.tor_cache ? (
                <div className="grid gap-4 sm:grid-cols-4">
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
                    <p className="text-lg font-bold text-indigo-400">{status.tor_cache.hits.toLocaleString()}</p>
                    <p className="mt-1 text-xs text-zinc-500">Aciertos (hits)</p>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
                    <p className="text-lg font-bold text-amber-400">{status.tor_cache.misses.toLocaleString()}</p>
                    <p className="mt-1 text-xs text-zinc-500">Fallos (misses)</p>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
                    <p className="text-lg font-bold text-emerald-400">
                      {(status.tor_cache.hit_rate * 100).toFixed(1)}%
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">Hit rate</p>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
                    <p className="text-lg font-bold text-zinc-100">{status.tor_cache.cache_size}</p>
                    <p className="mt-1 text-xs text-zinc-500">Entradas en cache</p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-zinc-500">Cache no disponible</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Historial ── */}
        <TabsContent value="history" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                <History className="h-4 w-4" />
                Historial de ticks
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TickHistoryCard history={status?.history || []} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Diálogo nueva variable ── */}
      <Dialog open={showVarDialog} onOpenChange={setShowVarDialog}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Nueva variable orbital</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Define una variable con fase inicial, amplitud y velocidad orbital
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-zinc-300">
                Nombre <span className="text-red-400">*</span>
              </label>
              <Input
                value={varForm.name}
                onChange={(e) => setVarForm({ ...varForm, name: e.target.value })}
                placeholder="Ej: Demanda, Precio, Oferta"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-sm text-zinc-300">θ inicial</label>
                <Input
                  type="number"
                  step={0.1}
                  value={varForm.theta}
                  onChange={(e) => setVarForm({ ...varForm, theta: e.target.value })}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-zinc-300">Amplitud</label>
                <Input
                  type="number"
                  step={0.5}
                  value={varForm.amplitude}
                  onChange={(e) => setVarForm({ ...varForm, amplitude: e.target.value })}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm text-zinc-300">Velocidad</label>
                <Input
                  type="number"
                  step={0.01}
                  value={varForm.velocity}
                  onChange={(e) => setVarForm({ ...varForm, velocity: e.target.value })}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowVarDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleCreateVariable}
              disabled={savingVar || !varForm.name.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {savingVar ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Creando…
                </>
              ) : (
                "Crear variable"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Diálogo nuevo ciclo ── */}
      <Dialog open={showCycleDialog} onOpenChange={setShowCycleDialog}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Nuevo ciclo orbital</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Agrupa variables en un ciclo cerrado con un umbral de resonancia
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm text-zinc-300">
                Nombre del ciclo <span className="text-red-400">*</span>
              </label>
              <Input
                value={cycleForm.name}
                onChange={(e) => setCycleForm({ ...cycleForm, name: e.target.value })}
                placeholder="Ej: Económico, Logístico"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-300">
                Variables <span className="text-red-400">*</span>
              </label>
              <Input
                value={cycleForm.variables}
                onChange={(e) => setCycleForm({ ...cycleForm, variables: e.target.value })}
                placeholder="Ej: Demanda, Precio, Oferta"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Separadas por coma. Variables disponibles: {variableNames.join(", ") || "ninguna"}
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-300">Umbral de resonancia</label>
              <Input
                type="number"
                step={0.1}
                min={0}
                max={1}
                value={cycleForm.threshold}
                onChange={(e) => setCycleForm({ ...cycleForm, threshold: e.target.value })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
              <p className="mt-1 text-xs text-zinc-500">Entre 0 y 1. Más alto = más difícil resonar</p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowCycleDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleCreateCycle}
              disabled={savingCycle || !cycleForm.name.trim() || !cycleForm.variables.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {savingCycle ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Creando…
                </>
              ) : (
                "Crear ciclo"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
