/// Tipos para el sistema de notificaciones y toasts

export interface Toast {
  id: string
  title: string
  description?: string
  variant?: "default" | "success" | "error" | "warning"
  duration?: number
}
