import { useEffect, useState, useCallback, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { StatusBadge } from "@/components/StatusBadge"
import { AnimatedCounter } from "@/components/dashboard/AnimatedCounter"
import { LiveExecutionFeed } from "@/components/dashboard/LiveExecutionFeed"
import { TimelineChart } from "@/components/dashboard/TimelineChart"
import { SuccessChart } from "@/components/dashboard/SuccessChart"
import { ToolsChart } from "@/components/dashboard/ToolsChart"
import type { ToolData, TimelineData } from "@/types/reports"
import { apiFetch } from "@/hooks/useApi"
import { cn } from "@/lib/utils"
import { useSSE } from "@/hooks/useSSE"
import { error as humanError } from "@/utils/humanize"
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  PauseCircle,
  RefreshCw,
} from "lucide-react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { toast } from "@/components/ui/toast"

interface DashboardStats {
  stats: {
    total: number
    by_status: Record<string, number>
    recent_executions: Array<{
      id: number
      name: string
      status: string
      started_at: string
    }>
  }
  trial: {
    is_trial: boolean
    days_left: number
  }
}

interface TimelineResponse {
  daily: TimelineData[]
  tools: ToolData[]
}

interface LiveEvent {
  id: string
  workflow_id: number
  name: string
  status: "started" | "completed" | "failed"
  duration_ms?: number
  error?: string
  timestamp: string
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardStats | null>(null)
  const [timeline, setTimeline] = useState<TimelineData[]>([])
  const [tools, setTools] = useState<ToolData[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const eventIdCounter = useRef(0)
  const cancelledRef = useRef(false)

  // ── Load initial data ──────────────────────────────────
  const loadData = useCallback(async () => {
    try {
      const [statsRes, timelineRes] = await Promise.all([
        apiFetch<DashboardStats>("/api/dashboard/stats"),
        apiFetch<TimelineResponse>("/api/dashboard/timeline?days=14"),
      ])
      if (cancelledRef.current) return
      if (statsRes) setData(statsRes)
      if (cancelledRef.current) return
      if (timelineRes) {
        setTimeline(timelineRes.daily || [])
        setTools(timelineRes.tools || [])
      }
    } catch (e) {
      if (!cancelledRef.current) {
        toast({ title: "Error al cargar dashboard", description: humanError(e), variant: "error" })
      }
    } finally {
      if (!cancelledRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    cancelledRef.current = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData()
    return () => { cancelledRef.current = true }
  }, [loadData])

  const handleRefresh = async () => {
    setRefreshing(true)
    await loadData()
    setRefreshing(false)
  }

  // ── SSE: Real-time events ──────────────────────────────
  const { on: onSSE, connected } = useSSE("/api/events/stream")

  // Listen for execution events
  useEffect(() => {
    // BUG P1-9: antes los setTimeout en los handlers SSE no se cancelaban en
    // cleanup, causando memory leak y llamadas a loadData() sobre un componente
    // desmontado. Ahora se trackean y se cancelan en el cleanup del effect.
    const pendingTimers = new Set<ReturnType<typeof setTimeout>>()
    const scheduleRefresh = () => {
      const id = setTimeout(() => loadData(), 500)
      pendingTimers.add(id)
    }
    const unsubStarted = onSSE("execution.started", (event) => {
      const liveEvent: LiveEvent = {
        id: `live-${++eventIdCounter.current}`,
        workflow_id: event.data.workflow_id as number,
        name: event.data.name as string,
        status: "started",
        timestamp: event.data.timestamp as string,
      }
      window.dispatchEvent(new CustomEvent("dashboard-live-event", { detail: liveEvent }))
    })

    const unsubCompleted = onSSE("execution.completed", (event) => {
      const liveEvent: LiveEvent = {
        id: `live-${++eventIdCounter.current}`,
        workflow_id: event.data.workflow_id as number,
        name: event.data.name as string,
        status: "completed",
        duration_ms: event.data.duration_ms as number,
        timestamp: event.data.timestamp as string,
      }
      window.dispatchEvent(new CustomEvent("dashboard-live-event", { detail: liveEvent }))
      scheduleRefresh()
    })

    const unsubFailed = onSSE("execution.failed", (event) => {
      const liveEvent: LiveEvent = {
        id: `live-${++eventIdCounter.current}`,
        workflow_id: event.data.workflow_id as number,
        name: event.data.name as string,
        status: "failed",
        error: event.data.error as string,
        timestamp: event.data.timestamp as string,
      }
      window.dispatchEvent(new CustomEvent("dashboard-live-event", { detail: liveEvent }))
      scheduleRefresh()
    })

    return () => {
      unsubStarted()
      unsubCompleted()
      unsubFailed()
      // Cancela los timers pendientes para evitar el leak (BUG P1-9).
      pendingTimers.forEach((id) => clearTimeout(id))
      pendingTimers.clear()
    }
  }, [onSSE, loadData])

  const stats = data?.stats
  const trial = data?.trial

  // ── Compute totals ────────────────────────────────────
  const totalErrors = (stats?.by_status?.failed ?? 0) + (stats?.by_status?.error ?? 0)
  const totalCompleted = timeline.reduce((s, d) => s + d.completed, 0)
  const totalFailed = timeline.reduce((s, d) => s + d.failed, 0)

  const cards = [
    {
      title: "Total",
      value: stats?.total ?? 0,
      icon: Activity,
      color: "text-blue-500",
      bg: "bg-blue-500/10",
    },
    {
      title: "Activos",
      value: stats?.by_status?.active ?? 0,
      icon: CheckCircle2,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10",
    },
    {
      title: "Errores",
      value: totalErrors,
      icon: AlertTriangle,
      color: "text-red-500",
      bg: "bg-red-500/10",
    },
    {
      title: "Pausados",
      value: stats?.by_status?.paused ?? 0,
      icon: PauseCircle,
      color: "text-amber-500",
      bg: "bg-amber-500/10",
    },
  ]

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="skeleton h-4 w-20 mb-3" />
                <div className="skeleton h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="skeleton h-[250px]" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Panel Principal</h1>
          <p className="text-muted-foreground text-sm flex items-center gap-2">
            Resumen de tus flujos y automatizaciones
            {connected && (
              <span className="flex items-center gap-1 text-[10px] text-emerald-500">
                <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                En vivo
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={cn("size-3.5 mr-1", refreshing && "animate-spin")} />
            Recargar
          </Button>

          {trial?.is_trial ? (
            <Badge variant="warning">
              Prueba: {trial.days_left}d restantes
            </Badge>
          ) : (
            <Badge variant="success">Licencia activa</Badge>
          )}
          <Link to="/app/editor">
            <Badge variant="default" className="cursor-pointer hover:opacity-80 transition-opacity">
              + Nuevo flujo
            </Badge>
          </Link>
        </div>
      </div>

      {/* Stats grid with animated counters */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {card.title}
              </CardTitle>
              <div className={cn("rounded-lg p-2", card.bg)}>
                <card.icon className={cn("size-4", card.color)} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                <AnimatedCounter value={card.value} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Charts row */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              📈 Ejecuciones por día
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[220px]">
              <TimelineChart data={timeline} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              ✅ Tasa de éxito
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[220px]">
              <SuccessChart completed={totalCompleted} failed={totalFailed} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom grid: Tools + Live feed */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Tools chart */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              🔧 Tools más usadas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[250px]">
              <ToolsChart data={tools} />
            </div>
          </CardContent>
        </Card>

        {/* Live execution feed */}
        <LiveExecutionFeed />
      </div>

      {/* Recent executions */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">🕐 Últimas ejecuciones</CardTitle>
        </CardHeader>
        <CardContent>
          {stats?.recent_executions?.length ? (
            <div className="space-y-2">
              {stats.recent_executions.map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center justify-between rounded-lg border p-3 hover:bg-accent/50 transition-colors"
                >
                  <span className="text-sm font-medium">{exec.name}</span>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={exec.status} />
                    <span className="text-xs text-muted-foreground">
                      {exec.started_at
                        ? new Date(exec.started_at).toLocaleDateString("es-ES", {
                            day: "numeric",
                            month: "short",
                          })
                        : ""}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-6 text-center">
              Sin ejecuciones aún.{" "}
              <Link to="/app/editor" className="text-primary hover:underline">
                Crea tu primer flujo
              </Link>
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
