// Etapas del pipeline CRM. Debe coincidir con tools/crm/service.py:STAGES.
// Single source of truth: CrmPage.tsx y otros componentes deben importar desde aquí.
export const STAGES = [
  "new",
  "contacted",
  "qualified",
  "proposal",
  "negotiation",
  "closed_won",
  "closed_lost",
] as const

export type LeadStage = (typeof STAGES)[number]

export interface Lead {
  id: number
  name: string
  email?: string
  phone?: string
  company?: string
  source: string
  stage: string
  notes?: string
  created_at?: string
  user_id?: number
}

export interface LeadFormData {
  name: string
  email: string
  phone: string
  company: string
  source: string
  notes: string
}

export type StageCounts = Record<string, number>
