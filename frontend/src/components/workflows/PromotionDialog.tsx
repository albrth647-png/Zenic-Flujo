/**
 * PromotionDialog — Modal para promover un workflow entre entornos.
 *
 * Sprint 9: muestra el entorno origen, el destino, calcula el diff
 * potencial y permite añadir notas antes de confirmar la promoción.
 *
 * Validaciones:
 * - Solo permite promociones válidas según PROMOTION_FLOW (dev→staging, staging→prod).
 * - Bloquea el botón "Promover" si no hay selección o si la promoción es inválida.
 */
import { useState, useEffect, useMemo } from "react"
import { Rocket, ArrowRight, AlertCircle } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { toast } from "@/components/ui/toast"
import { apiFetch } from "@/hooks/useApi"
import {
  type Environment,
  type WorkflowEnvironment,
  ENVIRONMENT_LABELS,
  ENVIRONMENT_BADGE_COLORS,
  ENVIRONMENT_ICONS,
  PROMOTION_FLOW,
  isValidPromotion,
  getAvailablePromotions,
} from "@/types/versioning"

interface PromotionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  workflowId: number
  workflowName: string
  currentEnvironments: WorkflowEnvironment[]
  onPromoted: () => void
}

export function PromotionDialog({
  open,
  onOpenChange,
  workflowId,
  workflowName,
  currentEnvironments,
  onPromoted,
}: PromotionDialogProps) {
  const [sourceEnv, setSourceEnv] = useState<Environment | "">("")
  const [targetEnv, setTargetEnv] = useState<Environment | "">("")
  const [notes, setNotes] = useState("")
  const [submitting, setSubmitting] = useState(false)

  // Lista de promociones válidas basada en los entornos donde está el workflow
  const availablePromotions = useMemo(
    () => getAvailablePromotions(currentEnvironments.map((e) => e.environment)),
    [currentEnvironments],
  )

  // Reset al abrir: auto-seleccionar la primera promoción disponible.
  // El eslint-disable es intencional: este effect sincroniza el estado interno
  // del diálogo (sourceEnv, targetEnv, notes) cuando se abre, lo cual es un
  // patrón legítimo de "reset state on prop change".
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (open) {
      if (availablePromotions.length > 0) {
        setSourceEnv(availablePromotions[0].source)
        setTargetEnv(availablePromotions[0].target)
      } else {
        setSourceEnv("")
        setTargetEnv("")
      }
      setNotes("")
    }
  }, [open, availablePromotions])
  /* eslint-enable react-hooks/set-state-in-effect */

  const isValid = Boolean(sourceEnv && targetEnv && isValidPromotion(sourceEnv as Environment, targetEnv as Environment))

  const handleSubmit = async () => {
    if (!isValid) return
    setSubmitting(true)
    try {
      const resp = await apiFetch(`/api/workflows/${workflowId}/promote`, {
        method: "POST",
        body: JSON.stringify({
          source_env: sourceEnv,
          target_env: targetEnv,
          notes,
        }),
      })
      if (resp && typeof resp === "object" && "id" in resp) {
        toast({
          title: "Promoción exitosa",
          description: `${workflowName} promovido a ${ENVIRONMENT_LABELS[targetEnv as Environment]}`,
          variant: "success",
        })
        onPromoted()
        onOpenChange(false)
      } else {
        const errMsg = (resp as { error?: string })?.error || "No se pudo promover el workflow"
        toast({ title: "Error", description: errMsg, variant: "error" })
      }
    } catch (e) {
      toast({
        title: "Error de conexión",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Rocket className="size-5" />
            Promover workflow
          </DialogTitle>
          <DialogDescription>
            Promueve <span className="font-medium text-foreground">{workflowName}</span> entre entornos.
            El flujo permitido es dev → staging → prod.
          </DialogDescription>
        </DialogHeader>

        {availablePromotions.length === 0 ? (
          <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
            <AlertCircle className="size-5 text-amber-500 mt-0.5 shrink-0" />
            <div className="text-sm">
              <p className="font-medium">No hay promociones disponibles</p>
              <p className="text-muted-foreground mt-1">
                Este workflow ya está en todos los entornos alcanzables desde su estado actual,
                o no está asignado a ningún entorno. Asigna el workflow a un entorno primero.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-4 py-2">
            {/* Selector de promoción */}
            <div className="space-y-2">
              <Label htmlFor="promote-source-target">Promoción</Label>
              <Select
                value={sourceEnv && targetEnv ? `${sourceEnv}->${targetEnv}` : ""}
                onValueChange={(val) => {
                  const [s, t] = val.split("->") as [Environment, Environment]
                  setSourceEnv(s)
                  setTargetEnv(t)
                }}
              >
                <SelectTrigger id="promote-source-target">
                  <SelectValue placeholder="Selecciona una promoción" />
                </SelectTrigger>
                <SelectContent>
                  {availablePromotions.map(({ source, target }) => (
                    <SelectItem key={`${source}->${target}`} value={`${source}->${target}`}>
                      <span className="flex items-center gap-2">
                        <span>{ENVIRONMENT_ICONS[source]}</span>
                        <span>{ENVIRONMENT_LABELS[source]}</span>
                        <ArrowRight className="size-3" />
                        <span>{ENVIRONMENT_ICONS[target]}</span>
                        <span>{ENVIRONMENT_LABELS[target]}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Visual de flujo */}
            {sourceEnv && targetEnv && (
              <div className="flex items-center justify-center gap-3 rounded-lg border bg-muted/30 p-4">
                <Badge className={ENVIRONMENT_BADGE_COLORS[sourceEnv as Environment]} variant="outline">
                  {ENVIRONMENT_ICONS[sourceEnv as Environment]} {ENVIRONMENT_LABELS[sourceEnv as Environment]}
                </Badge>
                <ArrowRight className="size-4 text-muted-foreground" />
                <Badge className={ENVIRONMENT_BADGE_COLORS[targetEnv as Environment]} variant="outline">
                  {ENVIRONMENT_ICONS[targetEnv as Environment]} {ENVIRONMENT_LABELS[targetEnv as Environment]}
                </Badge>
              </div>
            )}

            {/* Notas */}
            <div className="space-y-2">
              <Label htmlFor="promote-notes">Notas (opcional)</Label>
              <Textarea
                id="promote-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Ej: Cambios validados en QA, listo para producción..."
                rows={3}
                className="resize-none"
              />
            </div>

            <div className="text-xs text-muted-foreground">
              Al promover se creará una nueva versión del workflow (snapshot) y se registrará
              en el histórico de promociones para auditoría.
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!isValid || submitting || availablePromotions.length === 0}
          >
            {submitting ? "Promoviendo..." : `Promover a ${targetEnv ? ENVIRONMENT_LABELS[targetEnv as Environment] : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Re-export para uso directo en otros componentes
export { PROMOTION_FLOW }
