import { useState, useCallback } from "react"

interface ConfirmOptions {
  title?: string
  description?: string
  confirmText?: string
  cancelText?: string
  variant?: "default" | "destructive"
}

interface ConfirmState {
  open: boolean
  title: string
  description: string
  confirmText: string
  cancelText: string
  variant: "default" | "destructive"
  resolve: (value: boolean) => void
}

export function useConfirm() {
  const [state, setState] = useState<ConfirmState | null>(null)

  const confirm = useCallback(
    (options: ConfirmOptions = {}): Promise<boolean> => {
      return new Promise((resolve) => {
        setState({
          open: true,
          title: options.title || "Confirmar",
          description: options.description || "¿Estás seguro de realizar esta acción?",
          confirmText: options.confirmText || "Confirmar",
          cancelText: options.cancelText || "Cancelar",
          variant: options.variant || "default",
          resolve,
        })
      })
    },
    []
  )

  const handleConfirm = useCallback(() => {
    if (state) {
      state.resolve(true)
      setState(null)
    }
  }, [state])

  const handleCancel = useCallback(() => {
    if (state) {
      state.resolve(false)
      setState(null)
    }
  }, [state])

  return {
    confirm,
    state,
    handleConfirm,
    handleCancel,
  }
}
