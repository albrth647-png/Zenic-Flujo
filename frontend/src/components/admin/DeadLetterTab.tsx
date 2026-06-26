/**
 * DeadLetterTab — Buzón de errores (Dead Letter Queue) para admin.
 *
 * Sprint 4 (bug #59): extraído de AdminPage.tsx para reducir LOC.
 * Estado local: entries, stats, loading, filter.
 * API: GET /api/dead-letter, /api/dead-letter/stats,
 *      POST /api/dead-letter/:id/retry, /:id/discard,
 *           /api/dead-letter/retry-all, /discard-all.
 */
import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Trash2,
  RefreshCw,
  Play,
  XCircle,
  RotateCcw,
  CheckCircle2,
} from "lucide-react"
import type { DeadLetterEntry, DeadLetterStats } from "@/types/admin"

export function DeadLetterTab() {
  const { getApi } = useApi()
  const [entries, setEntries] = useState<DeadLetterEntry[]>([])
  const [stats, setStats] = useState<DeadLetterStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>("all")

  const loadData = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const [data, statsData] = await Promise.all([
        api.get(`/api/dead-letter${filter !== "all" ? `?status=${filter}` : ""}`, { signal }),
        api.get("/api/dead-letter/stats", { signal }),
      ])
      if (signal?.aborted) return
      const r = data as { entries: DeadLetterEntry[]; stats: DeadLetterStats }
      setEntries(r.entries || [])
      setStats(statsData as DeadLetterStats)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar buzón", variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi, filter])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(ac.signal)
    return () => ac.abort()
  }, [loadData])

  async function handleRetry(entryId: number) {
    try {
      const api = getApi()
      await api.post(`/api/dead-letter/${entryId}/retry`)
      loadData()
    } catch {
      toast({ title: "Error al reintentar", variant: "error" })
    }
  }

  async function handleDiscard(entryId: number) {
    try {
      const api = getApi()
      await api.post(`/api/dead-letter/${entryId}/discard`)
      loadData()
    } catch {
      toast({ title: "Error al descartar", variant: "error" })
    }
  }

  async function handleRetryAll() {
    try {
      const api = getApi()
      await api.post("/api/dead-letter/retry-all")
      loadData()
    } catch {
      toast({ title: "Error al reintentar todos", variant: "error" })
    }
  }

  async function handleDiscardAll() {
    if (!confirm("¿Estás seguro de descartar todos los errores? Esta acción no se puede deshacer.")) return
    try {
      const api = getApi()
      await api.post("/api/dead-letter/discard-all")
      loadData()
    } catch {
      toast({ title: "Error al descartar todos", variant: "error" })
    }
  }

  function getStatusBadge(status: string) {
    const styles: Record<string, string> = {
      pending: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      retrying: "bg-blue-500/10 text-blue-400 border-blue-500/20",
      resolved: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
      discarded: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
    }
    const labels: Record<string, string> = {
      pending: "Pendiente",
      retrying: "Reintentando",
      resolved: "Resuelto",
      discarded: "Descartado",
    }
    return (
      <Badge variant="outline" className={`border ${styles[status] || styles.pending}`}>
        {labels[status] || status}
      </Badge>
    )
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 w-full rounded-lg bg-zinc-800" />
        ))}
      </div>
    )
  }

  return (
    <div>
      {/* Resumen */}
      {stats && (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            { label: "Total", value: stats.total, color: "text-zinc-300" },
            { label: "Pendientes", value: stats.pending, color: "text-amber-400" },
            { label: "Reintentando", value: stats.retrying, color: "text-blue-400" },
            { label: "Resueltos", value: stats.resolved, color: "text-emerald-400" },
            { label: "Descartados", value: stats.discarded, color: "text-zinc-500" },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center"
            >
              <p className={`text-2xl font-bold ${item.color}`}>{item.value}</p>
              <p className="mt-1 text-xs text-zinc-500">{item.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filtros y acciones */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-[150px] border-zinc-700 bg-zinc-800 text-zinc-200">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-zinc-700 bg-zinc-800 text-zinc-200">
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="pending">Pendientes</SelectItem>
              <SelectItem value="retrying">Reintentando</SelectItem>
              <SelectItem value="resolved">Resueltos</SelectItem>
              <SelectItem value="discarded">Descartados</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRetryAll}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            Reintentar todos
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDiscardAll}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Descartar todos
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => loadData()}
            className="text-zinc-400 hover:text-zinc-200"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {entries.length === 0 ? (
        <EmptyState
          icon={<CheckCircle2 className="h-12 w-12 text-emerald-400" />}
          title="Todo en orden"
          description="No hay errores pendientes. Todos los workflows están funcionando correctamente."
        />
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="mb-1 flex items-center gap-2">
                    {getStatusBadge(entry.status)}
                    <span className="text-sm font-medium text-zinc-200">
                      {entry.workflow_name || `Workflow #${entry.workflow_id}`}
                    </span>
                    {entry.retry_count > 0 && (
                      <span className="text-xs text-zinc-500">
                        ({entry.retry_count} reintento{entry.retry_count !== 1 ? "s" : ""})
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-400">{entry.error_message}</p>
                  <div className="mt-1 flex items-center gap-3 text-xs text-zinc-600">
                    <span>{new Date(entry.failed_at).toLocaleString("es-MX")}</span>
                    {entry.step_id && <span>· Paso: {entry.step_id}</span>}
                  </div>
                </div>
                <div className="flex gap-1">
                  {(entry.status === "pending" || entry.status === "retrying") && (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRetry(entry.id)}
                        className="text-zinc-400 hover:text-emerald-400"
                        title="Reintentar"
                        aria-label={`Reintentar entrada ${entry.id}`}
                      >
                        <Play className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDiscard(entry.id)}
                        className="text-zinc-400 hover:text-red-400"
                        title="Descartar"
                        aria-label={`Descartar entrada ${entry.id}`}
                      >
                        <XCircle className="h-4 w-4" />
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
