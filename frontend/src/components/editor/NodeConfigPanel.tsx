import { useCallback } from "react"
import { useReactFlow } from "@xyflow/react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import {
  TOOL_ACTIONS,
  PARAM_LABELS,
  EVENT_OPTIONS,
} from "@/types/workflow"
import type {
  WorkflowNode,
  TriggerNodeData,
  ActionNodeData,
  TriggerType,
} from "@/types/workflow"
import { cn } from "@/lib/utils"
import { X, Trash2 } from "lucide-react"

interface NodeConfigPanelProps {
  node: WorkflowNode | null
  onClose: () => void
  onDelete: (nodeId: string) => void
}

export function NodeConfigPanel({ node, onClose, onDelete }: NodeConfigPanelProps) {
  const { updateNodeData, deleteElements } = useReactFlow()

  // Actualiza los datos del nodo. Acepta un Partial del tipo data y lo pasa
  // a updateNodeData (que internamente espera Record<string, unknown>).
  // El index signature en TriggerNodeData/ActionNodeData garantiza que son
  // compatibles con Record<string, unknown>.
  const updateData = useCallback(
    (data: Partial<TriggerNodeData> | Partial<ActionNodeData>) => {
      if (!node) return
      updateNodeData(node.id, data as Record<string, unknown>)
    },
    [node, updateNodeData]
  )

  if (!node) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        <p className="text-sm text-muted-foreground">
          Selecciona un nodo para configurarlo
        </p>
      </div>
    )
  }

  const handleDelete = () => {
    if (node.id === "trigger") return
    deleteElements({ nodes: [{ id: node.id }] })
    onDelete(node.id)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <h3 className="text-sm font-semibold">
          {node.data.nodeType === "trigger" ? "⚡ Configurar Trigger" : "🔧 Configurar Acción"}
        </h3>
        <Button variant="ghost" size="icon" className="size-7" onClick={onClose} aria-label="Cerrar panel de configuración">
          <X className="size-3.5" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-4">
          {node.data.nodeType === "trigger" ? (
            <TriggerConfig
              data={node.data as TriggerNodeData}
              onChange={(d) => updateData(d)}
            />
          ) : (
            <ActionConfig
              data={node.data as ActionNodeData}
              onChange={(d) => updateData(d)}
            />
          )}
        </div>
      </ScrollArea>

      {/* Footer */}
      {node.id !== "trigger" && (
        <div className="p-3 border-t">
          <Button
            variant="destructive"
            size="sm"
            className="w-full"
            onClick={handleDelete}
          >
            <Trash2 className="size-3.5 mr-1" />
            Eliminar paso
          </Button>
        </div>
      )}
    </div>
  )
}

// ── Trigger Config ──────────────────────────────────────────

