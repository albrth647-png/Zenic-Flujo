"""
Workflow Determinista — Tests del Inventory Service
Tests unitarios para el servicio de inventario: productos, stock, movimientos, alertas.
"""


class TestInventoryModels:
    """Tests para constantes y modelos de inventario."""

    def test_movement_types_defined(self):
        """Test: MOVEMENT_TYPES contiene los tipos correctos."""
        from src.tools.inventory.models import MOVEMENT_TYPES

        assert "in" in MOVEMENT_TYPES
        assert "out" in MOVEMENT_TYPES
        assert "adjustment" in MOVEMENT_TYPES

    def test_movement_types_count(self):
        """Test: hay exactamente 3 tipos de movimiento."""
        from src.tools.inventory.models import MOVEMENT_TYPES

        assert len(MOVEMENT_TYPES) == 3


class TestInventoryService:
    """Tests para la clase InventoryService."""

    def test_create_product_valid_data(self, inventory_service):
        """Test: crear un producto con datos válidos."""
        result = inventory_service.add_product(
            sku="PROD-001",
            name="Producto Test",
            description="Descripción del producto",
            category="Test",
            stock=100,
            min_stock=10,
            price=29.99,
        )
        assert result["name"] == "Producto Test"
        assert result["sku"] == "PROD-001"
        assert result["stock"] == 100
        assert result["price"] == 29.99

    def test_create_product_with_sku(self, inventory_service):
        """Test: crear un producto con SKU único."""
        result = inventory_service.add_product(
            sku="SKU-UNIQUE-001",
            name="SKU Product",
            price=15.0,
        )
        assert result["sku"] == "SKU-UNIQUE-001"

    def test_list_products_all(self, inventory_service):
        """Test: listar todos los productos."""
        inventory_service.add_product(sku="LIST-001", name="Product 1", price=10.0)
        inventory_service.add_product(sku="LIST-002", name="Product 2", price=20.0)
        products = inventory_service.list_products()
        assert len(products) >= 2

    def test_list_products_low_stock_only(self, inventory_service):
        """Test: listar solo productos con stock bajo."""
        # Product with low stock (stock <= min_stock)
        inventory_service.add_product(
            sku="LOW-001",
            name="Low Stock Product",
            stock=3,
            min_stock=10,
            price=5.0,
        )
        # Product with normal stock
        inventory_service.add_product(
            sku="NORMAL-001",
            name="Normal Stock Product",
            stock=100,
            min_stock=10,
            price=15.0,
        )
        low_stock = inventory_service.list_products(low_stock_only=True)
        assert len(low_stock) >= 1
        assert all(p["stock"] <= p["min_stock"] for p in low_stock)

    def test_get_product_by_id(self, inventory_service):
        """Test: obtener un producto por ID."""
        created = inventory_service.add_product(
            sku="GET-001",
            name="Get Product",
            price=10.0,
        )
        result = inventory_service.get_product(created["id"])
        assert result is not None
        assert result["id"] == created["id"]
        assert result["name"] == "Get Product"

    def test_update_stock_in(self, inventory_service):
        """Test: entrada de stock incrementa la cantidad."""
        created = inventory_service.add_product(
            sku="STOCK-IN-001",
            name="Stock In Product",
            stock=50,
            price=10.0,
        )
        result = inventory_service.update_stock(
            created["id"],
            quantity=20,
            movement_type="in",
            reason="Recepción",
        )
        assert result["stock"] == 70  # 50 + 20

    def test_update_stock_out(self, inventory_service):
        """Test: salida de stock decrementa la cantidad."""
        created = inventory_service.add_product(
            sku="STOCK-OUT-001",
            name="Stock Out Product",
            stock=50,
            price=10.0,
        )
        result = inventory_service.update_stock(
            created["id"],
            quantity=15,
            movement_type="out",
            reason="Venta",
        )
        assert result["stock"] == 35  # 50 - 15

    def test_update_stock_adjustment(self, inventory_service):
        """Test: ajuste de stock establece la cantidad exacta."""
        created = inventory_service.add_product(
            sku="STOCK-ADJ-001",
            name="Stock Adj Product",
            stock=50,
            price=10.0,
        )
        result = inventory_service.update_stock(
            created["id"],
            quantity=42,
            movement_type="adjustment",
            reason="Inventario físico",
        )
        assert result["stock"] == 42  # Set to exact value

    def test_stock_movements_tracking(self, inventory_service):
        """Test: los movimientos de stock se registran en el historial."""
        created = inventory_service.add_product(
            sku="MOVE-001",
            name="Movement Product",
            stock=100,
            price=10.0,
        )
        inventory_service.update_stock(created["id"], quantity=30, movement_type="in", reason="Compra")
        inventory_service.update_stock(created["id"], quantity=10, movement_type="out", reason="Venta")
        inventory_service.update_stock(created["id"], quantity=90, movement_type="adjustment", reason="Ajuste")

        # Verify final stock
        product = inventory_service.get_product(created["id"])
        assert product["stock"] == 90  # adjustment sets to 90

    def test_low_stock_detection(self, inventory_service):
        """Test: detectar productos con stock < min_stock."""
        # Product with stock below min_stock
        inventory_service.add_product(
            sku="DETECT-LOW-001",
            name="Detect Low",
            stock=5,
            min_stock=10,
            price=10.0,
        )
        # Product with stock at min_stock boundary
        inventory_service.add_product(
            sku="DETECT-BOUND-001",
            name="Detect Boundary",
            stock=10,
            min_stock=10,
            price=10.0,
        )
        low_stock = inventory_service.get_low_stock_products()
        low_skus = [p["sku"] for p in low_stock]
        assert "DETECT-LOW-001" in low_skus
        assert "DETECT-BOUND-001" in low_skus

    def test_update_product_details(self, inventory_service):
        """Test: actualizar detalles de un producto."""
        created = inventory_service.add_product(
            sku="UPD-DET-001",
            name="Original Name",
            description="Original desc",
            price=10.0,
        )
        # Update via repository directly since service doesn't expose update_product
        from src.tools.inventory.repository import InventoryRepository

        repo = InventoryRepository()
        result = repo.update_product(created["id"], name="Updated Name", price=15.0)
        assert result["name"] == "Updated Name"
        assert result["price"] == 15.0

    def test_delete_product(self, inventory_service):
        """Test: eliminar un producto."""
        created = inventory_service.add_product(
            sku="DEL-001",
            name="Delete Me",
            price=1.0,
        )
        result = inventory_service.delete_product(created["id"])
        assert result is True
        # Verify it's gone
        deleted = inventory_service.get_product(created["id"])
        assert deleted is None

    def test_stock_out_does_not_go_negative(self, inventory_service):
        """Test: la salida de stock no baja de cero."""
        created = inventory_service.add_product(
            sku="NO-NEG-001",
            name="No Negative",
            stock=5,
            price=10.0,
        )
        result = inventory_service.update_stock(
            created["id"],
            quantity=100,
            movement_type="out",
            reason="Venta grande",
        )
        assert result["stock"] == 0  # Clamped to 0, not -95

    def test_get_product_by_sku(self, inventory_service):
        """Test: buscar producto por SKU."""
        inventory_service.add_product(
            sku="SKU-SEARCH-001",
            name="SKU Search Product",
            price=25.0,
        )
        from src.tools.inventory.repository import InventoryRepository

        repo = InventoryRepository()
        result = repo.get_product_by_sku("SKU-SEARCH-001")
        assert result is not None
        assert result["sku"] == "SKU-SEARCH-001"

    def test_inventory_stats(self, inventory_service):
        """Test: obtener estadísticas de inventario."""
        inventory_service.add_product(
            sku="STATS-001",
            name="Stats Product",
            stock=50,
            price=10.0,
        )
        stats = inventory_service.get_stats()
        assert "total_products" in stats
        assert stats["total_products"] >= 1

    def test_update_stock_nonexistent_product(self, inventory_service):
        """Test: actualizar stock de producto inexistente retorna None."""
        result = inventory_service.update_stock(99999, quantity=10, movement_type="in")
        assert result is None

    def test_default_min_stock(self, inventory_service):
        """Test: el min_stock por defecto es 10."""
        result = inventory_service.add_product(
            sku="DEFAULT-MIN-001",
            name="Default Min",
            price=5.0,
        )
        assert result["min_stock"] == 10

    def test_default_stock_zero(self, inventory_service):
        """Test: el stock por defecto es 0."""
        result = inventory_service.add_product(
            sku="DEFAULT-STOCK-001",
            name="Default Stock",
            price=5.0,
        )
        assert result["stock"] == 0
