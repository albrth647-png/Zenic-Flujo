export type InvoiceStatus = "pending" | "paid" | "overdue" | "cancelled"

export interface InvoiceItem {
  description: string
  quantity: number
  unit_price: number
}

export interface Invoice {
  id: number
  number: string
  client_name: string
  client_email?: string
  items: InvoiceItem[]
  subtotal: number
  tax_rate: number
  tax_amount: number
  discount: number
  total: number
  status: string
  due_date: string
  notes?: string
  created_at?: string
  paid_at?: string
  user_id?: number
}

export interface InvoiceFormData {
  client: string
  client_email: string
  items: InvoiceItem[]
  tax: number
  discount: number
  due_date: string
}
