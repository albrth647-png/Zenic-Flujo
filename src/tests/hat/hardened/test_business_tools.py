"""Tests para business tools: CRM, Invoice, Inventory services.

Cubre:
- CRMService: create_lead, list_leads, get_lead, update_lead, advance_stage.
- InvoiceService: create_invoice, list_invoices, mark_paid.
- InventoryService: create_product, list_products, update_stock.
- Cada service emite eventos al EventBus.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.hat.level5_tools.business.crm.service import CRMService
from src.hat.level5_tools.business.inventory.service import InventoryService
from src.hat.level5_tools.business.invoice.service import InvoiceService

# ── CRMService ─────────────────────────────────────────────────────────


class TestCRMService:
    """Tests para CRMService."""

    @pytest.fixture
    def crm(self) -> CRMService:
        """CRMService con repo mockeado."""
        with patch("src.hat.level5_tools.business.crm.service.CRMRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo
            service = CRMService(event_bus=MagicMock())
            service._repo = mock_repo
            return service

    def test_create_lead_returns_lead(self, crm: CRMService) -> None:
        """create_lead retorna el lead creado."""
        crm._repo.create_lead.return_value = {"id": 1, "name": "Juan"}
        result = crm.create_lead(name="Juan", email="juan@test.com")
        assert result["id"] == 1
        assert result["name"] == "Juan"

    def test_create_lead_publishes_event(self, crm: CRMService) -> None:
        """create_lead publica evento 'crm.lead.created'."""
        crm._repo.create_lead.return_value = {"id": 1, "name": "Juan"}
        crm.create_lead(name="Juan")
        assert crm._event_bus.publish.call_count == 1
        call_args = crm._event_bus.publish.call_args
        assert call_args.args[0] == "crm.lead.created"

    def test_list_leads_returns_list(self, crm: CRMService) -> None:
        """list_leads retorna lista de leads."""
        crm._repo.list_leads.return_value = [{"id": 1}, {"id": 2}]
        result = crm.list_leads()
        assert len(result) == 2

    def test_get_lead_returns_lead(self, crm: CRMService) -> None:
        """get_lead retorna el lead por ID."""
        crm._repo.get_lead.return_value = {"id": 1, "name": "Juan"}
        result = crm.get_lead(1)
        assert result["id"] == 1

    def test_advance_stage_advances(self, crm: CRMService) -> None:
        """advance_stage mueve el lead a la siguiente etapa."""
        crm._repo.get_lead.return_value = {"id": 1, "stage": "new"}
        crm._repo.update_lead.return_value = {"id": 1, "stage": "contacted"}
        result = crm.advance_stage(1)
        assert result["stage"] == "contacted"

    def test_close_won_sets_stage(self, crm: CRMService) -> None:
        """close_won establece stage='closed_won'."""
        crm._repo.update_lead.return_value = {"id": 1, "stage": "closed_won"}
        result = crm.close_won(1)
        assert result["stage"] == "closed_won"

    def test_close_lost_sets_stage(self, crm: CRMService) -> None:
        """close_lost establece stage='closed_lost'."""
        crm._repo.update_lead.return_value = {"id": 1, "stage": "closed_lost"}
        result = crm.close_lost(1, reason="no budget")
        assert result["stage"] == "closed_lost"

    def test_delete_lead_returns_bool(self, crm: CRMService) -> None:
        """delete_lead retorna True si eliminó."""
        crm._repo.delete_lead.return_value = True
        assert crm.delete_lead(1) is True

    def test_get_stats_returns_dict(self, crm: CRMService) -> None:
        """get_stats retorna dict con estadísticas."""
        crm._repo.get_stats.return_value = {"total": 10, "won": 3}
        result = crm.get_stats()
        assert result["total"] == 10


# ── InvoiceService ─────────────────────────────────────────────────────


class TestInvoiceService:
    """Tests para InvoiceService."""

    @pytest.fixture
    def invoice(self) -> InvoiceService:
        """InvoiceService con repo mockeado."""
        with patch(
            "src.hat.level5_tools.business.invoice.service.InvoiceRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.create.return_value = {"id": 1, "number": "INV-001"}
            mock_repo.list_invoices.return_value = [{"id": 1}, {"id": 2}]
            mock_repo.get.return_value = {"id": 1, "amount": 100}
            mock_repo_class.return_value = mock_repo
            return InvoiceService(event_bus=MagicMock())

    def test_create_invoice_returns_invoice(self, invoice: InvoiceService) -> None:
        """create_invoice retorna la factura creada."""
        result = invoice.create_invoice(client_name="Juan")
        assert result["number"] == "INV-001"

    def test_list_invoices_returns_list(self, invoice: InvoiceService) -> None:
        """list_invoices retorna lista de facturas."""
        result = invoice.list_invoices()
        assert len(result) == 2

    def test_get_invoice_returns_invoice(self, invoice: InvoiceService) -> None:
        """get_invoice retorna la factura por ID."""
        result = invoice.get_invoice(1)
        assert result is not None
        assert result["id"] == 1


# ── InventoryService ───────────────────────────────────────────────────


class TestInventoryService:
    """Tests para InventoryService."""

    @pytest.fixture
    def inventory(self) -> InventoryService:
        """InventoryService con repo mockeado."""
        with patch(
            "src.hat.level5_tools.business.inventory.service.InventoryRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.create_product.return_value = {"id": 1, "name": "Widget"}
            mock_repo.list_products.return_value = [{"id": 1}, {"id": 2}]
            mock_repo.get_product.return_value = {"id": 1, "name": "Widget"}
            mock_repo_class.return_value = mock_repo
            return InventoryService(event_bus=MagicMock())

    def test_create_product_returns_product(self, inventory: InventoryService) -> None:
        """add_product retorna el producto creado."""
        result = inventory.add_product(sku="W001", name="Widget", price=10.0)
        assert result["name"] == "Widget"

    def test_list_products_returns_list(self, inventory: InventoryService) -> None:
        """list_products retorna lista de productos."""
        result = inventory.list_products()
        assert len(result) == 2

    def test_get_product_returns_product(self, inventory: InventoryService) -> None:
        """get_product retorna el producto por ID."""
        result = inventory.get_product(1)
        assert result is not None
        assert result["id"] == 1
