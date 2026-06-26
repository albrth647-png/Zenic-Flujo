import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useApi } from "@/hooks/useApi"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { error as humanError } from "@/utils/humanize"
import { Bot, Sparkles, Send, Loader2, Lightbulb, FileText, Workflow, CheckCircle2 } from "lucide-react"

type Message = {
  id: string
  role: "user" | "assistant"
  content: string
  mode?: string
  source?: string
  workflow?: Record<string, unknown>
  steps?: Array<{ id: string; tool: string; action: string; ok: boolean }>
  confidence?: number
  warnings?: string[]
  suggestions?: Array<{
    template_name: string
    confidence: number
    description: string
    trigger: string
    steps: number
  }>
}

export default function ChatPage() {
  const navigate = useNavigate()
  const { getApi } = useApi()
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "¡Hola! Soy tu asistente de automatización. Puedes contarme qué necesitas automatizar y yo lo armaré por ti.\n\n**Por ejemplo:**\n• *\"Cada vez que llegue un correo de Gmail, crear una tarea en Asana\"*\n• *\"Enviar un reporte semanal por correo\"*\n• *Cuando un cliente pague, enviarle un mensaje de WhatsApp\"*",
    },
  ])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState<"chat" | "analyze" | "generate">("chat")
  const [aiProvider, setAiProvider] = useState<string>("")
  const [suggestionsVisible, setSuggestionsVisible] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    setInput("")
    setSuggestionsVisible(false)

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const api = getApi()

      if (mode === "chat") {
        // M10: HATRouter (5 niveles) → /api/workflows/chat
        const res = await api.post("/api/workflows/chat", { message: text })
        const data = res as {
          dispatch_id?: string
          domain?: string
          response?: string
          status?: string
          orbital_resonance?: number
          anti_dup_layer_hit?: string
          duration_ms?: number
        }
        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: data.response || data.status || "No pude procesar tu solicitud.",
          mode: "chat",
        }
        setMessages((prev) => [...prev, assistantMsg])
      } else if (mode === "analyze") {
        // Modo "Analizar" → /api/nlu/understand
        const res = await api.post("/api/nlu/understand", { text, mode: "analyze" })
        const data = res as {
          status: string
          lang: string
          confidence: number
          intents?: Array<{ intent: string; score: number; evidence?: string[] }>
          entities?: Array<{ type: string; value: string }>
          slots?: Array<{ name: string; required: boolean; filled: boolean }>
          trace?: string[]
        }
        const intentInfo =
          data.intents
            ?.map((i) => `• **${i.intent}** — ${Math.round(i.score * 100)}% de coincidencia`)
            .join("\n") || "No se detectaron intenciones claras"
        const entityInfo =
          data.entities
            ?.map((e) => `• ${e.type}: **${e.value}**`)
            .join("\n") || "No se detectaron datos específicos"

        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: `## Lo que entendí de tu solicitud\n\n**Idioma:** ${data.lang === "es" ? "Español" : "Inglés"}\n**Confianza:** ${Math.round((data.confidence || 0) * 100)}%\n\n### Intenciones detectadas\n${intentInfo}\n\n### Datos que encontré\n${entityInfo}`,
          mode: "analyze",
          confidence: data.confidence,
        }
        setMessages((prev) => [...prev, assistantMsg])
      } else {
        // Modo "Generar" → /api/nlu/ai-generate
        const res = await api.post("/api/nlu/ai-generate", { text, mode: "hybrid" })
        const data = res as {
          status: string
          source: string
          explanation?: string
          workflow?: Record<string, unknown>
          ai_provider?: string
          ai_model?: string
          validated?: boolean
          validation_errors?: string[]
          missing_slots?: string[]
          error?: string
        }

        if (data.error) {
          setMessages((prev) => [
            ...prev,
            {
              id: `assistant-${Date.now()}`,
              role: "assistant",
              // data.error es string | undefined; ya validamos que existe con el if,
              // pero TS no lo infiere dentro del callback. Usamos ?? para garantizar string.
              content: data.error ?? "Error desconocido al generar el workflow",
              mode: "generate",
            },
          ])
          return
        }

        const sourceLabel =
          data.source === "ai" || data.source === "ai_fallback"
            ? `Generado con ${data.ai_provider || "IA"}`
            : data.source === "deterministic"
              ? "Generado con el motor determinista"
              : ""

        const stepsCount = data.workflow
          ? Object.keys(data.workflow).length
          : 0

        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: [
            data.explanation ? `## Resultado\n\n${data.explanation}` : "",
            sourceLabel ? `\n\n*${sourceLabel}*` : "",
            data.validated === false
              ? `\n\n⚠️ **Advertencias:** ${(data.validation_errors || []).join(", ")}`
              : "",
            data.missing_slots?.length
              ? `\n\n📋 **Información faltante:** ${data.missing_slots.join(", ")}`
              : "",
            data.workflow && stepsCount > 0
              ? `\n\n✅ **Workflow listo** — ${stepsCount} paso${stepsCount !== 1 ? "s" : ""}`
              : "",
          ]
            .filter(Boolean)
            .join(""),
          mode: "generate",
          source: data.source,
          workflow: data.workflow,
        }
        setMessages((prev) => [...prev, assistantMsg])
        setAiProvider(data.ai_provider || "")
      }
    } catch (err: unknown) {
      const errorMsg = humanError(err)
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          content: `❌ **Error:** ${errorMsg}`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function getModeIcon() {
    switch (mode) {
      case "chat":
        return <Lightbulb className="h-4 w-4" />
      case "analyze":
        return <FileText className="h-4 w-4" />
      case "generate":
        return <Sparkles className="h-4 w-4" />
    }
  }

  function getModeLabel() {
    switch (mode) {
      case "chat":
        return "Sugerencias"
      case "analyze":
        return "Analizar"
      case "generate":
        return "Generar con IA"
    }
  }

  function getModeDescription() {
    switch (mode) {
      case "chat":
        return "Cuéntame qué necesitas y te sugeriré workflows listos para usar"
      case "analyze":
        return "Analizo tu solicitud y te muestro exactamente lo que entendí"
      case "generate":
        return "Uso IA para crear un workflow completo desde tu descripción"
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Encabezado */}
      <div className="mb-4">
        <h1 className="text-2xl font-semibold text-zinc-100">Asistente Inteligente</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Describe lo que necesitas automatizar y yo lo armo por ti
        </p>
      </div>

      {/* Selector de modo */}
      <Card className="mb-4 border-zinc-800 bg-zinc-900/50">
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
                {getModeIcon()}
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-200">{getModeLabel()}</p>
                <p className="text-xs text-zinc-500">{getModeDescription()}</p>
              </div>
            </div>
            <Select value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
              <SelectTrigger className="w-[180px] border-zinc-700 bg-zinc-800 text-zinc-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="border-zinc-700 bg-zinc-800 text-zinc-200">
                <SelectItem value="chat">
                  <span className="flex items-center gap-2">
                    <Lightbulb className="h-4 w-4 text-amber-400" />
                    Sugerencias
                  </span>
                </SelectItem>
                <SelectItem value="analyze">
                  <span className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-blue-400" />
                    Analizar
                  </span>
                </SelectItem>
                <SelectItem value="generate">
                  <span className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-purple-400" />
                    Generar con IA
                  </span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Mensajes */}
      <Card className="flex-1 border-zinc-800 bg-zinc-900/50">
        <ScrollArea ref={scrollRef} className="h-full max-h-[550px] p-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`mb-4 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-zinc-800 text-zinc-200"
                }`}
              >
                {/* Encabezado del mensaje */}
                <div className="mb-2 flex items-center gap-2">
                  {msg.role === "assistant" && (
                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-700">
                      <Bot className="h-3.5 w-3.5 text-indigo-400" />
                    </div>
                  )}
                  <span className="text-xs font-medium opacity-70">
                    {msg.role === "user" ? "Tú" : "Asistente"}
                  </span>
                  {msg.mode && msg.role === "assistant" && (
                    <Badge
                      variant="secondary"
                      className="border-0 bg-zinc-700/50 text-[10px] text-zinc-400"
                    >
                      {msg.mode === "chat"
                        ? "Sugerencias"
                        : msg.mode === "analyze"
                          ? "Análisis"
                          : "Generación"}
                    </Badge>
                  )}
                  {msg.source === "ai" || msg.source === "ai_fallback" ? (
                    <Badge
                      variant="secondary"
                      className="border-0 bg-purple-500/10 text-[10px] text-purple-400"
                    >
                      <Sparkles className="mr-0.5 h-3 w-3" />
                      IA
                    </Badge>
                  ) : msg.source === "deterministic" ? (
                    <Badge
                      variant="secondary"
                      className="border-0 bg-emerald-500/10 text-[10px] text-emerald-400"
                    >
                      <CheckCircle2 className="mr-0.5 h-3 w-3" />
                      Determinista
                    </Badge>
                  ) : null}
                </div>

                {/* Contenido del mensaje */}
                <div className="whitespace-pre-wrap text-sm leading-relaxed">
                  {msg.content}
                </div>

                {/* Sugerencias (modo chat) */}
                {msg.suggestions && msg.suggestions.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {msg.suggestions.map((s, i) => (
                      <div
                        key={i}
                        className="rounded-lg border border-zinc-700/50 bg-zinc-800/50 p-3 transition-colors hover:border-zinc-600"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-medium text-zinc-200">
                              {s.description || s.template_name}
                            </p>
                            <p className="mt-0.5 text-xs text-zinc-500">
                              {s.trigger === "manual"
                                ? "Manual"
                                : s.trigger === "event"
                                  ? "Por evento"
                                  : s.trigger === "webhook"
                                    ? "Webhook"
                                    : s.trigger === "schedule"
                                      ? "Programado"
                                      : s.trigger}{" "}
                              · {s.steps} paso{s.steps !== 1 ? "s" : ""}
                            </p>
                          </div>
                          <Badge
                            className={`shrink-0 border-0 ${
                              s.confidence > 0.7
                                ? "bg-emerald-500/10 text-emerald-400"
                                : s.confidence > 0.4
                                  ? "bg-amber-500/10 text-amber-400"
                                  : "bg-zinc-700/50 text-zinc-400"
                            }`}
                          >
                            {Math.round(s.confidence * 100)}%
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Workflow generado (modo generate) */}
                {msg.workflow && Object.keys(msg.workflow).length > 0 && (
                  <div className="mt-3">
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-emerald-700 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                      onClick={() =>
                        navigate("/app/editor", { state: { importWorkflow: msg.workflow } })
                      }
                    >
                      <Workflow className="mr-1.5 h-3.5 w-3.5" />
                      Abrir en el Editor
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="mb-4 flex justify-start">
              <div className="max-w-[85%] rounded-2xl bg-zinc-800 px-4 py-3">
                <div className="mb-2 flex items-center gap-2">
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-700">
                    <Bot className="h-3.5 w-3.5 text-indigo-400" />
                  </div>
                  <span className="text-xs font-medium text-zinc-400">Asistente</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-zinc-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {mode === "chat"
                    ? "Buscando sugerencias…"
                    : mode === "analyze"
                      ? "Analizando tu solicitud…"
                      : "Generando tu workflow…"}
                </div>
              </div>
            </div>
          )}
        </ScrollArea>

        {/* Área de entrada */}
        <div className="border-t border-zinc-800 p-4">
          <div className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                mode === "chat"
                  ? "Describe qué necesitas automatizar…"
                  : mode === "analyze"
                    ? "Escribe una solicitud para analizar…"
                    : "Describe el workflow que quieres crear…"
              }
              className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              disabled={loading}
            />
            <Button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              aria-label={loading ? "Enviando solicitud" : "Enviar solicitud"}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          {aiProvider && (
            <p className="mt-2 text-[10px] text-zinc-600">
              Proveedor de IA activo: {aiProvider}
            </p>
          )}
        </div>
      </Card>

      {/* Sugerencias iniciales */}
      {suggestionsVisible && messages.length === 1 && (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            {
              icon: <Bot className="h-5 w-5" />,
              title: "Sugerencias",
              desc: "Cuéntame qué necesitas y te recomendaré la mejor opción",
              example: "\"Quiero enviar un correo cuando llegue un pago\"",
              mode: "chat" as const,
            },
            {
              icon: <FileText className="h-5 w-5" />,
              title: "Analizar",
              desc: "Veo qué tan clara es tu solicitud y qué información puedo extraer",
              example: "\"Cada lunes a las 9am, respaldar la base de datos\"",
              mode: "analyze" as const,
            },
            {
              icon: <Sparkles className="h-5 w-5" />,
              title: "Generar con IA",
              desc: "Uso inteligencia artificial para crear workflows complejos",
              example: "\"Cuando un cliente nuevo se registre, enviarle un correo de bienvenida y crear una tarea en el CRM\"",
              mode: "generate" as const,
            },
          ].map((item) => (
            <button
              key={item.mode}
              onClick={() => {
                setMode(item.mode)
                setInput(item.example)
              }}
              className="group rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-left transition-all hover:border-zinc-700 hover:bg-zinc-800/50"
            >
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400 transition-colors group-hover:bg-indigo-500/20">
                {item.icon}
              </div>
              <h3 className="mb-1 text-sm font-medium text-zinc-200">{item.title}</h3>
              <p className="mb-2 text-xs text-zinc-500">{item.desc}</p>
              <code className="text-[11px] text-zinc-600">{item.example}</code>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
