/**
 * QueueTab — Monitor de la cola de trabajos y workers para admin.
 *
 * Sprint 4 (bug #59): extraído de AdminPage.tsx para reducir LOC.
 * Estado local: metrics, workers, items, loading.
 * API: GET /api/queue/status, /api/queue/workers.
 */
import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Activity,
  AlertCircle,
  Inbox,
  CheckCircle2,
} from "lucide-react"
import type { QueueMetrics, WorkerInfo, QueueItem } from "@/types/admin"

export function QueueTab() {
  const { getApi } = useApi()
  const [metrics, setMetrics] = useState<QueueMetrics | null>(null)
  const [workers, setWorkers] = useState<WorkerInfo[]>([])
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const [statusData, workersData] = await Promise.all([
        api.get("/api/queue/status", { signal }),
        api.get("/api/queue/workers", { signal }),
      ])
      if (signal?.aborted) return
      const s = statusData as { metrics: QueueMetrics; next_items: QueueItem[] }
      setMetrics(s.metrics)
      setItems(s.next_items || [])
      setWorkers(workersData as WorkerInfo[])
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar cola", variant: "error" })
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

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`
    if (seconds < 3600) return `${Math.round(seconds / 60)}min`
    return `${(seconds / 3600).toFixed(1)}h`
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
      {/* Métricas */}
      {metrics && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            { label: "En cola", value: metrics.queue_size, icon: <Inbox className="h-4 w-4" />, color: "text-blue-400" },
            { label: "Procesando", value: metrics.processing, icon: <Activity className="h-4 w-4" />, color: "text-amber-400" },
            { label: "Completados", value: metrics.completed, icon: <CheckCircle2 className="h-4 w-4" />, color: "text-emerald-400" },
            { label: "Fallidos", value: metrics.failed, icon: <AlertCircle className="h-4 w-4" />, color: "text-red-400" },
            { label: "Ritmo", value: `${metrics.throughput_per_minute}/min`, icon: <Activity className="h-4 w-4" />, color: "text-zinc-300" },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3"
            >
              <div className="flex items-center justify-between">
                <p className={`text-lg font-bold ${item.color}`}>{item.value}</p>
                <span className="text-zinc-600">{item.icon}</span>
              </div>
              <p className="mt-1 text-xs text-zinc-500">{item.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Trabajadores activos */}
      <div className="mb-4">
        <h3 className="mb-2 text-sm font-medium text-zinc-300">Trabajadores activos</h3>
        {workers.length === 0 ? (
          <p className="text-sm text-zinc-500">No hay trabajadores activos en este momento</p>
        ) : (
          <div className="space-y-2">
            {workers.map((worker) => (
              <div
                key={worker.id}
                className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 p-3"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2 w-2 rounded-full ${
                      worker.status === "active" ? "bg-emerald-400" : "bg-zinc-600"
                    }`}
                  />
                  <div>
                    <p className="text-sm font-medium text-zinc-200">{worker.name}</p>
                    <p className="text-xs text-zinc-500">
                      {worker.tasks_completed} tarea{worker.tasks_completed !== 1 ? "s" : ""} completada{worker.tasks_completed !== 1 ? "s" : ""}
                      {worker.uptime_seconds > 0 && ` · ${formatTime(worker.uptime_seconds)} activo`}
                    </p>
                  </div>
                </div>
                {worker.current_task && (
                  <Badge variant="outline" className="border-blue-500/20 bg-blue-500/10 text-xs text-blue-400">
                    <Activity className="mr-1 h-3 w-3" />
                    {worker.current_task}
                  </Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Próximos trabajos */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-zinc-300">Próximos trabajos</h3>
        {items.length === 0 ? (
          <EmptyState
            icon={<Inbox className="h-10 w-10" />}
            title="Cola vacía"
            description="No hay trabajos pendientes. Todo está al día."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 p-3"
              >
                <div>
                  <p className="text-sm font-medium text-zinc-200">
                    {item.workflow_name || `Workflow #${item.workflow_id}`}
                  </p>
                  <p className="text-xs text-zinc-500">
                    Prioridad: {item.priority} · {new Date(item.created_at).toLocaleString("es-MX")}
                  </p>
                </div>
                <Badge
                  variant="outline"
                  className={`border ${
                    item.status === "processing"
                      ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
                      : item.status === "failed"
                        ? "border-red-500/20 bg-red-500/10 text-red-400"
                        : "border-zinc-700 bg-zinc-800 text-zinc-400"
                  }`}
                >
                  {item.status === "processing"
                    ? "Procesando"
                    : item.status === "failed"
                      ? "Fallido"
                      : "En espera"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
