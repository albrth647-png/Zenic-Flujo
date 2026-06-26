import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { apiFetch } from "@/hooks/useApi"
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  Lock,
  Activity,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react"

import type { ComplianceOverview } from "@/types/compliance"

const FRAMEWORK_META: Record<string, { label: string; icon: typeof Shield; color: string; bg: string }> = {
  soc2: { label: "SOC 2 Type I", icon: ShieldCheck, color: "text-blue-500", bg: "bg-blue-500/10" },
  gdpr: { label: "GDPR", icon: Lock, color: "text-purple-500", bg: "bg-purple-500/10" },
  hipaa: { label: "HIPAA", icon: Activity, color: "text-emerald-500", bg: "bg-emerald-500/10" },
}

const STATUS_META: Record<string, { label: string; icon: typeof CheckCircle2; color: string }> = {
  verified: { label: "Verificado", icon: CheckCircle2, color: "text-emerald-500" },
  implemented: { label: "Implementado", icon: ShieldCheck, color: "text-blue-500" },
  partial: { label: "Parcial", icon: AlertTriangle, color: "text-amber-500" },
  not_implemented: { label: "No implementado", icon: XCircle, color: "text-gray-400" },
  failed: { label: "Falló", icon: ShieldAlert, color: "text-red-500" },
}

const RISK_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  low: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
}

