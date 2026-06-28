/**
 * VariablesTab — Tab content de Variables orbitales.
 *
 * Sprint 4 (bug #59): extraído de OrbitalPage.tsx.
 * Recibe `status` como prop (estado lifted en OrbitalPage).
 * Renderiza VariableCard por cada variable, o estado vacío.
 */
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { CircleDot, Plus } from "lucide-react"
import { VariableCard } from "@/components/orbital/VariableCard"
import type { OrbitalStatus } from "@/types/orbital"

interface VariablesTabProps {
  status: OrbitalStatus
  onNewVariable: () => void
  onDeleteVariable: (name: string) => void
}

export function VariablesTab({ status, onNewVariable, onDeleteVariable }: VariablesTabProps) {
  const variableNames = Object.keys(status.variables)

  if (variableNames.length === 0) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/50">
        <CardContent className="flex flex-col items-center justify-center p-12">
          <CircleDot className="h-12 w-12 text-zinc-600" />
          <h3 className="mt-4 text-sm font-medium text-zinc-300">No hay variables orbitales</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Crea tu primera variable para empezar a orbitar
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={onNewVariable}
            className="mt-4 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <Plus className="mr-1.5 h-4 w-4" />
            Crear variable
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {variableNames.map((name) => (
        <VariableCard
          key={name}
          name={name}
          varData={status.variables[name]}
          onDelete={onDeleteVariable}
        />
      ))}
    </div>
  )
}
