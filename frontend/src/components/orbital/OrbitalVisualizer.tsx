/**
 * OrbitalVisualizer — Visualizador en tiempo real del motor ORBITAL (Sprint 12).
 *
 * Renderiza en Canvas 2D (sin WebGL para mantener simplicidad y compatibilidad):
 * - Cada variable orbital es una partícula en órbita circular.
 *   - Posición angular = theta (0 a 2π).
 *   - Distancia al centro = inverso de amplitud (mayor amplitud → más cerca del centro).
 *   - Color del grupo orbital.
 * - Las líneas entre partículas representan TOR (Tensión Orbital Recíproca).
 *   - Grosor = magnitud de TOR.
 *   - Color verde = resonancia positiva (alineación).
 *   - Color rojo = anti-resonancia.
 * - El COD (Colapso Orbital Determinista) se muestra como un punto pulsante en el centro.
 * - Auto-refresh cada 1s desde /api/orbital/status.
 *
 * Sprint 12: este visualizador es el showcase del diferenciador competitivo ORBITAL.
 */
import { useEffect, useRef, useState, useCallback } from "react"
import { Activity, Pause, Play, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { toast } from "@/components/ui/toast"
import { apiFetch } from "@/hooks/useApi"

// ─── Tipos ──────────────────────────────────────────────────────────────

interface OrbitalVariable {
  theta: number
  amplitude: number
  velocity: number
  value: number
  orbit_group: string
}

interface TorResult {
  variable_i: string
  variable_j: string
  tor_value: number
  alignment: number
}

interface OrbitalStatus {
  variables: Record<string, OrbitalVariable>
  tor_results?: TorResult[]
  tor_cache?: {
    hits: number
    misses: number
    cache_size: number
    hit_rate: number
  }
  cod?: {
    converged?: boolean
    iterations?: number
    [key: string]: unknown
  }
}

// ─── Constantes de visualización ────────────────────────────────────────

const POLL_INTERVAL_MS = 1000
const CANVAS_SIZE = 480
const CENTER_X = CANVAS_SIZE / 2
const CENTER_Y = CANVAS_SIZE / 2
const MIN_RADIUS = 60
const MAX_RADIUS = 200

// Colores por grupo orbital (paleta de 8 colores, cicla si hay más grupos)
const ORBIT_GROUP_COLORS = [
  "#6366f1", // indigo
  "#22c55e", // green
  "#f59e0b", // amber
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#a855f7", // purple
  "#ef4444", // red
  "#3b82f6", // blue
]

function colorForGroup(_group: string, index: number): string {
  const colorIndex = index % ORBIT_GROUP_COLORS.length
  return ORBIT_GROUP_COLORS[colorIndex]
}

// ─── Componente ─────────────────────────────────────────────────────────

interface OrbitalVisualizerProps {
  /** Tamaño del canvas en píxeles. Default: 480. */
  size?: number
}

export function OrbitalVisualizer({ size = CANVAS_SIZE }: OrbitalVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [status, setStatus] = useState<OrbitalStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [playing, setPlaying] = useState(true)
  const [tickCount, setTickCount] = useState(0)

  const loadStatus = useCallback(async () => {
    try {
      const resp = await apiFetch<OrbitalStatus>("/api/orbital/status")
      if (resp) {
        setStatus(resp)
      }
    } catch (e) {
      console.error("OrbitalVisualizer: error loading status", e)
    } finally {
      setLoading(false)
    }
  }, [])

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    loadStatus()
    if (!playing) return
    const interval = setInterval(() => {
      loadStatus()
      setTickCount((t) => t + 1)
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [loadStatus, playing])
  /* eslint-enable react-hooks/set-state-in-effect */

  // Redibuja el canvas cuando cambia el status o tickCount.
  // Este effect no llama a setState, solo dibuja en el canvas (efecto secundario puro).
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Limpiar canvas
    ctx.fillStyle = "#0a0a0f"
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Círculos concéntricos guía
    ctx.strokeStyle = "rgba(99, 102, 241, 0.08)"
    ctx.lineWidth = 1
    for (let r = MIN_RADIUS; r <= MAX_RADIUS; r += 35) {
      ctx.beginPath()
      ctx.arc(CENTER_X, CENTER_Y, r, 0, Math.PI * 2)
      ctx.stroke()
    }

    // Ejes guía
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)"
    ctx.beginPath()
    ctx.moveTo(CENTER_X - MAX_RADIUS, CENTER_Y)
    ctx.lineTo(CENTER_X + MAX_RADIUS, CENTER_Y)
    ctx.moveTo(CENTER_X, CENTER_Y - MAX_RADIUS)
    ctx.lineTo(CENTER_X, CENTER_Y + MAX_RADIUS)
    ctx.stroke()

    if (!status || !status.variables || Object.keys(status.variables).length === 0) {
      ctx.fillStyle = "rgba(255, 255, 255, 0.4)"
      ctx.font = "14px sans-serif"
      ctx.textAlign = "center"
      ctx.fillText("Sin variables orbitales", CENTER_X, CENTER_Y - 10)
      ctx.font = "11px sans-serif"
      ctx.fillText("Crea una variable o ejecuta un workflow", CENTER_X, CENTER_Y + 10)
      return
    }

    // Posiciones de cada variable
    const varEntries = Object.entries(status.variables)
    const positions: Record<string, { x: number; y: number; color: string }> = {}

    varEntries.forEach(([name, v], index) => {
      const amplitudeNormalized = Math.min(Math.max(v.amplitude, 0.1), 10)
      const radius = MAX_RADIUS - (amplitudeNormalized / 10) * (MAX_RADIUS - MIN_RADIUS)
      const theta = v.theta % (Math.PI * 2)
      const x = CENTER_X + radius * Math.cos(theta)
      const y = CENTER_Y + radius * Math.sin(theta)
      positions[name] = {
        x,
        y,
        color: colorForGroup(v.orbit_group || "default", index),
      }
    })

    // Líneas TOR
    if (status.tor_results && status.tor_results.length > 0) {
      status.tor_results.forEach((tor) => {
        const posI = positions[tor.variable_i]
        const posJ = positions[tor.variable_j]
        if (!posI || !posJ) return

        const torValue = tor.tor_value
        const absTor = Math.abs(torValue)
        const lineWidth = Math.min(Math.max(absTor * 2, 0.5), 4)

        if (torValue > 0) {
          ctx.strokeStyle = `rgba(34, 197, 94, ${Math.min(absTor / 10, 0.7)})`
        } else {
          ctx.strokeStyle = `rgba(239, 68, 68, ${Math.min(absTor / 10, 0.7)})`
        }
        ctx.lineWidth = lineWidth
        ctx.beginPath()
        ctx.moveTo(posI.x, posI.y)
        ctx.lineTo(posJ.x, posJ.y)
        ctx.stroke()
      })
    }

    // COD en el centro (punto pulsante)
    const codConverged = status.cod?.converged ?? true
    const codPulse = 1 + 0.2 * Math.sin(tickCount * 0.3)
    const codRadius = 8 * codPulse
    const codGradient = ctx.createRadialGradient(
      CENTER_X, CENTER_Y, 0,
      CENTER_X, CENTER_Y, codRadius * 2
    )
    if (codConverged) {
      codGradient.addColorStop(0, "rgba(99, 102, 241, 0.8)")
      codGradient.addColorStop(1, "rgba(99, 102, 241, 0)")
    } else {
      codGradient.addColorStop(0, "rgba(239, 68, 68, 0.8)")
      codGradient.addColorStop(1, "rgba(239, 68, 68, 0)")
    }
    ctx.fillStyle = codGradient
    ctx.beginPath()
    ctx.arc(CENTER_X, CENTER_Y, codRadius * 2, 0, Math.PI * 2)
    ctx.fill()

    ctx.fillStyle = codConverged ? "#6366f1" : "#ef4444"
    ctx.beginPath()
    ctx.arc(CENTER_X, CENTER_Y, codRadius, 0, Math.PI * 2)
    ctx.fill()

    // Variables como partículas
    Object.entries(positions).forEach(([name, pos]) => {
      const haloGradient = ctx.createRadialGradient(
        pos.x, pos.y, 0,
        pos.x, pos.y, 12
      )
      haloGradient.addColorStop(0, pos.color + "aa")
      haloGradient.addColorStop(1, pos.color + "00")
      ctx.fillStyle = haloGradient
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, 12, 0, Math.PI * 2)
      ctx.fill()

      ctx.fillStyle = pos.color
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, 5, 0, Math.PI * 2)
      ctx.fill()

      if (varEntries.length <= 12) {
        ctx.fillStyle = "rgba(255, 255, 255, 0.7)"
        ctx.font = "10px monospace"
        ctx.textAlign = "center"
        const label = name.length > 15 ? name.slice(0, 13) + "…" : name
        ctx.fillText(label, pos.x, pos.y - 12)
      }
    })

    ctx.fillStyle = "rgba(255, 255, 255, 0.6)"
    ctx.font = "9px monospace"
    ctx.textAlign = "center"
    ctx.fillText("COD", CENTER_X, CENTER_Y + codRadius + 14)
  }, [status, tickCount])

  const handleManualTick = async () => {
    try {
      await apiFetch("/api/orbital/tick", { method: "POST" })
      await loadStatus()
      toast({
        title: "Tick ejecutado",
        description: "El motor ORBITAL avanzó un paso",
        variant: "success",
      })
    } catch (e) {
      toast({
        title: "Error en tick",
        description: e instanceof Error ? e.message : "Intenta de nuevo",
        variant: "error",
      })
    }
  }

  const varCount = status?.variables ? Object.keys(status.variables).length : 0
  const torCount = status?.tor_results?.length ?? 0
  const torHitRate = status?.tor_cache?.hit_rate ?? 0
  const codConverged = status?.cod?.converged ?? true
  const codIterations = status?.cod?.iterations ?? 0

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="size-5 text-indigo-400" />
            <h3 className="font-semibold">Visualizador ORBITAL en tiempo real</h3>
            {loading ? (
              <Badge variant="outline" className="bg-muted">cargando…</Badge>
            ) : playing ? (
              <Badge variant="outline" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                ● live
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/20">
                ⏸ pausado
              </Badge>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPlaying((p) => !p)}
            >
              {playing ? <Pause className="size-3" /> : <Play className="size-3" />}
              {playing ? "Pausar" : "Reproducir"}
            </Button>
            <Button size="sm" variant="outline" onClick={handleManualTick}>
              <RefreshCw className="size-3" />
              Tick
            </Button>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-4">
          <canvas
            ref={canvasRef}
            width={CANVAS_SIZE}
            height={CANVAS_SIZE}
            style={{ width: size, height: size, maxWidth: "100%" }}
            className="rounded-lg border border-zinc-800 bg-zinc-950"
          />

          <div className="flex-1 space-y-3 min-w-0">
            <div className="grid grid-cols-2 gap-2">
              <MetricBox label="Variables" value={varCount} color="text-indigo-400" />
              <MetricBox label="Conexiones TOR" value={torCount} color="text-emerald-400" />
              <MetricBox
                label="TOR cache hit"
                value={`${Math.round(torHitRate * 100)}%`}
                color={torHitRate > 0.9 ? "text-emerald-400" : "text-amber-400"}
              />
              <MetricBox
                label="COD"
                value={codConverged ? "✓ convergido" : "⚠ oscilando"}
                color={codConverged ? "text-emerald-400" : "text-red-400"}
              />
              <MetricBox label="COD iteraciones" value={codIterations} color="text-muted-foreground" />
              <MetricBox label="Ticks" value={tickCount} color="text-muted-foreground" />
            </div>

            <div className="text-xs text-muted-foreground space-y-1">
              <p><span className="text-indigo-400">●</span> Variables orbitales (color por grupo)</p>
              <p><span className="text-emerald-400">──</span> Resonancia positiva (TOR &gt; 0)</p>
              <p><span className="text-red-400">──</span> Anti-resonancia (TOR &lt; 0)</p>
              <p><span className="text-indigo-400">◉</span> COD (Colapso Orbital Determinista)</p>
              <p className="pt-2 italic">
                Mayor amplitud → partícula más cerca del centro (mayor energía).
                Grosor de líneas = magnitud de TOR.
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function MetricBox({
  label,
  value,
  color,
}: {
  label: string
  value: number | string
  color: string
}) {
  return (
    <div className="rounded-md border bg-muted/30 p-2">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={`text-lg font-mono font-bold ${color}`}>{value}</div>
    </div>
  )
}
