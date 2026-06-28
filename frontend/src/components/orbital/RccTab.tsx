/**
 * RccTab — Tab content de Ciclos RCC.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Recibe `status` como prop (estado lifted en OrbitalPage).
 * Renderiza CycleCard por cada ciclo, o estado vacío con CTA.
 */
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Radio, Layers } from "lucide-react"
import { CycleCard } from "@/components/orbital/CycleCard"
import type { OrbitalStatus } from "@/types/orbital"

interface RccTabProps {
  status: OrbitalStatus
  variableNames: string[]
  onNewCycle: () => void
}

export function RccTab({ status, variableNames, onNewCycle }: RccTabProps) {
  if (!status.rcc || status.rcc.length === 0) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/50">
        <CardContent className="flex flex-col items-center justify-center p-12">
          <Radio className="h-12 w-12 text-zinc-600" />
          <h3 className="mt-4 text-sm font-medium text-zinc-300">No hay ciclos orbitales</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Crea un ciclo con al menos 2 variables para ver resonancia
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={onNewCycle}
            disabled={variableNames.length < 2}
            className="mt-4 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <Layers className="mr-1.5 h-4 w-4" />
            Crear ciclo
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {status.rcc.map((cycle) => {
        const cod = status.cod?.find((c) => c.cycle_id === cycle.cycle_id)
        return <CycleCard key={cycle.cycle_id} cycle={cycle} cod={cod} />
      })}
    </div>
  )
}
