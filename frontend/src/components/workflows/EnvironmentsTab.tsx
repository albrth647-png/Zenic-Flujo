/**
 * EnvironmentsTab — Pestaña de multi-entorno y versioning para un workflow.
 *
 * Sprint 9: muestra tres secciones coordinadas:
 * 1. Entornos: badges dev/staging/prod + botón "Promover"
 * 2. Versiones: lista de snapshots con rollback
 * 3. Histórico de promociones: auditoría de dev→staging→prod
 *
 * Carga asíncrona desde /api/workflows/:id/{environments,versions,promotions}.
 */
import { useEffect, useState, useCallback } from "react"
import { Rocket, History, GitBranch, RefreshCw, RotateCcw, Trash2, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { toast } from "@/components/ui/toast"
import { apiFetch } from "@/hooks/useApi"
import { PromotionDialog } from "@/components/workflows/PromotionDialog"
import {
  type Environment,
  type WorkflowEnvironment,
  type WorkflowVersion,
  type WorkflowPromotion,
  ENVIRONMENTS,
  ENVIRONMENT_LABELS,
  ENVIRONMENT_BADGE_COLORS,
  ENVIRONMENT_ICONS,
} from "@/types/versioning"

interface EnvironmentsTabProps {
  workflowId: number
  workflowName: string
}

export function EnvironmentsTab({ workflowId, workflowName }: EnvironmentsTabProps) {
  const [environments, setEnvironments] = useState<WorkflowEnvironment[]>([])
  const [versions, setVersions] = useState<WorkflowVersion[]>([])
  const [promotions, setPromotions] = useState<WorkflowPromotion[]>([])
  const [loading, setLoading] = useState(true)
  const [promotionDialogOpen, setPromotionDialogOpen] = useState(false)

  const loadData = useCallback(async () => {
    // Nota: no llamamos setLoading(true) aquí para evitar el warning
    // "react-hooks/set-state-in-effect" cuando loadData se invoca desde useEffect.
    // El estado `loading` se inicializa en true y solo se pone false al terminar.
    try {
      const [envsResp, versionsResp, promotionsResp] = await Promise.all([
        apiFetch<{ environments: WorkflowEnvironment[] }>(`/api/workflows/${workflowId}/environments`),
        apiFetch<{ versions: WorkflowVersion[] }>(`/api/workflows/${workflowId}/versions?limit=20`),
        apiFetch<{ promotions: WorkflowPromotion[] }>(`/api/workflows/${workflowId}/promotions?limit=20`),
      ])
      setEnvironments(envsResp?.environments ?? [])
      setVersions(versionsResp?.versions ?? [])
      setPromotions(promotionsResp?.promotions ?? [])
    } catch (e) {
      toast({
        title: "Error al cargar datos",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    } finally {
      setLoading(false)
    }
  }, [workflowId])

  // Carga inicial de datos cuando cambia el workflowId.
  // El eslint-disable es intencional: loadData llama a setEnvironments/setVersions/setPromotions
  // al resolver las promesas, lo cual es el patrón correcto para data fetching en effects.
  // React 19 recomienda use() para esto, pero mantenemos useEffect por compatibilidad con
  // el resto del código del proyecto.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    loadData()
  }, [loadData])
  /* eslint-enable react-hooks/set-state-in-effect */

  // Función separada para el botón "Refrescar" — esta sí puede poner loading=true
  // porque se invoca desde un event handler, no desde un effect.
  const handleRefresh = useCallback(async () => {
    setLoading(true)
    await loadData()
  }, [loadData])

  const handleAssignToDev = async () => {
    try {
      const resp = await apiFetch(`/api/workflows/${workflowId}/environments/dev`, {
        method: "POST",
        body: JSON.stringify({ notes: "Asignación inicial a dev" }),
      })
      if (resp && typeof resp === "object" && "id" in resp) {
        toast({
          title: "Asignado a Desarrollo",
          description: `${workflowName} ya está disponible en dev`,
          variant: "success",
        })
        loadData()
      } else {
        toast({ title: "Error", description: "No se pudo asignar", variant: "error" })
      }
    } catch (e) {
      toast({
        title: "Error",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    }
  }

  const handleRemoveFromEnvironment = async (env: Environment) => {
    if (!confirm(`¿Quitar ${workflowName} del entorno ${ENVIRONMENT_LABELS[env]}?`)) return
    try {
      const resp = await apiFetch(`/api/workflows/${workflowId}/environments/${env}`, {
        method: "DELETE",
      })
      if (resp !== null) {
        toast({
          title: "Entorno eliminado",
          description: `${workflowName} quitado de ${ENVIRONMENT_LABELS[env]}`,
          variant: "success",
        })
        loadData()
      }
    } catch (e) {
      toast({
        title: "Error",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    }
  }

  const handleRollback = async (versionNumber: number) => {
    if (!confirm(`¿Restaurar el workflow a la versión ${versionNumber}? Se creará una nueva versión con el contenido restaurado.`)) return
    try {
      const resp = await apiFetch<{ message: string }>(`/api/workflows/${workflowId}/versions/${versionNumber}/rollback`, {
        method: "POST",
      })
      if (resp && typeof resp === "object" && "message" in resp) {
        toast({
          title: "Rollback exitoso",
          description: resp.message,
          variant: "success",
        })
        loadData()
      }
    } catch (e) {
      toast({
        title: "Error en rollback",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    }
  }

  const currentEnvSet = new Set(environments.map((e) => e.environment))

  return (
    <div className="space-y-6">
      {/* ─── Sección 1: Entornos ─── */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <GitBranch className="size-4" />
            Entornos
          </CardTitle>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleRefresh}
              disabled={loading}
            >
              <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />
              Refrescar
            </Button>
            {currentEnvSet.size === 0 ? (
              <Button size="sm" onClick={handleAssignToDev}>
                <Plus className="size-3" />
                Asignar a dev
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => setPromotionDialogOpen(true)}
              >
                <Rocket className="size-3" />
                Promover
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {environments.length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">
              Este workflow no está asignado a ningún entorno.
              <br />
              Asígualo a <strong>dev</strong> para empezar el flujo de promoción.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {ENVIRONMENTS.map((envName) => {
                const env = environments.find((e) => e.environment === envName)
                const isAssigned = Boolean(env)
                return (
                  <div
                    key={envName}
                    className={`rounded-lg border p-3 transition-colors ${
                      isAssigned
                        ? "border-border bg-card"
                        : "border-dashed border-muted-foreground/30 bg-muted/20 opacity-60"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{ENVIRONMENT_ICONS[envName]}</span>
                        <div>
                          <div className="font-medium text-sm">{ENVIRONMENT_LABELS[envName]}</div>
                          {isAssigned && env && (
                            <div className="text-xs text-muted-foreground">
                              {env.promoted_from && `Desde ${env.promoted_from} · `}
                              {new Date(env.promoted_at || env.created_at).toLocaleDateString("es-ES")}
                            </div>
                          )}
                        </div>
                      </div>
                      {isAssigned && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                          onClick={() => handleRemoveFromEnvironment(envName)}
                          title={`Quitar de ${ENVIRONMENT_LABELS[envName]}`}
                          aria-label={`Quitar workflow del entorno ${ENVIRONMENT_LABELS[envName]}`}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      )}
                    </div>
                    {isAssigned ? (
                      <Badge
                        className={`mt-2 ${ENVIRONMENT_BADGE_COLORS[envName]}`}
                        variant="outline"
                      >
                        Activo
                      </Badge>
                    ) : (
                      <div className="mt-2 text-xs text-muted-foreground">No asignado</div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ─── Sección 2: Versiones ─── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4" />
            Versiones ({versions.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {versions.length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">
              No hay versiones registradas. Las versiones se crean automáticamente
              al promover el workflow entre entornos.
            </div>
          ) : (
            <ScrollArea className="h-[280px] pr-3">
              <div className="space-y-2">
                {versions.map((version) => (
                  <div
                    key={version.id}
                    className="flex items-start justify-between rounded-md border p-3 hover:bg-accent/50 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="font-mono">
                          v{version.version_number}
                        </Badge>
                        <span className="font-medium text-sm truncate">{version.name}</span>
                      </div>
                      {version.change_summary && (
                        <p className="text-xs text-muted-foreground mt-1 truncate">
                          {version.change_summary}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground mt-1">
                        {new Date(version.created_at).toLocaleString("es-ES")}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleRollback(version.version_number)}
                      title="Restaurar a esta versión"
                      disabled={version.version_number === versions[0]?.version_number}
                    >
                      <RotateCcw className="size-3" />
                      Restaurar
                    </Button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* ─── Sección 3: Histórico de promociones ─── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Rocket className="size-4" />
            Histórico de promociones ({promotions.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {promotions.length === 0 ? (
            <div className="text-sm text-muted-foreground py-6 text-center">
              No se han realizado promociones todavía.
            </div>
          ) : (
            <ScrollArea className="h-[200px] pr-3">
              <div className="space-y-2">
                {promotions.map((promo) => (
                  <div
                    key={promo.id}
                    className="rounded-md border p-3 flex items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <Badge className={ENVIRONMENT_BADGE_COLORS[promo.source_env]} variant="outline">
                        {ENVIRONMENT_ICONS[promo.source_env]} {ENVIRONMENT_LABELS[promo.source_env]}
                      </Badge>
                      <span className="text-muted-foreground">→</span>
                      <Badge className={ENVIRONMENT_BADGE_COLORS[promo.target_env]} variant="outline">
                        {ENVIRONMENT_ICONS[promo.target_env]} {ENVIRONMENT_LABELS[promo.target_env]}
                      </Badge>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-muted-foreground">
                        {new Date(promo.created_at).toLocaleString("es-ES")}
                      </div>
                      {promo.target_version && (
                        <div className="text-xs font-mono">v{promo.target_version}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      <Separator />

      {/* ─── Promotion Dialog ─── */}
      <PromotionDialog
        open={promotionDialogOpen}
        onOpenChange={setPromotionDialogOpen}
        workflowId={workflowId}
        workflowName={workflowName}
        currentEnvironments={environments}
        onPromoted={loadData}
      />
    </div>
  )
}
