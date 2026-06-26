import type {
  Workflow,
  WorkflowStep,
  WorkflowNode,
  WorkflowEdge,
  TriggerNodeData,
  ActionNodeData,
  TriggerType,
  TriggerConfig,
} from "@/types/workflow"
import { TOOL_ACTIONS } from "@/types/workflow"

// ── Workflow → React Flow ───────────────────────────────────

export function workflowToNodesAndEdges(workflow: Workflow): {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
} {
  const nodes: WorkflowNode[] = []
  const edges: WorkflowEdge[] = []

  // ── Trigger node ──────────────────────────────────────
  const triggerData: TriggerNodeData = {
    nodeType: "trigger",
    triggerType: workflow.trigger_type,
    triggerConfig: workflow.trigger_config,
    label: getTriggerLabel(workflow.trigger_type, workflow.trigger_config),
  }

  nodes.push({
    id: "trigger",
    type: "trigger",
    position: { x: 250, y: 50 },
    data: triggerData,
  })

  // ── Action nodes for each step ────────────────────────
  let prevId = "trigger"
  const steps = workflow.steps || []

  steps.forEach((step, index) => {
    const nodeId = `step-${step.id}`
    const actionData: ActionNodeData = {
      nodeType: "action",
      label: getActionLabel(step.tool, step.action),
      tool: step.tool,
      action: step.action,
      params: step.params,
      condition: step.condition,
    }

    nodes.push({
      id: nodeId,
      type: "action",
      position: { x: 250, y: 250 + index * 180 },
      data: actionData,
    })

    edges.push({
      id: `edge-${prevId}-${nodeId}`,
      source: prevId,
      target: nodeId,
      type: "smoothstep",
      animated: true,
      style: { stroke: "#6366f1", strokeWidth: 2 },
    })

    prevId = nodeId
  })

  return { nodes, edges }
}

// ── React Flow → Workflow ───────────────────────────────────

export function nodesAndEdgesToWorkflow(
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
  existingWorkflow?: Partial<Workflow>
): Partial<Workflow> {
  const triggerNode = nodes.find((n) => n.data.nodeType === "trigger")
  const actionNodes = nodes
    .filter((n): n is WorkflowNode & { data: ActionNodeData } => n.data.nodeType === "action")
    .sort((a, b) => a.position.y - b.position.y)

  const triggerData = triggerNode?.data as TriggerNodeData | undefined

  const steps: WorkflowStep[] = actionNodes.map((node, i) => ({
    id: i + 1,
    tool: node.data.tool,
    action: node.data.action,
    params: node.data.params,
    condition: node.data.condition,
  }))

  return {
    name: existingWorkflow?.name || "Workflow sin nombre",
    description: existingWorkflow?.description || "",
    trigger_type: triggerData?.triggerType || "manual",
    trigger_config: triggerData?.triggerConfig || {},
    steps,
    status: existingWorkflow?.status || "active",
  }
}

// ── Helpers ─────────────────────────────────────────────────

function getTriggerLabel(type: TriggerType, config?: TriggerConfig): string {
  const labels: Record<TriggerType, string> = {
    event: "📡 Evento",
    schedule: "⏰ Programado",
    webhook: "🔗 Webhook",
    manual: "▶️ Manual",
  }
  if (type === "schedule" && config) {
    const freq = config.frequency || "daily"
    const time = config.time || "23:00"
    return `⏰ ${freq} ${time}`
  }
  if (type === "event" && config?.event) {
    return `📡 ${config.event}`
  }
  return labels[type] || "⚡ Trigger"
}

function getActionLabel(tool: string, action: string): string {
  const toolConfig = TOOL_ACTIONS[tool]
  if (!toolConfig) return `${tool}: ${action}`
  const actionConfig = toolConfig.actions[action]
  if (!actionConfig) return `${toolConfig.label}: ${action}`
  return `${toolConfig.label}: ${actionConfig.label}`
}
