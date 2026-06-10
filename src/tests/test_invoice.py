"""
Workflow Determinista — Tests del Invoice Service
Tests unitarios para el servicio de facturación: crear, listar, pagar, cancelar, cálculos.
"""
from datetime import datetime


class TestInvoiceModels:
    """Tests para constantes y modelos de factura."""

    def test_invoice_statuses_defined(self):
        """Test: INVOICE_STATUSES contiene los estados correctos."""
        from src.tools.invoice.models import INVOICE_STATUSES
        assert "pending" in INVOICE_STATUSES
        assert "paid" in INVOICE_STATUSES
        assert "overdue" in INVOICE_STATUSES
        assert "cancelled" in INVOICE_STATUSES

    def test_invoice_statuses_count(self):
        """Test: hay exactamente 4 estados de factura."""
        from src.tools.invoice.models import INVOICE_STATUSES
        assert len(INVOICE_STATUSES) == 4


class TestInvoiceService:
    """Tests para la clase InvoiceService."""

    def test_create_invoice_valid_data(self, invoice_service):
        """Test: crear una factura con datos válidos."""
        result = invoice_service.create_invoice(
            client_name="Cliente Test",
            client_email="cliente@test.com",
            items=[{"description": "Servicio", "quantity": 1, "unit_price": 100.0}],
        )
        assert result["client_name"] == "Cliente Test"
        assert result["client_email"] == "cliente@test.com"
        assert result["status"] == "pending"

    def test_create_invoice_with_items(self, invoice_service):
        """Test: crear factura con múltiples items y verificar cálculos."""
        items = [
            {"description": "Servicio A", "quantity": 2, "unit_price": 50.0},
            {"description": "Servicio B", "quantity": 1, "unit_price": 100.0},
        ]
        result = invoice_service.create_invoice(
            client_name="Multi Items",
            items=items,
        )
        # subtotal = 2*50 + 1*100 = 200
        assert result["subtotal"] == 200.0
        # tax_amount = 200 * 0.16 = 32
        assert result["tax_amount"] == 32.0
        # total = 200 + 32 - 0 = 232
        assert result["total"] == 232.0

    def test_invoice_number_format(self, invoice_service):
        """Test: el número de factura sigue el formato FAC-YYYY-NNNN."""
        result = invoice_service.create_invoice(
            client_name="Format Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 10.0}],
        )
        number = result["number"]
        assert number.startswith("FAC-")
        current_year = str(datetime.now().year)
        assert current_year in number
        parts = number.split("-")
        assert parts[0] == "FAC"
        assert parts[1] == current_year

    def test_list_invoices_all(self, invoice_service):
        """Test: listar todas las facturas."""
        invoice_service.create_invoice(
            client_name="C1",
            items=[{"description": "I1", "quantity": 1, "unit_price": 100.0}],
        )
        invoice_service.create_invoice(
            client_name="C2",
            items=[{"description": "I2", "quantity": 1, "unit_price": 200.0}],
        )
        invoices = invoice_service.list_invoices()
        assert len(invoices) >= 2

    def test_list_invoices_by_status(self, invoice_service):
        """Test: filtrar facturas por estado."""
        inv1 = invoice_service.create_invoice(
            client_name="Pending One",
            items=[{"description": "P1", "quantity": 1, "unit_price": 50.0}],
        )
        inv2 = invoice_service.create_invoice(
            client_name="To Pay",
            items=[{"description": "P2", "quantity": 1, "unit_price": 150.0}],
        )
        # Mark one as paid
        invoice_service.mark_paid(inv2["id"])

        pending = invoice_service.list_invoices(status="pending")
        paid = invoice_service.list_invoices(status="paid")

        assert all(inv["status"] == "pending" for inv in pending)
        assert all(inv["status"] == "paid" for inv in paid)

    def test_get_invoice_by_id(self, invoice_service):
        """Test: obtener factura por ID."""
        created = invoice_service.create_invoice(
            client_name="Get Test",
            client_email="get@test.com",
            items=[{"description": "Item", "quantity": 1, "unit_price": 75.0}],
        )
        result = invoice_service.get_invoice(created["id"])
        assert result is not None
        assert result["id"] == created["id"]
        assert result["client_name"] == "Get Test"
        assert result["client_email"] == "get@test.com"

    def test_update_status_pending_to_paid(self, invoice_service):
        """Test: cambiar estado de pending a paid."""
        created = invoice_service.create_invoice(
            client_name="Status Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 200.0}],
        )
        assert created["status"] == "pending"
        result = invoice_service.mark_paid(created["id"])
        assert result["status"] == "paid"
        assert result["paid_at"] is not None

    def test_calculate_totals_with_discount(self, invoice_service):
        """Test: cálculo de subtotal, tax, descuento y total."""
        items = [{"description": "Servicio", "quantity": 3, "unit_price": 100.0}]
        result = invoice_service.create_invoice(
            client_name="Calc Test",
            items=items,
            tax_rate=0.16,
            discount=50.0,
        )
        # subtotal = 3 * 100 = 300
        assert result["subtotal"] == 300.0
        # tax = 300 * 0.16 = 48
        assert result["tax_amount"] == 48.0
        # discount = 50
        assert result["discount"] == 50.0
        # total = 300 + 48 - 50 = 298
        assert result["total"] == 298.0

    def test_cancel_invoice(self, invoice_service):
        """Test: cancelar una factura cambia el estado a cancelled."""
        created = invoice_service.create_invoice(
            client_name="Cancel Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 300.0}],
        )
        result = invoice_service.cancel(created["id"])
        assert result["status"] == "cancelled"

    def test_default_tax_rate_16_percent(self, invoice_service):
        """Test: la tasa de impuesto por defecto es 16%."""
        items = [{"description": "Item", "quantity": 1, "unit_price": 100.0}]
        result = invoice_service.create_invoice(
            client_name="Tax Test",
            items=items,
        )
        assert result["tax_rate"] == 0.16
        assert result["tax_amount"] == 16.0

    def test_empty_items_invoice(self, invoice_service):
        """Test: crear factura sin items resulta en totales cero."""
        result = invoice_service.create_invoice(
            client_name="Empty Items",
            items=[],
        )
        assert result["subtotal"] == 0.0
        assert result["tax_amount"] == 0.0
        assert result["total"] == 0.0

    def test_negative_discount_invoice(self, invoice_service):
        """Test: un descuento negativo incrementa el total."""
        items = [{"description": "Item", "quantity": 1, "unit_price": 100.0}]
        result = invoice_service.create_invoice(
            client_name="Neg Discount",
            items=items,
            discount=-20.0,
        )
        # subtotal=100, tax=16, discount=-20 => total = 100+16-(-20) = 136
        assert result["total"] == 136.0

    def test_custom_tax_rate(self, invoice_service):
        """Test: crear factura con tasa de impuesto personalizada."""
        items = [{"description": "Item", "quantity": 1, "unit_price": 100.0}]
        result = invoice_service.create_invoice(
            client_name="Custom Tax",
            items=items,
            tax_rate=0.21,
        )
        assert result["tax_rate"] == 0.21
        assert result["tax_amount"] == 21.0

    def test_invoice_due_date(self, invoice_service):
        """Test: la fecha de vencimiento por defecto es 30 días."""
        result = invoice_service.create_invoice(
            client_name="Due Date Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 50.0}],
        )
        assert result["due_date"] is not None
        # Verify due_date is a valid date string
        due = datetime.strptime(result["due_date"], "%Y-%m-%d")
        assert due > datetime.now()

    def test_invoice_stats(self, invoice_service):
        """Test: obtener estadísticas de facturación."""
        invoice_service.create_invoice(
            client_name="Stats1",
            items=[{"description": "I", "quantity": 1, "unit_price": 100.0}],
        )
        invoice_service.create_invoice(
            client_name="Stats2",
            items=[{"description": "I", "quantity": 1, "unit_price": 200.0}],
        )
        stats = invoice_service.get_stats()
        assert "total" in stats
        assert stats["total"] >= 2

    def test_mark_overdue_invoice(self, invoice_service):
        """Test: marcar factura como vencida."""
        created = invoice_service.create_invoice(
            client_name="Overdue Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 100.0}],
        )
        # Only pending invoices can be marked overdue
        result = invoice_service.mark_overdue(created["id"])
        assert result["status"] == "overdue"

    def test_mark_overdue_paid_invoice_no_change(self, invoice_service):
        """Test: una factura pagada no puede marcarse como vencida."""
        created = invoice_service.create_invoice(
            client_name="Paid Not Overdue",
            items=[{"description": "Item", "quantity": 1, "unit_price": 100.0}],
        )
        invoice_service.mark_paid(created["id"])
        result = invoice_service.mark_overdue(created["id"])
        # Should still be paid (not changed to overdue)
        assert result["status"] == "paid"