function TriggerConfig({
  data,
  onChange,
}: {
  data: TriggerNodeData
  onChange: (d: Partial<TriggerNodeData>) => void
}) {
  const triggerTypes: TriggerType[] = ["event", "schedule", "webhook", "manual"]

  const triggerConfigFor = (type: TriggerType): Partial<TriggerNodeData> => {
    const labels: Record<TriggerType, string> = {
      event: "📡 Evento",
      schedule: "⏰ Programado",
      webhook: "🔗 Webhook",
      manual: "▶️ Manual",
    }
    return { triggerType: type, label: labels[type] }
  }

  return (
    <div className="space-y-4">
      {/* Trigger type selector */}
      <div className="space-y-2">
        <Label>Tipo de disparador</Label>
        <div className="grid grid-cols-2 gap-1.5">
          {triggerTypes.map((t) => (
            <button
              key={t}
              onClick={() => onChange(triggerConfigFor(t))}
              className={cn(
                "rounded-lg border px-3 py-2 text-xs font-medium transition-all",
                data.triggerType === t
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:border-muted-foreground/30"
              )}
            >
              {triggerConfigFor(t).label}
            </button>
          ))}
        </div>
      </div>

      {/* Event selection */}
      {data.triggerType === "event" && (
        <div className="space-y-2">
          <Label htmlFor="trigger-event">Evento</Label>
          <select
            id="trigger-event"
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
            value={data.triggerConfig?.event || EVENT_OPTIONS[0]}
            onChange={(e) =>
              onChange({
                triggerConfig: { ...data.triggerConfig, event: e.target.value },
                label: `📡 ${e.target.value}`,
              })
            }
          >
            {EVENT_OPTIONS.map((ev) => (
              <option key={ev} value={ev}>
                {ev}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Schedule config */}
      {data.triggerType === "schedule" && (
        <>
          <div className="space-y-2">
            <Label htmlFor="trigger-frequency">Frecuencia</Label>
            <select
              id="trigger-frequency"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
              value={data.triggerConfig?.frequency || "daily"}
              onChange={(e) =>
                onChange({
                  triggerConfig: { ...data.triggerConfig, frequency: e.target.value },
                  label: `⏰ ${e.target.value} ${data.triggerConfig?.time || "23:00"}`,
                })
              }
            >
              <option value="daily">Diario</option>
              <option value="weekly">Semanal</option>
              <option value="monthly">Mensual</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="trigger-time">Hora</Label>
            <Input
              id="trigger-time"
              type="time"
              value={data.triggerConfig?.time || "23:00"}
              onChange={(e) =>
                onChange({
                  triggerConfig: { ...data.triggerConfig, time: e.target.value },
                  label: `⏰ ${data.triggerConfig?.frequency || "daily"} ${e.target.value}`,
                })
              }
            />
          </div>
        </>
      )}

      {/* Webhook config */}
      {data.triggerType === "webhook" && (
        <div className="space-y-2">
          <Label htmlFor="trigger-path">Path personalizado</Label>
          <Input
            id="trigger-path"
            value={data.triggerConfig?.path || "webhook"}
            onChange={(e) =>
              onChange({
                triggerConfig: { ...data.triggerConfig, path: e.target.value },
                label: `🔗 /${e.target.value}`,
              })
            }
            placeholder="webhook-path"
          />
        </div>
      )}

      {/* Manual */}
      {data.triggerType === "manual" && (
        <p className="text-xs text-muted-foreground italic">
          Ejecución manual — sin configuración adicional
        </p>
      )}
    </div>
  )
}

// ── Action Config ───────────────────────────────────────────

function ActionConfig({
  data,
  onChange,
}: {
  data: ActionNodeData
  onChange: (d: Partial<ActionNodeData>) => void
}) {
  const toolConfig = TOOL_ACTIONS[data.tool]
  const actions = toolConfig?.actions || {}
  const selectedAction = actions[data.action]
  const params = selectedAction?.params || []

  const handleToolChange = (tool: string) => {
    const newConfig = TOOL_ACTIONS[tool]
    const firstAction = Object.keys(newConfig.actions)[0]
    const actionConfig = newConfig.actions[firstAction]
    onChange({
      tool,
      action: firstAction,
      params: {},
      label: `${newConfig.label}: ${actionConfig.label}`,
    })
  }

  const handleActionChange = (action: string) => {
    const actionConfig = actions[action]
    onChange({
      action,
      params: {},
      label: `${toolConfig?.label || data.tool}: ${actionConfig?.label || action}`,
    })
  }

  const handleParamChange = (key: string, value: string) => {
    onChange({
      params: { ...data.params, [key]: value },
    } as Partial<ActionNodeData>)
  }

  return (
    <div className="space-y-4">
      {/* Tool selector */}
      <div className="space-y-2">
        <Label htmlFor="action-tool">Herramienta</Label>
        <select
          id="action-tool"
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          value={data.tool}
          onChange={(e) => handleToolChange(e.target.value)}
        >
          {Object.entries(TOOL_ACTIONS).map(([key, config]) => (
            <option key={key} value={key}>
              {config.label}
            </option>
          ))}
        </select>
      </div>

      {/* Action selector */}
      <div className="space-y-2">
        <Label htmlFor="action-name">Acción</Label>
        <select
          id="action-name"
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
          value={data.action}
          onChange={(e) => handleActionChange(e.target.value)}
        >
          {Object.entries(actions).map(([key, act]) => (
            <option key={key} value={key}>
              {act.label}
            </option>
          ))}
        </select>
      </div>

      <Separator />

      {/* Params */}
      {params.length > 0 ? (
        <div className="space-y-3">
          <Label className="text-xs text-muted-foreground uppercase tracking-wider">
            Parámetros
          </Label>
          {params.map((p) => (
            <div key={p} className="space-y-1.5">
              <Label htmlFor={`action-param-${p}`} className="text-xs">{PARAM_LABELS[p] || p}</Label>
              <Input
                id={`action-param-${p}`}
                value={data.params[p] || ""}
                onChange={(e) => handleParamChange(p, e.target.value)}
                placeholder={PARAM_LABELS[p] || p}
                className="h-8 text-xs"
              />
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic">
          Sin parámetros requeridos
        </p>
      )}

      <Separator />

      {/* Condition */}
      <div className="space-y-2">
        <Label htmlFor="action-condition" className="text-xs text-muted-foreground uppercase tracking-wider">
          Condición (opcional)
        </Label>
        <Input
          id="action-condition"
          value={data.condition || ""}
          onChange={(e) => onChange({ condition: e.target.value || undefined })}
          placeholder="Ej: stock &lt; 10"
          className="h-8 text-xs font-mono"
        />
        <p className="text-[10px] text-muted-foreground">
          Si se especifica, este paso solo se ejecuta si la condición se cumple
        </p>
      </div>
    </div>
  )
}
