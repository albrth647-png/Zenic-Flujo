/**
 * TorTab — Tab content de Matriz TOR.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Recibe `status` como prop (estado lifted en OrbitalPage).
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Zap } from "lucide-react"
import { TorMatrix } from "@/components/orbital/TorMatrix"
import type { OrbitalStatus } from "@/types/orbital"

interface TorTabProps {
  status: OrbitalStatus
}

export function TorTab({ status }: TorTabProps) {
  return (
    <Card className="border-zinc-800 bg-zinc-900/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
          <Zap className="h-4 w-4" />
          Tensiones Orbitales Recíprocas
          <span className="text-xs text-zinc-600 font-normal">
            ({status.tor.length} parejas)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <TorMatrix entries={status.tor} />
      </CardContent>
    </Card>
  )
}
