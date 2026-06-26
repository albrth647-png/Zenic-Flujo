"""Tests para OperacionesSupervisor — routing real por keywords.

Cubre:
- Routing a CrmSpecialist (cliente, lead, venta, crm, contacto).
- Routing a InvoiceSpecialist (factura, invoice, cobro, pago, stripe).
- Routing a InventorySpecialist (producto, stock, inventario).
- Fallback al primer specialist cuando no hay keyword match.
- Case-insensitive matching.
- Respuestas de error cuando faltan specialists.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level2_supervisors.operaciones.supervisor import OperacionesSupervisor

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_specialists() -> dict[str, MagicMock]:
    """3 specialists mockeados: crm, invoice, inventory."""
    return {
        "crm": MagicMock(),
        "invoice": MagicMock(),
        "inventory": MagicMock(),
    }


@pytest.fixture
def supervisor(mock_specialists: dict[str, MagicMock]) -> OperacionesSupervisor:
    """OperacionesSupervisor con 3 specialists."""
    return OperacionesSupervisor(specialists=mock_specialists)


# ── Tests de routing a CRM ─────────────────────────────────────────────


class TestRoutingToCRM:
    """Mensajes con keywords de CRM rutean a CrmSpecialist."""

    @pytest.mark.parametrize("message", [
        "listar leads",
        "crear cliente nuevo",
        "ver oportunidad de negocio",
        "gestionar contacto",
        "actualizar lead existente",
        "CRM dashboard",
    ])
    def test_crm_keywords_route_to_crm(
        self, supervisor: OperacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de CRM rutea al CrmSpecialist."""
        mock_specialists["crm"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["crm"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["crm"]


# ── Tests de routing a Invoice ─────────────────────────────────────────


class TestRoutingToInvoice:
    """Mensajes con keywords de Invoice rutean a InvoiceSpecialist."""

    @pytest.mark.parametrize("message", [
        "crear factura",
        "generar invoice",
        "procesar cobro",
        "registrar pago",
        "configurar stripe",
        "cobrar con mercadopago",
    ])
    def test_invoice_keywords_route_to_invoice(
        self, supervisor: OperacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Invoice rutea al InvoiceSpecialist."""
        mock_specialists["invoice"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["invoice"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["invoice"]


# ── Tests de routing a Inventory ───────────────────────────────────────


class TestRoutingToInventory:
    """Mensajes con keywords de Inventory rutean a InventorySpecialist."""

    @pytest.mark.parametrize("message", [
        "listar productos",
        "ver stock disponible",
        "actualizar inventario",
        "check inventory levels",
        "agregar producto nuevo",
    ])
    def test_inventory_keywords_route_to_inventory(
        self, supervisor: OperacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Inventory rutea al InventorySpecialist."""
        mock_specialists["inventory"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["inventory"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["inventory"]


# ── Tests de case-insensitive ──────────────────────────────────────────


class TestCaseInsensitive:
    """El matching de keywords es case-insensitive."""

    def test_uppercase_keywords_match(
        self, supervisor: OperacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Keywords en mayúsculas funcionan."""
        mock_specialists["crm"].handle.return_value = {"status": "completed"}
        supervisor.handle({"description": "LISTAR LEADS DEL CRM"})
        mock_specialists["crm"].handle.assert_called_once()
        assert True  # context manager completed without error

    def test_mixed_case_keywords_match(
        self, supervisor: OperacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Keywords en mixed case funcionan (solo keyword de invoice)."""
        mock_specialists["invoice"].handle.return_value = {"status": "completed"}
        # Solo keyword de invoice (sin 'cliente' que es de crm)
        supervisor.handle({"description": "Generar Invoice Para Empresa"})
        mock_specialists["invoice"].handle.assert_called_once()
        assert True  # context manager completed without error


# ── Tests de fallback ──────────────────────────────────────────────────


class TestFallback:
    """Fallback cuando no hay keyword match."""

    def test_fallback_to_first_specialist(
        self, supervisor: OperacionesSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Sin keyword match → primer specialist (crm por orden de inserción)."""
        mock_specialists["crm"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": "xyz qwerty unknown"})
        mock_specialists["crm"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["crm"]


# ── Tests de errores ───────────────────────────────────────────────────


class TestErrors:
    """Manejo de errores."""

    def test_no_specialists_returns_failed(self) -> None:
        """Sin specialists → respuesta failed."""
        sup = OperacionesSupervisor(specialists=None)
        result = sup.handle({"description": "listar leads"})
        assert result["status"] == "failed"
        assert result["domain"] == "operaciones"
        assert "no specialists" in result["error"]

    def test_partial_specialists_set(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si solo hay crm e invoice, routing a inventory keyword falla graceful."""
        partial = {
            "crm": mock_specialists["crm"],
            "invoice": mock_specialists["invoice"],
        }
        sup = OperacionesSupervisor(specialists=partial)
        # Keyword de inventory pero no hay inventory specialist
        result = sup.handle({"description": "ver stock disponible"})
        assert result["status"] == "failed"
        assert "inventory" in result["error"]


# ── Tests de domain attribute ──────────────────────────────────────────


class TestDomainAttribute:
    """El atributo domain está correctamente definido."""

    def test_domain_is_operaciones(self, supervisor: OperacionesSupervisor) -> None:
        """domain = 'operaciones'."""
        assert supervisor.domain == "operaciones"

    def test_keyword_map_is_populated(
        self, supervisor: OperacionesSupervisor,
    ) -> None:
        """_keyword_map tiene entradas para los 3 specialists."""
        assert len(supervisor._keyword_map) > 0
        # Al menos una keyword por specialist
        specialists_in_map = set(supervisor._keyword_map.values())
        assert "crm" in specialists_in_map
        assert "invoice" in specialists_in_map
        assert "inventory" in specialists_in_map


# ── Tests de __repr__ ──────────────────────────────────────────────────


class TestRepr:
    """Representación string."""

    def test_repr_includes_domain(
        self, supervisor: OperacionesSupervisor,
    ) -> None:
        """__repr__ incluye 'operaciones' y los specialists."""
        r = repr(supervisor)
        assert "OperacionesSupervisor" in r
        assert "operaciones" in r
        assert "crm" in r
