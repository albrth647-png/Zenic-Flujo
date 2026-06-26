import { useEffect, useState, useCallback } from "react"
import { useAgents } from "@/hooks/useAgents"
import type { AgentStatus, AgentConfig, TokenUsageSummary, RuntimeStats } from "@/types/agents"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Play, Pause, Square, RotateCcw, Plus, Loader2, Activity, DollarSign, Cpu,
} from "lucide-react"

const STATE_COLORS: Record<string, string> = {
  idle: "bg-gray-500",
  running: "bg-green-500",
  paused: "bg-yellow-500",
  terminated: "bg-red-500",
  error: "bg-red-700",
}

export default function AgentsPage() {
  const api = useAgents()
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [stats, setStats] = useState<RuntimeStats | null>(null)
  const [tokenSummary, setTokenSummary] = useState<TokenUsageSummary | null>(null)
  const [showSpawn, setShowSpawn] = useState(false)
  const [newAgent, setNewAgent] = useState<Partial<AgentConfig>>({ name: "", description: "" })
  const [activeTab, setActiveTab] = useState<"agents" | "tokens">("agents")

  const loadData = useCallback(async () => {
    const [agentsData, statsData, tokenData] = await Promise.all([
      api.list(),
      api.getStats(),
      api.getTokenSummary(),
    ])
    if (agentsData) setAgents(agentsData.agents)
    if (statsData) setStats(statsData)
    if (tokenData) setTokenSummary(tokenData)
  }, [api])

  useEffect(() => { loadData() }, [loadData])

  const handleSpawn = async () => {
    if (!newAgent.name) return
    const config: AgentConfig = {
      name: newAgent.name,
      description: newAgent.description || undefined,
      capabilities: newAgent.capabilities || [],
    }
    const result = await api.spawn(config)
    if (result) {
      setShowSpawn(false)
      setNewAgent({ name: "", description: "" })
      loadData()
    }
  }

  const handleAction = async (agentId: string, action: "run" | "pause" | "resume" | "terminate") => {
    let success = false
    switch (action) {
      case "run": { await api.run(agentId); success = true; break }
      case "pause": success = await api.pause(agentId); break
      case "resume": success = await api.resume(agentId); break
      case "terminate": success = await api.terminate(agentId); break
    }
    if (success) loadData()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agentes IA</h1>
          <p className="text-sm text-muted-foreground">Gestiona agentes de inteligencia artificial</p>
        </div>
        <Button onClick={() => setShowSpawn(!showSpawn)}>
          <Plus className="size-4 mr-2" /> Nuevo agente
        </Button>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Activos</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{stats?.active_agents ?? "—"}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Creados</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{stats?.total_agents_spawned ?? "—"}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Duración promedio</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{stats ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : "—"}</div></CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm font-medium text-muted-foreground">Tokens usados</CardTitle></CardHeader><CardContent><div className="text-2xl font-bold">{stats?.total_tokens_used?.toLocaleString() ?? "—"}</div></CardContent></Card>
      </div>

      {/* Spawn form */}
      {showSpawn && (
        <Card>
          <CardHeader><CardTitle>Configurar nuevo agente</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Input placeholder="Nombre del agente" value={newAgent.name} onChange={e => setNewAgent(p => ({ ...p, name: e.target.value }))} />
            <Textarea placeholder="Descripción (opcional)" value={newAgent.description} onChange={e => setNewAgent(p => ({ ...p, description: e.target.value }))} />
            <div className="flex gap-2">
              <Button onClick={handleSpawn} disabled={api.loading || !newAgent.name}>
                {api.loading ? <Loader2 className="size-4 mr-2 animate-spin" /> : <Plus className="size-4 mr-2" />}
                Crear agente
              </Button>
              <Button variant="outline" onClick={() => setShowSpawn(false)}>Cancelar</Button>
            </div>
            {api.error && <p className="text-sm text-destructive">{api.error}</p>}
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b pb-2">
        <button onClick={() => setActiveTab("agents")} className={`px-3 py-1.5 text-sm rounded-t-md transition ${activeTab === "agents" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>
          <Cpu className="size-3.5 inline mr-1.5" />Agentes
        </button>
        <button onClick={() => setActiveTab("tokens")} className={`px-3 py-1.5 text-sm rounded-t-md transition ${activeTab === "tokens" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>
          <DollarSign className="size-3.5 inline mr-1.5" />Tokens
        </button>
      </div>

      {/* Agents table */}
      {activeTab === "agents" && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Capacidades</TableHead>
                  <TableHead>Iteraciones</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {agents.length === 0 && (
                  <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No hay agentes. Crea uno nuevo.</TableCell></TableRow>
                )}
                {agents.map(agent => (
                  <TableRow key={agent.agent_id}>
                    <TableCell className="font-medium">{agent.name}</TableCell>
                    <TableCell><Badge className={`${STATE_COLORS[agent.state]} text-white`}>{agent.state}</Badge></TableCell>
                    <TableCell><span className="text-xs text-muted-foreground">{(agent.capabilities ?? []).join(", ") || "—"}</span></TableCell>
                    <TableCell>{agent.iteration_count ?? 0}</TableCell>
                    <TableCell>{agent.token_count?.toLocaleString() ?? 0}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {agent.state === "idle" && <Button size="icon" variant="ghost" onClick={() => handleAction(agent.agent_id, "run")} title="Ejecutar"><Play className="size-3.5" /></Button>}
                        {agent.state === "running" && <Button size="icon" variant="ghost" onClick={() => handleAction(agent.agent_id, "pause")} title="Pausar"><Pause className="size-3.5" /></Button>}
                        {agent.state === "paused" && <Button size="icon" variant="ghost" onClick={() => handleAction(agent.agent_id, "resume")} title="Reanudar"><RotateCcw className="size-3.5" /></Button>}
                        {(agent.state === "idle" || agent.state === "paused") && <Button size="icon" variant="ghost" onClick={() => handleAction(agent.agent_id, "terminate")} title="Terminar"><Square className="size-3.5" /></Button>}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Token usage */}
      {activeTab === "tokens" && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card><CardHeader><CardTitle className="text-sm">Total Tokens</CardTitle></CardHeader><CardContent><div className="text-3xl font-bold">{tokenSummary?.total_tokens?.toLocaleString() ?? "—"}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Costo Total</CardTitle></CardHeader><CardContent><div className="text-3xl font-bold">${tokenSummary?.total_cost?.toFixed(4) ?? "—"}</div></CardContent></Card>
          <Card><CardHeader><CardTitle className="text-sm">Promedio Diario</CardTitle></CardHeader><CardContent><div className="text-3xl font-bold">{tokenSummary?.daily_average?.toLocaleString() ?? "—"}</div></CardContent></Card>
        </div>
      )}
    </div>
  )
}
