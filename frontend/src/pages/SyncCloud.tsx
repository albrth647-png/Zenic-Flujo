import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import { apiFetch } from "@/hooks/useApi"
import {
  Cloud,
  CloudOff,
  Key,
  Upload,
  Download,
  RefreshCw,
  Shield,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Copy,
  EyeOff,
  Trash2,
  History,
} from "lucide-react"

import type { SyncConfig, SyncStats, SyncHistoryEntry } from "@/types/sync"

export default function SyncCloud() {
  const [config, setConfig] = useState<SyncConfig | null>(null)
  const [stats, setStats] = useState<SyncStats | null>(null)
  const [history, setHistory] = useState<SyncHistoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [generatedKey, setGeneratedKey] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)

  // ── Form state ────────────────────────────────────────
  const [targetUrl, setTargetUrl] = useState("")
  const [targetApiKey, setTargetApiKey] = useState("")
  const [enabled, setEnabled] = useState(false)
  const [autoSync, setAutoSync] = useState(false)
  const [includeCredentials, setIncludeCredentials] = useState(false)
  const [conflictStrategy, setConflictStrategy] = useState("timestamp_wins")
  const [syncInterval, setSyncInterval] = useState(60)

  // ── Load data ─────────────────────────────────────────
  const loadData = useCallback(async (signal?: AbortSignal) => {
    const [configRes, statsRes, historyRes] = await Promise.all([
      apiFetch<SyncConfig>("/api/sync/config", { signal }),
      apiFetch<SyncStats>("/api/sync/stats", { signal }),
      apiFetch<{ history: SyncHistoryEntry[] }>("/api/sync/history", { signal }),
    ])
    if (signal?.aborted) return
    if (configRes) {
      setConfig(configRes)
      setTargetUrl(configRes.target_url || "")
      setEnabled(configRes.enabled)
      setAutoSync(configRes.auto_sync)
      setIncludeCredentials(configRes.include_credentials)
      setConflictStrategy(configRes.conflict_strategy)
      setSyncInterval(configRes.sync_interval_minutes)
    }
    if (statsRes) setStats(statsRes)
    if (historyRes) setHistory(historyRes.history || [])
    if (!signal?.aborted) setLoading(false)
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(ac.signal)
    return () => ac.abort()
  }, [loadData])

  // ── Actions ────────────────────────────────────────────

  const handleSaveConfig = async () => {
    setSaving(true)
    const result = await apiFetch("/api/sync/config", {
      method: "PUT",
      body: JSON.stringify({
        enabled,
        target_url: targetUrl,
        target_api_key: targetApiKey,
        auto_sync: autoSync,
        include_credentials: includeCredentials,
        conflict_strategy: conflictStrategy,
        sync_interval_minutes: syncInterval,
      }),
    })
    setSaving(false)
    if (result) {
      await loadData()
    }
  }

  const handleGenerateKey = async () => {
    const result = await apiFetch<{ key_b64: string; hmac_key_b64: string }>("/api/sync/key/generate", {
      method: "POST",
    })
    if (result) {
      setGeneratedKey(result.key_b64)
      setShowKey(true)
      await loadData()
    }
  }

  const handleCopyKey = () => {
    if (generatedKey) {
      navigator.clipboard.writeText(generatedKey)
    }
  }

  const handleExportAll = async () => {
    const workflowsRes = await apiFetch<Array<{ id: number }>>("/api/workflows")
    if (!workflowsRes || workflowsRes.length === 0) return
    const workflowIds = workflowsRes.map((w: { id: number }) => w.id)
    const result = await apiFetch("/api/sync/export", {
      method: "POST",
      body: JSON.stringify({ workflow_ids: workflowIds, include_credentials: includeCredentials }),
    })
    if (result) {
      await loadData()
    }
  }

  const handlePushAll = async () => {
    const workflowsRes = await apiFetch<Array<{ id: number }>>("/api/workflows")
    if (!workflowsRes || workflowsRes.length === 0) return
    const workflowIds = workflowsRes.map((w: { id: number }) => w.id)
    const result = await apiFetch("/api/sync/push", {
      method: "POST",
      body: JSON.stringify({ workflow_ids: workflowIds }),
    })
    if (result) {
      await loadData()
    }
  }

  const handleDeleteConfig = async () => {
    if (!confirm("¿Estás seguro? Esto eliminará toda la configuración de sync y datos asociados.")) return
    await apiFetch("/api/sync/config", { method: "DELETE" })
    await loadData()
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}><CardContent className="p-6"><div className="skeleton h-4 w-24 mb-3" /><div className="skeleton h-8 w-16" /></CardContent></Card>
          ))}
        </div>
        <div className="skeleton h-[300px]" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Sincronización</h1>
          <p className="text-muted-foreground text-sm">
            Sincronización cifrada de flujos de trabajo entre servidores
          </p>
        </div>
        <Badge variant={enabled ? "success" : "secondary"} className="gap-1">
          {enabled ? <Cloud className="size-3" /> : <CloudOff className="size-3" />}
          {enabled ? "Activado" : "Desactivado"}
        </Badge>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Status card */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Shield className="size-4" />
              Cifrado
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Clave de cifrado</span>
              <span className={cn("flex items-center gap-1 font-medium", (config?.has_encryption_key || stats?.has_encryption_key) ? "text-emerald-500" : "text-red-500")}>
                {(config?.has_encryption_key || stats?.has_encryption_key) ? <><CheckCircle2 className="size-3" /> Configurada</> : <><XCircle className="size-3" /> Sin clave</>}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">URL destino</span>
              <span className={cn("font-medium", stats?.has_target ? "text-emerald-500" : "text-muted-foreground")}>
                {stats?.has_target ? "Configurada" : "No configurada"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Auto sincronización</span>
              <span className="font-medium">{stats?.auto_sync ? "Activado" : "Desactivado"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Última sincronización</span>
              <span className="font-medium">
                {stats?.last_sync_status === "completed"
                  ? new Date((stats?.last_sync_at || 0) * 1000).toLocaleDateString("es-ES", { day: "numeric", month: "short" })
                  : stats?.last_sync_status || "Nunca"}
              </span>
            </div>
            <Separator />
            <div className="flex justify-between">
              <span className="text-muted-foreground">Flujos exportados</span>
              <span className="font-medium">{stats?.total_exported_workflows || 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Operaciones totales</span>
              <span className="font-medium">{stats?.total_sync_operations || 0}</span>
            </div>
          </CardContent>
        </Card>

        {/* Configuration */}
        <Card className="md:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Cloud className="size-4" />
              Configuración
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2">
              <Label className="text-sm">Activar Sync Cloud</Label>
              <Button
                variant={enabled ? "default" : "outline"}
                size="sm"
                onClick={() => setEnabled(!enabled)}
                className="h-8"
              >
                {enabled ? "Activado" : "Desactivado"}
              </Button>
            </div>

            <div className="grid gap-3">
              <div>
                <Label htmlFor="sync-target-url" className="text-xs text-muted-foreground">URL del servidor destino</Label>
                <Input
                  id="sync-target-url"
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="https://tuservidor.com"
                  className="h-8 text-sm mt-1"
                />
              </div>
              <div>
                <Label htmlFor="sync-target-api-key" className="text-xs text-muted-foreground">API Key del servidor destino</Label>
                <Input
                  id="sync-target-api-key"
                  value={targetApiKey}
                  onChange={(e) => setTargetApiKey(e.target.value)}
                  placeholder={stats?.has_target ? "••••••••" : "Ingresa la API Key"}
                  className="h-8 text-sm mt-1"
                  type="password"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="sync-interval" className="text-xs text-muted-foreground">Intervalo (minutos)</Label>
                <Input
                  id="sync-interval"
                  type="number"
                  value={syncInterval}
                  onChange={(e) => setSyncInterval(parseInt(e.target.value) || 60)}
                  className="h-8 text-sm mt-1"
                  min={15}
                  max={1440}
                />
              </div>
              <div>
                <Label htmlFor="sync-conflict-strategy" className="text-xs text-muted-foreground">Estrategia de conflictos</Label>
                <select
                  id="sync-conflict-strategy"
                  value={conflictStrategy}
                  onChange={(e) => setConflictStrategy(e.target.value)}
                  className="flex h-8 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors mt-1"
                >
                  <option value="timestamp_wins">Gana el más reciente</option>
                  <option value="version_wins">Gana versión mayor</option>
                  <option value="keep_both">Mantener ambos</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-4 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoSync}
                  onChange={(e) => setAutoSync(e.target.checked)}
                  className="rounded"
                />
                Auto Sync programado
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeCredentials}
                  onChange={(e) => setIncludeCredentials(e.target.checked)}
                  className="rounded"
                />
                Incluir credenciales
              </label>
            </div>

            <div className="flex gap-2">
              <Button size="sm" className="h-8" onClick={handleSaveConfig} disabled={saving}>
                {saving ? <RefreshCw className="size-3.5 mr-1 animate-spin" /> : null}
                Guardar configuración
              </Button>
              <Button variant="destructive" size="sm" className="h-8" onClick={handleDeleteConfig}>
                <Trash2 className="size-3.5 mr-1" />
                Eliminar
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* E2E Key Generation */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <Key className="size-4" />
            Clave de cifrado
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-4">
            <div className="flex-1 space-y-2">
              <p className="text-sm text-muted-foreground">
                Esta clave protege los flujos de trabajo antes de enviarlos.
                La clave <strong>nunca</strong> se envía al otro servidor.
                El destino debe tener la <strong>misma clave</strong> para poder descifrar.
              </p>
              {generatedKey && showKey && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
                  <AlertTriangle className="size-4 text-amber-500 shrink-0" />
                  <code className="text-xs font-mono break-all flex-1">{generatedKey}</code>
                  <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={handleCopyKey} aria-label="Copiar clave de cifrado">
                    <Copy className="size-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" className="size-7 shrink-0" onClick={() => setShowKey(false)} aria-label="Ocultar clave de cifrado">
                    <EyeOff className="size-3.5" />
                  </Button>
                </div>
              )}
              {generatedKey && !showKey && (
                <p className="text-xs text-amber-500 flex items-center gap-1">
                  <AlertTriangle className="size-3" />
                  Clave generada. Haz clic en mostrar para copiarla (solo se muestra una vez).
                </p>
              )}
            </div>
            <Button size="sm" className="h-8 shrink-0" onClick={handleGenerateKey}>
              <Key className="size-3.5 mr-1" />
              {config?.has_encryption_key ? "Renovar clave" : "Generar clave"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex gap-3">
        <Button size="sm" className="h-8" onClick={handleExportAll}>
          <Download className="size-3.5 mr-1" />
          Exportar todos los flujos
        </Button>
        <Button size="sm" className="h-8" variant="secondary" onClick={handlePushAll} disabled={!stats?.has_target}>
          <Upload className="size-3.5 mr-1" />
          Enviar al servidor
        </Button>
      </div>

      {/* History */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
            <History className="size-4" />
            Historial de sincronización
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[300px]">
            {history.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">Sin operaciones de sync aún.</p>
            ) : (
              <div className="space-y-1">
                {history.map((entry) => (
                  <div
                    key={entry.entry_id}
                    className="flex items-center justify-between rounded-lg border p-2.5 hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "size-7 rounded-lg flex items-center justify-center",
                        entry.status === "completed" ? "bg-emerald-500/10" : "bg-red-500/10"
                      )}>
                        {entry.status === "completed"
                          ? <CheckCircle2 className="size-3.5 text-emerald-500" />
                          : <XCircle className="size-3.5 text-red-500" />
                        }
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium capitalize">{entry.action}</span>
                          <Badge variant="outline" className="text-[10px] px-1 py-0">
                            {entry.workflow_count} workflows
                          </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground">
                          {new Date(entry.timestamp * 1000).toLocaleString("es-ES")}
                        </p>
                      </div>
                    </div>
                    {entry.error_message && (
                      <span className="text-[11px] text-red-500 max-w-[200px] truncate">{entry.error_message}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
