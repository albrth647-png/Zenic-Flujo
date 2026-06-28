export interface Product {
  id: number
  sku: string
  name: string
  description?: string
  category?: string
  stock: number
  min_stock: number
  price: number
  created_at?: string
  user_id?: number
}

export interface StockMovement {
  id: string
  product_id: string
  type: "in" | "out" | "adjustment"
  quantity: number
  reason: string
  created_at: string
}

export interface LowStockAlert {
  product: Product
  current_stock: number
  deficit: number
}
