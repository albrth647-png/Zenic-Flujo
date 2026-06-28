import { memo } from "react"
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react"
import { Zap, Clock, Link, Play } from "lucide-react"
import type { TriggerNodeData } from "@/types/workflow"

// En @xyflow/react v12, NodeProps<T> requiere que T sea un Node completo,
// no solo el tipo data. Por eso envolvemos TriggerNodeData en Node<...>.
type TriggerNodeType = Node<TriggerNodeData, "trigger">

const triggerIcons: Record<string, React.ReactNode> = {
  event: <Zap className="size-4" />,
  schedule: <Clock className="size-4" />,
  webhook: <Link className="size-4" />,
  manual: <Play className="size-4" />,
}

const triggerColors: Record<string, string> = {
  event: "bg-blue-500",
  schedule: "bg-amber-500",
  webhook: "bg-purple-500",
  manual: "bg-emerald-500",
}

function TriggerNode({ data }: NodeProps<TriggerNodeType>) {
  return (
    <div className="relative">
      {/* Node body */}
      <div className="flex items-center gap-3 rounded-xl border-2 border-blue-500/30 bg-card px-4 py-3 shadow-md min-w-[200px]">
        <div className={`flex size-8 items-center justify-center rounded-lg ${triggerColors[data.triggerType] || "bg-primary"} text-white`}>
          {triggerIcons[data.triggerType] || <Zap className="size-4" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">DISPARADOR</p>
          <p className="text-sm font-semibold truncate">{data.label}</p>
        </div>
      </div>

      {/* Output handle (bottom) */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!border-2 !border-blue-500 !size-3 !bg-card"
      />
    </div>
  )
}

export default memo(TriggerNode)
