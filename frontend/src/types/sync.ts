export interface SyncConfig {
  config_id: string
  tenant_id: string
  enabled: boolean
  sync_interval_minutes: number
  conflict_strategy: string
  has_encryption_key: boolean
  target_url: string
  has_target_api_key: boolean
  last_sync_at: number
  last_sync_status: string
  auto_sync: boolean
  include_credentials: boolean
}

export interface SyncStats {
  enabled: boolean
  has_encryption_key: boolean
  has_target: boolean
  auto_sync: boolean
  last_sync_at: number
  last_sync_status: string
  total_sync_operations: number
  last_push_at: number
  last_pull_at: number
  total_exported_workflows: number
}

export interface SyncHistoryEntry {
  entry_id: string
  action: string
  status: string
  workflow_count: number
  duration_ms: number
  error_message: string
  timestamp: number
  package_id: string
}
