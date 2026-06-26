/**
 * AlertsTab — Gestión de alertas del sistema.
 *
 * Sprint 11: muestra 3 secciones:
 * 1. Resumen de alertas (stats por severidad + botón "Evaluar ahora")
 * 2. Lista de alertas activas con botón "Resolver"
 * 3. Histórico de alertas resueltas
 * 4. Reglas configuradas (read-only por ahora)
 */
import { useEffect, useState, useCallback } from "react"
import { Bell, AlertCircle, CheckCircle2, Play, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { toast } from "@/components/ui/toast"
import { apiFetch } from "@/hooks/useApi"
import {
  type AlertEvent,
  type AlertStats,
  type AlertRule,
  SEVERITY_LABELS,
  SEVERITY_BADGE_COLORS,
  SEVERITY_ICONS,
  STATUS_LABELS,
  STATUS_BADGE_COLORS,
  formatComparison,
} from "@/types/monitoring"

export function AlertsTab() {
  const [stats, setStats] = useState<AlertStats | null>(null)
  const [activeAlerts, setActiveAlerts] = useState<AlertEvent[]>([])
  const [resolvedAlerts, setResolvedAlerts] = useState<AlertEvent[]>([])
  const [rules, setRules] = useState<AlertRule[]>([])
  const [loading, setLoading] = useState(true)
  const [evaluating, setEvaluating] = useState(false)

  const loadAll = useCallback(async () => {
    try {
      const [statsResp, activeResp, resolvedResp, rulesResp] = await Promise.all([
        apiFetch<AlertStats>("/api/admin/alerts/stats"),
        apiFetch<{ alerts: AlertEvent[] }>("/api/admin/alerts?status=active&limit=50"),
        apiFetch<{ alerts: AlertEvent[] }>("/api/admin/alerts?status=resolved&limit=20"),
        apiFetch<{ rules: AlertRule[] }>("/api/admin/alerts/rules"),
      ])
      setStats(statsResp)
      setActiveAlerts(activeResp?.alerts ?? [])
      setResolvedAlerts(resolvedResp?.alerts ?? [])
      setRules(rulesResp?.rules ?? [])
    } catch (e) {
      toast({
        title: "Error al cargar alertas",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    } finally {
      setLoading(false)
    }
  }, [])

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    loadAll()
  }, [loadAll])
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleResolve = async (alertId: number) => {
    try {
      const resp = await apiFetch(`/api/admin/alerts/${alertId}/resolve`, { method: "POST" })
      if (resp !== null) {
        toast({
          title: "Alerta resuelta",
          description: `Alerta #${alertId} marcada como resuelta`,
          variant: "success",
        })
        loadAll()
      }
    } catch (e) {
      toast({
        title: "Error",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    }
  }

  const handleEvaluate = async () => {
    setEvaluating(true)
    try {
      const resp = await apiFetch<{ triggered_count: number }>("/api/admin/alerts/evaluate", {
        method: "POST",
      })
      if (resp && typeof resp === "object" && "triggered_count" in resp) {
        toast({
          title: "Evaluación completada",
          description: `${resp.triggered_count} alerta(s) disparada(s)`,
          variant: resp.triggered_count > 0 ? "warning" : "success",
        })
        loadAll()
      }
    } catch (e) {
      toast({
        title: "Error",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    } finally {
      setEvaluating(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header con botones */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Bell className="size-5" />
            Alertas del sistema
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {stats?.total_active ?? 0} activas · {stats?.total_resolved ?? 0} resueltas · {stats?.rules_count ?? 0} reglas
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={loadAll} disabled={loading}>
            <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
          <Button size="sm" onClick={handleEvaluate} disabled={evaluating}>
            <Play className="size-3" />
            {evaluating ? "Evaluando..." : "Evaluar ahora"}
          </Button>
        </div>
      </div>

      {/* Resumen por severidad */}
      {stats && (
        <div className="grid gap-3 grid-cols-3">
          {(["info", "warning", "critical"] as const).map((sev) => {
            const sevStats = stats.by_severity[sev] ?? { active: 0, resolved: 0, suppressed: 0 }
            return (
              <Card key={sev}>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">{SEVERITY_ICONS[sev]}</span>
                    <span className="text-sm font-medium">{SEVERITY_LABELS[sev]}</span>
                  </div>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Activas:</span>
                      <span className={`font-mono ${sevStats.active > 0 ? "text-red-400" : ""}`}>
                        {sevStats.active ?? 0}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Resueltas:</span>
                      <span className="font-mono text-emerald-400">{sevStats.resolved ?? 0}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Alertas activas */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <AlertCircle className="size-4" />
            Alertas activas ({activeAlerts.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {activeAlerts.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              ✅ No hay alertas activas. El sistema está saludable.
            </p>
          ) : (
            <ScrollArea className="h-[300px] pr-3">
              <div className="space-y-2">
                {activeAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="rounded-md border p-3 space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <Badge className={SEVERITY_BADGE_COLORS[alert.severity]} variant="outline">
                          {SEVERITY_ICONS[alert.severity]} {SEVERITY_LABELS[alert.severity]}
                        </Badge>
                        <span className="font-medium text-sm truncate">{alert.rule_name}</span>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleResolve(alert.id)}
                        title="Marcar como resuelta"
                      >
                        <CheckCircle2 className="size-3" />
                        Resolver
                      </Button>
                    </div>
                    <p className="text-sm text-muted-foreground">{alert.message}</p>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>Valor: <span className="font-mono">{alert.metric_value}</span></span>
                      <span>Umbral: <span className="font-mono">{alert.threshold}</span></span>
                      <span>·</span>
                      <span>{new Date(alert.created_at).toLocaleString("es-ES")}</span>
                      {alert.channels_notified.length > 0 && (
                        <>
                          <span>·</span>
                          <span>Notificado vía: {alert.channels_notified.join(", ")}</span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Histórico de resueltas */}
      {resolvedAlerts.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle2 className="size-4" />
              Histórico reciente ({resolvedAlerts.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[200px] pr-3">
              <div className="space-y-1">
                {resolvedAlerts.map((alert) => (
                  <div
                    key={alert.id}
                    className="rounded-md border p-2 flex items-center justify-between text-sm"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge className={SEVERITY_BADGE_COLORS[alert.severity]} variant="outline">
                        {SEVERITY_ICONS[alert.severity]}
                      </Badge>
                      <span className="truncate">{alert.rule_name}</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Badge className={STATUS_BADGE_COLORS[alert.status]} variant="outline">
                        {STATUS_LABELS[alert.status]}
                      </Badge>
                      <span>{new Date(alert.created_at).toLocaleString("es-ES")}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Reglas configuradas */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Reglas configuradas ({rules.length})</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {rules.map((rule) => (
              <div
                key={rule.name}
                className={`rounded-md border p-3 ${!rule.enabled ? "opacity-60" : ""}`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <Badge className={SEVERITY_BADGE_COLORS[rule.severity]} variant="outline">
                      {SEVERITY_LABELS[rule.severity]}
                    </Badge>
                    <span className="font-medium text-sm font-mono">{rule.name}</span>
                    {!rule.enabled && (
                      <Badge variant="outline" className="bg-muted">deshabilitada</Badge>
                    )}
                  </div>
                  <Badge variant="outline" className="bg-muted">
                    {rule.channels.join(" + ")}
                  </Badge>
                </div>
                <p className="text-sm text-muted-foreground">{rule.description}</p>
                <p className="text-xs text-muted-foreground mt-1 font-mono">
                  {rule.metric_name} {formatComparison(rule.comparison, rule.threshold)}
                  {" · "}cooldown {rule.cooldown_seconds}s
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
