/**
 * HistoryTab — Tab content con TickHistoryCard.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Recibe `status` como prop (estado lifted en OrbitalPage).
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { History } from "lucide-react"
import { TickHistoryCard } from "@/components/orbital/TickHistoryCard"
import type { OrbitalStatus } from "@/types/orbital"

interface HistoryTabProps {
  status: OrbitalStatus
}

export function HistoryTab({ status }: HistoryTabProps) {
  return (
    <Card className="border-zinc-800 bg-zinc-900/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-400 flex items-center gap-2">
          <History className="h-4 w-4" />
          Historial de ticks
        </CardTitle>
      </CardHeader>
      <CardContent>
        <TickHistoryCard history={status.history || []} />
      </CardContent>
    </Card>
  )
}
