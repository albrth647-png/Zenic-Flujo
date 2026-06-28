/**
 * MetricsTab — Dashboard de métricas en tiempo real para admin.
 *
 * Sprint 11: muestra 4 secciones coordinadas:
 * 1. KPIs principales (cola, DLQ, throughput)
 * 2. Estadísticas de ejecución por status (última hora)
 * 3. Top 10 workflows más lentos (última hora)
 * 4. Timeline 24h (completadas vs fallidas)
 *
 * Refresca automáticamente cada 30s, también manualmente con botón.
 */
import { useEffect, useState, useCallback } from "react"
import { Activity, Clock, AlertTriangle, Gauge, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "@/components/ui/toast"
import { apiFetch } from "@/hooks/useApi"
import type { AdminMetricsResponse } from "@/types/monitoring"

const REFRESH_INTERVAL_MS = 30_000

export function MetricsTab() {
  const [metrics, setMetrics] = useState<AdminMetricsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const loadMetrics = useCallback(async () => {
    try {
      const resp = await apiFetch<AdminMetricsResponse>("/api/admin/metrics")
      if (resp) {
        setMetrics(resp)
        setLastRefresh(new Date())
      }
    } catch (e) {
      toast({
        title: "Error al cargar métricas",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    } finally {
      setLoading(false)
    }
  }, [])

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    loadMetrics()
    const interval = setInterval(loadMetrics, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [loadMetrics])
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleRefresh = useCallback(async () => {
    setLoading(true)
    await loadMetrics()
  }, [loadMetrics])

  if (loading && !metrics) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  const queueDepth = metrics?.workqueue?.depth ?? 0
  const dlqTotal = metrics?.dead_letter?.total ?? 0
  const workflowStats = metrics?.workflow_stats_1h ?? {}
  const totalCompleted = workflowStats["completed"]?.count ?? 0
  const totalFailed = workflowStats["failed"]?.count ?? 0
  const successRate = totalCompleted + totalFailed > 0
    ? Math.round((totalCompleted / (totalCompleted + totalFailed)) * 100)
    : 100

  return (
    <div className="space-y-4">
      {/* Header con botón de refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Activity className="size-5" />
            Métricas del sistema
          </h3>
          {lastRefresh && (
            <p className="text-xs text-muted-foreground mt-1">
              Última actualización: {lastRefresh.toLocaleTimeString("es-ES")}
              <span className="ml-2 text-muted-foreground/60">
                (auto-refresh cada 30s)
              </span>
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading}>
          <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />
          Refrescar
        </Button>
      </div>

      {/* KPIs principales */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        <KpiCard
          icon={<Gauge className="size-4" />}
          label="Cola pendiente"
          value={queueDepth}
          color="text-blue-400"
        />
        <KpiCard
          icon={<AlertTriangle className="size-4" />}
          label="Dead letter queue"
          value={dlqTotal}
          color={dlqTotal > 50 ? "text-red-400" : "text-amber-400"}
        />
        <KpiCard
          icon={<Activity className="size-4" />}
          label="Completadas (1h)"
          value={totalCompleted}
          color="text-emerald-400"
        />
        <KpiCard
          icon={<Clock className="size-4" />}
          label="Tasa de éxito"
          value={`${successRate}%`}
          color={successRate >= 95 ? "text-emerald-400" : successRate >= 80 ? "text-amber-400" : "text-red-400"}
        />
      </div>

      {/* Stats por status + slowest workflows */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Ejecuciones por estado (última hora)</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(workflowStats).length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Sin ejecuciones en la última hora.
              </p>
            ) : (
              <div className="space-y-2">
                {Object.entries(workflowStats).map(([status, stats]) => (
                  <div key={status} className="flex items-center justify-between rounded-md border p-2">
                    <Badge variant="outline" className={
                      status === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                      status === "failed" ? "bg-red-500/10 text-red-400" :
                      status === "running" ? "bg-blue-500/10 text-blue-400" :
                      "bg-muted"
                    }>
                      {status}
                    </Badge>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="font-mono">{stats.count}</span>
                      {stats.avg_duration_ms != null && (
                        <span className="text-muted-foreground">
                          avg {Math.round(stats.avg_duration_ms)}ms
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Top 10 workflows más lentos (1h)</CardTitle>
          </CardHeader>
          <CardContent>
            {!metrics?.slowest_workflows_1h?.length ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Sin datos de rendimiento en la última hora.
              </p>
            ) : (
              <ScrollArea className="h-[260px] pr-3">
                <div className="space-y-2">
                  {metrics.slowest_workflows_1h.map((wf, i) => (
                    <div
                      key={`${wf.workflow_id}-${wf.started_at}-${i}`}
                      className="rounded-md border p-2 flex items-center justify-between"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="font-medium text-sm truncate">
                          {wf.workflow_name}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {new Date(wf.started_at).toLocaleString("es-ES")}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className={
                          wf.status === "completed" ? "bg-emerald-500/10 text-emerald-400" :
                          wf.status === "failed" ? "bg-red-500/10 text-red-400" :
                          "bg-muted"
                        }>
                          {wf.status}
                        </Badge>
                        <span className="font-mono text-sm">
                          {wf.duration_ms}ms
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Timeline 24h */}
      {metrics?.timeline_24h && metrics.timeline_24h.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Timeline de ejecuciones (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {metrics.timeline_24h
                .reduce((acc, item) => {
                  const existing = acc.find((x) => x.hour === item.hour)
                  if (existing) {
                    existing[item.status] = item.count
                  } else {
                    acc.push({ hour: item.hour, [item.status]: item.count })
                  }
                  return acc
                }, [] as Array<{ hour: string; [key: string]: string | number }>)
                .slice(-12)  // últimas 12 horas
                .map((entry) => {
                  const completed = Number(entry.completed ?? 0)
                  const failed = Number(entry.failed ?? 0)
                  const total = completed + failed
                  const completedPct = total > 0 ? (completed / total) * 100 : 0
                  return (
                    <div key={entry.hour} className="flex items-center gap-2 text-xs">
                      <span className="text-muted-foreground w-32 font-mono">
                        {new Date(entry.hour).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <div className="flex-1 flex h-5 rounded overflow-hidden bg-muted">
                        {total > 0 && (
                          <>
                            <div
                              className="bg-emerald-500/60"
                              style={{ width: `${completedPct}%` }}
                              title={`${completed} completadas`}
                            />
                            <div
                              className="bg-red-500/60"
                              style={{ width: `${100 - completedPct}%` }}
                              title={`${failed} fallidas`}
                            />
                          </>
                        )}
                      </div>
                      <span className="font-mono w-12 text-right">{total}</span>
                    </div>
                  )
                })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function KpiCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode
  label: string
  value: number | string
  color: string
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
          {icon}
          {label}
        </div>
        <div className={`text-2xl font-bold ${color}`}>{value}</div>
      </CardContent>
    </Card>
  )
}
