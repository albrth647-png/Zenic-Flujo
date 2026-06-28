/**
 * OrbitalPage — Monitor del motor ORBITAL (shell con Tabs + 2 Dialogs).
 *
 * Sprint 4 (bug #59): dividido en sub-componentes en `components/orbital/`:
 * - VariableCard / TorMatrix / CycleCard / TickHistoryCard (cards puras)
 * - VariablesTab / TorTab / RccTab / CacheTab / HistoryTab (tab contents)
 * - VariableDialog / CycleDialog (diálogos controlados con form state interno)
 * - helpers.ts (degrees, torColor, torBg)
 *
 * `status` (OrbitalStatus) se mantiene como estado lifted aquí para
 * evitar 6x fetchs y race conditions entre tabs.
 */
import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { OrbitalVisualizer } from "@/components/orbital/OrbitalVisualizer"
import { VariablesTab } from "@/components/orbital/VariablesTab"
import { TorTab } from "@/components/orbital/TorTab"
import { RccTab } from "@/components/orbital/RccTab"
import { CacheTab } from "@/components/orbital/CacheTab"
import { HistoryTab } from "@/components/orbital/HistoryTab"
import { VariableDialog, type VariableFormValues } from "@/components/orbital/VariableDialog"
import { CycleDialog, type CycleFormValues } from "@/components/orbital/CycleDialog"
import { error as humanError } from "@/utils/humanize"
import {
  Activity,
  RefreshCw,
  Play,
  RotateCcw,
  Plus,
  Loader2,
  Zap,
  Radio,
  BarChart3,
  History,
  Cpu,
  CircleDot,
  Layers,
  XCircle,
} from "lucide-react"
import type { OrbitalStatus } from "@/types/orbital"

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
  // Diálogo nuevo ciclo
  const [showCycleDialog, setShowCycleDialog] = useState(false)

  const loadStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const data = await api.get("/api/orbital/status", { signal })
      if (signal?.aborted) return
      setStatus(data as OrbitalStatus)
      setError(null)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar estado", description: humanError(e), variant: "error" })
      setError("No se pudo conectar con el motor ORBITAL. Verifica que el servidor esté corriendo.")
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadStatus(ac.signal)
    return () => ac.abort()
  }, [loadStatus])

  async function handleTick() {
    setTicking(true)
    try {
      const api = getApi()
      await api.post("/api/orbital/tick")
      await loadStatus()
    } catch (e) {
      toast({ title: "Error al ejecutar ciclo", description: humanError(e), variant: "error" })
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
    } catch (e) {
      toast({ title: "Error al reiniciar", description: humanError(e), variant: "error" })
    } finally {
      setResetting(false)
    }
  }

  async function handleCreateVariable(form: VariableFormValues): Promise<void> {
    const api = getApi()
    await api.post("/api/orbital/variable", form)
    await loadStatus()
  }

  async function handleDeleteVariable(name: string) {
    if (!confirm(`¿Eliminar la variable "${name}"?`)) return
    try {
      const api = getApi()
      await api.delete(`/api/orbital/variable/${name}`)
      await loadStatus()
    } catch (e) {
      toast({ title: "Error al eliminar variable", description: humanError(e), variant: "error" })
    }
  }

  async function handleCreateCycle(form: CycleFormValues): Promise<void> {
    const api = getApi()
    await api.post("/api/orbital/cycle", form)
    await loadStatus()
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
              onClick={() => loadStatus()}
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
            onClick={() => loadStatus()}
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
            Reiniciar
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
                Ejecutar ciclo
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
          <p className="mt-1 text-xs text-zinc-500">Aciertos de caché TOR</p>
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
          {status && (
            <VariablesTab
              status={status}
              onNewVariable={() => setShowVarDialog(true)}
              onDeleteVariable={handleDeleteVariable}
            />
          )}
        </TabsContent>

        {/* ── Matriz TOR ── */}
        <TabsContent value="tor" className="mt-4">
          {status && <TorTab status={status} />}
        </TabsContent>

        {/* ── Ciclos RCC ── */}
        <TabsContent value="rcc" className="mt-4">
          {status && (
            <RccTab
              status={status}
              variableNames={variableNames}
              onNewCycle={() => setShowCycleDialog(true)}
            />
          )}
        </TabsContent>

        {/* ── Cache TOR ── */}
        <TabsContent value="cache" className="mt-4">
          {status && <CacheTab status={status} />}
        </TabsContent>

        {/* ── Historial ── */}
        <TabsContent value="history" className="mt-4">
          {status && <HistoryTab status={status} />}
        </TabsContent>
      </Tabs>

      {/* ── Diálogo nueva variable ── */}
      <VariableDialog
        open={showVarDialog}
        onOpenChange={setShowVarDialog}
        onSubmit={handleCreateVariable}
      />

      {/* ── Diálogo nuevo ciclo ── */}
      <CycleDialog
        open={showCycleDialog}
        onOpenChange={setShowCycleDialog}
        onSubmit={handleCreateCycle}
        variableNames={variableNames}
      />
    </div>
  )
}
