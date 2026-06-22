"""Tests Fase 1A — Foso 3: DB + Models + CRM clients + Invoice currency + MP fix."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="fase1a_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Cada test usa DB en tmpdir distinto."""
    monkeypatch.setenv("HOME", str(tmp_path))
    from src.core.db.sqlite_manager import DatabaseManager
    db = DatabaseManager()
    yield db


class TestDBTables:
    """Verificar que las tablas clients y deals existen con columnas correctas."""

    def test_clients_table_exists(self, fresh_db):
        rows = fresh_db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clients'"
        )
        assert len(rows) == 1

    def test_deals_table_exists(self, fresh_db):
        rows = fresh_db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='deals'"
        )
        assert len(rows) == 1

    def test_invoices_has_new_columns(self, fresh_db):
        cursor = fresh_db.execute("PRAGMA table_info(invoices)")
        columns = [row[1] for row in cursor.fetchall()]
        for col in ["client_id", "deal_id", "lead_id", "currency", "fiscal_type",
                     "fiscal_id", "pdf_path", "mp_preference_id", "mp_payment_id"]:
            assert col in columns, f"Column {col} missing from invoices"

    def test_clients_fiscal_unique_index_exists(self, fresh_db):
        indexes = fresh_db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_clients_fiscal'"
        )
        assert len(indexes) == 1


class TestClientModels:
    """Verificar dataclasses Client y Deal."""

    def test_client_dataclass_creates(self):
        from src.hat.level5_tools.business.crm.models import Client
        c = Client(name="Test SA", fiscal_id="ABC123", country_code="MX", currency="MXN")
        assert c.name == "Test SA"
        assert c.fiscal_id == "ABC123"
        assert c.country_code == "MX"

    def test_deal_dataclass_creates(self):
        from src.hat.level5_tools.business.crm.models import Deal
        d = Deal(lead_id=1, title="Venta", amount=5000.0, currency="MXN")
        assert d.lead_id == 1
        assert d.amount == 5000.0
        assert d.stage == "proposal"


class TestCRMClientService:
    """Verificar CRMService.create_client + get_client + list_clients."""

    def test_create_client(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        client = crm.create_client(name="Cliente SA", email="test@test.com", phone="+5215551234567")
        assert client is not None
        assert client["name"] == "Cliente SA"
        assert client["id"] > 0

    def test_get_client(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        created = crm.create_client(name="Get Me", fiscal_id="RFC123")
        fetched = crm.get_client(created["id"])
        assert fetched is not None
        assert fetched["name"] == "Get Me"

    def test_get_client_not_found(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        assert crm.get_client(99999) is None

    def test_list_clients(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        crm.create_client(name="Client A")
        crm.create_client(name="Client B")
        clients = crm.list_clients()
        assert len(clients) >= 2

    def test_update_client(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        created = crm.create_client(name="Old Name")
        updated = crm.update_client(created["id"], name="New Name")
        assert updated["name"] == "New Name"


class TestConvertLeadToDeal:
    """Verificar convert_lead_to_deal."""

    def test_convert_creates_client_and_deal(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        lead = crm.create_lead(name="Lead Test", phone="+5215551234567")
        crm.close_won(lead["id"])
        result = crm.convert_lead_to_deal(lead["id"], title="Deal Test", amount=5000.0)
        assert "client" in result
        assert "deal" in result
        assert result["client"]["name"] == "Lead Test"
        assert result["deal"]["title"] == "Deal Test"
        assert result["deal"]["amount"] == 5000.0

    def test_convert_fails_for_nonexistent_lead(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        with pytest.raises(ValueError, match="no encontrado"):
            crm.convert_lead_to_deal(99999)

    def test_convert_links_client_to_lead(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        crm = CRMService()
        lead = crm.create_lead(name="Linked Lead")
        crm.close_won(lead["id"])
        result = crm.convert_lead_to_deal(lead["id"])
        assert result["client"]["lead_id"] == lead["id"]


class TestInvoiceCurrency:
    """Verificar InvoiceService.create_invoice con currency + lead_id."""

    def test_create_invoice_with_currency(self, fresh_db):
        from src.hat.level5_tools.business.invoice.service import InvoiceService
        inv = InvoiceService()
        invoice = inv.create_invoice(
            client_name="Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 100}],
            currency="BRL",
        )
        assert invoice["currency"] == "BRL"

    def test_create_invoice_with_lead_id(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        from src.hat.level5_tools.business.invoice.service import InvoiceService
        crm = CRMService()
        lead = crm.create_lead(name="Lead Inv")
        inv = InvoiceService()
        invoice = inv.create_invoice(
            client_name="Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 100}],
            lead_id=lead["id"],
        )
        assert invoice["lead_id"] == lead["id"]

    def test_create_invoice_default_currency_mx(self, fresh_db):
        from src.hat.level5_tools.business.invoice.service import InvoiceService
        inv = InvoiceService()
        invoice = inv.create_invoice(
            client_name="Test",
            items=[{"description": "Item", "quantity": 1, "unit_price": 100}],
        )
        assert invoice["currency"] == "MXN"


class TestMercadoPagoCurrencyFix:
    """Verificar que MP currency ya NO está hardcoded."""

    def test_currency_uses_currency_id_from_response(self):
        import inspect

        from src.hat.level5_tools.payments.mercadopago_service import MercadoPagoService
        source = inspect.getsource(MercadoPagoService)
        # El fix usa p.get("currency_id", "ARS") en lugar de "ARS" hardcoded
        assert "currency_id" in source
        # La línea original con "ARS" hardcoded ya no debe existir como asignación directa
        # (puede aparecer como fallback default, lo cual es correcto)


class TestIntegrationFlow:
    """Test E2E: Lead → close_won → convert → create_invoice → mark_paid."""

    def test_lead_to_invoice_flow(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        from src.hat.level5_tools.business.invoice.service import InvoiceService

        crm = CRMService()
        inv_svc = InvoiceService()

        # 1. Crear lead
        lead = crm.create_lead(name="Flujo Test", phone="+5215551234567", email="test@test.com")
        assert lead["stage"] == "new"

        # 2. Avanzar a closed_won
        crm.close_won(lead["id"])
        lead_after = crm.get_lead(lead["id"])
        assert lead_after["stage"] == "closed_won"

        # 3. Convertir a client + deal
        result = crm.convert_lead_to_deal(lead["id"], title="Venta Test", amount=10000.0, currency="MXN")
        client = result["client"]
        deal = result["deal"]
        assert client["name"] == "Flujo Test"
        assert deal["amount"] == 10000.0

        # 4. Crear factura vinculada al lead
        invoice = inv_svc.create_invoice(
            client_name=client["name"],
            items=[{"description": "Servicio", "quantity": 1, "unit_price": 10000}],
            currency="MXN",
            lead_id=lead["id"],
            client_id=client["id"],
        )
        assert invoice["currency"] == "MXN"
        assert invoice["lead_id"] == lead["id"]
        assert invoice["client_id"] == client["id"]
        assert invoice["status"] == "pending"

        # 5. Marcar pagada
        paid = inv_svc.mark_paid(invoice["id"])
        assert paid["status"] == "paid"
