import { useState, useCallback, useRef } from "react"
import type { Toast } from "@/types/notifications"

interface ToastOptions {
  title: string
  description?: string
  variant?: Toast["variant"]
  duration?: number
}

const defaultDuration = 4000

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counterRef = useRef(0)

  const addToast = useCallback((options: ToastOptions) => {
    const id = `toast-${++counterRef.current}`
    const duration = options.duration ?? defaultDuration
    const toast: Toast = {
      id,
      title: options.title,
      description: options.description,
      variant: options.variant || "default",
      duration,
    }
    setToasts((prev) => [...prev, toast])

    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, duration)
    }

    return id
  }, [])

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const success = useCallback(
    (title: string, description?: string) => addToast({ title, description, variant: "success" }),
    [addToast]
  )

  const error = useCallback(
    (title: string, description?: string) => addToast({ title, description, variant: "error" }),
    [addToast]
  )

  const warning = useCallback(
    (title: string, description?: string) => addToast({ title, description, variant: "warning" }),
    [addToast]
  )

  return { toasts, addToast, dismissToast, success, error, warning }
}
