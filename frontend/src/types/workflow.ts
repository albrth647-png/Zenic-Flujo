import type { Node, Edge } from "@xyflow/react"

// ── Workflow API types ──────────────────────────────────────

export interface Workflow {
  id: number
  name: string
  description: string
  trigger_type: TriggerType
  trigger_config: TriggerConfig
  steps: WorkflowStep[]
  status: string
  created_at: string
  updated_at: string
}

export type TriggerType = "event" | "schedule" | "webhook" | "manual"

export interface TriggerConfig {
  event?: string
  frequency?: string
  time?: string
  path?: string
}

export interface WorkflowStep {
  id: number
  tool: string
  action: string
  params: Record<string, string>
  condition?: string
}

// ── Editor types ────────────────────────────────────────────

export type NodeType = "trigger" | "action"

// Index signature `[key: string]: unknown` es requerida por @xyflow/react v12
// para que el tipo data del Node satisfaga el constraint Record<string, unknown>.
export interface TriggerNodeData {
  [key: string]: unknown
  nodeType: "trigger"
  triggerType: TriggerType
  triggerConfig: TriggerConfig
  label: string
}

export interface ActionNodeData {
  [key: string]: unknown
  nodeType: "action"
  label: string
  tool: string
  action: string
  params: Record<string, string>
  condition?: string
}

export type WorkflowNodeData = TriggerNodeData | ActionNodeData

export type WorkflowNode = Node<WorkflowNodeData, NodeType>
export type WorkflowEdge = Edge

// ── Tool configuration ──────────────────────────────────────

export interface ToolAction {
  label: string
  params: string[]
}

export interface ToolConfig {
  label: string
  icon: string
  color: string
  actions: Record<string, ToolAction>
}

export const TOOL_ACTIONS: Record<string, ToolConfig> = {
  crm: {
    label: "CRM",
    icon: "Users",
    color: "#6366f1",
    actions: {
      create_lead: { label: "Crear lead", params: ["name", "email", "phone", "company", "source", "notes"] },
      update_lead: { label: "Actualizar lead", params: ["lead_id", "name", "email", "phone", "stage"] },
      list_leads: { label: "Listar leads", params: ["stage"] },
      move_stage: { label: "Mover etapa", params: ["lead_id", "stage"] },
    },
  },
  invoice: {
    label: "Facturas",
    icon: "FileText",
    color: "#22c55e",
    actions: {
      create_invoice: { label: "Crear factura", params: ["client_name", "client_email", "items", "tax_rate", "discount", "due_days", "notes"] },
      list_invoices: { label: "Listar facturas", params: ["status"] },
      mark_paid: { label: "Marcar pagada", params: ["invoice_id"] },
    },
  },
  inventory: {
    label: "Inventario",
    icon: "Package",
    color: "#f59e0b",
    actions: {
      create_product: { label: "Crear producto", params: ["sku", "name", "description", "category", "stock", "min_stock", "price"] },
      update_stock: { label: "Actualizar stock", params: ["product_id", "quantity", "type", "reason"] },
      list_products: { label: "Listar productos", params: [] },
      low_stock: { label: "Stock bajo", params: [] },
    },
  },
  notification: {
    label: "Notificaciones",
    icon: "Bell",
    color: "#ef4444",
    actions: {
      send_email: { label: "Enviar email", params: ["to", "subject", "body"] },
      send_notification: { label: "Enviar notificación", params: ["user_id", "title", "message"] },
    },
  },
  system: {
    label: "Sistema",
    icon: "Settings",
    color: "#8b5cf6",
    actions: {
      backup: { label: "Backup", params: [] },
      log: { label: "Log", params: [] },
    },
  },
  subworkflow: {
    label: "Sub-workflow",
    icon: "GitBranch",
    color: "#06b6d4",
    actions: {
      execute: { label: "Ejecutar sub-workflow", params: ["workflow_id", "input_mapping", "output_mapping"] },
    },
  },
}

export const PARAM_LABELS: Record<string, string> = {
  name: "Nombre",
  email: "Email",
  phone: "Teléfono",
  company: "Empresa",
  source: "Origen",
  notes: "Notas",
  lead_id: "ID Lead",
  stage: "Etapa",
  client_name: "Cliente",
  client_email: "Email cliente",
  items: "Items (JSON)",
  tax_rate: "Impuesto %",
  discount: "Descuento",
  due_days: "Días vencimiento",
  invoice_id: "ID Factura",
  status: "Estado",
  sku: "SKU",
  description: "Descripción",
  category: "Categoría",
  stock: "Stock",
  min_stock: "Stock mínimo",
  price: "Precio",
  product_id: "ID Producto",
  quantity: "Cantidad",
  type: "Tipo movimiento",
  reason: "Razón",
  to: "Para",
  subject: "Asunto",
  body: "Cuerpo",
  user_id: "ID Usuario",
  title: "Título",
  message: "Mensaje",
  workflow_id: "ID Workflow",
  input_mapping: "Mapeo entrada",
  output_mapping: "Mapeo salida",
}

export const EVENT_OPTIONS = [
  "crm.lead.created",
  "crm.lead.updated",
  "crm.lead.stage_changed",
  "invoice.created",
  "invoice.paid",
  "invoice.overdue",
  "inventory.stock_low",
  "inventory.stock_updated",
  "inventory.product_created",
]
