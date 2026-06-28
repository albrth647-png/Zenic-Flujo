/**
 * VariableCard — Tarjeta de variable orbital con SVG de fase.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 */
import { Button } from "@/components/ui/button"
import { Trash2, CircleDot } from "lucide-react"
import { degrees } from "@/components/orbital/helpers"
import type { OrbitalVariable } from "@/types/orbital"

interface VariableCardProps {
  name: string
  varData: OrbitalVariable
  onDelete: (name: string) => void
}

export function VariableCard({ name, varData, onDelete }: VariableCardProps) {
  const deg = degrees(varData.theta)
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CircleDot className="h-4 w-4 text-indigo-400" />
          <span className="font-medium text-zinc-200">{name}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-zinc-500 hover:text-red-400"
          onClick={() => onDelete(name)}
          title="Eliminar variable"
          aria-label={`Eliminar variable ${name}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Fase visual */}
      <div className="mb-3 flex items-center justify-center">
        <div className="relative flex h-16 w-16 items-center justify-center">
          <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
            <circle cx="32" cy="32" r="28" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
            <circle
              cx="32"
              cy="32"
              r="28"
              fill="none"
              stroke="#6366f1"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${(deg / 360) * 176} 176`}
              className="transition-all duration-500"
            />
            <circle
              cx={32 + 28 * Math.sin(varData.theta)}
              cy={32 - 28 * Math.cos(varData.theta)}
              r="4"
              fill="#6366f1"
              className="transition-all duration-500"
            />
          </svg>
        </div>
      </div>

      {/* Métricas */}
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between text-zinc-400">
          <span>θ</span>
          <span className="font-mono text-zinc-200">{deg.toFixed(1)}°</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Amplitud</span>
          <span className="font-mono text-zinc-200">{varData.amplitude.toFixed(1)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Velocidad</span>
          <span className="font-mono text-zinc-200">{varData.velocity.toFixed(3)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Valor</span>
          <span className="font-mono text-zinc-200">{varData.value.toFixed(4)}</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Grupo</span>
          <span className="text-zinc-500">{varData.orbit_group || "default"}</span>
        </div>
      </div>
    </div>
  )
}
