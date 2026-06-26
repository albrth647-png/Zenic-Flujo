import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import { error as humanError } from "@/utils/humanize"
import {
  FileText,
  Plus,
  Search,
  RefreshCw,
  Eye,
  Loader2,
  Calendar,
  User,
  Mail,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  Receipt,
} from "lucide-react"

import type { Invoice, InvoiceItem } from "@/types/invoice"

const INVOICE_STATUSES = ["pending", "paid", "overdue", "cancelled"]

const STATUS_LABELS: Record<string, string> = {
  pending: "Pendiente",
  paid: "Pagada",
  overdue: "Vencida",
  cancelled: "Cancelada",
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  paid: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  overdue: "bg-red-500/10 text-red-400 border-red-500/20",
  cancelled: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
}

// ── Componente ─────────────────────────────────

export default function InvoicesPage() {
  const { getApi } = useApi()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [showDialog, setShowDialog] = useState(false)
  const [showDetailDialog, setShowDetailDialog] = useState(false)
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [form, setForm] = useState({
    client_name: "",
    client_email: "",
    tax_rate: 16,
    discount: 0,
    due_days: 30,
    notes: "",
    items: [{ description: "", quantity: 1, unit_price: 0 }] as InvoiceItem[],
  })

  const loadInvoices = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const query = statusFilter !== "all" ? `?status=${statusFilter}` : ""
      const data = (await api.get(`/api/tools/invoice/list${query}`, { signal })) as Invoice[]
      if (signal?.aborted) return
      setInvoices(data)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar facturas", description: humanError(e), variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi, statusFilter])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadInvoices(ac.signal)
    return () => ac.abort()
  }, [loadInvoices])

  const filteredInvoices = invoices.filter((inv) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      inv.client_name.toLowerCase().includes(q) ||
      inv.number.toLowerCase().includes(q) ||
      (inv.client_email || "").toLowerCase().includes(q)
    )
  })

  const totals = {
    pending: invoices.filter((i) => i.status === "pending").reduce((s, i) => s + i.total, 0),
    overdue: invoices.filter((i) => i.status === "overdue").reduce((s, i) => s + i.total, 0),
    paid: invoices.filter((i) => i.status === "paid").reduce((s, i) => s + i.total, 0),
  }

  function calcSubtotal(items: InvoiceItem[]) {
    return items.reduce((sum, item) => sum + item.quantity * item.unit_price, 0)
  }

  function calcTotal(items: InvoiceItem[], taxRate: number, discount: number) {
    const sub = calcSubtotal(items)
    const tax = sub * (taxRate / 100)
    return sub + tax - discount
  }

  async function handleSave() {
    if (!form.client_name.trim()) return
    setSaving(true)
    setError("")
    try {
      const api = getApi()
      await api.post("/api/tools/invoice/create", {
        client_name: form.client_name,
        client_email: form.client_email || undefined,
        items: form.items.filter((i) => i.description.trim()),
        tax_rate: form.tax_rate / 100,
        discount: form.discount,
        due_days: form.due_days,
        notes: form.notes || undefined,
      })
      setShowDialog(false)
      setForm({
        client_name: "",
        client_email: "",
        tax_rate: 16,
        discount: 0,
        due_days: 30,
        notes: "",
        items: [{ description: "", quantity: 1, unit_price: 0 }],
      })
      loadInvoices()
    } catch (err: unknown) {
      setError(humanError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleMarkPaid(invoiceId: number) {
    try {
      const api = getApi()
      await api.post(`/api/tools/invoice/${invoiceId}/pay`)
      loadInvoices()
    } catch (e) {
      toast({ title: "Error al marcar como pagada", description: humanError(e), variant: "error" })
    }
  }

  async function handleCancel(invoiceId: number) {
    if (!confirm("¿Cancelar esta factura? Esta acción no se puede deshacer.")) return
    try {
      const api = getApi()
      await api.post(`/api/tools/invoice/${invoiceId}/cancel`)
      loadInvoices()
    } catch (e) {
      toast({ title: "Error al cancelar factura", description: humanError(e), variant: "error" })
    }
  }

  function addItem() {
    setForm({
      ...form,
      items: [...form.items, { description: "", quantity: 1, unit_price: 0 }],
    })
  }

  function removeItem(index: number) {
    if (form.items.length <= 1) return
    setForm({
      ...form,
      items: form.items.filter((_, i) => i !== index),
    })
  }

  function updateItem(index: number, field: keyof InvoiceItem, value: string | number) {
    const items = [...form.items]
    items[index] = { ...items[index], [field]: value }
    setForm({ ...form, items })
  }

  const statusBadge = (status: string) => (
    <Badge variant="outline" className={`border ${STATUS_COLORS[status] || STATUS_COLORS.pending}`}>
      {STATUS_LABELS[status] || status}
    </Badge>
  )

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 bg-zinc-800" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-lg bg-zinc-800" />
          ))}
        </div>
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-zinc-800" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Encabezado */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-100">Facturación</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Crea y administra tus facturas, da seguimiento a los pagos de tus clientes
        </p>
      </div>

      {/* Tarjetas de resumen */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-amber-400">
              ${totals.pending.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
            </p>
            <Clock className="h-4 w-4 text-amber-500" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Por cobrar</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-red-400">
              ${totals.overdue.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
            </p>
            <AlertTriangle className="h-4 w-4 text-red-500" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Vencido</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-emerald-400">
              ${totals.paid.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
            </p>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Cobrado</p>
        </div>
      </div>

      {/* Barra de búsqueda y acciones */}
      <Card className="mb-4 border-zinc-800 bg-zinc-900/50">
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar factura por cliente, folio o correo…"
                className="border-zinc-700 bg-zinc-800 pl-9 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
                {["all", ...INVOICE_STATUSES].map((s) => (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                      statusFilter === s
                        ? "bg-zinc-800 text-zinc-200"
                        : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {s === "all" ? "Todas" : STATUS_LABELS[s]}
                  </button>
                ))}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadInvoices()}
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                <RefreshCw className="mr-1.5 h-4 w-4" />
                Actualizar
              </Button>
              <Button
                onClick={() => {
                  setForm({
                    client_name: "",
                    client_email: "",
                    tax_rate: 16,
                    discount: 0,
                    due_days: 30,
                    notes: "",
                    items: [{ description: "", quantity: 1, unit_price: 0 }],
                  })
                  setError("")
                  setShowDialog(true)
                }}
                className="bg-indigo-600 text-white hover:bg-indigo-500"
              >
                <Plus className="mr-1.5 h-4 w-4" />
                Nueva factura
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Lista de facturas */}
      {filteredInvoices.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-12">
            <EmptyState
              icon={<Receipt className="h-12 w-12 text-zinc-600" />}
              title={invoices.length === 0 ? "No hay facturas aún" : "Sin resultados"}
              description={
                invoices.length === 0
                  ? "Crea tu primera factura para empezar a facturar a tus clientes."
                  : "Ninguna factura coincide con tu búsqueda."
              }
            />
          </CardContent>
        </Card>
      ) : (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-0">
            <div className="divide-y divide-zinc-800">
              {filteredInvoices.map((inv) => (
                <div
                  key={inv.id}
                  className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-zinc-800/30"
                >
                  <div className="flex flex-1 items-center gap-4">
                    {/* Icono */}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-800">
                      <FileText className="h-5 w-5 text-zinc-400" />
                    </div>

                    {/* Info principal */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-200">{inv.number}</span>
                        {statusBadge(inv.status)}
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
                        <span className="flex items-center gap-1">
                          <User className="h-3 w-3" />
                          {inv.client_name}
                        </span>
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          Vence: {new Date(inv.due_date).toLocaleDateString("es-MX")}
                        </span>
                        {inv.created_at && (
                          <span>· Creada: {new Date(inv.created_at).toLocaleDateString("es-MX")}</span>
                        )}
                      </div>
                    </div>

                    {/* Monto y acciones */}
                    <div className="flex items-center gap-3 shrink-0">
                      <div className="text-right">
                        <p className="text-sm font-bold text-zinc-100">
                          ${inv.total.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
                        </p>
                        {inv.status === "overdue" && (
                          <p className="text-[10px] text-red-400">Vencida</p>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedInvoice(inv)
                          setShowDetailDialog(true)
                        }}
                        className="text-zinc-500 hover:text-zinc-200"
                        title="Ver detalle"
                        aria-label={`Ver detalle de factura ${inv.number}`}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      {inv.status === "pending" && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleMarkPaid(inv.id)}
                            className="text-zinc-500 hover:text-emerald-400"
                            title="Marcar como pagada"
                            aria-label={`Marcar factura ${inv.number} como pagada`}
                          >
                            <CheckCircle2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCancel(inv.id)}
                            className="text-zinc-500 hover:text-red-400"
                            title="Cancelar factura"
                            aria-label={`Cancelar factura ${inv.number}`}
                          >
                            <XCircle className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Total */}
            <div className="border-t border-zinc-800 px-4 py-2 text-xs text-zinc-600">
              {filteredInvoices.length} de {invoices.length} factura{invoices.length !== 1 ? "s" : ""}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diálogo crear factura */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-2xl border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Nueva factura</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Crea una factura para tu cliente. Puedes agregar varios conceptos.
            </DialogDescription>
          </DialogHeader>

          <div className="max-h-[60vh] space-y-4 overflow-y-auto pr-2">
            {/* Datos del cliente */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label htmlFor="invoice-client-name" className="mb-1 block text-sm text-zinc-300">
                  Cliente <span className="text-red-400">*</span>
                </label>
                <Input
                  id="invoice-client-name"
                  value={form.client_name}
                  onChange={(e) => setForm({ ...form, client_name: e.target.value })}
                  placeholder="Nombre del cliente"
                  className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
                />
              </div>
              <div>
                <label htmlFor="invoice-client-email" className="mb-1 block text-sm text-zinc-300">Correo del cliente</label>
                <Input
                  id="invoice-client-email"
                  type="email"
                  value={form.client_email}
                  onChange={(e) => setForm({ ...form, client_email: e.target.value })}
                  placeholder="cliente@correo.com"
                  className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
                />
              </div>
              <div>
                <label htmlFor="invoice-due-days" className="mb-1 block text-sm text-zinc-300">Días para vencer</label>
                <Input
                  id="invoice-due-days"
                  type="number"
                  min={1}
                  value={form.due_days}
                  onChange={(e) => setForm({ ...form, due_days: parseInt(e.target.value) || 30 })}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>
            </div>

            {/* Conceptos */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm text-zinc-300">Conceptos</label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={addItem}
                  className="text-indigo-400 hover:text-indigo-300"
                >
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  Agregar concepto
                </Button>
              </div>
              <div className="space-y-2">
                {form.items.map((item, index) => (
                  <div key={index} className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-zinc-800/30 p-3">
                    <div className="flex-1">
                      <Input
                        value={item.description}
                        onChange={(e) => updateItem(index, "description", e.target.value)}
                        placeholder="Descripción del concepto"
                        className="mb-2 border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
                      />
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label htmlFor={`invoice-item-quantity-${index}`} className="block text-[10px] text-zinc-500">Cant.</label>
                          <Input
                            id={`invoice-item-quantity-${index}`}
                            type="number"
                            min={1}
                            value={item.quantity}
                            onChange={(e) => updateItem(index, "quantity", Math.max(1, parseInt(e.target.value) || 1))}
                            className="border-zinc-700 bg-zinc-800 text-zinc-200"
                          />
                        </div>
                        <div className="flex-1">
                          <label htmlFor={`invoice-item-price-${index}`} className="block text-[10px] text-zinc-500">Precio unit.</label>
                          <Input
                            id={`invoice-item-price-${index}`}
                            type="number"
                            min={0}
                            step={0.01}
                            value={item.unit_price || ""}
                            onChange={(e) => updateItem(index, "unit_price", parseFloat(e.target.value) || 0)}
                            className="border-zinc-700 bg-zinc-800 text-zinc-200"
                          />
                        </div>
                        <div className="flex items-end">
                          <p className="pb-2 text-sm font-medium text-zinc-300">
                            ${(item.quantity * item.unit_price).toFixed(2)}
                          </p>
                        </div>
                        {form.items.length > 1 && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => removeItem(index)}
                            className="mt-5 text-zinc-500 hover:text-red-400"
                            aria-label={`Eliminar concepto ${index + 1}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Impuestos y descuentos */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="invoice-tax-rate" className="mb-1 block text-sm text-zinc-300">IVA / Impuesto (%)</label>
                <Input
                  id="invoice-tax-rate"
                  type="number"
                  min={0}
                  max={100}
                  value={form.tax_rate}
                  onChange={(e) => setForm({ ...form, tax_rate: parseInt(e.target.value) || 0 })}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>
              <div>
                <label htmlFor="invoice-discount" className="mb-1 block text-sm text-zinc-300">Descuento ($)</label>
                <Input
                  id="invoice-discount"
                  type="number"
                  min={0}
                  step={0.01}
                  value={form.discount || ""}
                  onChange={(e) => setForm({ ...form, discount: parseFloat(e.target.value) || 0 })}
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>
            </div>

            {/* Resumen */}
            <div className="rounded-lg border border-zinc-800 bg-zinc-800/30 p-4">
              <div className="space-y-1 text-sm">
                <div className="flex justify-between text-zinc-400">
                  <span>Subtotal</span>
                  <span>${calcSubtotal(form.items).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-zinc-400">
                  <span>IVA ({form.tax_rate}%)</span>
                  <span>${(calcSubtotal(form.items) * (form.tax_rate / 100)).toFixed(2)}</span>
                </div>
                {form.discount > 0 && (
                  <div className="flex justify-between text-zinc-400">
                    <span>Descuento</span>
                    <span>-${form.discount.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between border-t border-zinc-700 pt-1 text-base font-bold text-zinc-100">
                  <span>Total</span>
                  <span>${calcTotal(form.items, form.tax_rate, form.discount).toFixed(2)}</span>
                </div>
              </div>
            </div>

            <div>
              <label htmlFor="invoice-notes" className="mb-1 block text-sm text-zinc-300">Notas (opcional)</label>
              <textarea
                id="invoice-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Condiciones de pago, información adicional…"
                rows={2}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || !form.client_name.trim() || form.items.every((i) => !i.description.trim())}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Creando factura…
                </>
              ) : (
                <>
                  <FileText className="mr-1.5 h-4 w-4" />
                  Crear factura
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Diálogo de detalle */}
      <Dialog open={showDetailDialog} onOpenChange={setShowDetailDialog}>
        <DialogContent className="max-w-lg border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedInvoice?.number}
              {selectedInvoice && statusBadge(selectedInvoice.status)}
            </DialogTitle>
          </DialogHeader>

          {selectedInvoice && (
            <div className="space-y-4">
              {/* Cliente */}
              <div className="rounded-lg bg-zinc-800/30 p-4">
                <div className="flex items-center gap-2 text-sm text-zinc-400">
                  <User className="h-4 w-4" />
                  {selectedInvoice.client_name}
                </div>
                {selectedInvoice.client_email && (
                  <div className="mt-1 flex items-center gap-2 text-sm text-zinc-400">
                    <Mail className="h-4 w-4" />
                    {selectedInvoice.client_email}
                  </div>
                )}
                <div className="mt-1 flex items-center gap-2 text-sm text-zinc-400">
                  <Calendar className="h-4 w-4" />
                  Vence: {new Date(selectedInvoice.due_date).toLocaleDateString("es-MX")}
                </div>
              </div>

              {/* Conceptos */}
              <div>
                <h4 className="mb-2 text-sm font-medium text-zinc-300">Conceptos</h4>
                <div className="space-y-2">
                  {selectedInvoice.items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between rounded-lg bg-zinc-800/20 px-3 py-2">
                      <div>
                        <p className="text-sm text-zinc-200">{item.description}</p>
                        <p className="text-xs text-zinc-500">
                          {item.quantity} × ${item.unit_price.toFixed(2)}
                        </p>
                      </div>
                      <p className="text-sm font-medium text-zinc-200">
                        ${(item.quantity * item.unit_price).toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Totales */}
              <div className="rounded-lg border border-zinc-800 bg-zinc-800/20 p-4">
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between text-zinc-400">
                    <span>Subtotal</span>
                    <span>${selectedInvoice.subtotal.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-zinc-400">
                    <span>IVA ({(selectedInvoice.tax_rate * 100).toFixed(0)}%)</span>
                    <span>${selectedInvoice.tax_amount.toFixed(2)}</span>
                  </div>
                  {selectedInvoice.discount > 0 && (
                    <div className="flex justify-between text-zinc-400">
                      <span>Descuento</span>
                      <span>-${selectedInvoice.discount.toFixed(2)}</span>
                    </div>
                  )}
                  <div className="flex justify-between border-t border-zinc-700 pt-1 text-base font-bold text-zinc-100">
                    <span>Total</span>
                    <span>${selectedInvoice.total.toFixed(2)}</span>
                  </div>
                </div>
              </div>

              {selectedInvoice.notes && (
                <div>
                  <h4 className="mb-1 text-sm font-medium text-zinc-300">Notas</h4>
                  <p className="text-sm text-zinc-400">{selectedInvoice.notes}</p>
                </div>
              )}

              {selectedInvoice.paid_at && (
                <div className="rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-400">
                  Pagada el {new Date(selectedInvoice.paid_at).toLocaleDateString("es-MX")}
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDetailDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
