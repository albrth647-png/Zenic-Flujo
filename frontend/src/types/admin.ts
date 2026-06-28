export interface AdminUser {
  id: number
  username: string
  display_name?: string
  email?: string
  role: "admin" | "editor" | "viewer"
  is_active: boolean
  created_at?: string
}

export interface DeadLetterEntry {
  id: number
  workflow_id?: number
  workflow_name?: string
  step_id?: string
  error_type: string
  error_message: string
  failed_at: string
  retry_count: number
  status: "pending" | "retrying" | "resolved" | "discarded"
  payload?: Record<string, unknown>
}

export interface DeadLetterStats {
  total: number
  pending: number
  retrying: number
  resolved: number
  discarded: number
}

export interface QueueMetrics {
  queue_size: number
  processing: number
  completed: number
  failed: number
  avg_wait_seconds: number
  throughput_per_minute: number
}

export interface WorkerInfo {
  id: string
  name: string
  status: string
  current_task?: string
  tasks_completed: number
  uptime_seconds: number
}

export interface QueueItem {
  id: number
  workflow_id: number
  workflow_name?: string
  status: string
  priority: number
  created_at: string
}
