"""Tests Fase 1B+C — PymeOrchestrator subscribers + flows + webhooks."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_tmpdir = tempfile.mkdtemp(prefix="fase1bc_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from src.core.db.sqlite_manager import DatabaseManager
    yield DatabaseManager()


@pytest.fixture
def services(fresh_db):
    """Servicios con DB fresca."""
    from src.events.bus import EventBus
    from src.hat.level5_tools.business.crm.service import CRMService
    from src.hat.level5_tools.business.inventory.service import InventoryService
    from src.hat.level5_tools.business.invoice.service import InvoiceService
    bus = EventBus()
    return {
        "bus": bus,
        "crm": CRMService(event_bus=bus),
        "inv": InvoiceService(event_bus=bus),
        "inv_svc": InventoryService(event_bus=bus),
    }


class TestSubscribersRegistration:
    """Verificar que register_subscribers registra los 6 suscriptores."""

    def test_register_subscribers(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import register_subscribers
        bus = services["bus"]
        register_subscribers(bus)
        # EventBus._subscribers es un dict event_type → list[handler]
        assert "invoice.paid" in bus._handlers
        assert "invoice.overdue" in bus._handlers
        assert "inventory.stock_low" in bus._handlers
        assert "inventory.stock_out" in bus._handlers
        assert "crm.lead.stage_changed" in bus._handlers
        assert "crm.lead.created" in bus._handlers


class TestOnInvoicePaid:
    """Subscriber: invoice.paid → descontar stock + WhatsApp."""

    def test_deducts_stock_on_invoice_paid(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import (
            _on_invoice_paid,
            register_subscribers,
        )
        bus = services["bus"]
        register_subscribers(bus)

        # Crear producto con stock 10
        product = services["inv_svc"].add_product(
            sku="TEST-001", name="Test Product", stock=10, min_stock=2, price=100.0
        )

        # Crear factura con item que referencia SKU
        invoice = services["inv"].create_invoice(
            client_name="Test Client",
            items=[{"sku": "TEST-001", "quantity": 3, "unit_price": 100}],
        )

        # Mock WhatsApp (no enviar real)
        with patch("src.hat.level5_tools.business.pyme_orchestrator.subscribers._get_services") as mock_svc:
            mock_notif = MagicMock()
            mock_svc.return_value = (services["crm"], services["inv"], services["inv_svc"], mock_notif)
            # Disparar evento invoice.paid
            _on_invoice_paid({"invoice_id": invoice["id"]})

        # Verificar stock descontado
        product_after = services["inv_svc"].get_product(product["id"])
        assert product_after["stock"] == 7  # 10 - 3

    def test_sends_whatsapp_on_invoice_paid(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import _on_invoice_paid

        # Crear lead con phone, crear factura vinculada
        lead = services["crm"].create_lead(name="Cliente Phone", phone="+5215551234567")
        invoice = services["inv"].create_invoice(
            client_name="Cliente Phone",
            items=[{"description": "Servicio", "quantity": 1, "unit_price": 100}],
            lead_id=lead["id"],
        )

        with patch("src.hat.level5_tools.business.pyme_orchestrator.subscribers._get_services") as mock_svc:
            mock_notif = MagicMock()
            mock_svc.return_value = (services["crm"], services["inv"], services["inv_svc"], mock_notif)
            _on_invoice_paid({"invoice_id": invoice["id"]})
            # Verificar que se llamó send_whatsapp
            mock_notif.send_whatsapp.assert_called_once()
            call_args = mock_notif.send_whatsapp.call_args
            assert "+5215551234567" in str(call_args)


class TestOnLeadStageChanged:
    """Subscriber: lead.stage_changed → closed_won → auto-crear Deal."""

    def test_auto_creates_deal_on_closed_won(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import _on_lead_stage_changed

        lead = services["crm"].create_lead(name="Lead Test")
        _on_lead_stage_changed({
            "lead_id": lead["id"],
            "from_stage": "proposal",
            "to_stage": "closed_won",
        })

        # Verificar que se creó un deal
        deals = services["crm"]._repo.list_deals(lead_id=lead["id"])
        assert len(deals) >= 1
        assert "Lead Test" in deals[0]["title"]

    def test_does_nothing_on_non_closed_won(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import _on_lead_stage_changed

        lead = services["crm"].create_lead(name="Lead Test 2")
        _on_lead_stage_changed({
            "lead_id": lead["id"],
            "from_stage": "new",
            "to_stage": "contacted",
        })

        deals = services["crm"]._repo.list_deals(lead_id=lead["id"])
        assert len(deals) == 0


class TestOnLeadCreated:
    """Subscriber: lead.created → welcome WhatsApp."""

    def test_sends_welcome_whatsapp(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import _on_lead_created

        with patch("src.hat.level5_tools.business.pyme_orchestrator.subscribers._get_services") as mock_svc:
            mock_notif = MagicMock()
            mock_svc.return_value = (services["crm"], services["inv"], services["inv_svc"], mock_notif)
            _on_lead_created({"name": "Juan", "phone": "+5215551234567"})
            mock_notif.send_whatsapp.assert_called_once()
            msg = mock_notif.send_whatsapp.call_args[0][1]
            assert "Juan" in msg

    def test_no_whatsapp_without_phone(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import _on_lead_created

        with patch("src.hat.level5_tools.business.pyme_orchestrator.subscribers._get_services") as mock_svc:
            mock_notif = MagicMock()
            mock_svc.return_value = (services["crm"], services["inv"], services["inv_svc"], mock_notif)
            _on_lead_created({"name": "Sin Phone", "phone": None})
            mock_notif.send_whatsapp.assert_not_called()


class TestFlows:
    """Tests de flows de alto nivel."""

    def test_lead_to_invoice_flow(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.flows import lead_to_invoice_flow

        lead = services["crm"].create_lead(name="Flow Lead", phone="+5215551234567")
        result = lead_to_invoice_flow(
            lead_id=lead["id"],
            items=[{"description": "Servicio", "quantity": 1, "unit_price": 1000}],
            tax_rate=0.16,
            currency="MXN",
            event_bus=services["bus"],
        )

        assert "client" in result
        assert "deal" in result
        assert "invoice" in result
        assert result["client"]["name"] == "Flow Lead"
        assert result["invoice"]["currency"] == "MXN"
        assert result["invoice"]["lead_id"] == lead["id"]

    def test_lead_to_invoice_flow_fails_for_nonexistent_lead(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.flows import lead_to_invoice_flow

        with pytest.raises(ValueError, match="no encontrado"):
            lead_to_invoice_flow(
                lead_id=99999,
                items=[],
                event_bus=services["bus"],
            )


class TestWebhooks:
    """Tests de webhooks MP + WhatsApp."""

    def test_mercadopago_webhook_returns_200(self, fresh_db):
        from flask import Flask

        from src.web.routes.webhooks import webhooks_bp

        app = Flask(__name__)
        app.register_blueprint(webhooks_bp)
        client = app.test_client()

        r = client.post("/webhooks/mercadopago", json={"type": "payment", "data": {"id": "123"}})
        assert r.status_code == 200
        assert r.json["received"] is True

    def test_whatsapp_webhook_verification(self, fresh_db):
        from flask import Flask

        from src.web.routes.webhooks import webhooks_bp

        app = Flask(__name__)
        app.config["WHATSAPP_VERIFY_TOKEN"] = "zenic_verify"
        app.register_blueprint(webhooks_bp)
        client = app.test_client()

        r = client.get("/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=zenic_verify&hub.challenge=abc123")
        assert r.status_code == 200
        assert r.data == b"abc123"

    def test_whatsapp_webhook_wrong_token_returns_403(self, fresh_db):
        from flask import Flask

        from src.web.routes.webhooks import webhooks_bp

        app = Flask(__name__)
        app.config["WHATSAPP_VERIFY_TOKEN"] = "zenic_verify"
        app.register_blueprint(webhooks_bp)
        client = app.test_client()

        r = client.get("/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=abc")
        assert r.status_code == 403

    def test_whatsapp_webhook_post_returns_200(self, fresh_db):
        from flask import Flask

        from src.web.routes.webhooks import webhooks_bp

        app = Flask(__name__)
        app.register_blueprint(webhooks_bp)
        client = app.test_client()

        r = client.post("/webhooks/whatsapp", json={"entry": [{"changes": [{"value": {"messages": []}}]}]})
        assert r.status_code == 200


class TestIntegrationE2E:
    """Test E2E: Lead → close_won → convert → invoice → mark_paid → stock deducted."""

    def test_full_flow_with_subscribers(self, services):
        from src.hat.level5_tools.business.pyme_orchestrator.flows import lead_to_invoice_flow
        from src.hat.level5_tools.business.pyme_orchestrator.subscribers import register_subscribers

        # Registrar subscribers
        register_subscribers(services["bus"])

        # Crear producto
        product = services["inv_svc"].add_product(
            sku="E2E-001", name="Producto E2E", stock=10, min_stock=2, price=50.0
        )

        # Crear lead
        lead = services["crm"].create_lead(name="Cliente E2E", phone="+5215551234567")

        # Flow: lead → invoice
        result = lead_to_invoice_flow(
            lead_id=lead["id"],
            items=[{"sku": "E2E-001", "description": "Producto", "quantity": 4, "unit_price": 50}],
            event_bus=services["bus"],
        )

        invoice = result["invoice"]

        # Mock WhatsApp
        with patch("src.hat.level5_tools.business.pyme_orchestrator.subscribers._get_services") as mock_svc:
            mock_notif = MagicMock()
            mock_svc.return_value = (services["crm"], services["inv"], services["inv_svc"], mock_notif)
            # Marcar pagada → dispara subscriber → descuenta stock
            services["inv"].mark_paid(invoice["id"])

        # Verificar stock descontado
        product_after = services["inv_svc"].get_product(product["id"])
        assert product_after["stock"] == 6  # 10 - 4

        # Verificar WhatsApp enviado
        mock_notif.send_whatsapp.assert_called()
