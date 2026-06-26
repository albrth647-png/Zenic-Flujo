import { useState, useEffect, useCallback } from "react"
import { useApi } from "@/hooks/useApi"
import { toast } from "@/components/ui/toast"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/ui/empty-state"
import { error as humanError } from "@/utils/humanize"
import {
  Package,
  Plus,
  Search,
  RefreshCw,
  Edit,
  Trash2,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Loader2,
  DollarSign,
  Archive,
  BarChart3,
  Warehouse,
} from "lucide-react"

import type { Product } from "@/types/inventory"

// ── Componente ─────────────────────────────────

export default function InventoryPage() {
  const { getApi } = useApi()
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [showDialog, setShowDialog] = useState(false)
  const [showMovementDialog, setShowMovementDialog] = useState(false)
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [form, setForm] = useState({
    name: "",
    sku: "",
    description: "",
    category: "",
    stock: 0,
    min_stock: 10,
    price: 0,
  })
  const [movement, setMovement] = useState({
    type: "in" as "in" | "out" | "adjustment",
    quantity: 1,
    reason: "",
  })

  const loadProducts = useCallback(async (signal?: AbortSignal) => {
    try {
      const api = getApi()
      const path = lowStockOnly
        ? "/api/tools/inventory/low-stock"
        : "/api/tools/inventory/products"
      const data = (await api.get(path, { signal })) as Product[]
      if (signal?.aborted) return
      setProducts(data)
    } catch (e) {
      if (signal?.aborted || (e instanceof DOMException && e.name === "AbortError")) return
      toast({ title: "Error al cargar productos", description: humanError(e), variant: "error" })
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [getApi, lowStockOnly])

  useEffect(() => {
    const ac = new AbortController()
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadProducts(ac.signal)
    return () => ac.abort()
  }, [loadProducts])

  const filteredProducts = products.filter((p) => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      p.name.toLowerCase().includes(q) ||
      p.sku.toLowerCase().includes(q) ||
      (p.category || "").toLowerCase().includes(q)
    )
  })

  const lowStockCount = products.filter((p) => p.stock <= p.min_stock).length

  const totalValue = products.reduce((sum, p) => sum + p.price * p.stock, 0)

  async function handleSave() {
    if (!form.name.trim()) return
    setSaving(true)
    setError("")
    try {
      const api = getApi()
      if (editingProduct) {
        await api.put(`/api/tools/inventory/products/${editingProduct.id}`, form)
      } else {
        await api.post("/api/tools/inventory/products", form)
      }
      setShowDialog(false)
      setEditingProduct(null)
      setForm({ name: "", sku: "", description: "", category: "", stock: 0, min_stock: 10, price: 0 })
      loadProducts()
    } catch (err: unknown) {
      setError(humanError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleStockMovement() {
    if (!selectedProduct || movement.quantity <= 0) return
    setSaving(true)
    setError("")
    try {
      const api = getApi()
      await api.post("/api/tools/inventory/stock-movement", {
        product_id: selectedProduct.id,
        quantity: movement.quantity,
        type: movement.type,
        reason: movement.reason,
      })
      setShowMovementDialog(false)
      setSelectedProduct(null)
      setMovement({ type: "in", quantity: 1, reason: "" })
      loadProducts()
    } catch (err: unknown) {
      setError(humanError(err))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(productId: number, name: string) {
    if (!confirm(`¿Eliminar "${name}"? Esta acción no se puede deshacer.`)) return
    try {
      const api = getApi()
      await api.delete(`/api/tools/inventory/products/${productId}`)
      loadProducts()
    } catch (e) {
      toast({ title: "Error al eliminar producto", description: humanError(e), variant: "error" })
    }
  }

  function openEdit(product: Product) {
    setEditingProduct(product)
    setForm({
      name: product.name,
      sku: product.sku,
      description: product.description || "",
      category: product.category || "",
      stock: product.stock,
      min_stock: product.min_stock,
      price: product.price,
    })
    setShowDialog(true)
  }

  function openNew() {
    setEditingProduct(null)
    setForm({ name: "", sku: "", description: "", category: "", stock: 0, min_stock: 10, price: 0 })
    setShowDialog(true)
  }

  const stockBadge = (product: Product) => {
    if (product.stock <= 0) {
      return <Badge variant="outline" className="border-red-500/20 bg-red-500/10 text-red-400">Sin stock</Badge>
    }
    if (product.stock <= product.min_stock) {
      return <Badge variant="outline" className="border-amber-500/20 bg-amber-500/10 text-amber-400">Stock bajo</Badge>
    }
    return <Badge variant="outline" className="border-emerald-500/20 bg-emerald-500/10 text-emerald-400">En stock</Badge>
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48 bg-zinc-800" />
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
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
        <h1 className="text-2xl font-semibold text-zinc-100">Inventario</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Controla tu catálogo de productos, lleva el stock al día y registra movimientos
        </p>
      </div>

      {/* Tarjetas de resumen */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-zinc-100">{products.length}</p>
            <Package className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Productos registrados</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-amber-400">{lowStockCount}</p>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Con stock bajo</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-emerald-400">
              ${totalValue.toLocaleString("es-MX", { minimumFractionDigits: 0 })}
            </p>
            <DollarSign className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Valor en inventario</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center justify-between">
            <p className="text-lg font-bold text-zinc-100">
              {products.length > 0
                ? Math.round(products.reduce((s, p) => s + p.stock, 0) / products.length)
                : 0}
            </p>
            <BarChart3 className="h-4 w-4 text-zinc-600" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Stock promedio</p>
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
                placeholder="Buscar producto por nombre, SKU o categoría…"
                className="border-zinc-700 bg-zinc-800 pl-9 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant={lowStockOnly ? "default" : "outline"}
                size="sm"
                onClick={() => setLowStockOnly(!lowStockOnly)}
                className={
                  lowStockOnly
                    ? "bg-amber-600 text-white hover:bg-amber-500"
                    : "border-zinc-700 text-zinc-300 hover:bg-zinc-800"
                }
              >
                <AlertTriangle className="mr-1.5 h-4 w-4" />
                Stock bajo
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadProducts()}
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                <RefreshCw className="mr-1.5 h-4 w-4" />
                Actualizar
              </Button>
              <Button
                onClick={openNew}
                className="bg-indigo-600 text-white hover:bg-indigo-500"
              >
                <Plus className="mr-1.5 h-4 w-4" />
                Nuevo producto
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Lista de productos */}
      {filteredProducts.length === 0 ? (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-12">
            <EmptyState
              icon={<Warehouse className="h-12 w-12 text-zinc-600" />}
              title={products.length === 0 ? "Tu inventario está vacío" : "Sin resultados"}
              description={
                products.length === 0
                  ? "Agrega tu primer producto para empezar a controlar tu inventario."
                  : "Ningún producto coincide con tu búsqueda."
              }
            />
          </CardContent>
        </Card>
      ) : (
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardContent className="p-0">
            <div className="divide-y divide-zinc-800">
              {filteredProducts.map((product) => (
                <div
                  key={product.id}
                  className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-zinc-800/30"
                >
                  <div className="flex flex-1 items-center gap-4">
                    {/* Icono */}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-800">
                      <Package className="h-5 w-5 text-zinc-400" />
                    </div>

                    {/* Info principal */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-200">{product.name}</span>
                        <span className="text-xs text-zinc-600">SKU: {product.sku}</span>
                      </div>
                      <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-zinc-500">
                        {product.category && (
                          <span className="flex items-center gap-1">
                            <Archive className="h-3 w-3" />
                            {product.category}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <DollarSign className="h-3 w-3" />
                          ${product.price.toFixed(2)}
                        </span>
                        {product.description && (
                          <span className="truncate max-w-[200px]">· {product.description}</span>
                        )}
                      </div>
                    </div>

                    {/* Stock y acciones */}
                    <div className="flex items-center gap-3 shrink-0">
                      {/* Barra de stock */}
                      <div className="text-right">
                        <p className={`text-sm font-bold ${
                          product.stock <= 0
                            ? "text-red-400"
                            : product.stock <= product.min_stock
                              ? "text-amber-400"
                              : "text-emerald-400"
                        }`}>
                          {product.stock}
                        </p>
                        <p className="text-[10px] text-zinc-600">mín: {product.min_stock}</p>
                      </div>
                      {stockBadge(product)}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedProduct(product)
                          setMovement({ type: "in", quantity: 1, reason: "" })
                          setError("")
                          setShowMovementDialog(true)
                        }}
                        className="text-zinc-500 hover:text-indigo-400"
                        title="Registrar movimiento"
                        aria-label={`Registrar movimiento de stock para ${product.name}`}
                      >
                        {product.stock <= product.min_stock ? (
                          <TrendingUp className="h-4 w-4" />
                        ) : (
                          <TrendingDown className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEdit(product)}
                        className="text-zinc-500 hover:text-zinc-200"
                        title="Editar"
                        aria-label={`Editar producto ${product.name}`}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(product.id, product.name)}
                        className="text-zinc-500 hover:text-red-400"
                        title="Eliminar"
                        aria-label={`Eliminar producto ${product.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Total */}
            <div className="border-t border-zinc-800 px-4 py-2 text-xs text-zinc-600">
              {filteredProducts.length} de {products.length} producto{products.length !== 1 ? "s" : ""}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diálogo crear/editar producto */}
      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-lg border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>{editingProduct ? "Editar producto" : "Nuevo producto"}</DialogTitle>
            <DialogDescription className="text-zinc-400">
              {editingProduct
                ? "Actualiza los datos del producto"
                : "Agrega un producto a tu catálogo"}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor="inventory-product-name" className="mb-1 block text-sm text-zinc-300">
                Nombre <span className="text-red-400">*</span>
              </label>
              <Input
                id="inventory-product-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Ej: Laptop Pro X1"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="inventory-product-sku" className="mb-1 block text-sm text-zinc-300">
                SKU <span className="text-red-400">*</span>
              </label>
              <Input
                id="inventory-product-sku"
                value={form.sku}
                onChange={(e) => setForm({ ...form, sku: e.target.value })}
                placeholder="Ej: LP-X1-001"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="inventory-product-category" className="mb-1 block text-sm text-zinc-300">Categoría</label>
              <Input
                id="inventory-product-category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                placeholder="Ej: Electrónicos"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="inventory-product-price" className="mb-1 block text-sm text-zinc-300">Precio</label>
              <Input
                id="inventory-product-price"
                type="number"
                min={0}
                step={0.01}
                value={form.price || ""}
                onChange={(e) => setForm({ ...form, price: parseFloat(e.target.value) || 0 })}
                placeholder="0.00"
                className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
              />
            </div>
            <div>
              <label htmlFor="inventory-product-stock" className="mb-1 block text-sm text-zinc-300">Stock inicial</label>
              <Input
                id="inventory-product-stock"
                type="number"
                min={0}
                value={form.stock}
                onChange={(e) => setForm({ ...form, stock: parseInt(e.target.value) || 0 })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="inventory-product-min-stock" className="mb-1 block text-sm text-zinc-300">Stock mínimo</label>
              <Input
                id="inventory-product-min-stock"
                type="number"
                min={0}
                value={form.min_stock}
                onChange={(e) => setForm({ ...form, min_stock: parseInt(e.target.value) || 0 })}
                className="border-zinc-700 bg-zinc-800 text-zinc-200"
              />
              <p className="mt-1 text-xs text-zinc-500">
                Te avisaremos cuando el stock baje de esta cantidad
              </p>
            </div>
            <div className="sm:col-span-2">
              <label htmlFor="inventory-product-description" className="mb-1 block text-sm text-zinc-300">Descripción</label>
              <textarea
                id="inventory-product-description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Descripción del producto…"
                rows={2}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            {error && (
              <div className="sm:col-span-2 rounded-lg bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
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
              disabled={saving || !form.name.trim() || !form.sku.trim()}
              className="bg-indigo-600 text-white hover:bg-indigo-500"
            >
              {saving ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Guardando…
                </>
              ) : editingProduct ? (
                "Guardar cambios"
              ) : (
                "Crear producto"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Diálogo de movimiento de stock */}
      <Dialog open={showMovementDialog} onOpenChange={setShowMovementDialog}>
        <DialogContent className="max-w-md border-zinc-800 bg-zinc-900 text-zinc-200">
          <DialogHeader>
            <DialogTitle>Movimiento de stock</DialogTitle>
            <DialogDescription className="text-zinc-400">
              {selectedProduct
                ? `Registra una entrada o salida para "${selectedProduct.name}"`
                : "Selecciona un producto"}
            </DialogDescription>
          </DialogHeader>

          {selectedProduct && (
            <div className="space-y-4">
              <div className="rounded-lg bg-zinc-800/50 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-300">{selectedProduct.name}</span>
                  <span className="text-sm font-bold text-zinc-100">
                    Stock actual: {selectedProduct.stock}
                  </span>
                </div>
                <p className="mt-1 text-xs text-zinc-500">SKU: {selectedProduct.sku}</p>
              </div>

              <div>
                <label htmlFor="inventory-movement-type" className="mb-1 block text-sm text-zinc-300">Tipo de movimiento</label>
                <Select
                  value={movement.type}
                  onValueChange={(v) => setMovement({ ...movement, type: v as typeof movement.type })}
                >
                  <SelectTrigger id="inventory-movement-type" className="border-zinc-700 bg-zinc-800 text-zinc-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-zinc-700 bg-zinc-800 text-zinc-200">
                    <SelectItem value="in">
                      <span className="flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-emerald-400" />
                        Entrada
                      </span>
                    </SelectItem>
                    <SelectItem value="out">
                      <span className="flex items-center gap-2">
                        <TrendingDown className="h-4 w-4 text-red-400" />
                        Salida
                      </span>
                    </SelectItem>
                    <SelectItem value="adjustment">
                      <span className="flex items-center gap-2">
                        <Edit className="h-4 w-4 text-amber-400" />
                        Ajuste
                      </span>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label htmlFor="inventory-movement-quantity" className="mb-1 block text-sm text-zinc-300">Cantidad</label>
                <Input
                  id="inventory-movement-quantity"
                  type="number"
                  min={1}
                  value={movement.quantity}
                  onChange={(e) =>
                    setMovement({ ...movement, quantity: Math.max(1, parseInt(e.target.value) || 1) })
                  }
                  className="border-zinc-700 bg-zinc-800 text-zinc-200"
                />
              </div>

              <div>
                <label htmlFor="inventory-movement-reason" className="mb-1 block text-sm text-zinc-300">Motivo (opcional)</label>
                <Input
                  id="inventory-movement-reason"
                  value={movement.reason}
                  onChange={(e) => setMovement({ ...movement, reason: e.target.value })}
                  placeholder="Ej: Recepción de proveedor"
                  className="border-zinc-700 bg-zinc-800 text-zinc-200 placeholder:text-zinc-500"
                />
              </div>

              {error && (
                <div className="rounded-lg bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowMovementDialog(false)}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleStockMovement}
              disabled={saving || !selectedProduct}
              className={
                movement.type === "in"
                  ? "bg-emerald-600 text-white hover:bg-emerald-500"
                  : movement.type === "out"
                    ? "bg-red-600 text-white hover:bg-red-500"
                    : "bg-amber-600 text-white hover:bg-amber-500"
              }
            >
              {saving ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Guardando…
                </>
              ) : movement.type === "in" ? (
                "Registrar entrada"
              ) : movement.type === "out" ? (
                "Registrar salida"
              ) : (
                "Aplicar ajuste"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