export default function Compliance() {
  const [data, setData] = useState<ComplianceOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [selectedFramework, setSelectedFramework] = useState<string | null>(null)
  const [selectedStatus, setSelectedStatus] = useState<string | null>(null)

  const loadData = async (signal?: AbortSignal) => {
    const result = await apiFetch<ComplianceOverview>("/api/compliance/overview", { signal })
    if (signal?.aborted) return
    if (result) setData(result)
    if (!signal?.aborted) setLoading(false)
  }

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(ac.signal)
    return () => ac.abort()
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    await loadData()
    setRefreshing(false)
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-6">
                <div className="skeleton h-4 w-24 mb-3" />
                <div className="skeleton h-8 w-16 mb-2" />
                <div className="skeleton h-2 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="skeleton h-[400px]" />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <ShieldAlert className="size-12 text-muted-foreground" />
        <p className="text-muted-foreground">No se pudieron cargar los datos de compliance</p>
        <Button onClick={handleRefresh}>Reintentar</Button>
      </div>
    )
  }

  const { scores } = data
  const frameworks = scores.frameworks || {}

  // Filter controls based on selection
  let filteredControls = data.controls || []
  if (selectedFramework) {
    filteredControls = filteredControls.filter((c) => c.framework === selectedFramework)
  }
  if (selectedStatus) {
    filteredControls = filteredControls.filter((c) => c.status === selectedStatus)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Cumplimiento</h1>
          <p className="text-muted-foreground text-sm">
            Gestión de certificaciones — SOC 2, GDPR e HIPAA
          </p>
        </div>
        <Button variant="outline" size="sm" className="h-8" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw className={cn("size-3.5 mr-1", refreshing && "animate-spin")} />
          Recargar
        </Button>
      </div>

      {/* Framework score cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(frameworks).map(([fwKey, fw]) => {
          const meta = FRAMEWORK_META[fwKey] || { label: fwKey, icon: Shield, color: "text-gray-500", bg: "bg-gray-500/10" }
          const Icon = meta.icon

          return (
            <Card
              key={fwKey}
              className={cn(
                "cursor-pointer transition-all hover:shadow-md",
                selectedFramework === fwKey && "ring-2 ring-primary"
              )}
              onClick={() => setSelectedFramework(selectedFramework === fwKey ? null : fwKey)}
            >
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <div className={cn("rounded-lg p-1.5", meta.bg)}>
                    <Icon className={cn("size-4", meta.color)} />
                  </div>
                  {meta.label}
                </CardTitle>
                <Badge variant={fw.score >= 80 ? "success" : fw.score >= 50 ? "warning" : "destructive"}>
                  {fw.score}%
                </Badge>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Controles</span>
                    <span className="font-medium text-foreground">{fw.total}</span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-2">
                    <div
                      className={cn(
                        "h-2 rounded-full transition-all duration-500",
                        fw.score >= 80 ? "bg-emerald-500" : fw.score >= 50 ? "bg-amber-500" : "bg-red-500"
                      )}
                      style={{ width: `${fw.score}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground mt-2">
                    <span className="flex items-center gap-1">
                      <CheckCircle2 className="size-3 text-emerald-500" />
                      {fw.implemented} implementados
                    </span>
                    <span className="flex items-center gap-1">
                      <AlertTriangle className="size-3 text-amber-500" />
                      {fw.not_implemented} pendientes
                    </span>
                    {fw.failed > 0 && (
                      <span className="flex items-center gap-1">
                        <XCircle className="size-3 text-red-500" />
                        {fw.failed} fallaron
                      </span>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Overall score */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-muted-foreground">Puntaje Global de Cumplimiento</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-6">
            <div className="relative size-24">
              <svg className="size-24 -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="hsl(var(--muted))" strokeWidth="8" />
                <circle
                  cx="50" cy="50" r="42" fill="none"
                  stroke={
                    scores.overall_score >= 80 ? "#10b981" :
                    scores.overall_score >= 50 ? "#f59e0b" : "#ef4444"
                  }
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${(scores.overall_score / 100) * 264} 264`}
                  className="transition-all duration-1000"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold">{scores.overall_score}%</span>
              </div>
            </div>
            <div className="space-y-1 text-sm">
              <p className="text-muted-foreground">
                Basado en <strong>{scores.total_controls}</strong> controles en total
              </p>
              <p className="text-muted-foreground">
                a través de <strong>{Object.keys(frameworks).length}</strong> frameworks
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={selectedStatus === null ? "default" : "outline"}
          size="sm"
          onClick={() => setSelectedStatus(null)}
        >
          Todos
        </Button>
        {Object.entries(STATUS_META).map(([key, meta]) => {
          const Icon = meta.icon
          return (
            <Button
              key={key}
              variant={selectedStatus === key ? "default" : "outline"}
              size="sm"
              onClick={() => setSelectedStatus(selectedStatus === key ? null : key)}
              className="h-8"
            >
              <Icon className={cn("size-3.5 mr-1", meta.color)} />
              {meta.label}
            </Button>
          )
        })}
      </div>

      {/* Controls list */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Shield className="size-4" />
            Controles de Cumplimiento
            {filteredControls.length > 0 && (
              <span className="text-sm font-normal text-muted-foreground">
                ({filteredControls.length})
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px]">
            {filteredControls.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">
                No hay controles que coincidan con los filtros seleccionados.
              </p>
            ) : (
              <div className="space-y-2">
                {filteredControls.map((control) => {
                  const statusMeta = STATUS_META[control.status] || STATUS_META.not_implemented
                  const StatusIcon = statusMeta.icon
                  return (
                    <div
                      key={control.control_id}
                      className="flex items-center justify-between rounded-lg border p-3 hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">{control.name}</span>
                          <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-medium", RISK_COLORS[control.risk_level] || "")}>
                            {control.risk_level}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[11px] text-muted-foreground font-mono">{control.ref_code}</span>
                          <span className="text-[10px] px-1 py-0.5 rounded bg-accent text-muted-foreground">
                            {FRAMEWORK_META[control.framework]?.label || control.framework}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 ml-2 shrink-0">
                        <StatusIcon className={cn("size-4", statusMeta.color)} />
                        <span className={cn("text-xs font-medium", statusMeta.color)}>
                          {statusMeta.label}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Recommendations */}
      {data.recommendations && data.recommendations.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <AlertTriangle className="size-4 text-amber-500" />
              Recomendaciones Priorizadas
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.recommendations.map((rec, i) => (
                <div key={i} className="flex items-start gap-2 rounded-lg border p-3 text-sm">
                  <span className="size-5 shrink-0 rounded-full bg-amber-500/10 text-amber-500 flex items-center justify-center text-[10px] font-bold">
                    {i + 1}
                  </span>
                  <span className="text-muted-foreground">{rec}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
