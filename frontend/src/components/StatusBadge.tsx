import { Badge } from "@/components/ui/badge"
import { status as humanStatus } from "@/utils/humanize"

const statusConfig: Record<
  string,
  { variant: "success" | "warning" | "destructive" | "default" | "outline"; label: string }
> = {
  active: { variant: "success", label: "Activo" },
  completed: { variant: "success", label: "Completado" },
  running: { variant: "default", label: "Ejecutando" },
  paused: { variant: "warning", label: "Pausado" },
  failed: { variant: "destructive", label: "Fallido" },
  error: { variant: "destructive", label: "Error" },
  archived: { variant: "outline", label: "Archivado" },
}

export function StatusBadge({ status }: { status: string }) {
  const config = statusConfig[status] || { variant: "outline" as const, label: humanStatus(status) || status }
  return <Badge variant={config.variant}>{config.label}</Badge>
}
