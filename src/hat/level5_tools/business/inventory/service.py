"""
Workflow Determinista — Inventory Service
"""

from src.events.bus import EventBus
from src.hat.level5_tools.business.inventory.repository import InventoryRepository
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class InventoryService:
    def __init__(self, event_bus: EventBus | None = None):
        self._repo = InventoryRepository()
        self._event_bus = event_bus or EventBus()

    def add_product(
        self,
        sku: str,
        name: str,
        description: str = "",
        category: str = "",
        stock: int = 0,
        min_stock: int = 10,
        price: float = 0.0,
        user_id: int | None = None,
    ) -> dict:
        product = self._repo.create_product(sku, name, description, category, stock, min_stock, price, user_id)
        logger.info(f"Producto creado: {name} (SKU: {sku})")
        return product

    def update_stock(
        self, product_id: int, quantity: int, movement_type: str = "adjustment", reason: str = ""
    ) -> dict | None:
        product = self._repo.get_product(product_id)
        if not product:
            return None

        if movement_type == "in":
            new_stock = product["stock"] + quantity
        elif movement_type == "out":
            new_stock = max(0, product["stock"] - quantity)
        else:  # adjustment
            new_stock = quantity

        self._repo.add_movement(product_id, movement_type, quantity, reason)
        result = self._repo.update_product(product_id, stock=new_stock)

        if result and result["stock"] <= result["min_stock"]:
            self._event_bus.publish("inventory.stock_low", dict(result))
        if result and result["stock"] == 0:
            self._event_bus.publish("inventory.stock_out", dict(result))

        return result

    def get_product(self, product_id: int) -> dict | None:
        return self._repo.get_product(product_id)

    def list_products(
        self, category: str | None = None, low_stock_only: bool = False, user_id: int | None = None
    ) -> list[dict]:
        return self._repo.list_products(category, low_stock_only, user_id)

    def update_product(self, product_id: int, **fields) -> dict | None:
        """Actualiza campos de un producto (nombre, precio, descripción, etc.)."""
        return self._repo.update_product(product_id, **fields)

    def delete_product(self, product_id: int) -> bool:
        return self._repo.delete_product(product_id)

    def get_low_stock_products(self) -> list[dict]:
        return self._repo.get_low_stock()

    def get_stats(self) -> dict:
        return self._repo.get_stats()
