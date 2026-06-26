/**
 * NluPage — Interfaz del Pipeline NLU
 * =====================================
 *
 * 7 endpoints expuestos en tabs:
 *   🔍 Understand  — Procesar texto (etapas 1-6)
 *   ⚙️  Compile     — Compilar workflow desde texto (1-11)
 *   🧪 Dry Run     — Simulación sin efectos (1-12)
 *   📋 Intents     — Listar intenciones registradas
 *   🏷️  Entities    — Listar tipos de entidades
 *   🎓 Training    — Disparar y monitorear entrenamiento
 */

import { useState, useEffect, useCallback } from "react"
import { useNlu } from "@/hooks/useNlu"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import {
  Search,
  Code2,
  FlaskConical,
  List,
  Tags,
  BrainCircuit,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Sparkles,
  RefreshCw,
  Activity,
} from "lucide-react"
import { error as humanError } from "@/utils/humanize"
import type {
  NLUUnderstandResponse,
  NLUCompileResponse,
  NLUDryRunResult,
  NLUIntentsResponse,
  NLUEntitiesResponse,
  NLUTrainResponse,
  NLUTrainingStatus,
} from "@/types/nlu"

type TabId = "understand" | "compile" | "dry-run" | "intents" | "entities" | "training"

interface Tab {
  id: TabId
  label: string
  icon: React.FC<{ className?: string }>
}

const TABS: Tab[] = [
  { id: "understand", label: "Analizar", icon: Search },
  { id: "compile", label: "Generar", icon: Code2 },
  { id: "dry-run", label: "Simular", icon: FlaskConical },
  { id: "intents", label: "Intenciones", icon: List },
  { id: "entities", label: "Entidades", icon: Tags },
  { id: "training", label: "Entrenar", icon: BrainCircuit },
]

