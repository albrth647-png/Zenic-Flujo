import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from "recharts"
import { error as humanError } from "@/utils/humanize"
import {
  BarChart3,
  FileText,
  FileSpreadsheet,
  Activity,
  Users,
  Package,
  Receipt,
  RefreshCw,
  TrendingUp,
  CheckCircle2,
  Clock,
  AlertTriangle,
} from "lucide-react"

import type {
  ReportLead as Lead,
  ReportProduct as Product,
  ReportInvoice as Invoice,
  DashboardStats,
} from "@/types/reports"

// ── Helpers ────────────────────────────────────

function downloadReport(url: string, filename: string) {
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
}

// ── Componente tarjeta de reporte ──────────────

function ReportCard({
  title,
  icon: Icon,
  count,
  subtitle,
  color,
  bgColor,
  csvUrl,
  pdfUrl,
}: {
  title: string
  icon: React.ElementType
  count: number | string
  subtitle?: string
  color: string
  bgColor: string
  csvUrl: string
  pdfUrl: string
}) {
  return (
    <Card className="border-zinc-800 bg-zinc-900/50 transition-all hover:border-zinc-700">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${bgColor}`}>
              <Icon className={`h-5 w-5 ${color}`} />
            </div>
            <div>
              <p className="text-sm font-medium text-zinc-300">{title}</p>
              <p className={`text-2xl font-bold ${color}`}>{count}</p>
              {subtitle && <p className="mt-0.5 text-xs text-zinc-500">{subtitle}</p>}
            </div>
          </div>
        </div>
        <div className="mt-4 flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadReport(csvUrl, `${title.toLowerCase().replace(/\s+/g, "_")}.csv`)}
            className="flex-1 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <FileSpreadsheet className="mr-1.5 h-4 w-4 text-emerald-400" />
            CSV
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadReport(pdfUrl, `${title.toLowerCase().replace(/\s+/g, "_")}.pdf`)}
            className="flex-1 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
          >
            <FileText className="mr-1.5 h-4 w-4 text-red-400" />
            PDF
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Componente principal ───────────────────────

export default function ReportsPage() {
  const { getApi } = useApi()
  const [loading, setLoading] = useState(true)
  const [workflowStats, setWorkflowStats] = useState({ total: 0, active: 0, failed: 0, paused: 0 })
  const [leadCount, setLeadCount] = useState(0)
  const [productCount, setProductCount] = useState(0)
  const [lowStockCount, setLowStockCount] = useState(0)
  const [invoiceCounts, setInvoiceCounts] = useState({ pending: 0, paid: 0, overdue: 0, cancelled: 0, total: 0 })
  const [totalRevenue, setTotalRevenue] = useState(0)
  const [activeTab, setActiveTab] = useState("resumen")
  const [invoices, setInvoices] = useState<Invoice[]>([])

  const loadData = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const [dashRes, leadsRes, productsRes, lowStockRes, invoicesRes] = await Promise.all([
        api.get("/api/dashboard/stats", { signal }),
        api.get("/api/tools/crm/leads", { signal }),
        api.get("/api/tools/inventory/products", { signal }),
        api.get("/api/tools/inventory/low-stock", { signal }),
        api.get("/api/tools/invoice/list", { signal }),
      ])
      if (signal?.aborted) return

      const dash = dashRes as DashboardStats | null
      if (dash?.stats) {
        setWorkflowStats({
          total: dash.stats.total || 0,
          active: dash.stats.by_status?.active || 0,
          failed: (dash.stats.by_status?.failed || 0) + (dash.stats.by_status?.error || 0),
          paused: dash.stats.by_status?.paused || 0,
        })
      }

      const l = leadsRes as Lead[]
      setLeadCount(l?.length || 0)

      const p = productsRes as Product[]
      const lp = lowStockRes as Product[]
      setLowStockCount(lp?.length || 0)
      setProductCount(p?.length || 0)

      const inv = invoicesRes as Invoice[]
      setInvoices(inv || [])
      const counts = { pending: 0, paid: 0, overdue: 0, cancelled: 0, total: 0 }
      let revenue = 0
      for (const i of inv || []) {
        counts.total++
        if (i.status in counts) (counts as Record<string, number>)[i.status]++
        if (i.status === "paid") revenue += i.total
        if (i.status === "pending") revenue += i.total
      }
      setInvoiceCounts(counts)
      setTotalRevenue(revenue)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar reportes", description: humanError(e), variant: "error" })
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

  // ── Check if dark mode ──────────────────────
  const isDark = typeof document !== "undefined" && document.documentElement.classList.contains("dark")
  const textColor = isDark ? "#888" : "#6b7280"
  const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"

  // Datos para gráficos
  const moduleData = [
    { name: "Flujos", value: workflowStats.total, color: "#6366f1" },
    { name: "Clientes", value: leadCount, color: "#22c55e" },
    { name: "Productos", value: productCount, color: "#f59e0b" },
    { name: "Facturas", value: invoiceCounts.total, color: "#ef4444" },
  ].filter((d) => d.value > 0)

  const statusData = [
    { name: "Activos", value: workflowStats.active, color: "#22c55e" },
    { name: "Errores", value: workflowStats.failed, color: "#ef4444" },
    { name: "Pausados", value: workflowStats.paused, color: "#f59e0b" },
  ].filter((d) => d.value > 0)

  const invoiceStatusData = [
    { name: "Pendientes", value: invoiceCounts.pending, color: "#f59e0b" },
    { name: "Pagadas", value: invoiceCounts.paid, color: "#22c55e" },
    { name: "Vencidas", value: invoiceCounts.overdue, color: "#ef4444" },
    { name: "Canceladas", value: invoiceCounts.cancelled, color: "#6b7280" },
  ].filter((d) => d.value > 0)

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-8 w-48 bg-zinc-800" />
          <Skeleton className="mt-1 h-4 w-64 bg-zinc-800" />
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-28 rounded-xl bg-zinc-800" />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-64 rounded-xl bg-zinc-800" />
          <Skeleton className="h-64 rounded-xl bg-zinc-800" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Reportes</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Descarga reportes detallados y visualiza el rendimiento de tu negocio
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadData()}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Actualizar
        </Button>
      </div>

      {/* Tarjetas de módulos */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <ReportCard
          title="Flujos de trabajo"
          icon={Activity}
          count={workflowStats.total}
          subtitle={`${workflowStats.active} activos · ${workflowStats.failed} errores`}
          color="text-indigo-400"
          bgColor="bg-indigo-500/10"
          csvUrl="/api/reports/workflows/csv"
          pdfUrl="/api/reports/workflows/pdf"
        />
        <ReportCard
          title="Clientes CRM"
          icon={Users}
          count={leadCount}
          subtitle="Prospectos registrados"
          color="text-emerald-400"
          bgColor="bg-emerald-500/10"
          csvUrl="/api/reports/crm/csv"
          pdfUrl="/api/reports/crm/pdf"
        />
        <ReportCard
          title="Inventario"
          icon={Package}
          count={productCount}
          subtitle={`${lowStockCount} con stock bajo`}
          color="text-amber-400"
          bgColor="bg-amber-500/10"
          csvUrl="/api/reports/inventory/csv"
          pdfUrl="/api/reports/inventory/pdf"
        />
        <ReportCard
          title="Facturación"
          icon={Receipt}
          count={invoiceCounts.total}
          subtitle={`$${totalRevenue.toLocaleString("es-MX", { minimumFractionDigits: 0 })}`}
          color="text-red-400"
          bgColor="bg-red-500/10"
          csvUrl="/api/reports/invoices/csv"
          pdfUrl="/api/reports/invoices/pdf"
        />
      </div>

      {/* Gráficos y detalles */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="border-zinc-800 bg-zinc-900">
          <TabsTrigger
            value="resumen"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <BarChart3 className="mr-1.5 h-4 w-4" />
            Resumen visual
          </TabsTrigger>
          <TabsTrigger
            value="workflows"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Activity className="mr-1.5 h-4 w-4" />
            Flujos
          </TabsTrigger>
          <TabsTrigger
            value="facturas"
            className="data-[state=active]:bg-zinc-800 data-[state=active]:text-zinc-100"
          >
            <Receipt className="mr-1.5 h-4 w-4" />
            Facturas
          </TabsTrigger>
        </TabsList>

        {/* ── Resumen visual ── */}
        <TabsContent value="resumen" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Gráfico de módulos */}
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400">
                  <BarChart3 className="mr-1.5 inline h-4 w-4" />
                  Totales por módulo
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[250px]">
                  {moduleData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={moduleData} barSize={40}>
                        <XAxis
                          dataKey="name"
                          tick={{ fill: textColor, fontSize: 11 }}
                          axisLine={{ stroke: gridColor }}
                          tickLine={false}
                        />
                        <YAxis
                          tick={{ fill: textColor, fontSize: 10 }}
                          axisLine={false}
                          tickLine={false}
                          allowDecimals={false}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: isDark ? "#1a1a1a" : "#fff",
                            border: `1px solid ${gridColor}`,
                            borderRadius: "8px",
                            fontSize: "12px",
                          }}
                        />
                        <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                          {moduleData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                      Sin datos disponibles
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Estado de workflows */}
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400">
                  <Activity className="mr-1.5 inline h-4 w-4" />
                  Estado de workflows
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[250px]">
                  {statusData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={statusData}
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={80}
                          paddingAngle={3}
                          dataKey="value"
                          strokeWidth={0}
                        >
                          {statusData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Legend
                          wrapperStyle={{ fontSize: "11px", color: textColor }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                      Sin datos de workflows
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Estado de facturas */}
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400">
                  <Receipt className="mr-1.5 inline h-4 w-4" />
                  Estado de facturas
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-[220px]">
                  {invoiceStatusData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={invoiceStatusData}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={75}
                          paddingAngle={3}
                          dataKey="value"
                          strokeWidth={0}
                        >
                          {invoiceStatusData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Legend
                          wrapperStyle={{ fontSize: "11px", color: textColor }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-zinc-500">
                      Sin facturas
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Resumen rápido */}
            <Card className="border-zinc-800 bg-zinc-900/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-zinc-400">
                  <TrendingUp className="mr-1.5 inline h-4 w-4" />
                  Resumen rápido
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className="text-sm text-zinc-400">Workflows activos</span>
                    <span className="text-sm font-bold text-emerald-400">{workflowStats.active}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className="text-sm text-zinc-400">Clientes en CRM</span>
                    <span className="text-sm font-bold text-emerald-400">{leadCount}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className="text-sm text-zinc-400">Productos con stock bajo</span>
                    <span className={`text-sm font-bold ${lowStockCount > 0 ? "text-amber-400" : "text-emerald-400"}`}>
                      {lowStockCount}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className="text-sm text-zinc-400">Facturas por cobrar</span>
                    <span className={`text-sm font-bold ${invoiceCounts.pending > 0 ? "text-amber-400" : "text-emerald-400"}`}>
                      {invoiceCounts.pending}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className="text-sm text-zinc-400">Facturas vencidas</span>
                    <span className={`text-sm font-bold ${invoiceCounts.overdue > 0 ? "text-red-400" : "text-emerald-400"}`}>
                      {invoiceCounts.overdue}
                    </span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-zinc-800/30 px-3 py-2">
                    <span className="text-sm text-zinc-400">Errores en workflows</span>
                    <span className={`text-sm font-bold ${workflowStats.failed > 0 ? "text-red-400" : "text-emerald-400"}`}>
                      {workflowStats.failed}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ── Tabla de Workflows ── */}
        <TabsContent value="workflows" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardContent className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-zinc-200">Flujos registrados</h3>
                  <p className="text-xs text-zinc-500">
                    Total: {workflowStats.total} · Activos: {workflowStats.active} · Errores: {workflowStats.failed} · Pausados: {workflowStats.paused}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadReport("/api/reports/workflows/csv", "workflows.csv")}
                    className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <FileSpreadsheet className="mr-1.5 h-4 w-4 text-emerald-400" />
                    CSV
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadReport("/api/reports/workflows/pdf", "workflows.pdf")}
                    className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <FileText className="mr-1.5 h-4 w-4 text-red-400" />
                    PDF
                  </Button>
                </div>
              </div>

              {/* Estado gráfico de workflows */}
              <div className="grid gap-4 sm:grid-cols-4">
                {[
                  { label: "Activos", value: workflowStats.active, color: "text-emerald-400", bg: "bg-emerald-500/10", icon: CheckCircle2 },
                  { label: "Con errores", value: workflowStats.failed, color: "text-red-400", bg: "bg-red-500/10", icon: AlertTriangle },
                  { label: "Pausados", value: workflowStats.paused, color: "text-amber-400", bg: "bg-amber-500/10", icon: Clock },
                  { label: "Total", value: workflowStats.total, color: "text-indigo-400", bg: "bg-indigo-500/10", icon: Activity },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                    <item.icon className={`mx-auto h-5 w-5 ${item.color}`} />
                    <p className={`mt-1 text-xl font-bold ${item.color}`}>{item.value}</p>
                    <p className="text-xs text-zinc-500">{item.label}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tabla de Facturas ── */}
        <TabsContent value="facturas" className="mt-4">
          <Card className="border-zinc-800 bg-zinc-900/50">
            <CardContent className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-zinc-200">Facturas registradas</h3>
                  <p className="text-xs text-zinc-500">
                    Total: {invoiceCounts.total} · Pendientes: {invoiceCounts.pending} · Pagadas: {invoiceCounts.paid} · Vencidas: {invoiceCounts.overdue} · Canceladas: {invoiceCounts.cancelled}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadReport("/api/reports/invoices/csv", "facturas.csv")}
                    className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <FileSpreadsheet className="mr-1.5 h-4 w-4 text-emerald-400" />
                    CSV
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadReport("/api/reports/invoices/pdf", "facturas.pdf")}
                    className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                  >
                    <FileText className="mr-1.5 h-4 w-4 text-red-400" />
                    PDF
                  </Button>
                </div>
              </div>

              {/* Resumen de facturas */}
              <div className="grid gap-4 sm:grid-cols-4">
                {[
                  { label: "Pendientes", value: invoiceCounts.pending, color: "text-amber-400", icon: Clock },
                  { label: "Pagadas", value: invoiceCounts.paid, color: "text-emerald-400", icon: CheckCircle2 },
                  { label: "Vencidas", value: invoiceCounts.overdue, color: "text-red-400", icon: AlertTriangle },
                  { label: "Canceladas", value: invoiceCounts.cancelled, color: "text-zinc-400", icon: AlertTriangle },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-center">
                    <item.icon className={`mx-auto h-5 w-5 ${item.color}`} />
                    <p className={`mt-1 text-xl font-bold ${item.color}`}>{item.value}</p>
                    <p className="text-xs text-zinc-500">{item.label}</p>
                  </div>
                ))}
              </div>

              {/* Últimas facturas */}
              {invoices.length > 0 && (
                <div className="mt-4">
                  <h4 className="mb-2 text-xs font-medium text-zinc-500">ÚLTIMAS FACTURAS</h4>
                  <div className="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
                    {invoices.slice(0, 10).map((inv) => {
                      const statusStyles: Record<string, string> = {
                        pending: "text-amber-400 bg-amber-500/10",
                        paid: "text-emerald-400 bg-emerald-500/10",
                        overdue: "text-red-400 bg-red-500/10",
                        cancelled: "text-zinc-400 bg-zinc-500/10",
                      }
                      const statusLabels: Record<string, string> = {
                        pending: "Pendiente",
                        paid: "Pagada",
                        overdue: "Vencida",
                        cancelled: "Cancelada",
                      }
                      return (
                        <div key={inv.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                          <div className="flex items-center gap-3">
                            <span className="font-medium text-zinc-200">{inv.number}</span>
                            <span className="text-zinc-400">{inv.client_name}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="font-medium text-zinc-100">
                              ${inv.total.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
                            </span>
                            <span className={`rounded-md px-2 py-0.5 text-[10px] font-medium ${statusStyles[inv.status] || ""}`}>
                              {statusLabels[inv.status] || inv.status}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
