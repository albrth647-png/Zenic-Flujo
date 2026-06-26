import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import { toast } from "@/components/ui/toast"
import { error as humanError } from "@/utils/humanize"
import {
  Search,
  Download,
  Trash2,
  CheckCircle2,
  RefreshCw,
  Loader2,
  Package,
  Plug,
  Star,
  Info,
  Grid3x3,
  Layers,
} from "lucide-react"

// ── Tipos locales (específicos del marketplace) ──

type Connector = {
  name: string
  version: string
  description: string
  category: string
  icon: string
  author: string
  rating: number
  installed: boolean
}

type Category = {
  name: string
  count: number
  icon: string
}

type ConnectorDetail = Connector & {
  class_name?: string
  module?: string
  actions?: string[]
  status?: {
    connected: boolean
    healthy: boolean
    circuit_breaker?: Record<string, unknown>
  }
  config?: Record<string, unknown>
}

const CATEGORY_LABELS: Record<string, string> = {
  ai: "Inteligencia Artificial",
  communication: "Comunicación",
  crm: "CRM",
  database: "Base de datos",
  devops: "DevOps",
  finance: "Finanzas",
  messaging: "Mensajería",
  monitoring: "Monitoreo",
  productivity: "Productividad",
  storage: "Almacenamiento",
  social: "Redes sociales",
  general: "General",
}

const CATEGORY_ICONS: Record<string, string> = {
  ai: "🧠", communication: "📧", crm: "👥", database: "🗄️",
  devops: "🔧", finance: "💰", messaging: "💬", monitoring: "📊",
  productivity: "⚡", storage: "💾", social: "🔗", general: "🔌",
}

// ── Componente principal ───────────────────────