export default function NluPage() {
  const { understand, compile, dryRun, listIntents, listEntities, train, getTrainingStatus } = useNlu()
  const [activeTab, setActiveTab] = useState<TabId>("understand")
  const [text, setText] = useState("")
  const [lang, setLang] = useState("es")
  const [loading, setLoading] = useState(false)
  const [intentsData, setIntentsData] = useState<NLUIntentsResponse | null>(null)
  const [entitiesData, setEntitiesData] = useState<NLUEntitiesResponse | null>(null)
  const [trainingStatus, setTrainingStatus] = useState<NLUTrainingStatus | null>(null)
  const [trainingLang, setTrainingLang] = useState("es")

  // Results per tab
  const [understandResult, setUnderstandResult] = useState<NLUUnderstandResponse | null>(null)
  const [compileResult, setCompileResult] = useState<NLUCompileResponse | null>(null)
  const [dryRunResult, setDryRunResult] = useState<NLUDryRunResult | null>(null)

  // ── Actions ─────────────────────────────────────────────────────

  // Resetea loading al cambiar de tab para evitar interferencia entre tabs
  useEffect(() => {
    setLoading(false)
  }, [activeTab])

  const handleUnderstand = async () => {
    if (!text.trim()) return
    setLoading(true)
    setUnderstandResult(null)
    try {
      const res = await understand(text.trim(), lang)
      setUnderstandResult(res)
      toast({ title: "Pipeline NLU completado", description: `Confianza: ${(res.confidence * 100).toFixed(1)}%`, variant: "success" })
    } catch (err) {
      toast({ title: "Error en NLU", description: humanError(err), variant: "error" })
    } finally {
      setLoading(false)
    }
  }

  const handleCompile = async () => {
    if (!text.trim()) return
    setLoading(true)
    setCompileResult(null)
    try {
      const res = await compile(text.trim(), lang)
      setCompileResult(res)
      toast({ title: `Workflow ${res.status}`, description: res.explanation.slice(0, 120), variant: "success" })
    } catch (err) {
      toast({ title: "Error compilando", description: humanError(err), variant: "error" })
    } finally {
      setLoading(false)
    }
  }

  const handleDryRun = async () => {
    if (!text.trim()) return
    setLoading(true)
    setDryRunResult(null)
    try {
      const res = await dryRun(text.trim(), lang)
      setDryRunResult(res)
      toast({
        title: res.overall_feasible ? "Simulación viable" : "Simulación no viable",
        description: res.summary.slice(0, 120),
        variant: res.overall_feasible ? "success" : "warning",
      })
    } catch (err) {
      toast({ title: "Error en simulación", description: humanError(err), variant: "error" })
    } finally {
      setLoading(false)
    }
  }

  const loadIntents = useCallback(async () => {
    try {
      const res = await listIntents()
      setIntentsData(res)
    } catch (err) {
      toast({ title: "Error cargando intenciones", description: humanError(err), variant: "error" })
    }
  }, [listIntents])

  const loadEntities = useCallback(async () => {
    try {
      const res = await listEntities()
      setEntitiesData(res)
    } catch (err) {
      toast({ title: "Error cargando entidades", description: humanError(err), variant: "error" })
    }
  }, [listEntities])

  const handleTrain = async () => {
    setLoading(true)
    try {
      const res = await train(trainingLang)
      setTrainingStatus(res)
      toast({ title: `Entrenamiento ${res.status}`, description: res.message, variant: "success" })
    } catch (err) {
      toast({ title: "Error en entrenamiento", description: humanError(err), variant: "error" })
    } finally {
      setLoading(false)
    }
  }

  const refreshTrainingStatus = async () => {
    try {
      const res = await getTrainingStatus()
      setTrainingStatus(res)
    } catch (e) {
      const silentErr = humanError(e)
      if (!silentErr.includes("Error de conexión") && !silentErr.includes("desconocido")) {
        console.warn("Training status check:", silentErr)
      }
    }
  }

  // Load intents/entities on tab switch
  useEffect(() => {
    if (activeTab === "intents" && !intentsData) loadIntents()
    if (activeTab === "entities" && !entitiesData) loadEntities()
    if (activeTab === "training") refreshTrainingStatus()
  }, [activeTab, intentsData, entitiesData, loadIntents, loadEntities])

  // Auto-refresh training status every 5s while training
  useEffect(() => {
    if (trainingStatus?.status !== "training" && trainingStatus?.status !== "queued") return
    const interval = setInterval(refreshTrainingStatus, 5000)
    return () => clearInterval(interval)
  }, [trainingStatus?.status])

  // ── Render by tab ───────────────────────────────────────────────

  const renderUnderstand = () => (
    <div className="space-y-4">
      <div className="flex gap-3 items-start">
        <div className="flex-1 space-y-2">
          <label className="text-xs text-zinc-400">Texto en lenguaje natural</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='Ej: "Enviar correo a cliente cuando la factura supere $10,000 MXN"'
            rows={4}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md p-3 text-sm font-mono resize-y"
          />
        </div>
        <div className="space-y-2 w-24">
          <label className="text-xs text-zinc-400">Idioma</label>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-2 text-sm"
          >
            <option value="es">ES</option>
            <option value="en">EN</option>
            <option value="pt">PT</option>
          </select>
        </div>
      </div>
      <Button onClick={handleUnderstand} disabled={loading || !text.trim()}>
        {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Search className="h-4 w-4 mr-2" />}
        {loading ? "Procesando..." : "Entender texto"}
      </Button>

      {understandResult && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-zinc-300">Confianza:</span>
            <span className={`text-xs font-mono ${understandResult.confidence > 0.7 ? "text-emerald-400" : understandResult.confidence > 0.4 ? "text-amber-400" : "text-red-400"}`}>
              {(understandResult.confidence * 100).toFixed(1)}%
            </span>
            <Badge variant="outline" className="text-xs">{understandResult.lang}</Badge>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Card>
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500 mb-1">Tokens</div>
                <div className="text-lg font-bold">{understandResult.tokens.length}</div>
                <div className="text-[10px] text-zinc-600 truncate">
                  {understandResult.tokens.map(t => t.text).join(", ")}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500 mb-1">Entities</div>
                <div className="text-lg font-bold">{understandResult.entities.length}</div>
                <div className="text-[10px] text-zinc-600 truncate">
                  {understandResult.entities.map(e => `${e.type}:${e.value}`).join(", ")}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500 mb-1">Intents detectados</div>
                <div className="text-lg font-bold">{understandResult.intents.length}</div>
                <div className="text-[10px] text-zinc-600 truncate">
                  {understandResult.intents.map(i => `${i.intent} (${(i.score * 100).toFixed(0)}%)`).join(", ")}
                </div>
              </CardContent>
            </Card>
          </div>

          {understandResult.slots.length > 0 && (
            <Card>
              <CardContent className="p-3">
                <div className="text-xs font-semibold text-zinc-300 mb-2">Slots llenados</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {understandResult.slots.map((slot, i) => (
                    <div key={i} className="text-xs p-2 bg-zinc-800/50 rounded border border-zinc-700/50">
                      <span className="text-zinc-500">{slot.name}:</span>{" "}
                      <span className="text-zinc-200 font-mono">{slot.value}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {understandResult.trace.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-blue-400 hover:underline">Bitácora del análisis</summary>
              <pre className="mt-2 p-3 bg-zinc-950 border border-zinc-800 rounded-md max-h-48 overflow-auto font-mono text-[10px]">
                {understandResult.trace.join("\n")}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )

  const renderCompile = () => (
    <div className="space-y-4">
      <div className="flex gap-3 items-start">
        <div className="flex-1 space-y-2">
          <label className="text-xs text-zinc-400">Descripción del workflow</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='Ej: "Cuando un cliente paga una factura, enviar un correo de confirmación y actualizar el CRM"'
            rows={4}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md p-3 text-sm font-mono resize-y"
          />
        </div>
        <div className="space-y-2 w-24">
          <label className="text-xs text-zinc-400">Idioma</label>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-2 text-sm"
          >
            <option value="es">ES</option>
            <option value="en">EN</option>
            <option value="pt">PT</option>
          </select>
        </div>
      </div>
      <Button onClick={handleCompile} disabled={loading || !text.trim()}>
        {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Code2 className="h-4 w-4 mr-2" />}
        {loading ? "Compilando..." : "Compilar workflow"}
      </Button>

      {compileResult && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant={compileResult.status === "valid" ? "default" : compileResult.status === "partial" ? "secondary" : "destructive"}>
              {compileResult.status}
            </Badge>
            <span className="text-xs text-zinc-400">{compileResult.explanation}</span>
          </div>

          {compileResult.missing_slots.length > 0 && (
            <Card className="border-amber-500/30">
              <CardContent className="p-3 flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
                <div>
                  <div className="text-xs font-medium text-amber-300">Slots faltantes</div>
                  <div className="text-xs text-zinc-400 mt-1">
                    {compileResult.missing_slots.join(", ")}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <details className="text-xs">
            <summary className="cursor-pointer text-blue-400 hover:underline">
              Workflow generado ({Object.keys(compileResult.workflow).length} keys)
            </summary>
            <pre className="mt-2 p-3 bg-zinc-950 border border-zinc-800 rounded-md max-h-64 overflow-auto font-mono text-[10px]">
              {JSON.stringify(compileResult.workflow, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  )

  const renderDryRun = () => (
    <div className="space-y-4">
      <div className="flex gap-3 items-start">
        <div className="flex-1 space-y-2">
          <label className="text-xs text-zinc-400">Texto a simular</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder='Ej: "Validar y aprobar facturas mayores a $50,000 MXN antes de enviarlas al SAT"'
            rows={4}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-md p-3 text-sm font-mono resize-y"
          />
        </div>
        <div className="space-y-2 w-24">
          <label className="text-xs text-zinc-400">Idioma</label>
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-2 text-sm"
          >
            <option value="es">ES</option>
            <option value="en">EN</option>
            <option value="pt">PT</option>
          </select>
        </div>
      </div>
      <Button onClick={handleDryRun} disabled={loading || !text.trim()}>
        {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FlaskConical className="h-4 w-4 mr-2" />}
        {loading ? "Simulando..." : "Ejecutar dry-run"}
      </Button>

      {dryRunResult && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Badge variant={dryRunResult.overall_feasible ? "default" : "destructive"}>
              {dryRunResult.overall_feasible ? "VIABLE" : "NO VIABLE"}
            </Badge>
            <span className="text-xs text-zinc-400">Workflow: {dryRunResult.workflow_name}</span>
            <Badge variant="outline" className="text-[10px]">{dryRunResult.trigger_type}</Badge>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Card>
              <CardContent className="p-3 text-center">
                <div className="text-lg font-bold text-zinc-200">{dryRunResult.total_steps}</div>
                <div className="text-[10px] text-zinc-500">Total pasos</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3 text-center">
                <div className="text-lg font-bold text-emerald-400">{dryRunResult.steps_that_would_succeed}</div>
                <div className="text-[10px] text-zinc-500">Éxito</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-3 text-center">
                <div className="text-lg font-bold text-red-400">{dryRunResult.steps_that_would_fail}</div>
                <div className="text-[10px] text-zinc-500">Fallarían</div>
              </CardContent>
            </Card>
          </div>

          <Card className="bg-zinc-900/50 border-zinc-700/50">
            <CardContent className="p-3">
              <div className="text-xs text-zinc-300 mb-1 font-medium">Resumen</div>
              <p className="text-xs text-zinc-400">{dryRunResult.summary}</p>
            </CardContent>
          </Card>

          {dryRunResult.warnings.length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-amber-400">Advertencias</div>
              {dryRunResult.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-amber-300/80 p-2 bg-amber-500/5 rounded border border-amber-500/20">
                  <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                  {w}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )

  const renderIntents = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-400">
          {intentsData ? `${intentsData.total} intenciones registradas` : "Cargando..."}
        </p>
        <Button variant="ghost" size="sm" onClick={loadIntents}>
          <RefreshCw className="h-3 w-3 mr-1" /> Recargar
        </Button>
      </div>

      {!intentsData ? (
        <Skeleton className="h-48 w-full" />
      ) : intentsData.intents.length === 0 ? (
        <EmptyState icon={<List className="h-8 w-8" />} title="Sin intenciones" description="No hay intenciones registradas en el sistema NLU." />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {intentsData.intents.map((intent) => (
            <div key={intent.name} className="p-3 rounded-md border border-zinc-700 bg-zinc-900/50">
              <div className="text-sm font-mono text-zinc-200 truncate">{intent.name}</div>
              <Badge variant="outline" className="text-[9px] mt-1">{intent.source}</Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  const renderEntities = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-400">
          {entitiesData ? `${entitiesData.total} tipos de entidades` : "Cargando..."}
        </p>
        <Button variant="ghost" size="sm" onClick={loadEntities}>
          <RefreshCw className="h-3 w-3 mr-1" /> Recargar
        </Button>
      </div>

      {!entitiesData ? (
        <Skeleton className="h-48 w-full" />
      ) : entitiesData.entities.length === 0 ? (
        <EmptyState icon={<Tags className="h-8 w-8" />} title="Sin entidades" description="No hay entidades configuradas." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {entitiesData.entities.map((entity) => (
            <Card key={entity.name}>
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="font-mono text-sm text-zinc-200">{entity.name}</div>
                  <div className="flex gap-1">
                    {entity.patterns.map((p) => (
                      <Badge key={p} variant="outline" className="text-[9px]">{p}</Badge>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-zinc-500 mt-1">{entity.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )

  const renderTraining = () => (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <BrainCircuit className="h-5 w-5 text-purple-400" />
            <h3 className="text-sm font-semibold">Entrenar el sistema de lenguaje</h3>
          </div>

          <div className="flex gap-3 items-end">
            <div className="space-y-1 w-32">
              <label className="text-xs text-zinc-400">Idioma</label>
              <select
                value={trainingLang}
                onChange={(e) => setTrainingLang(e.target.value)}
                className="w-full h-9 bg-zinc-900 border border-zinc-700 rounded-md px-2 text-sm"
              >
                <option value="es">Español</option>
                <option value="en">Inglés</option>
                <option value="pt">Portugués</option>
              </select>
            </div>
            <Button onClick={handleTrain} disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <BrainCircuit className="h-4 w-4 mr-2" />}
              {loading ? "Entrenando..." : "Entrenar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Activity className="h-4 w-4 text-blue-400" />
              Estado del entrenamiento
            </h3>
            <Button variant="ghost" size="sm" onClick={refreshTrainingStatus}>
              <RefreshCw className="h-3 w-3 mr-1" /> Refrescar
            </Button>
          </div>

          {!trainingStatus ? (
            <Skeleton className="h-20 w-full" />
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <Badge
                  variant={
                    trainingStatus.status === "completed" ? "default" :
                    trainingStatus.status === "failed" ? "destructive" :
                    trainingStatus.status === "training" ? "secondary" :
                    "outline"
                  }
                >
                  {trainingStatus.status}
                </Badge>
                {trainingStatus.status === "training" && (
                  <span className="text-xs text-zinc-400">
                    Progreso: {(trainingStatus.progress * 100).toFixed(0)}%
                  </span>
                )}
                {trainingStatus.job_id !== "none" && (
                  <span className="text-[10px] text-zinc-600">ID de entrenamiento: {trainingStatus.job_id.slice(0, 8)}...</span>
                )}
              </div>

              {trainingStatus.status === "training" && (
                <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-purple-500 rounded-full transition-all duration-500"
                    style={{ width: `${trainingStatus.progress * 100}%` }}
                  />
                </div>
              )}

              {trainingStatus.error_message && (
                <div className="flex items-start gap-2 text-xs text-red-300 p-2 bg-red-500/5 rounded border border-red-500/20">
                  <XCircle className="h-3 w-3 mt-0.5 shrink-0" />
                  {trainingStatus.error_message}
                </div>
              )}

              {trainingStatus.started_at && (
                <div className="text-[10px] text-zinc-500">
                  Iniciado: {new Date(trainingStatus.started_at).toLocaleString()}
                  {trainingStatus.completed_at && ` — Completado: ${new Date(trainingStatus.completed_at).toLocaleString()}`}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )

  const TAB_RENDERERS: Record<TabId, () => React.ReactNode> = {
    understand: renderUnderstand,
    compile: renderCompile,
    "dry-run": renderDryRun,
    intents: renderIntents,
    entities: renderEntities,
    training: renderTraining,
  }

  return (
    <div className="space-y-6 p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BrainCircuit className="h-7 w-7 text-purple-400" />
          NLU — Procesamiento de Lenguaje Natural
        </h1>
      <p className="text-sm text-zinc-400 mt-1">
        Analiza, genera y simula flujos de trabajo escribiendo como hablas.
        Del lenguaje natural a procesos listos para usar.
      </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-zinc-800 pb-px overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition-colors ${
                isActive
                  ? "border-purple-400 text-purple-300"
                  : "border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      {TAB_RENDERERS[activeTab]()}
    </div>
  )
}


