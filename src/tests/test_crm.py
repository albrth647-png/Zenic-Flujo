"""
Workflow Determinista — Tests del CRM
Tests unitarios para el servicio CRM: crear leads, actualizar etapas, estadísticas.
"""
import pytest


class TestCRMService:
    """Tests para la clase CRMService."""

    def test_create_lead(self, crm_service):
        """Test: crear un lead nuevo."""
        result = crm_service.create_lead(
            name="Juan Pérez",
            email="juan@test.com",
            phone="+535551234",
            company="Test Corp",
        )
        assert result["name"] == "Juan Pérez"
        assert result["email"] == "juan@test.com"
        assert result["stage"] == "new"

    def test_get_lead(self, crm_service):
        """Test: obtener un lead por ID."""
        created = crm_service.create_lead(name="María", email="maria@test.com")
        result = crm_service.get_lead(created["id"])
        assert result is not None
        assert result["name"] == "María"

    def test_list_leads(self, crm_service):
        """Test: listar leads."""
        crm_service.create_lead(name="Lead 1", email="lead1@test.com")
        crm_service.create_lead(name="Lead 2", email="lead2@test.com")
        leads = crm_service.list_leads()
        assert len(leads) >= 2

    def test_list_leads_by_stage(self, crm_service):
        """Test: filtrar leads por etapa."""
        crm_service.create_lead(name="New Lead", email="new@test.com")
        leads = crm_service.list_leads(stage="new")
        assert all(lead["stage"] == "new" for lead in leads)

    def test_update_lead(self, crm_service):
        """Test: actualizar datos de un lead."""
        created = crm_service.create_lead(name="Original", email="orig@test.com")
        result = crm_service.update_lead(created["id"], name="Actualizado")
        assert result["name"] == "Actualizado"

    def test_advance_stage(self, crm_service):
        """Test: avanzar un lead de etapa."""
        created = crm_service.create_lead(name="Test", email="test@test.com")
        result = crm_service.advance_stage(created["id"])
        assert result["stage"] == "contacted"

    def test_close_won(self, crm_service):
        """Test: cerrar un lead como ganado."""
        created = crm_service.create_lead(name="Winner", email="win@test.com")
        result = crm_service.close_won(created["id"])
        assert result["stage"] == "closed_won"

    def test_close_lost(self, crm_service):
        """Test: cerrar un lead como perdido."""
        created = crm_service.create_lead(name="Loser", email="lose@test.com")
        result = crm_service.close_lost(created["id"])
        assert result["stage"] == "closed_lost"

    def test_delete_lead(self, crm_service):
        """Test: eliminar un lead."""
        created = crm_service.create_lead(name="ToDelete", email="del@test.com")
        result = crm_service.delete_lead(created["id"])
        assert result is True

    def test_get_stats(self, crm_service):
        """Test: obtener estadísticas del CRM."""
        crm_service.create_lead(name="S1", email="s1@test.com")
        stats = crm_service.get_stats()
        assert "total" in stats


class TestInvoiceService:
    """Tests para la clase InvoiceService."""

    def test_create_invoice(self, invoice_service):
        """Test: crear una factura."""
        result = invoice_service.create_invoice(
            client_name="Cliente Test",
            client_email="cliente@test.com",
            items=[{"description": "Servicio", "quantity": 1, "price": 100.0}],
        )
        assert result["client_name"] == "Cliente Test"
        assert result["status"] == "pending"

    def test_get_invoice(self, invoice_service):
        """Test: obtener una factura por ID."""
        created = invoice_service.create_invoice(
            client_name="Test Client",
            items=[{"description": "Item", "quantity": 1, "price": 50.0}],
        )
        result = invoice_service.get_invoice(created["id"])
        assert result is not None
        assert result["client_name"] == "Test Client"

    def test_mark_paid(self, invoice_service):
        """Test: marcar factura como pagada."""
        created = invoice_service.create_invoice(
            client_name="Pago Test",
            items=[{"description": "Item", "quantity": 1, "price": 200.0}],
        )
        result = invoice_service.mark_paid(created["id"])
        assert result["status"] == "paid"

    def test_cancel_invoice(self, invoice_service):
        """Test: cancelar una factura."""
        created = invoice_service.create_invoice(
            client_name="Cancel Test",
            items=[{"description": "Item", "quantity": 1, "price": 300.0}],
        )
        result = invoice_service.cancel(created["id"])
        assert result["status"] == "cancelled"

    def test_list_invoices(self, invoice_service):
        """Test: listar facturas."""
        invoice_service.create_invoice(client_name="C1", items=[{"description": "I1", "quantity": 1, "price": 100.0}])
        invoice_service.create_invoice(client_name="C2", items=[{"description": "I2", "quantity": 1, "price": 200.0}])
        invoices = invoice_service.list_invoices()
        assert len(invoices) >= 2

    def test_get_stats(self, invoice_service):
        """Test: obtener estadísticas de facturación."""
        invoice_service.create_invoice(client_name="Stats", items=[{"description": "I", "quantity": 1, "price": 100.0}])
        stats = invoice_service.get_stats()
        assert "total" in stats


class TestInventoryService:
    """Tests para la clase InventoryService."""

    def test_add_product(self, inventory_service):
        """Test: agregar un producto."""
        result = inventory_service.add_product(
            sku="TEST-001",
            name="Producto Test",
            price=99.99,
            stock=50,
        )
        assert result["name"] == "Producto Test"
        assert result["sku"] == "TEST-001"

    def test_get_product(self, inventory_service):
        """Test: obtener un producto por ID."""
        created = inventory_service.add_product(sku="GET-001", name="Get Test", price=10.0)
        result = inventory_service.get_product(created["id"])
        assert result is not None
        assert result["name"] == "Get Test"

    def test_update_stock(self, inventory_service):
        """Test: actualizar stock de un producto."""
        created = inventory_service.add_product(sku="UPD-001", name="Stock Test", stock=100, price=5.0)
        result = inventory_service.update_stock(created["id"], quantity=10, movement_type="out", reason="Sale")
        assert result is not None

    def test_list_products(self, inventory_service):
        """Test: listar productos."""
        inventory_service.add_product(sku="L1-001", name="List 1", price=10.0)
        inventory_service.add_product(sku="L2-001", name="List 2", price=20.0)
        products = inventory_service.list_products()
        assert len(products) >= 2

    def test_delete_product(self, inventory_service):
        """Test: eliminar un producto."""
        created = inventory_service.add_product(sku="DEL-001", name="Delete Test", price=1.0)
        result = inventory_service.delete_product(created["id"])
        assert result is True

    def test_get_stats(self, inventory_service):
        """Test: obtener estadísticas de inventario."""
        inventory_service.add_product(sku="S-001", name="Stat Product", price=10.0)
        stats = inventory_service.get_stats()
        assert "total_products" in stats
