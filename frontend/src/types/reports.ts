export interface ReportLead {
  id: number
  name: string
  stage: string
}

export interface ReportProduct {
  id: number
  name: string
  stock: number
  min_stock: number
  price: number
}

export interface ReportInvoice {
  id: number
  number: string
  client_name: string
  total: number
  status: string
  due_date: string
}

export interface DashboardStats {
  stats: {
    total: number
    by_status: Record<string, number>
  }
}

export type ReportFormat = "csv" | "pdf"

export interface ReportOption {
  id: string
  name: string
  description: string
  endpoint: string
  formats: ReportFormat[]
}

export interface ReportRequest {
  type: string
  format: ReportFormat
  filters?: Record<string, string>
}

export interface ReportResponse {
  url: string
  filename: string
  format: ReportFormat
  size: number
}

// ── Dashboard chart types ────────────────────────────────

export interface ToolData {
  tool: string
  count: number
}

export interface TimelineData {
  day: string
  completed: number
  failed: number
  total: number
}
