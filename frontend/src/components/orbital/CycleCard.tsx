/**
 * CycleCard — Tarjeta de ciclo RCC + estado COD (convergencia).
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 */
import { Badge } from "@/components/ui/badge"
import { Radio, CheckCircle2, XCircle } from "lucide-react"
import type { RccCycle, CodResult } from "@/types/orbital"

interface CycleCardProps {
  cycle: RccCycle
  cod?: CodResult
}

export function CycleCard({ cycle, cod }: CycleCardProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio className={`h-4 w-4 ${cycle.is_resonant ? "text-emerald-400" : "text-zinc-500"}`} />
          <span className="text-sm font-medium text-zinc-200">{cycle.cycle_name}</span>
        </div>
        <Badge
          variant="outline"
          className={
            cycle.is_resonant
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
              : "border-zinc-700 bg-zinc-800 text-zinc-400"
          }
        >
          {cycle.is_resonant ? "Resonante" : "Silencio"}
        </Badge>
      </div>
      <div className="space-y-1 text-xs text-zinc-500">
        <div className="flex justify-between">
          <span>ID: {cycle.cycle_id}</span>
          <span>Fuerza: {cycle.strength.toFixed(4)}</span>
        </div>
        {cod && (
          <div className="flex justify-between pt-1 border-t border-zinc-800">
            <span className="flex items-center gap-1">
              {cod.converged ? (
                <CheckCircle2 className="h-3 w-3 text-emerald-400" />
              ) : (
                <XCircle className="h-3 w-3 text-red-400" />
              )}
              {cod.converged ? "Convergió" : "No convergió"}
            </span>
            <span>{cod.iterations} iteraciones</span>
            <span>Δ: {cod.convergence_delta.toExponential(2)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