export default function Plugins() {
  const { getApi } = useApi()
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [installing, setInstalling] = useState<string | null>(null)
  const [detailConnector, setDetailConnector] = useState<ConnectorDetail | null>(null)
  const [showDetail, setShowDetail] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)

  const loadData = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const [connRes, catRes] = await Promise.all([
        api.get("/api/marketplace/connectors", { signal }),
        api.get("/api/marketplace/categories", { signal }),
      ])
      if (signal?.aborted) return
      const c = connRes as { connectors: Connector[] }
      if (c?.connectors) setConnectors(c.connectors)
      if (catRes) setCategories(catRes as Category[])
    } catch (e) {
      // AbortError: el componente se desmontó, no mostramos toast (BUG-2-FE).
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar extensiones", description: humanError(e), variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(ac.signal)
    return () => ac.abort()
  }, [loadData])

  const filtered = connectors.filter((c) => {
    const matchesSearch =
      !searchQuery ||
      c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = !selectedCategory || c.category === selectedCategory
    return matchesSearch && matchesCategory
  })

  const installedCount = connectors.filter((c) => c.installed).length

  async function handleInstall(name: string) {
    setInstalling(name)
    try {
      const api = getApi()
      const res = await api.post(`/api/marketplace/connectors/${name}/install`)
      const r = res as { status: string; message: string }
      if (r?.status === "installed" || r?.status === "already_installed") {
        toast({ title: `✅ ${name} instalado`, variant: "success" })
        loadData()
      } else {
        toast({ title: `No se pudo instalar ${name}`, variant: "error" })
      }
    } catch (e) {
      toast({ title: `Error al instalar ${name}`, description: humanError(e), variant: "error" })
    } finally {
      setInstalling(null)
    }
  }

  async function handleUninstall(name: string) {
    if (!confirm(`¿Desinstalar "${name}"? Los workflows que lo usen dejarán de funcionar.`)) return
    try {
      const api = getApi()
      await api.post(`/api/marketplace/connectors/${name}/uninstall`)
      toast({ title: `❌ ${name} desinstalado`, variant: "success" })
      loadData()
    } catch (e) {
      toast({ title: `Error al desinstalar ${name}`, description: humanError(e), variant: "error" })
    }
  }

  async function openDetail(name: string) {
    setDetailLoading(true)
    setShowDetail(true)
    try {
      const api = getApi()
      const res = await api.get(`/api/marketplace/connectors/${name}`)
      setDetailConnector(res as ConnectorDetail)
    } catch (e) {
      toast({ title: "Error al cargar detalles", description: humanError(e), variant: "error" })
      setShowDetail(false)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Extensiones</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Explora, instala y gestiona conectores para extender lo que puede hacer tu plataforma
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadData()}
          disabled={loading}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Recargar
        </Button>
      </div>

      {/* Resumen */}
      <div className="flex items-center gap-4 text-sm text-zinc-400">
        <span className="flex items-center gap-1.5">
          <Package className="h-4 w-4 text-indigo-400" />
          <strong className="text-zinc-200">{connectors.length}</strong> conectores disponibles
        </span>
        <span className="flex items-center gap-1.5">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <strong className="text-zinc-200">{installedCount}</strong> instalado{installedCount !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Búsqueda y categorías */}
      <Card className="border-zinc-800 bg-zinc-900/50">
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar conector por nombre o descripción…"
                className="border-zinc-700 bg-zinc-800 pl-9 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Badge
                variant={selectedCategory === null ? "default" : "outline"}
                className={`cursor-pointer whitespace-nowrap ${
                  selectedCategory === null
                    ? "bg-indigo-600 text-white"
                    : "border-zinc-700 text-zinc-400 hover:text-zinc-200"
                }`}
                onClick={() => setSelectedCategory(null)}
              >
                <Grid3x3 className="mr-1 h-3 w-3" />
                Todos
              </Badge>
              {categories.map((cat) => (
                <Badge
                  key={cat.name}
                  variant={selectedCategory === cat.name ? "default" : "outline"}
                  className={`cursor-pointer whitespace-nowrap ${
                    selectedCategory === cat.name
                      ? "bg-indigo-600 text-white"
                      : "border-zinc-700 text-zinc-400 hover:text-zinc-200"
                  }`}
                  onClick={() =>
                    setSelectedCategory(selectedCategory === cat.name ? null : cat.name)
                  }
                >
                  {CATEGORY_ICONS[cat.name] || "🔌"} {cat.name} ({cat.count})
                </Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Grid de conectores */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i} className="border-zinc-800 bg-zinc-900/50">
              <CardContent className="p-5">
                <Skeleton className="h-5 w-32 bg-zinc-800" />
                <Skeleton className="mt-2 h-3 w-full bg-zinc-800" />
                <Skeleton className="mt-1 h-3 w-3/4 bg-zinc-800" />
                <Skeleton className="mt-4 h-8 w-24 bg-zinc-800" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-12">
            <EmptyState
              icon={<Plug className="h-12 w-12 text-zinc-600" />}
              title={
                searchQuery
                  ? `No encontramos nada para "${searchQuery}"`
                  : "No hay conectores disponibles"
              }
              description={
                searchQuery
                  ? "Prueba con otro término o explora todas las categorías."
                  : "El marketplace no tiene conectores registrados aún."
              }
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((connector) => (
            <Card
              key={connector.name}
              className={`border-zinc-800 bg-zinc-900/50 transition-all duration-200 hover:border-zinc-700 ${
                connector.installed ? "ring-1 ring-emerald-500/20" : ""
              }`}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/10 text-lg">
                      {CATEGORY_ICONS[connector.category] || "🔌"}
                    </div>
                    <div>
                      <CardTitle className="text-sm font-semibold text-zinc-200 capitalize">
                        {connector.name.replace(/_/g, " ")}
                      </CardTitle>
                      <p className="text-[10px] text-zinc-500">
                        v{connector.version}
                        {connector.author ? ` · ${connector.author}` : ""}
                      </p>
                    </div>
                  </div>
                  {connector.installed && (
                    <Badge className="border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-400">
                      <CheckCircle2 className="mr-0.5 h-3 w-3" />
                      Instalado
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <p className="mb-3 min-h-[2.5em] text-xs leading-relaxed text-zinc-400 line-clamp-2">
                  {connector.description || "Sin descripción"}
                </p>

                <div className="flex items-center gap-1.5">
                  <Badge
                    variant="outline"
                    className="border-zinc-700/50 bg-zinc-800/50 text-[10px] text-zinc-500"
                  >
                    {CATEGORY_ICONS[connector.category] || "🔌"}{" "}
                    {CATEGORY_LABELS[connector.category] || connector.category}
                  </Badge>

                  {connector.rating > 0 && (
                    <div className="flex items-center gap-0.5 text-[10px] text-amber-400">
                      <Star className="h-3 w-3 fill-amber-400" />
                      {connector.rating.toFixed(1)}
                    </div>
                  )}
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => openDetail(connector.name)}
                    className="h-8 text-xs text-zinc-400 hover:text-zinc-200"
                  >
                    <Info className="mr-1 h-3.5 w-3.5" />
                    Detalles
                  </Button>
                  <div className="flex-1" />
                  {connector.installed ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleUninstall(connector.name)}
                      className="h-8 border-zinc-700 text-xs text-zinc-300 hover:border-red-500/30 hover:text-red-400"
                    >
                      <Trash2 className="mr-1 h-3.5 w-3.5" />
                      Desinstalar
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() => handleInstall(connector.name)}
                      disabled={installing === connector.name}
                      className="h-8 bg-indigo-600 text-xs text-white hover:bg-indigo-500"
                    >
                      {installing === connector.name ? (
                        <>
                          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                          Instalando…
                        </>
                      ) : (
                        <>
                          <Download className="mr-1 h-3.5 w-3.5" />
                          Instalar
                        </>
                      )}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Diálogo de detalle */}
      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="max-w-lg border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {detailConnector && (
                <>
                  <span className="text-lg">
                    {CATEGORY_ICONS[detailConnector.category] || "🔌"}
                  </span>
                  <span className="capitalize">
                    {detailConnector.name.replace(/_/g, " ")}
                  </span>
                </>
              )}
            </DialogTitle>
            <DialogDescription className="text-zinc-400">
              {detailConnector?.description || "Información del conector"}
            </DialogDescription>
          </DialogHeader>

          {detailLoading ? (
            <div className="space-y-3 py-4">
              <Skeleton className="h-4 w-full bg-zinc-800" />
              <Skeleton className="h-4 w-3/4 bg-zinc-800" />
              <Skeleton className="h-4 w-1/2 bg-zinc-800" />
            </div>
          ) : detailConnector ? (
            <div className="space-y-4">
              {/* Versión, autor, categoría */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-zinc-800/30 p-3">
                  <p className="text-[10px] text-zinc-500">Versión</p>
                  <p className="text-sm font-medium text-zinc-200">v{detailConnector.version}</p>
                </div>
                <div className="rounded-lg bg-zinc-800/30 p-3">
                  <p className="text-[10px] text-zinc-500">Autor</p>
                  <p className="text-sm font-medium text-zinc-200">
                    {detailConnector.author || "Desconocido"}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-800/30 p-3">
                  <p className="text-[10px] text-zinc-500">Categoría</p>
                  <p className="text-sm font-medium text-zinc-200">
                    {CATEGORY_LABELS[detailConnector.category] || detailConnector.category}
                  </p>
                </div>
                <div className="rounded-lg bg-zinc-800/30 p-3">
                  <p className="text-[10px] text-zinc-500">Calificación</p>
                  <p className="text-sm font-medium text-zinc-200">
                    {detailConnector.rating > 0
                      ? `⭐ ${detailConnector.rating.toFixed(1)} / 5`
                      : "Sin calificar"}
                  </p>
                </div>
              </div>

              {/* Estado de conexión */}
              {detailConnector.status && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-800/20 p-3">
                  <p className="mb-2 text-xs font-medium text-zinc-400">Estado</p>
                  <div className="flex gap-3">
                    <span className="flex items-center gap-1.5 text-xs">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          detailConnector.status.connected ? "bg-emerald-400" : "bg-zinc-600"
                        }`}
                      />
                      {detailConnector.status.connected ? "Conectado" : "Desconectado"}
                    </span>
                    <span className="flex items-center gap-1.5 text-xs">
                      <span
                        className={`h-2 w-2 rounded-full ${
                          detailConnector.status.healthy ? "bg-emerald-400" : "bg-red-400"
                        }`}
                      />
                      {detailConnector.status.healthy ? "Saludable" : "Problemas"}
                    </span>
                    <span className="flex items-center gap-1.5 text-xs">
                      {detailConnector.installed ? (
                        <Badge className="border-emerald-500/20 bg-emerald-500/10 text-[10px] text-emerald-400">
                          <CheckCircle2 className="mr-0.5 h-3 w-3" />
                          Instalado
                        </Badge>
                      ) : (
                        <Badge
                          variant="outline"
                          className="border-zinc-700 text-[10px] text-zinc-400"
                        >
                          No instalado
                        </Badge>
                      )}
                    </span>
                  </div>
                </div>
              )}

              {/* Acciones disponibles */}
              {detailConnector.actions && detailConnector.actions.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-medium text-zinc-400">Acciones disponibles</p>
                  <div className="flex flex-wrap gap-1.5">
                    {detailConnector.actions.map((action) => (
                      <Badge
                        key={action}
                        variant="outline"
                        className="border-indigo-500/20 bg-indigo-500/10 text-[10px] text-indigo-400"
                      >
                        <Layers className="mr-1 h-3 w-3" />
                        {action}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Clase y módulo */}
              {detailConnector.class_name && (
                <div className="text-[10px] text-zinc-600">
                  <p>
                    {detailConnector.module
                      ? `${detailConnector.module}.${detailConnector.class_name}`
                      : detailConnector.class_name}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="py-8 text-center text-sm text-zinc-500">
              No se pudieron cargar los detalles
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDetail(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cerrar
            </Button>
            {detailConnector && !detailConnector.installed && (
              <Button
                onClick={() => {
                  setShowDetail(false)
                  handleInstall(detailConnector.name)
                }}
                disabled={installing === detailConnector.name}
                className="bg-indigo-600 text-white hover:bg-indigo-500"
              >
                {installing === detailConnector.name ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    Instalando…
                  </>
                ) : (
                  <>
                    <Download className="mr-1.5 h-4 w-4" />
                    Instalar conector
                  </>
                )}
              </Button>
            )}
            {detailConnector?.installed && (
              <Button
                variant="outline"
                onClick={() => {
                  setShowDetail(false)
                  handleUninstall(detailConnector.name)
                }}
                className="border-red-500/30 text-red-400 hover:bg-red-500/10"
              >
                <Trash2 className="mr-1.5 h-4 w-4" />
                Desinstalar
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
