/**
 * VariableDialog — Diálogo "Nueva variable orbital" (controlado).
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Encapsulamiento: el form state + submitting state viven aquí.
 *
 * Props:
 * - open: boolean
 * - onOpenChange: (open: boolean) => void
 * - onSubmit: (form: { name; theta; amplitude; velocity }) => Promise<void>
 *   Si resolve → el diálogo se cierra y resetea. Si reject → queda abierto.
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

export interface VariableFormValues {
  name: string
  theta: number
  amplitude: number
  velocity: number
}

interface VariableDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (form: VariableFormValues) => Promise<void>
}

const DEFAULT_FORM = { name: "", theta: "0", amplitude: "10", velocity: "0.1" }

export function VariableDialog({ open, onOpenChange, onSubmit }: VariableDialogProps) {
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
    if (!form.name.trim()) return
    setSubmitting(true)
    try {
      await onSubmit({
        name: form.name.trim(),
        theta: parseFloat(form.theta) || 0,
        amplitude: parseFloat(form.amplitude) || 10,
        velocity: parseFloat(form.velocity) || 0.1,
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
          <DialogTitle>Nueva variable orbital</DialogTitle>
          <DialogDescription className="text-zinc-400">
            Define una variable con fase inicial, amplitud y velocidad orbital
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label htmlFor="orbital-variable-name" className="mb-1 block text-sm text-zinc-300">
              Nombre <span className="text-red-400">*</span>
            </label>
            <Input
              id="orbital-variable-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Ej: Demanda, Precio, Oferta"
              className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label htmlFor="orbital-variable-theta" className="mb-1 block text-sm text-zinc-300">θ inicial</label>
              <Input
                id="orbital-variable-theta"
                type="number"
                step={0.1}
                value={form.theta}
                onChange={(e) => setForm({ ...form, theta: e.target.value })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
            </div>
            <div>
              <label htmlFor="orbital-variable-amplitude" className="mb-1 block text-sm text-zinc-300">Amplitud</label>
              <Input
                id="orbital-variable-amplitude"
                type="number"
                step={0.5}
                value={form.amplitude}
                onChange={(e) => setForm({ ...form, amplitude: e.target.value })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
            </div>
            <div>
              <label htmlFor="orbital-variable-velocity" className="mb-1 block text-sm text-zinc-300">Velocidad</label>
              <Input
                id="orbital-variable-velocity"
                type="number"
                step={0.01}
                value={form.velocity}
                onChange={(e) => setForm({ ...form, velocity: e.target.value })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
            </div>
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
            disabled={submitting || !form.name.trim()}
            className="bg-indigo-600 text-white hover:bg-indigo-500"
          >
            {submitting ? (
              <>
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                Creando…
              </>
            ) : (
              "Crear variable"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
