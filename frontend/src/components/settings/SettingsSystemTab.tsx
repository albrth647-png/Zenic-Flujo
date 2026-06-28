/**
 * SettingsSystemTab — Tab de sistema en Settings.
 *
 * Endpoint contract:
 *   GET    /api/system/status          → info del sistema (legacy)
 *   GET    /api/system/logs?limit=20   → últimos eventos de audit_log
 *   POST   /api/system/backup          → backup manual inmediato
 *   GET    /api/system/backups         → lista de backups disponibles (M3b)
 *   POST   /api/system/restore         → restaura desde un backup (M3b, SOC 2 A1.3)
 *   GET    /api/system/backup/auto     → estado del auto-backup (M3b)
 *   POST   /api/system/backup/auto     → activa/desactiva auto-backup (M3b)
 *
 * Bug P1-8 (memory leak): los useEffect usan AbortController y lo abortan
 * en cleanup para cancelar fetchs pendientes al desmontar.
 *
 * WCAG: los botones de solo ícono (refresh, restore) llevan aria-label.
 */
import { useEffect, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { apiFetch, useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import {
  Server,
  Loader2,
  Database,
  Activity,
  HardDrive,
  Download,
  RotateCcw,
  RefreshCw,
  Clock,
  ShieldAlert,
} from "lucide-react"

interface SystemStatus {
  version: string
  status: string
  db_path?: string
}

interface AuditLogEntry {
  id: number
  action: string
  created_at: string
}

interface BackupInfo {
  filename: string
  path: string
  name: string
  size_bytes: number
  size_mb: number
  created_at: string
  is_valid: boolean
}

interface BackupListResponse {
  backups: BackupInfo[]
  total_backups: number
  total_size_mb: number
}

interface AutoBackupStatus {
  enabled: boolean
  interval_hours: number | null
  last_backup_at: string | null
}

interface RestoreResponse {
  success: boolean
  restored_path: string
  message: string
}

/** Intervalos soportados por el Select (horas → etiqueta). */
const INTERVAL_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "1", label: "Cada 1 hora" },
  { value: "6", label: "Cada 6 horas" },
  { value: "12", label: "Cada 12 horas" },
  { value: "24", label: "Cada 24 horas" },
  { value: "48", label: "Cada 48 horas" },
]

