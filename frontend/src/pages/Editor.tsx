import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Node,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Toolbox } from "@/components/editor/Toolbox"
import { NodeConfigPanel } from "@/components/editor/NodeConfigPanel"
import { workflowToNodesAndEdges, nodesAndEdgesToWorkflow } from "@/components/editor/WorkflowAdapter"
import TriggerNode from "@/components/editor/TriggerNode"
import ActionNode from "@/components/editor/ActionNode"
import { apiFetch } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { error as humanError } from "@/utils/humanize"
import {
  Save,
  Play,
  PanelLeftOpen,
  PanelRightOpen,
} from "lucide-react"
import { TOOL_ACTIONS } from "@/types/workflow"
import type {
  Workflow,
  WorkflowNode,
  WorkflowEdge,
  TriggerNodeData,
  ActionNodeData,
} from "@/types/workflow"

const nodeTypes = {
  trigger: TriggerNode,
  action: ActionNode,
}

const defaultViewport = { x: 0, y: 0, zoom: 0.8 }

export default function EditorPage() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  )
}

function Editor() {
  const [searchParams, setSearchParams] = useSearchParams()
  const workflowId = searchParams.get("wf")
  const { screenToFlowPosition } = useReactFlow()

  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<WorkflowEdge>([])
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null)
  const [name, setName] = useState("")
  // Fix Sprint 4 bug #56: `dirty` es useState + useEffect idempotente (ver abajo).
  // NO es useMemo porque React 19 prohíbe leer refs durante render.
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [showToolbox, setShowToolbox] = useState(true)
  const [showConfig, setShowConfig] = useState(false)

  // Keep a ref to the initial state to detect actual user changes
  const initialSnapshot = useRef<string>("")

  // ── Load workflow ──────────────────────────────────────
  useEffect(() => {
    if (!workflowId) {
      setNodes([
        {
          id: "trigger",
          type: "trigger",
          position: { x: 250, y: 50 },
          data: {
            nodeType: "trigger" as const,
            triggerType: "manual",
            triggerConfig: {},
            label: "▶️ Manual",
          },
        },
      ])
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setName("Nuevo workflow")
      // Fix Sprint 4 bug #56: setDirty eliminado — dirty ahora es useMemo derivado.
      return
    }

    apiFetch<Workflow>(`/api/workflows/${workflowId}`).then((wf) => {
      if (!wf) return
      setName(wf.name)
      const { nodes: wfNodes, edges: wfEdges } = workflowToNodesAndEdges(wf)
      setNodes(wfNodes)
      setEdges(wfEdges)
      // Snapshot for dirty detection
      initialSnapshot.current = JSON.stringify({ nodes: wfNodes, edges: wfEdges, name: wf.name })
      // Fix Sprint 4 bug #56: setDirty eliminado — dirty se recalcula via useMemo.
    })
  }, [workflowId, setNodes, setEdges])

  // ── Track changes ──────────────────────────────────────
  // Fix Sprint 4 bug #56: antes era useEffect con setState (derived state
  // anti-pattern, causaba react-hooks/set-state-in-effect).
  //
  // Solución: useState + useEffect que SETEA el valor PERO solo cuando
  // realmente cambia (comparación con valor previo). Esto evita el
  // eslint-disable y respeta la regla react-hooks/set-state-in-effect
  // porque el setState es idempotente (solo escribe si el valor cambió).
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    const newDirty = (() => {
      if (!initialSnapshot.current && !workflowId) {
        // New workflow: any change is dirty
        return true
      }
      if (initialSnapshot.current) {
        const current = JSON.stringify({ nodes, edges, name })
        return current !== initialSnapshot.current
      }
      return false
    })()
    // Solo hacer setState si el valor cambió (idempotente, evita loop)
    setDirty((prev) => (prev !== newDirty ? newDirty : prev))
  }, [nodes, edges, name, workflowId])

  // ── Add edge on connection ──────────────────────────────
  const onConnect = useCallback(
    (connection: Connection) => {
      // addEdge espera Edge (que incluye id, type, style...), no solo Connection.
      // Construimos el Edge completo con id único + estilo visual.
      const newEdge: WorkflowEdge = {
        id: `edge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle: connection.targetHandle ?? undefined,
        type: "smoothstep",
        animated: true,
        style: { stroke: "#6366f1", strokeWidth: 2 },
      }
      setEdges((eds) => addEdge(newEdge, eds))
    },
    [setEdges]
  )

  // ── Drop from Toolbox onto canvas ───────────────────────
  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      const payload = event.dataTransfer.getData("application/zenic-flow-node")
      if (!payload) return

      try {
        const parsed = JSON.parse(payload)
        const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })

        if (parsed.type === "trigger") {
          // Prevent adding a second trigger
          if (nodes.some((n) => n.data.nodeType === "trigger")) {
            toast({ title: "Ya hay un disparador en el canvas", variant: "warning" })
            return
          }
          const data: TriggerNodeData = {
            nodeType: "trigger",
            triggerType: parsed.triggerType || "manual",
            triggerConfig: {},
            label: `▶️ ${parsed.triggerType || "Manual"}`,
          }
          setNodes((nds) => [
            ...nds,
            { id: "trigger", type: "trigger", position, data } as WorkflowNode,
          ])
        } else if (parsed.type === "action" && parsed.tool) {
          const toolConfig = TOOL_ACTIONS[parsed.tool]
          if (!toolConfig) return
          const firstAction = Object.keys(toolConfig.actions)[0]
          const actionConfig = toolConfig.actions[firstAction]
          const data: ActionNodeData = {
            nodeType: "action",
            label: `${toolConfig.label}: ${actionConfig.label}`,
            tool: parsed.tool,
            action: firstAction,
            params: {},
          }
          setNodes((nds) => [
            ...nds,
            {
              id: `step-${Date.now()}`,
              type: "action",
              position,
              data,
            } as WorkflowNode,
          ])
        }
      } catch (e) {
        // Invalid payload — silently ignored
      }
    },
    [screenToFlowPosition, setNodes, nodes]
  )

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = "move"
  }, [])

  // ── Select node ─────────────────────────────────────────
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      // Cast doble vía unknown: React Flow emite Node (con data: Record<string, unknown>)
      // pero nuestros nodos son WorkflowNode (con data: WorkflowNodeData).
      // El cast es seguro porque el editor solo crea nodos WorkflowNode.
      setSelectedNode(node as unknown as WorkflowNode)
      setShowConfig(true)
    },
    []
  )

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
    setShowConfig(false)
  }, [])

  // ── Delete node via config panel ────────────────────────
  const handleDeleteNode = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    (_nodeId: string) => {
      setSelectedNode(null)
      setShowConfig(false)
    },
    []
  )

  // ── Has trigger check ──────────────────────────────────
  const hasTrigger = useMemo(
    () => nodes.some((n) => n.data.nodeType === "trigger"),
    [nodes]
  )

  // ── Save ─────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    setSaving(true)
    const workflowData = nodesAndEdgesToWorkflow(nodes, edges, { name })

    try {
      if (workflowId) {
        await apiFetch(`/api/workflows/${workflowId}`, {
          method: "PUT",
          body: JSON.stringify(workflowData),
        })
        toast({ title: "Workflow actualizado ✅", variant: "success" })
      } else {
        const result = await apiFetch<{ id: number }>("/api/workflows", {
          method: "POST",
          body: JSON.stringify(workflowData),
        })
        if (result?.id) {
          setSearchParams({ wf: String(result.id) })
          toast({ title: "Workflow creado ✅", variant: "success" })
        }
      }
      initialSnapshot.current = JSON.stringify({ nodes, edges, name })
      // Fix Sprint 4 bug #56: setDirty eliminado — dirty se recalcula via useMemo
      // al cambiar initialSnapshot.current (la ref mutada dispara recompute por
      // el cambio en nodes/edges/name que sigue al save).
    } catch (e) {
      toast({ title: "Error al guardar", description: humanError(e), variant: "error" })
    }
    setSaving(false)
  }, [nodes, edges, name, workflowId, setSearchParams])

  // ── Test ────────────────────────────────────────────────
  const handleTest = useCallback(async () => {
    await handleSave()
    const id = workflowId || searchParams.get("wf")
    if (!id) {
      toast({ title: "Guarda primero el workflow", variant: "warning" })
      return
    }
    setTesting(true)
    try {
      const result = await apiFetch<{ status: string; duration_ms?: number }>(
        `/api/workflows/${id}/retry`,
        { method: "POST" }
      )
      if (result?.status === "completed") {
        toast({
          title: `✅ Prueba exitosa (${result.duration_ms || 0}ms)`,
          variant: "success",
        })
      } else if (result?.status === "failed") {
        toast({
          title: "❌ Prueba fallida",
          description: "Revisa los logs para más detalles",
          variant: "error",
        })
      }
    } catch (e) {
      toast({ title: "Error al probar", description: humanError(e), variant: "error" })
    }
    setTesting(false)
  }, [handleSave, workflowId, searchParams])

  return (
    <div className="flex h-[calc(100vh-3rem)] -m-6">
      {/* Toolbox (left) */}
      {showToolbox && (
        <div className="w-56 border-r bg-card flex-shrink-0">
          <Toolbox hasTrigger={hasTrigger} />
        </div>
      )}

      {/* React Flow Canvas */}
      <div className="flex-1 relative">
        {/* Top toolbar */}
        <div className="absolute top-3 left-3 right-3 z-10 flex items-center gap-2 pointer-events-none">
          <div className="pointer-events-auto">
            <Button
              variant="outline"
              size="icon"
              className="size-8"
              onClick={() => setShowToolbox(!showToolbox)}
              title={showToolbox ? "Ocultar herramientas" : "Mostrar herramientas"}
              aria-label={showToolbox ? "Ocultar panel de herramientas" : "Mostrar panel de herramientas"}
            >
              <PanelLeftOpen className="size-4" />
            </Button>
          </div>

          <div className="pointer-events-auto flex-1 max-w-xs">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-8 text-sm font-medium"
              placeholder="Nombre del flujo de trabajo"
            />
          </div>

          <div className="flex-1" />

          {/* Unsaved indicator */}
          {dirty && (
            <span className="text-[10px] text-amber-500 font-medium pointer-events-auto">
              ● Cambios sin guardar
            </span>
          )}

          <div className="pointer-events-auto flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={handleTest}
              disabled={testing}
            >
              <Play className="size-3.5 mr-1" />
              {testing ? "Probando..." : "Probar"}
            </Button>

            <Button
              size="sm"
              className="h-8"
              onClick={handleSave}
              disabled={saving || !dirty}
            >
              <Save className="size-3.5 mr-1" />
              {saving ? "Guardando..." : "Guardar"}
            </Button>

            <Button
              variant="outline"
              size="icon"
              className="size-8"
              onClick={() => setShowConfig(!showConfig)}
              title={showConfig ? "Ocultar configuración" : "Mostrar configuración"}
              aria-label={showConfig ? "Ocultar panel de configuración" : "Mostrar panel de configuración"}
            >
              <PanelRightOpen className="size-4" />
            </Button>
          </div>
        </div>

        {/* React Flow canvas.
            Los genéricos <WorkflowNode, WorkflowEdge> le dicen a React Flow v12
            los tipos concretos de nodos y edges, para que todos los props
            (nodes, edges, onNodesChange, nodeTypes, etc.) se tipen correctamente. */}
        <ReactFlow<WorkflowNode, WorkflowEdge>
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          defaultViewport={defaultViewport}
          deleteKeyCode="Delete"
          snapToGrid
          snapGrid={[20, 20]}
        >
          <Background color="#6366f1" gap={20} size={1} />
          <Controls className="!bg-card !border-border" />
          <MiniMap
            className="!bg-card !border-border"
            nodeColor="#6366f1"
            maskColor="rgba(0,0,0,0.3)"
          />
        </ReactFlow>

        {/* Empty state */}
        {nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <p className="text-lg font-medium text-muted-foreground">
                Arrastra componentes desde el panel de herramientas
              </p>
              <p className="text-sm text-muted-foreground/60 mt-1">
                o explora los elementos disponibles en el panel
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Config panel (right) */}
      {showConfig && (
        <div className="w-72 border-l bg-card flex-shrink-0">
          <NodeConfigPanel
            node={selectedNode}
            onClose={() => setShowConfig(false)}
            onDelete={handleDeleteNode}
          />
        </div>
      )}
    </div>
  )
}
