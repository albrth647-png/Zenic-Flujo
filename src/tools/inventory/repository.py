"""
Workflow Determinista — Inventory Repository
"""

from src.data.database_manager import DatabaseManager
from src.utils.sql import build_update_query


class InventoryRepository:
    def __init__(self):
        self._db = DatabaseManager()

    def create_product(
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
        cursor = self._db.execute(
            """INSERT INTO products (sku, name, description, category, stock, min_stock, price, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (sku, name, description, category, stock, min_stock, price, user_id or 1),
        )
        self._db.commit()
        return self.get_product(cursor.lastrowid)

    def get_product(self, product_id: int) -> dict | None:
        return self._db.fetchone("SELECT * FROM products WHERE id = ?", (product_id,))

    def get_product_by_sku(self, sku: str) -> dict | None:
        return self._db.fetchone("SELECT * FROM products WHERE sku = ?", (sku,))

    def list_products(
        self, category: str | None = None, low_stock_only: bool = False, user_id: int | None = None
    ) -> list[dict]:
        if low_stock_only and user_id:
            return self._db.fetchall(
                "SELECT * FROM products WHERE stock <= min_stock AND user_id = ? ORDER BY name",
                (user_id,),
            )
        elif low_stock_only:
            return self._db.fetchall("SELECT * FROM products WHERE stock <= min_stock ORDER BY name")
        if category:
            return self._db.fetchall("SELECT * FROM products WHERE category = ? ORDER BY name", (category,))
        if user_id:
            return self._db.fetchall("SELECT * FROM products WHERE user_id = ? ORDER BY name", (user_id,))
        return self._db.fetchall("SELECT * FROM products ORDER BY name")

    def update_product(self, product_id: int, **fields) -> dict | None:
        allowed = {"sku", "name", "description", "category", "stock", "min_stock", "price"}
        result = build_update_query("products", allowed, fields)
        if result is None:
            return self.get_product(product_id)
        sql, params = result
        # Append el valor del WHERE (id = ?) al final de los params
        self._db.execute(sql, (*params, product_id))
        self._db.commit()
        return self.get_product(product_id)

    def delete_product(self, product_id: int) -> bool:
        self._db.execute("DELETE FROM stock_movements WHERE product_id = ?", (product_id,))
        self._db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        self._db.commit()
        return True

    def add_movement(self, product_id: int, movement_type: str, quantity: int, reason: str = "") -> dict:
        cursor = self._db.execute(
            "INSERT INTO stock_movements (product_id, type, quantity, reason) VALUES (?, ?, ?, ?)",
            (product_id, movement_type, quantity, reason),
        )
        self._db.commit()
        return {"id": cursor.lastrowid, "product_id": product_id}

    def get_movements(self, product_id: int, limit: int = 20) -> list[dict]:
        return self._db.fetchall(
            "SELECT * FROM stock_movements WHERE product_id = ? ORDER BY created_at DESC LIMIT ?",
            (product_id, limit),
        )

    def get_low_stock(self) -> list[dict]:
        return self._db.fetchall("SELECT * FROM products WHERE stock <= min_stock ORDER BY stock ASC")

    def get_stats(self) -> dict:
        stats = self._db.fetchone(
            """SELECT COUNT(*) as total_products,
               SUM(CASE WHEN stock <= min_stock THEN 1 ELSE 0 END) as low_stock,
               SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) as out_of_stock,
               SUM(stock * price) as total_value
               FROM products"""
        )
        return dict(stats) if stats else {}