/** Formatea bytes a una representación humana (B/KB/MB/GB). */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB", "TB"]
  let value = bytes / 1024
  let unitIdx = 0
  while (value >= 1024 && unitIdx < units.length - 1) {
    value /= 1024
    unitIdx++
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIdx]}`
}

/** Formatea una fecha ISO a string localizado en español. */
function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleString("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return iso
  }
}

export function SettingsSystemTab() {
  const { getApi } = useApi()
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [backingUp, setBackingUp] = useState(false)
  const [logs, setLogs] = useState<AuditLogEntry[]>([])

  // Backups disponibles + estado del restore dialog.
  const [backups, setBackups] = useState<BackupInfo[]>([])
  const [backupsLoading, setBackupsLoading] = useState(true)
  const [restoring, setRestoring] = useState(false)
  const [restoreTarget, setRestoreTarget] = useState<BackupInfo | null>(null)

  // Auto-backup config.
  const [autoStatus, setAutoStatus] = useState<AutoBackupStatus>({
    enabled: false,
    interval_hours: null,
    last_backup_at: null,
  })
  const [autoLoading, setAutoLoading] = useState(true)
  const [autoSaving, setAutoSaving] = useState(false)

  // ── Carga inicial: sistema + logs ──────────────────────────
  // Mantiene el patrón original (apiFetch no-throw) para no romper el
  // comportamiento existente. AbortController para evitar updates tras unmount.
  useEffect(() => {
    const ac = new AbortController()
    Promise.all([
      apiFetch<SystemStatus>("/api/system/status", { signal: ac.signal }),
      apiFetch<AuditLogEntry[]>("/api/system/logs?limit=20", { signal: ac.signal }),
    ]).then(([statusRes, logsRes]) => {
      if (ac.signal.aborted) return
      if (statusRes) setStatus(statusRes)
      if (logsRes) setLogs(logsRes)
      setLoading(false)
    })
    return () => ac.abort()
  }, [])

  // ── Carga de backups disponibles ───────────────────────────
  const loadBackups = useCallback(async (signal?: AbortSignal) => {
    setBackupsLoading(true)
    try {
      const api = getApi()
      const data = await api.get<BackupListResponse>("/api/system/backups", { signal })
      if (signal?.aborted) return
      setBackups(data?.backups ?? [])
    } catch (e) {
      if (signal?.aborted) return
      if (e instanceof DOMException && e.name === "AbortError") return
      toast({
        title: "Error al cargar backups",
        description: "No se pudo obtener la lista de backups",
        variant: "error",
      })
    } finally {
      if (!signal?.aborted) setBackupsLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadBackups(ac.signal)
    return () => ac.abort()
  }, [loadBackups])

  // ── Carga del estado del auto-backup ───────────────────────
  const loadAutoStatus = useCallback(async (signal?: AbortSignal) => {
    setAutoLoading(true)
    try {
      const api = getApi()
      const data = await api.get<AutoBackupStatus>("/api/system/backup/auto", { signal })
      if (signal?.aborted) return
      if (data) setAutoStatus(data)
    } catch (e) {
      if (signal?.aborted) return
      if (e instanceof DOMException && e.name === "AbortError") return
      // No molestar al usuario con un toast si solo falló cargar el estado
      // (es información secundaria). Lo dejamos en default desactivado.
    } finally {
      if (!signal?.aborted) setAutoLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAutoStatus(ac.signal)
    return () => ac.abort()
  }, [loadAutoStatus])

  // ── Acciones ───────────────────────────────────────────────
  const handleBackup = async () => {
    setBackingUp(true)
    try {
      const api = getApi()
      const res = await api.post<{ path: string; status: string }>("/api/system/backup")
      if (res?.status === "completed") {
        toast({
          title: "Backup completado",
          description: "La copia de seguridad se creó correctamente",
          variant: "success",
        })
        // Recargar la lista de backups para mostrar el recién creado.
        loadBackups()
        // Refrescar last_backup_at del auto-backup status.
        loadAutoStatus()
      } else {
        toast({
          title: "Error al hacer backup",
          description: "No se pudo completar la copia de seguridad",
          variant: "error",
        })
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error de conexión"
      toast({
        title: "Error al hacer backup",
        description: msg,
        variant: "error",
      })
    } finally {
      setBackingUp(false)
    }
  }

  const handleRestore = async (backup: BackupInfo) => {
    setRestoring(true)
    try {
      const api = getApi()
      const res = await api.post<RestoreResponse>("/api/system/restore", {
        backup_filename: backup.filename,
      })
      if (res?.success) {
        toast({
          title: "Restauración completada",
          description: res.message || "Base de datos restaurada correctamente",
          variant: "success",
        })
        setRestoreTarget(null)
        // El restore cambia la DB: recargar todo lo que dependa de ella.
        loadBackups()
        loadAutoStatus()
      } else {
        toast({
          title: "Error al restaurar",
          description: "El servidor no confirmó la restauración",
          variant: "error",
        })
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Error de conexión"
      toast({
        title: "Error al restaurar",
        description: msg,
        variant: "error",
      })
    } finally {
      setRestoring(false)
    }
  }

  const handleAutoToggle = async (enabled: boolean) => {
    setAutoSaving(true)
    const prev = autoStatus
    // Optimistic update para feedback inmediato del Switch.
    setAutoStatus({ ...prev, enabled })
    try {
      const api = getApi()
      const intervalHours = prev.interval_hours ?? 24
      const res = await api.post<AutoBackupStatus & { success: boolean }>(
        "/api/system/backup/auto",
        enabled
          ? { enabled: true, interval_hours: intervalHours }
          : { enabled: false },
      )
      if (res) {
        // El backend devuelve {success, enabled, interval_hours}. Sincronizamos
        // last_backup_at desde el estado previo (el POST no lo devuelve).
        setAutoStatus({
          enabled: res.enabled,
          interval_hours: res.interval_hours,
          last_backup_at: prev.last_backup_at,
        })
      }
      toast({
        title: enabled ? "Backup automático activado" : "Backup automático desactivado",
        variant: "success",
      })
    } catch (e) {
      // Revertir el optimistic update.
      setAutoStatus(prev)
      const msg = e instanceof Error ? e.message : "Error de conexión"
      toast({
        title: "Error al configurar backup automático",
        description: msg,
        variant: "error",
      })
    } finally {
      setAutoSaving(false)
    }
  }

  const handleIntervalChange = async (hoursStr: string) => {
    const intervalHours = parseInt(hoursStr, 10)
    if (Number.isNaN(intervalHours) || intervalHours < 1) return
    setAutoSaving(true)
    const prev = autoStatus
    setAutoStatus({ ...prev, interval_hours: intervalHours, enabled: true })
    try {
      const api = getApi()
      const res = await api.post<{ success: boolean; enabled: boolean; interval_hours: number }>(
        "/api/system/backup/auto",
        { enabled: true, interval_hours: intervalHours },
      )
      if (res) {
        setAutoStatus({
          enabled: res.enabled,
          interval_hours: res.interval_hours,
          last_backup_at: prev.last_backup_at,
        })
      }
      toast({
        title: "Intervalo actualizado",
        description: `Backup automático cada ${intervalHours}h`,
        variant: "success",
      })
    } catch (e) {
      setAutoStatus(prev)
      const msg = e instanceof Error ? e.message : "Error de conexión"
      toast({
        title: "Error al cambiar el intervalo",
        description: msg,
        variant: "error",
      })
    } finally {
      setAutoSaving(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="skeleton h-4 w-32 mb-4" />
          <div className="skeleton h-20 w-full mb-3" />
          <div className="skeleton h-40 w-full" />
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Server className="size-4" />
            Información del sistema
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  <Activity className="size-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Versión</span>
                </div>
                <span className="font-medium">{status?.version || "—"}</span>
              </div>
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  <Activity className="size-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Estado</span>
                </div>
                <Badge variant="success">Funcionando</Badge>
              </div>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  <Database className="size-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Base de datos</span>
                </div>
                <span className="text-xs font-mono text-muted-foreground truncate max-w-[140px]">
                  {status?.db_path || "—"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="flex items-center gap-2">
                  <HardDrive className="size-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Backup</span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleBackup}
                  disabled={backingUp}
                >
                  {backingUp ? (
                    <Loader2 className="size-3 mr-1 animate-spin" />
                  ) : (
                    <Download className="size-3 mr-1" />
                  )}
                  {backingUp ? "Respaldando..." : "Hacer backup"}
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Backup automático ───────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Clock className="size-4" />
            Backup automático
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Programa copias de seguridad periódicas de la base de datos
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">Activar backup automático</div>
              <div className="text-xs text-muted-foreground">
                {autoLoading
                  ? "Cargando estado…"
                  : autoStatus.enabled
                    ? `Activo · último backup: ${formatDate(autoStatus.last_backup_at)}`
                    : "Desactivado"}
              </div>
            </div>
            <Switch
              checked={autoStatus.enabled}
              onCheckedChange={handleAutoToggle}
              disabled={autoLoading || autoSaving}
              aria-label="Activar o desactivar backup automático"
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3">
            <div className="space-y-0.5">
              <div className="text-sm font-medium">Intervalo</div>
              <div className="text-xs text-muted-foreground">
                Frecuencia con la que se ejecuta el backup automático
              </div>
            </div>
            <div className="w-[180px]">
              <Select
                value={String(autoStatus.interval_hours ?? 24)}
                onValueChange={handleIntervalChange}
                disabled={!autoStatus.enabled || autoLoading || autoSaving}
              >
                <SelectTrigger
                  aria-label="Intervalo de backup automático en horas"
                  className="h-8 text-xs"
                >
                  <SelectValue placeholder="Seleccionar intervalo" />
                </SelectTrigger>
                <SelectContent>
                  {INTERVAL_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {autoStatus.enabled && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-400">
              <Clock className="size-3.5 mt-0.5 shrink-0" />
              <span>
                El backup automático se ejecuta en segundo plano. El siguiente
                backup se realizará {autoStatus.last_backup_at
                  ? `aprox. ${formatDate(autoStatus.last_backup_at)} + ${autoStatus.interval_hours}h`
                  : `en ${autoStatus.interval_hours}h`}.
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Historial de backups ────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                <Database className="size-4" />
                Backups disponibles
              </CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                {backups.length} backup{backups.length !== 1 ? "s" : ""} en el directorio de copias
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => loadBackups()}
              disabled={backupsLoading}
              aria-label="Refrescar lista de backups"
            >
              {backupsLoading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {backupsLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-12 w-full rounded-lg" />
              ))}
            </div>
          ) : backups.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No hay backups disponibles. Crea uno con el botón "Hacer backup".
            </p>
          ) : (
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {backups.map((backup) => (
                <div
                  key={backup.path}
                  className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <Database className="size-3.5 text-muted-foreground shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono truncate">
                          {backup.filename}
                        </span>
                        {!backup.is_valid && (
                          <Badge
                            variant="outline"
                            className="border-red-500/30 bg-red-500/10 text-[10px] text-red-500"
                          >
                            <ShieldAlert className="size-2.5 mr-1" />
                            corrupto
                          </Badge>
                        )}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-2">
                        <span>{formatBytes(backup.size_bytes)}</span>
                        <span>·</span>
                        <span>{formatDate(backup.created_at)}</span>
                      </div>
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs ml-2 shrink-0"
                    onClick={() => setRestoreTarget(backup)}
                    disabled={!backup.is_valid || restoring}
                    aria-label={`Restaurar backup ${backup.filename}`}
                  >
                    <RotateCcw className="size-3 mr-1" />
                    Restaurar
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Registro de actividades</CardTitle>
          <p className="text-sm text-muted-foreground">
            Últimas acciones registradas en el sistema
          </p>
        </CardHeader>
        <CardContent>
          {logs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No hay registros de actividad aún
            </p>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm hover:bg-accent/50 transition-colors"
                >
                  <span className="text-muted-foreground text-xs font-mono truncate flex-1">
                    {log.action}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0 ml-2">
                    {log.created_at
                      ? new Date(log.created_at).toLocaleString("es-ES", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Dialog de confirmación de restore ───────────────── */}
      <Dialog
        open={restoreTarget !== null}
        onOpenChange={(open) => {
          if (!open && !restoring) setRestoreTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldAlert className="size-5 text-amber-500" />
              Confirmar restauración
            </DialogTitle>
            <DialogDescription>
              Vas a reemplazar la base de datos actual por el contenido del
              backup seleccionado. Esta operación es destructiva e
              irreversible, aunque el sistema creará automáticamente un safety
              backup del estado actual antes de sobrescribirlo.
            </DialogDescription>
          </DialogHeader>

          {restoreTarget && (
            <div className="rounded-lg border bg-muted/40 p-3 text-sm space-y-1">
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Archivo:</span>
                <span className="font-mono text-xs break-all">
                  {restoreTarget.filename}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Tamaño:</span>
                <span>{formatBytes(restoreTarget.size_bytes)}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Fecha:</span>
                <span>{formatDate(restoreTarget.created_at)}</span>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRestoreTarget(null)}
              disabled={restoring}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (restoreTarget) handleRestore(restoreTarget)
              }}
              disabled={restoring}
            >
              {restoring ? (
                <>
                  <Loader2 className="size-4 mr-1.5 animate-spin" />
                  Restaurando…
                </>
              ) : (
                <>
                  <RotateCcw className="size-4 mr-1.5" />
                  Restaurar ahora
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
