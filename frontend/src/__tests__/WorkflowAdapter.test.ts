/**
 * Tests del módulo WorkflowAdapter.
 *
 * Verifica la conversión bidireccional entre el modelo Workflow del backend
 * y el modelo Node/Edge de React Flow que usa el Editor.
 *
 * Previenen regressiones en el flujo: cargar workflow → editar → guardar.
 */
import { describe, it, expect } from "vitest"
import { workflowToNodesAndEdges, nodesAndEdgesToWorkflow } from "@/components/editor/WorkflowAdapter"
import type { Workflow } from "@/types/workflow"

const sampleWorkflow: Workflow = {
  id: 1,
  name: "Test workflow",
  description: "Workflow de prueba",
  trigger_type: "event",
  trigger_config: { event: "crm.lead.created" },
  steps: [
    {
      id: 100,
      tool: "crm",
      action: "create_lead",
      params: { name: "John Doe", email: "john@test.com" },
    },
    {
      id: 101,
      tool: "notification",
      action: "send_email",
      params: { to: "admin@test.com", subject: "Nuevo lead" },
      condition: "$trigger.stage == 'new'",
    },
  ],
  status: "active",
  created_at: "2026-06-17T10:00:00Z",
  updated_at: "2026-06-17T10:00:00Z",
}

describe("workflowToNodesAndEdges", () => {
  it("convierte Workflow → 1 trigger node + N action nodes", () => {
    const { nodes } = workflowToNodesAndEdges(sampleWorkflow)

    expect(nodes).toHaveLength(3) // 1 trigger + 2 actions
    expect(nodes[0].id).toBe("trigger")
    expect(nodes[0].type).toBe("trigger")
    expect(nodes[0].data.nodeType).toBe("trigger")

    expect(nodes[1].id).toBe("step-100")
    expect(nodes[1].type).toBe("action")
    expect(nodes[1].data.nodeType).toBe("action")
    expect(nodes[1].data.tool).toBe("crm")
  })

  it("crea edges conectando trigger → step-1 → step-2 → ...", () => {
    const { edges } = workflowToNodesAndEdges(sampleWorkflow)

    expect(edges).toHaveLength(2)
    expect(edges[0].source).toBe("trigger")
    expect(edges[0].target).toBe("step-100")
    expect(edges[1].source).toBe("step-100")
    expect(edges[1].target).toBe("step-101")
  })

  it("trigger node preserva el event del trigger_config", () => {
    const { nodes } = workflowToNodesAndEdges(sampleWorkflow)
    const triggerData = nodes[0].data as { triggerType: string; triggerConfig: { event?: string } }

    expect(triggerData.triggerType).toBe("event")
    expect(triggerData.triggerConfig.event).toBe("crm.lead.created")
  })

  it("action node preserva condition si existe", () => {
    const { nodes } = workflowToNodesAndEdges(sampleWorkflow)
    const actionData = nodes[2].data as { condition?: string }

    expect(actionData.condition).toBe("$trigger.stage == 'new'")
  })

  it("maneja workflow sin steps (solo trigger)", () => {
    const emptyWorkflow: Workflow = {
      ...sampleWorkflow,
      steps: [],
    }

    const { nodes, edges } = workflowToNodesAndEdges(emptyWorkflow)

    expect(nodes).toHaveLength(1)
    expect(nodes[0].id).toBe("trigger")
    expect(edges).toHaveLength(0)
  })
})

describe("nodesAndEdgesToWorkflow", () => {
  it("convierte Nodes+Edges → Workflow con steps", () => {
    const { nodes } = workflowToNodesAndEdges(sampleWorkflow)
    const { edges } = workflowToNodesAndEdges(sampleWorkflow)

    const result = nodesAndEdgesToWorkflow(nodes, edges, {
      name: "Test workflow",
      description: "Description",
    })

    expect(result.name).toBe("Test workflow")
    expect(result.trigger_type).toBe("event")
    expect(result.trigger_config?.event).toBe("crm.lead.created")
    expect(result.steps).toHaveLength(2)
    expect(result.steps?.[0].tool).toBe("crm")
    expect(result.steps?.[0].action).toBe("create_lead")
  })

  it("preserva condition al hacer round-trip", () => {
    const { nodes, edges } = workflowToNodesAndEdges(sampleWorkflow)
    const result = nodesAndEdgesToWorkflow(nodes, edges, { name: "Test" })

    expect(result.steps?.[1].condition).toBe("$trigger.stage == 'new'")
  })
})

describe("round-trip integrity", () => {
  it("workflow → nodes/edges → workflow preserva la estructura", () => {
    const { nodes, edges } = workflowToNodesAndEdges(sampleWorkflow)
    const result = nodesAndEdgesToWorkflow(nodes, edges, {
      name: sampleWorkflow.name,
      description: sampleWorkflow.description,
    })

    expect(result.trigger_type).toBe(sampleWorkflow.trigger_type)
    expect(result.trigger_config).toEqual(sampleWorkflow.trigger_config)
    expect(result.steps).toHaveLength(sampleWorkflow.steps.length)

    result.steps?.forEach((step, i) => {
      expect(step.tool).toBe(sampleWorkflow.steps[i].tool)
      expect(step.action).toBe(sampleWorkflow.steps[i].action)
      expect(step.params).toEqual(sampleWorkflow.steps[i].params)
      expect(step.condition).toBe(sampleWorkflow.steps[i].condition)
    })
  })
})
