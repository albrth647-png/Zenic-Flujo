import { useCallback } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { TOOL_ACTIONS } from "@/types/workflow"
import type { TriggerType } from "@/types/workflow"
import { cn } from "@/lib/utils"

const toolIcons: Record<string, string> = {
  crm: "👤",
  invoice: "📄",
  inventory: "📦",
  notification: "🔔",
  system: "⚙️",
  subworkflow: "🔀",
}

const triggerTypes: { type: TriggerType; icon: string; label: string; color: string }[] = [
  { type: "event", icon: "📡", label: "Evento", color: "bg-blue-500" },
  { type: "schedule", icon: "⏰", label: "Programado", color: "bg-amber-500" },
  { type: "webhook", icon: "🔗", label: "Webhook", color: "bg-purple-500" },
  { type: "manual", icon: "▶️", label: "Manual", color: "bg-emerald-500" },
]

interface ToolboxProps {
  hasTrigger: boolean
}

export function Toolbox({ hasTrigger }: ToolboxProps) {
  const onDragStart = useCallback(
    (event: React.DragEvent, payload: string) => {
      event.dataTransfer.effectAllowed = "move"
      event.dataTransfer.setData("application/zenic-flow-node", payload)
      // Add a small drag image
      const el = document.createElement("div")
      el.className = "size-4 rounded-full bg-primary"
      el.style.position = "absolute"
      el.style.top = "-1000px"
      document.body.appendChild(el)
      event.dataTransfer.setDragImage(el, 8, 8)
      setTimeout(() => document.body.removeChild(el), 0)
    },
    []
  )

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b">
        <h3 className="text-sm font-semibold">Toolbox</h3>
        <p className="text-[10px] text-muted-foreground">Arrastra al canvas</p>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-4">
          {/* Triggers */}
          <div>
            <h4 className="text-[10px] uppercase font-semibold text-muted-foreground tracking-wider mb-2">
              Disparadores
            </h4>
            <div className="space-y-1.5">
              {triggerTypes.map((t) => (
                <div
                  key={t.type}
                  draggable={!hasTrigger}
                  onDragStart={(e) => onDragStart(e, JSON.stringify({ type: "trigger", triggerType: t.type }))}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm cursor-grab active:cursor-grabbing border transition-colors select-none",
                    hasTrigger
                      ? "opacity-40 cursor-not-allowed border-border bg-muted/30"
                      : "border-border hover:border-primary/50 hover:bg-accent/50"
                  )}
                  title={hasTrigger ? "Ya hay un disparador en el canvas" : `Arrastrar ${t.label}`}
                >
                  <div className={cn("flex size-7 items-center justify-center rounded-md text-xs", t.color, "text-white")}>
                    {t.icon}
                  </div>
                  <span className="text-xs font-medium">{t.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          <div>
            <h4 className="text-[10px] uppercase font-semibold text-muted-foreground tracking-wider mb-2">
              Acciones
            </h4>
            <div className="space-y-1.5">
              {Object.entries(TOOL_ACTIONS).map(([key, config]) => (
                <div
                  key={key}
                  draggable
                  onDragStart={(e) => onDragStart(e, JSON.stringify({ type: "action", tool: key }))}
                  className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm cursor-grab active:cursor-grabbing border border-border hover:border-primary/50 hover:bg-accent/50 transition-colors select-none"
                >
                  <div
                    className="flex size-7 items-center justify-center rounded-md text-xs"
                    style={{ backgroundColor: `${config.color}15` }}
                  >
                    {toolIcons[key] || "⚡"}
                  </div>
                  <span className="text-xs font-medium">{config.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}
