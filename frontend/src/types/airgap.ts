export interface AirgapStatus {
  valid: boolean
  checks: Record<string, { passed: boolean; message: string }>
  all_passed: boolean
  error?: string
}

export interface AirgapConfig {
  cloud_connectors: string[]
  local_connectors: string[]
  internal_dns: string
  mode: string
  version: string
}
