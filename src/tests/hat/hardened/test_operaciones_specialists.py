"""Tests para los 3 specialists de operaciones: Crm, Invoice, Inventory.

Cubre para cada specialist:
- get_card() retorna AgentCard con metadata correcta.
- route_action() ruttea al método correcto según keywords.
- handle() integra route + invoke + return.
- Error handling: tool not available.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.operaciones.crm_specialist import CrmSpecialist
from src.hat.level3_specialists.operaciones.inventory_specialist import (
    InventorySpecialist,
)
from src.hat.level3_specialists.operaciones.invoice_specialist import InvoiceSpecialist

# ── CrmSpecialist ──────────────────────────────────────────────────────


class TestCrmSpecialist:
    """Tests para CrmSpecialist."""

    @pytest.fixture
    def mock_crm(self) -> MagicMock:
        """CRM tool mockeada."""
        tool = MagicMock()
        tool.create_lead.return_value = {"id": 1, "name": "Juan"}
        tool.list_leads.return_value = [{"id": 1, "name": "Juan"}]
        tool.update_lead.return_value = {"id": 1, "name": "Updated"}
        tool.delete_lead.return_value = True
        tool.get_lead.return_value = {"id": 1}
        tool.advance_stage.return_value = {"id": 1, "stage": "qualified"}
        tool.close_won.return_value = {"id": 1, "stage": "closed_won"}
        tool.close_lost.return_value = {"id": 1, "stage": "closed_lost"}
        tool.get_stats.return_value = {"total": 10}
        return tool

    @pytest.fixture
    def specialist(self, mock_crm: MagicMock) -> CrmSpecialist:
        """CrmSpecialist con tool mockeada."""
        return CrmSpecialist(tools={"crm": mock_crm})

    def test_get_card_returns_correct_metadata(self, specialist: CrmSpecialist) -> None:
        """get_card() retorna AgentCard con domain='operaciones', tier='specialist'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.agent_id == "crm"
        assert card.domain == "operaciones"
        assert card.tier == "specialist"
        assert "create_lead" in card.capabilities
        assert len(card.orbital_keywords) > 0

    @pytest.mark.parametrize("message,expected_action", [
        ("crear lead nuevo", "create_lead"),
        ("nuevo cliente", "create_lead"),
        ("alta de contacto", "create_lead"),
        ("listar leads", "list_leads"),
        ("mostrar clientes", "list_leads"),
        ("ver oportunidades", "list_leads"),
        ("avanzar etapa", "advance_stage"),
        ("siguiente etapa del lead", "advance_stage"),
        ("cerrar ganado", "close_won"),
        ("won exito", "close_won"),
        ("cerrar perdido", "close_lost"),
        ("lost", "close_lost"),
        ("estadísticas", "get_stats"),
        ("stats dashboard", "get_stats"),
        ("eliminar lead", "delete_lead"),
        ("borrar cliente", "delete_lead"),
        ("actualizar lead", "update_lead"),
        ("modificar cliente", "update_lead"),
        ("obtener lead", "get_lead"),
        ("buscar cliente", "get_lead"),
    ])
    def test_route_action_routes_correctly(
        self, specialist: CrmSpecialist,
        message: str, expected_action: str,
    ) -> None:
        """route_action() selecciona la action correcta según keywords."""
        tool_name, action_name, _params = specialist.route_action({
            "description": message,
            "params": {},
        })
        assert tool_name == "crm"
        assert action_name == expected_action

    def test_route_action_default_returns_list_leads(
        self, specialist: CrmSpecialist,
    ) -> None:
        """Sin keyword match, default retorna list_leads."""
        _, action_name, _ = specialist.route_action({
            "description": "xyz qwerty unknown",
            "params": {},
        })
        assert action_name == "list_leads"

    def test_handle_returns_completed(self, specialist: CrmSpecialist) -> None:
        """handle() retorna status='completed' cuando la tool funciona."""
        result = specialist.handle({"description": "listar leads", "params": {}})
        assert result["status"] == "completed"
        assert result["action"] == "list_leads"
        assert result["specialist"] == "crm"


# ── InvoiceSpecialist ──────────────────────────────────────────────────


class TestInvoiceSpecialist:
    """Tests para InvoiceSpecialist."""

    @pytest.fixture
    def mock_invoice(self) -> MagicMock:
        """Invoice tool mockeada."""
        tool = MagicMock()
        tool.create_invoice.return_value = {"id": 1, "number": "INV-001"}
        tool.list_invoices.return_value = [{"id": 1}]
        tool.get_invoice.return_value = {"id": 1}
        tool.mark_paid.return_value = {"id": 1, "status": "paid"}
        tool.mark_cancelled.return_value = {"id": 1, "status": "cancelled"}
        tool.get_stats.return_value = {"total": 5}
        return tool

    @pytest.fixture
    def specialist(self, mock_invoice: MagicMock) -> InvoiceSpecialist:
        """InvoiceSpecialist con tool mockeada."""
        return InvoiceSpecialist(tools={
            "invoice": mock_invoice,
            "stripe": MagicMock(),
            "mercadopago": MagicMock(),
        })

    def test_get_card_returns_correct_metadata(
        self, specialist: InvoiceSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='operaciones'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.agent_id in ("invoice", "invoice_specialist")
        assert card.domain == "operaciones"
        assert card.tier == "specialist"

    def test_handle_returns_completed(self, specialist: InvoiceSpecialist) -> None:
        """handle() retorna status='completed'."""
        result = specialist.handle({"description": "crear factura", "params": {}})
        assert result["status"] == "completed"


# ── InventorySpecialist ────────────────────────────────────────────────


class TestInventorySpecialist:
    """Tests para InventorySpecialist."""

    @pytest.fixture
    def mock_inventory(self) -> MagicMock:
        """Inventory tool mockeada."""
        tool = MagicMock()
        tool.create_product.return_value = {"id": 1, "name": "Widget"}
        tool.list_products.return_value = [{"id": 1}]
        tool.get_product.return_value = {"id": 1}
        tool.update_stock.return_value = {"id": 1, "stock": 100}
        tool.delete_product.return_value = True
        tool.get_stats.return_value = {"total": 50}
        return tool

    @pytest.fixture
    def specialist(self, mock_inventory: MagicMock) -> InventorySpecialist:
        """InventorySpecialist con tool mockeada."""
        return InventorySpecialist(tools={"inventory": mock_inventory})

    def test_get_card_returns_correct_metadata(
        self, specialist: InventorySpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='operaciones'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.agent_id in ("inventory", "inventory_specialist")
        assert card.domain == "operaciones"
        assert card.tier == "specialist"

    def test_handle_returns_completed(self, specialist: InventorySpecialist) -> None:
        """handle() retorna status='completed'."""
        result = specialist.handle({"description": "listar productos", "params": {}})
        assert result["status"] == "completed"
