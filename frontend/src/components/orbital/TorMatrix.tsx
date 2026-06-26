/**
 * TorMatrix — Lista de parejas TOR con color de fondo.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 */
import { torColor, torBg } from "@/components/orbital/helpers"
import type { TorEntry } from "@/types/orbital"

interface TorMatrixProps {
  entries: TorEntry[]
}

export function TorMatrix({ entries }: TorMatrixProps) {
  if (entries.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-zinc-500">
        Sin datos TOR — ejecuta un tick primero
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {entries.slice(0, 25).map((entry, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-zinc-800/30"
          style={{ backgroundColor: torBg(entry.tor_value) }}
        >
          <span className="text-zinc-300">
            <span className="text-indigo-400">{entry.variable_i}</span>
            {" ↔ "}
            <span className="text-indigo-400">{entry.variable_j}</span>
          </span>
          <div className="flex items-center gap-3">
            <span className={`font-mono text-xs ${torColor(entry.tor_value)}`}>
              {entry.tor_value.toFixed(4)}
            </span>
            <span className={`text-[10px] ${entry.alignment > 0 ? "text-emerald-500" : "text-red-500"}`}>
              {entry.alignment > 0 ? "resonante" : "opuesta"}
            </span>
          </div>
        </div>
      ))}
      {entries.length > 25 && (
        <p className="pt-1 text-center text-[10px] text-zinc-600">
          Mostrando 25 de {entries.length} parejas
        </p>
      )}
    </div>
  )
}
