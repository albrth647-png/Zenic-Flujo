"""
API v2 router para Inventory — espejo de Flask.

# Audience: External + SPA (MiNegocioPage usa /stats)
# Purpose: Inventory stats (usado por MiNegocioPage) + CRUD products para integraciones externas.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.hat.level5_tools.business.inventory.service import InventoryService
from typing import Any

router = APIRouter(prefix="/api/v2/inventory", tags=["inventory"])

_svc = InventoryService()


class ProductCreate(BaseModel):
    sku: str
    name: str
    description: str = ""
    category: str = "General"
    stock: int = 0
    min_stock: int = 0
    price: float = 0.0


class StockUpdate(BaseModel):
    quantity: int
    movement_type: str = "adjustment"  # in | out | adjustment
    reason: str = ""


@router.get("/products")
async def list_products(limit: int = Query(50, le=200)) -> list[dict]:
    return _svc.list_products(limit=limit)


@router.post("/products", status_code=201)
async def add_product(product: ProductCreate) -> dict[str, Any]:
    return _svc.add_product(**product.model_dump())


@router.get("/products/{product_id}")
async def get_product(product_id: int) -> dict[str, Any]:
    p = _svc.get_product(product_id)
    if not p:
        raise HTTPException(404, "Producto no encontrado")
    return p


@router.put("/products/{product_id}/stock")
async def update_stock(product_id: int, update: StockUpdate) -> dict[str, Any]:
    result = _svc.update_stock(
        product_id, update.quantity,
        movement_type=update.movement_type,
        reason=update.reason,
    )
    if not result:
        raise HTTPException(404, "Producto no encontrado")
    return result


@router.get("/stats")
async def get_inventory_stats() -> dict[str, Any]:
    products = _svc.list_products(limit=10000)
    total = len(products)
    low_stock = sum(1 for p in products if p.get("stock", 0) <= p.get("min_stock", 0) and p.get("stock", 0) > 0)
    out_of_stock = sum(1 for p in products if p.get("stock", 0) == 0)
    total_value = sum(p.get("stock", 0) * p.get("price", 0) for p in products)
    return {"total": total, "low_stock": low_stock, "out_of_stock": out_of_stock, "total_value": total_value}
