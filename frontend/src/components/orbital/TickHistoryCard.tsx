/**
 * TickHistoryCard — Lista de ticks ejecutados (orden descendente).
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 */
import type { TickHistory } from "@/types/orbital"

interface TickHistoryCardProps {
  history: TickHistory[]
}

export function TickHistoryCard({ history }: TickHistoryCardProps) {
  if (history.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-sm text-zinc-500">
        Aún no hay ticks ejecutados
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {[...history].reverse().map((h, i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-zinc-800/30"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-500/10 text-[10px] font-bold text-indigo-400">
              #{h.tick}
            </span>
            <span className="text-zinc-400">{h.variables} variables</span>
          </div>
          <span className="font-mono text-xs text-zinc-500">{h.duration_ms}ms</span>
        </div>
      ))}
    </div>
  )
}
