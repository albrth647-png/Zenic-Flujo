export interface ComplianceOverview {
  scores: {
    overall_score: number
    frameworks: Record<string, FrameworkScore>
    total_controls: number
  }
  controls_count: number
  controls: ComplianceControl[]
  recommendations: string[]
}

export interface FrameworkScore {
  score: number
  total: number
  implemented: number
  verified: number
  failed: number
  not_implemented: number
  by_status: Record<string, number>
}

export interface ComplianceControl {
  control_id: string
  name: string
  ref_code: string
  framework: string
  status: string
  risk_level: string
  last_tested: number
  remediation_notes: string
}

export interface Soc2Period {
  id: string
  start_date: string
  end_date: string
  status: "active" | "completed" | "upcoming"
  bridge_letter: string | null
}

export interface Soc2TestResult {
  id: string
  period_id: string
  control: string
  result: "passed" | "failed"
  evidence: string
  tested_at: string
}

export interface GdprConsent {
  id: string
  user_id: string
  purpose: string
  status: "granted" | "revoked" | "expired"
  granted_at: string
  expires_at: string | null
}

export interface HipaaBaa {
  id: string
  partner: string
  signed_at: string
  expires_at: string
  status: "active" | "expired"
}

export interface AuditEntry {
  id: string
  action: string
  user: string
  timestamp: string
  details: string
}
