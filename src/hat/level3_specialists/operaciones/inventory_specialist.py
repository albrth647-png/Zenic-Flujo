"""
HAT NIVEL 3 — InventorySpecialist
==================================

UNA SOLA RESPONSABILIDAD: Inventario/stock.

Coordina los workers del Nivel 4 para la tool Inventory (Nivel 5):
- add_product, update_stock, update_product, get_product,
  list_products, delete_product, get_low_stock_products, get_stats

Routing por keywords:
- "añadir", "agregar", "crear producto" → add_product
- "stock", "ajustar stock" → update_stock
- "listar productos", "ver inventario" → list_products
- "stock bajo", "alerta stock" → get_low_stock_products
- Default: list_products
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class InventorySpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: inventario/stock."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="inventory",
            responsibility="inventario_stock",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="inventory",
            agent_name="Inventory",
            domain="operaciones",
            tier="specialist",
            capabilities=[
                "add_product", "update_stock", "update_product", "get_product",
                "list_products", "delete_product", "get_low_stock_products", "get_stats",
            ],
            cost_per_call=0.0,
            avg_latency_ms=50,
            orbital_keywords=[
                "inventario", "stock", "producto", "sku", "almacén", "almacen",
                "mercancía", "mercancia", "cantidad", "existencia",
            ],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or subtask.get("message") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        if any(kw in desc for kw in ["stock bajo", "alerta stock", "bajo stock", "agotado"]):
            return "inventory", "get_low_stock_products", params
        if any(kw in desc for kw in ["añadir", "agregar", "crear producto", "nuevo producto", "alta producto"]):
            return "inventory", "add_product", params
        if any(kw in desc for kw in ["ajustar stock", "actualizar stock", "entrada stock", "salida stock", "movimiento stock"]):
            return "inventory", "update_stock", params
        if any(kw in desc for kw in ["eliminar", "borrar", "delete"]):
            return "inventory", "delete_product", params
        if any(kw in desc for kw in ["estadística", "stats", "resumen", "dashboard"]):
            return "inventory", "get_stats", params
        if any(kw in desc for kw in ["actualizar", "modificar", "update"]) and "producto" in desc:
            return "inventory", "update_product", params
        if any(kw in desc for kw in ["obtener", "buscar", "get"]) and "producto" in desc:
            return "inventory", "get_product", params
        if any(kw in desc for kw in ["listar", "mostrar", "ver inventario", "ver productos"]):
            return "inventory", "list_products", params

        # Default seguro: listar productos
        return "inventory", "list_products", params

    def handle(self, subtask: Subtask) -> SpecialistResult:
        """Ejecuta el specialist: route → invoke tool → return result."""
        import time
        start = time.monotonic()

        tool_name, action_name, params = self.route_action(subtask)
        tool = self._tools.get(tool_name)

        if tool is None:
            return SpecialistResult(
                status="failed",
                error=f"tool '{tool_name}' not available",
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            method = getattr(tool, action_name)
            result = method(**params) if params else method()
            return SpecialistResult(
                status="completed",
                action=action_name,
                result=result,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return SpecialistResult(
                status="failed",
                error=str(exc),
                action=action_name,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
