export interface OrbitalVariable {
  name?: string
  theta: number
  amplitude: number
  velocity: number
  value: number
  orbit_group?: string
}

export interface TorEntry {
  variable_i: string
  variable_j: string
  tor_value: number
  alignment: number
}

export interface RccCycle {
  cycle_id: string
  cycle_name: string
  is_resonant: boolean
  strength: number
}

export interface CodResult {
  cycle_id: string
  converged: boolean
  iterations: number
  convergence_delta: number
}

export interface TickHistory {
  tick: number
  duration_ms: number
  variables: number
}

export interface TorCache {
  hits: number
  misses: number
  cache_size: number
  hit_rate: number
}

export interface OrbitalStatus {
  variables: Record<string, OrbitalVariable>
  tor: TorEntry[]
  tor_cache: TorCache
  rcc: RccCycle[]
  cod: CodResult[]
  tick: number
  variable_count: number
  cycle_count: number
  history: TickHistory[]
}
