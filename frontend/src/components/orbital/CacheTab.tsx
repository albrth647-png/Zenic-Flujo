/**
 * CacheTab — Tab content con 4 stats de tor_cache.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Recibe `status` como prop (estado lifted en OrbitalPage).
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { BarChart3 } from "lucide-react"
import type { OrbitalStatus } from "@/types/orbital"

interface CacheTabProps {
  status: OrbitalStatus
}

export function CacheTab({ status }: CacheTabProps) {
  return (
    <Card className="border-zinc-800 bg-zinc-900/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Estadísticas del Cache TOR
        </CardTitle>
      </CardHeader>
      <CardContent>
        {status.tor_cache ? (
          <div className="grid gap-4 sm:grid-cols-4">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
              <p className="text-lg font-bold text-indigo-400">{status.tor_cache.hits.toLocaleString()}</p>
              <p className="mt-1 text-xs text-zinc-500">Aciertos (hits)</p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
              <p className="text-lg font-bold text-amber-400">{status.tor_cache.misses.toLocaleString()}</p>
              <p className="mt-1 text-xs text-zinc-500">Fallos (misses)</p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
              <p className="text-lg font-bold text-emerald-400">
                {(status.tor_cache.hit_rate * 100).toFixed(1)}%
              </p>
              <p className="mt-1 text-xs text-zinc-500">Hit rate</p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
              <p className="text-lg font-bold text-zinc-100">{status.tor_cache.cache_size}</p>
              <p className="mt-1 text-xs text-zinc-500">Entradas en cache</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">Cache no disponible</p>
        )}
      </CardContent>
    </Card>
  )
}
