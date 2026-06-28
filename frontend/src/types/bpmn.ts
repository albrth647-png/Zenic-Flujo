/**
 * BPMN types — corresponden a src/api_v2/routers/bpmn.py
 */

export interface BPMNElement {
  name: string
  type: "startEvent" | "endEvent" | "task" | "userTask" | "serviceTask" | "exclusiveGateway" | "parallelGateway" | "inclusiveGateway"
  incoming: string[]
  outgoing: string[]
}

export interface BPMNFlow {
  name: string
  source: string
  target: string
  condition?: string
}

export interface BPMNProcess {
  process_id: string
  name: string
  is_executable: boolean
  documentation?: string
  version?: string
  elements: Record<string, BPMNElement>
  flows: Record<string, BPMNFlow>
  validation: BPMNValidationError[]
}

export interface BPMNValidationError {
  element_id?: string
  message: string
  type: "error" | "warning"
}

export interface BPMNImportResponse {
  process_id: string
  name: string
  elements: number
  flows: number
  validation_errors: BPMNValidationError[]
}

export interface BPMNExportResponse {
  process_id: string
  bpmn_xml: string
}

export interface BPMNValidateResponse {
  valid: boolean
  errors: BPMNValidationError[]
}

export interface BPMNProcessSummary {
  process_id: string
  name: string
  elements: number
  flows: number
  start_events: number
  end_events: number
  tasks: number
  gateways: number
}

export interface BPMNListResponse {
  processes: BPMNProcessSummary[]
  count: number
}

export interface BPMNConvertResponse {
  workflow_id?: string
  name: string
  steps: unknown[]
  [key: string]: unknown
}
