import { memo } from "react"
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { TOOL_ACTIONS } from "@/types/workflow"
import type { ActionNodeData } from "@/types/workflow"
import { cn } from "@/lib/utils"

// En @xyflow/react v12, NodeProps<T> requiere que T sea un Node completo.
type ActionNodeType = Node<ActionNodeData, "action">

const toolIcons: Record<string, string> = {
  crm: "👤",
  invoice: "📄",
  inventory: "📦",
  notification: "🔔",
  system: "⚙️",
  subworkflow: "🔀",
}

function ActionNode({ data, selected }: NodeProps<ActionNodeType>) {
  const toolConfig = TOOL_ACTIONS[data.tool]
  const color = toolConfig?.color || "#6366f1"
  const icon = toolIcons[data.tool] || "⚡"
  const paramCount = Object.keys(data.params || {}).length

  return (
    <div className={cn(
      "relative transition-shadow duration-200",
      selected && "drop-shadow-[0_0_12px_rgba(99,102,241,0.3)]"
    )}>
      {/* Input handle (top) */}
      <Handle
        type="target"
        position={Position.Top}
        className="!border-2 !border-primary !size-3 !bg-card"
      />

      {/* Node body */}
      <div className={cn(
        "rounded-xl border bg-card px-4 py-3 shadow-md min-w-[220px]",
        selected ? "border-primary ring-2 ring-primary/20" : "border-border"
      )}>
        {/* Header */}
        <div className="flex items-center gap-3">
          <div
            className="flex size-8 items-center justify-center rounded-lg text-lg"
            style={{ backgroundColor: `${color}15` }}
          >
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {toolConfig?.label || data.tool}
            </p>
            <p className="text-sm font-semibold truncate">
              {data.label}
            </p>
          </div>
        </div>

        {/* Condition badge */}
        {data.condition && (
          <div className="mt-2 flex items-center gap-1.5 rounded-md bg-amber-500/10 px-2 py-1 text-[10px] font-medium text-amber-600 dark:text-amber-400">
            <span>🔀</span>
            <span className="truncate">{data.condition}</span>
          </div>
        )}

        {/* Param count */}
        {paramCount > 0 && (
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            {paramCount} parámetro{paramCount !== 1 ? "s" : ""}
          </p>
        )}
      </div>

      {/* Output handle (bottom) */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!border-2 !border-primary !size-3 !bg-card"
      />
    </div>
  )
}

export default memo(ActionNode)
