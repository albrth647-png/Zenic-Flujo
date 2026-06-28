/**
 * Agent types — corresponden a src/api_v2/routers/agents.py
 */
export type AgentState = "idle" | "running" | "paused" | "terminated" | "error"

export interface AgentConfig {
  name: string
  description?: string
  capabilities?: string[]
  system_prompt?: string
  model?: string
  max_iterations?: number
  temperature?: number
  custom_config?: Record<string, unknown>
}

export interface AgentStatus {
  agent_id: string
  name: string
  state: AgentState
  description?: string
  capabilities: string[]
  is_active: boolean
  created_at: string
  updated_at?: string
  last_error?: string
  iteration_count?: number
  token_count?: number
}

export interface AgentListResponse {
  agents: AgentStatus[]
  count: number
}

export interface AgentRunResponse {
  agent_id: string
  result: unknown
  status: AgentStatus
}

export interface AgentOrchestrationPlan {
  pattern: "sequential" | "parallel" | "fan_out" | "debate" | "consensus"
  agents: Array<{
    agent_id: string
    input?: Record<string, unknown>
  }>
  max_rounds?: number
  timeout_ms?: number
}

export interface AgentOrchestrationResult {
  plan_id: string
  pattern: string
  final_result: unknown
  agent_results: Array<{
    agent_id: string
    result: unknown
    duration_ms: number
  }>
  total_duration_ms: number
  rounds_completed: number
  success: boolean
  error?: string
}

export interface TokenUsageSummary {
  total_tokens: number
  total_cost: number
  daily_average: number
  monthly_total: number
}

export interface DailyTokenUsage {
  date: string
  tokens: number
  cost: number
}

export interface RuntimeStats {
  total_agents_spawned: number
  active_agents: number
  avg_duration_ms: number
  total_tokens_used: number
}
