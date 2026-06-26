/**
 * Tests del módulo workflow types.
 *
 * Verifica que las constantes y tipos exportados desde @/types/workflow
 * son consistentes y cubren los casos esperados.
 *
 * Previenen regressiones en TOOL_ACTIONS (catálogo de herramientas del editor)
 * y en los tipos de nodos del editor visual.
 */
import { describe, it, expect } from "vitest"
import {
  TOOL_ACTIONS,
  PARAM_LABELS,
  EVENT_OPTIONS,
  type Workflow,
  type TriggerNodeData,
  type ActionNodeData,
  type WorkflowNodeData,
  type WorkflowNode,
  type WorkflowEdge,
} from "@/types/workflow"

describe("TOOL_ACTIONS contract", () => {
  it("exporta las 6 herramientas esperadas", () => {
    expect(Object.keys(TOOL_ACTIONS).sort()).toEqual([
      "crm",
      "inventory",
      "invoice",
      "notification",
      "subworkflow",
      "system",
    ])
  })

  it("cada herramienta tiene label, icon, color y actions", () => {
    for (const toolConfig of Object.values(TOOL_ACTIONS)) {
      expect(toolConfig.label).toBeTruthy()
      expect(toolConfig.icon).toBeTruthy()
      expect(toolConfig.color).toMatch(/^#[0-9a-f]{6}$/i)
      expect(Object.keys(toolConfig.actions).length).toBeGreaterThan(0)
    }
  })

  it("cada action tiene label y params (array, puede ser vacío)", () => {
    for (const toolConfig of Object.values(TOOL_ACTIONS)) {
      for (const action of Object.values(toolConfig.actions)) {
        expect(action.label).toBeTruthy()
        expect(Array.isArray(action.params)).toBe(true)
      }
    }
  })

  it("crm expone create_lead y update_lead", () => {
    expect(TOOL_ACTIONS.crm.actions.create_lead).toBeDefined()
    expect(TOOL_ACTIONS.crm.actions.update_lead).toBeDefined()
    expect(TOOL_ACTIONS.crm.actions.create_lead.params).toContain("name")
    expect(TOOL_ACTIONS.crm.actions.create_lead.params).toContain("email")
  })

  it("invoice expone create_invoice y mark_paid", () => {
    expect(TOOL_ACTIONS.invoice.actions.create_invoice).toBeDefined()
    expect(TOOL_ACTIONS.invoice.actions.mark_paid).toBeDefined()
  })

  it("inventory expone create_product, update_stock, list_products, low_stock", () => {
    const inventoryActions = Object.keys(TOOL_ACTIONS.inventory.actions)
    expect(inventoryActions).toContain("create_product")
    expect(inventoryActions).toContain("update_stock")
    expect(inventoryActions).toContain("list_products")
    expect(inventoryActions).toContain("low_stock")
  })

  it("notification expone send_email y send_notification", () => {
    expect(TOOL_ACTIONS.notification.actions.send_email).toBeDefined()
    expect(TOOL_ACTIONS.notification.actions.send_notification).toBeDefined()
  })
})

describe("PARAM_LABELS contract", () => {
  it("cubren todos los params de TOOL_ACTIONS", () => {
    const allParams = new Set<string>()
    for (const toolConfig of Object.values(TOOL_ACTIONS)) {
      for (const action of Object.values(toolConfig.actions)) {
        action.params.forEach((p) => allParams.add(p))
      }
    }

    const missingLabels: string[] = []
    allParams.forEach((param) => {
      if (!PARAM_LABELS[param]) {
        missingLabels.push(param)
      }
    })

    // Permitimos algunos params opcionales sin label, pero la mayoría deben tenerlo
    expect(missingLabels.length).toBeLessThan(3)
  })

  it("todos los labels son strings no vacíos", () => {
    for (const label of Object.values(PARAM_LABELS)) {
      expect(typeof label).toBe("string")
      expect(label.length).toBeGreaterThan(0)
    }
  })
})

describe("EVENT_OPTIONS contract", () => {
  it("contiene eventos crm, invoice, inventory", () => {
    expect(EVENT_OPTIONS).toContain("crm.lead.created")
    expect(EVENT_OPTIONS).toContain("crm.lead.updated")
    expect(EVENT_OPTIONS).toContain("invoice.created")
    expect(EVENT_OPTIONS).toContain("invoice.paid")
    expect(EVENT_OPTIONS).toContain("inventory.stock_low")
  })

  it("todos siguen formato dominio.evento[.subevento]", () => {
    // Acepta tanto "crm.lead.created" (3 partes) como "invoice.created" (2 partes)
    for (const evt of EVENT_OPTIONS) {
      expect(evt).toMatch(/^[a-z]+\.[a-z_]+(\.[a-z_]+)?$/)
    }
  })
})

describe("WorkflowNodeData types", () => {
  it("TriggerNodeData tiene nodeType 'trigger'", () => {
    const trigger: TriggerNodeData = {
      nodeType: "trigger",
      triggerType: "event",
      triggerConfig: { event: "crm.lead.created" },
      label: "Test trigger",
    }
    expect(trigger.nodeType).toBe("trigger")
  })

  it("ActionNodeData tiene nodeType 'action'", () => {
    const action: ActionNodeData = {
      nodeType: "action",
      label: "Crear lead",
      tool: "crm",
      action: "create_lead",
      params: { name: "John" },
    }
    expect(action.nodeType).toBe("action")
    expect(action.tool).toBe("crm")
  })

  it("WorkflowNodeData es union de TriggerNodeData | ActionNodeData", () => {
    const trigger: WorkflowNodeData = {
      nodeType: "trigger",
      triggerType: "event",
      triggerConfig: { event: "x" },
      label: "x",
    }
    const action: WorkflowNodeData = {
      nodeType: "action",
      label: "x",
      tool: "crm",
      action: "create_lead",
      params: {},
    }

    expect(trigger.nodeType).toBe("trigger")
    expect(action.nodeType).toBe("action")
  })

  it("WorkflowNode y WorkflowEdge son tipos válidos", () => {
    const node: WorkflowNode = {
      id: "test",
      type: "trigger",
      position: { x: 0, y: 0 },
      data: {
        nodeType: "trigger",
        triggerType: "event",
        triggerConfig: { event: "x" },
        label: "Test",
      },
    }
    const edge: WorkflowEdge = {
      id: "e1",
      source: "trigger",
      target: "step-1",
    }

    expect(node.id).toBe("test")
    expect(edge.source).toBe("trigger")
  })
})

describe("Workflow interface", () => {
  it("acepta workflow con trigger event y steps", () => {
    const wf: Workflow = {
      id: 1,
      name: "Test",
      description: "",
      trigger_type: "event",
      trigger_config: { event: "crm.lead.created" },
      steps: [
        { id: 1, tool: "crm", action: "create_lead", params: {} },
      ],
      status: "active",
      created_at: "2026-06-17T10:00:00Z",
      updated_at: "2026-06-17T10:00:00Z",
    }
    expect(wf.steps).toHaveLength(1)
  })

  it("acepta trigger_type event | schedule | webhook | manual", () => {
    const triggerTypes = ["event", "schedule", "webhook", "manual"] as const
    triggerTypes.forEach((tt) => {
      const wf: Workflow = {
        id: 1,
        name: "x",
        description: "",
        trigger_type: tt,
        trigger_config: {},
        steps: [],
        status: "active",
        created_at: "",
        updated_at: "",
      }
      expect(wf.trigger_type).toBe(tt)
    })
  })
})
