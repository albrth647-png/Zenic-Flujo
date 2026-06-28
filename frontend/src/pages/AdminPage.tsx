/**
 * AdminPage — Página de administración (shell con Tabs).
 *
 * Sprint 4 (bug #59): dividido en sub-componentes en `components/admin/`:
 * - UsersTab       — gestión de usuarios (GET/POST/PUT/DELETE /api/users)
 * - DeadLetterTab  — buzón de errores DLQ
 * - QueueTab       — cola de trabajos y workers
 * - MetricsTab     — dashboard de métricas (Sprint 11)
 * - AlertsTab      — gestión de alertas (Sprint 11)
 */
import { Card, CardContent } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Users as UsersIcon, Activity, AlertCircle } from "lucide-react"
import { UsersTab } from "@/components/admin/UsersTab"
import { DeadLetterTab } from "@/components/admin/DeadLetterTab"
import { QueueTab } from "@/components/admin/QueueTab"
import { MetricsTab } from "@/components/admin/MetricsTab"
import { AlertsTab } from "@/components/admin/AlertsTab"

export default function AdminPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-100">Panel de Administración</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Gestiona usuarios, revisa errores y supervisa el motor de workflows
        </p>
      </div>

      <Tabs defaultValue="users" className="w-full">
        <TabsList className="border-zinc-800 bg-zinc-900">
          <TabsTrigger
            value="users"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <UsersIcon className="mr-1.5 h-4 w-4" />
            Usuarios
          </TabsTrigger>
          <TabsTrigger
            value="dead-letter"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <AlertCircle className="mr-1.5 h-4 w-4" />
            Buzón de errores
          </TabsTrigger>
          <TabsTrigger
            value="queue"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Activity className="mr-1.5 h-4 w-4" />
            Cola de trabajos
          </TabsTrigger>
          <TabsTrigger
            value="metrics"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Activity className="mr-1.5 h-4 w-4" />
            Métricas
          </TabsTrigger>
          <TabsTrigger
            value="alerts"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <AlertCircle className="mr-1.5 h-4 w-4" />
            Alertas
          </TabsTrigger>
        </TabsList>

        <div className="mt-4">
          <TabsContent value="users">
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-4">
                <UsersTab />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="dead-letter">
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-4">
                <DeadLetterTab />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="queue">
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-4">
                <QueueTab />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="metrics">
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-4">
                <MetricsTab />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="alerts">
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-4">
                <AlertsTab />
              </CardContent>
            </Card>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}
