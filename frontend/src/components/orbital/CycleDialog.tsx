/**
 * CycleDialog — Diálogo "Nuevo ciclo orbital" (controlado).
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Encapsulamiento: el form state + submitting state viven aquí.
 *
 * Props:
 * - open: boolean
 * - onOpenChange: (open: boolean) => void
 * - onSubmit: (form: { name; variables; threshold }) => Promise<void>
 *   Si resolve → el diálogo se cierra y resetea. Si reject → queda abierto.
 * - variableNames: string[] — para mostrar variables disponibles.
 */
import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Loader2 } from "lucide-react"

export interface CycleFormValues {
  name: string
  variables: string[]
  threshold: number
}

interface CycleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (form: CycleFormValues) => Promise<void>
  variableNames: string[]
}

const DEFAULT_FORM = { name: "", variables: "", threshold: "0.5" }

export function CycleDialog({ open, onOpenChange, onSubmit, variableNames }: CycleDialogProps) {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [submitting, setSubmitting] = useState(false)

  // Reset form cuando el diálogo se cierra
  useEffect(() => {
    if (!open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setForm(DEFAULT_FORM)
    }
  }, [open])

  async function handleSubmit() {
    if (!form.name.trim() || !form.variables.trim()) return
    setSubmitting(true)
    try {
      await onSubmit({
        name: form.name.trim(),
        variables: form.variables.split(",").map((v) => v.trim()).filter(Boolean),
        threshold: parseFloat(form.threshold) || 0.5,
      })
      onOpenChange(false)
    } catch {
      // El padre ya mostró el toast; mantener diálogo abierto para reintentar.
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
        <DialogHeader>
          <DialogTitle>Nuevo ciclo orbital</DialogTitle>
          <DialogDescription className="text-zinc-400">
            Agrupa variables en un ciclo cerrado con un umbral de resonancia
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label htmlFor="orbital-cycle-name" className="mb-1 block text-sm text-zinc-300">
              Nombre del ciclo <span className="text-red-400">*</span>
            </label>
            <Input
              id="orbital-cycle-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Ej: Económico, Logístico"
              className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
            />
          </div>
          <div>
            <label htmlFor="orbital-cycle-variables" className="mb-1 block text-sm text-zinc-300">
              Variables <span className="text-red-400">*</span>
            </label>
            <Input
              id="orbital-cycle-variables"
              value={form.variables}
              onChange={(e) => setForm({ ...form, variables: e.target.value })}
              placeholder="Ej: Demanda, Precio, Oferta"
              className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
            />
            <p className="mt-1 text-xs text-zinc-500">
              Separadas por coma. Variables disponibles: {variableNames.join(", ") || "ninguna"}
            </p>
          </div>
          <div>
            <label htmlFor="orbital-cycle-threshold" className="mb-1 block text-sm text-zinc-300">Umbral de resonancia</label>
            <Input
              id="orbital-cycle-threshold"
              type="number"
              step={0.1}
              min={0}
              max={1}
              value={form.threshold}
              onChange={(e) => setForm({ ...form, threshold: e.target.value })}
              className="border-zinc-700 bg-zinc-800 text-zinc-200"
            />
            <p className="mt-1 text-xs text-zinc-500">Entre 0 y 1. Más alto = más difícil resonar</p>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={submitting || !form.name.trim() || !form.variables.trim()}
            className="bg-indigo-600 text-white hover:bg-indigo-500"
          >
            {submitting ? (
              <>
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                Creando…
              </>
            ) : (
              "Crear ciclo"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
