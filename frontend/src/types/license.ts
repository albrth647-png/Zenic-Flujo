/** Información devuelta por GET /api/license/info */
export interface LicenseInfo {
  /** Tipo de licencia: free, trial, individual, reseller, enterprise */
  type: string
  /** Nombre del cliente (solo para licencias pagas) */
  client_name?: string
  /** Fecha de expiración ISO (null si perpetua) */
  expires_at: string | null
  /** Indica si está en período de prueba */
  is_trial: boolean
  /** Indica si es plan gratuito */
  is_free: boolean
  /** Días restantes de prueba (solo cuando is_trial) */
  days_left?: number
  /** Máximo de workflows permitidos (-1 = ilimitados) */
  max_workflows?: number
  /** Herramientas permitidas (["all"] = todas) */
  allowed_tools?: string[]
}

/** Respuesta de POST /api/license/validate */
export interface LicenseValidation {
  valid: boolean
  type?: string
  client_name?: string
  expires_at?: string | null
  error?: string
  // Mensaje opcional del backend (puede venir en lugar de `error`)
  message?: string
}
