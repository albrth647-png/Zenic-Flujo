"use client"

import { useState, useEffect } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

interface Toast {
  id: string
  title: string
  description?: string
  variant?: "default" | "success" | "error" | "warning"
}

let toastId = 0
let listeners: Array<(toasts: Toast[]) => void> = []
let toasts: Toast[] = []

function emitChange() {
  listeners.forEach((l) => l([...toasts]))
}

// eslint-disable-next-line react-refresh/only-export-components
export function toast({
  title,
  description,
  variant = "default",
}: Omit<Toast, "id">) {
  const id = String(++toastId)
  toasts = [...toasts, { id, title, description, variant }]
  emitChange()
  setTimeout(() => {
    toasts = toasts.filter((t) => t.id !== id)
    emitChange()
  }, 4000)
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const [state, setState] = useState<Toast[]>(toasts)

  useEffect(() => {
    const listener = (newToasts: Toast[]) => setState(newToasts)
    listeners.push(listener)
    return () => {
      listeners = listeners.filter((l) => l !== listener)
    }
  }, [])

  return {
    toasts: state,
    toast,
    dismiss: (id: string) => {
      toasts = toasts.filter((t) => t.id !== id)
      emitChange()
    },
  }
}

const variantStyles: Record<string, string> = {
  default: "bg-primary text-primary-foreground",
  success: "bg-emerald-600 text-white",
  error: "bg-destructive text-destructive-foreground",
  warning: "bg-amber-600 text-white",
}

export function ToastContainer() {
  const { toasts, dismiss } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "flex items-start gap-3 rounded-lg px-4 py-3 shadow-lg text-sm animate-in slide-in-from-right-2 fade-in",
            variantStyles[t.variant || "default"]
          )}
        >
          <div className="flex-1">
            <p className="font-medium">{t.title}</p>
            {t.description && (
              <p className="opacity-80 text-xs mt-0.5">{t.description}</p>
            )}
          </div>
          <button
            onClick={() => dismiss(t.id)}
            className="shrink-0 opacity-70 hover:opacity-100 transition-opacity"
            aria-label="Cerrar notificación"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
