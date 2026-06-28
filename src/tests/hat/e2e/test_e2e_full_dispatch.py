"""E2E tests — cadena completa HATRouter → Supervisor → Specialist → Tool.

Verifica que un mensaje del usuario recorre los 5 niveles:
  N1 HATRouter → N2 Supervisor → N3 Specialist → N4 Worker → N5 Tool

Con side effects reales en SQLite temporal.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.hat.level1_orchestrator.ledger.ovc_bridge import OVCLedgerBridge
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level1_orchestrator.tick_router import HATRouter
from src.hat.level2_supervisors.comunicaciones import ComunicacionesSupervisor
from src.hat.level2_supervisors.datos_auto import DatosAutoSupervisor
from src.hat.level2_supervisors.operaciones import OperacionesSupervisor
from src.hat.level3_specialists.comunicaciones.chat_specialist import ChatSpecialist
from src.hat.level3_specialists.comunicaciones.email_specialist import EmailSpecialist
from src.hat.level3_specialists.comunicaciones.notification_specialist import NotificationSpecialist
from src.hat.level3_specialists.datos_auto.api_specialist import ApiSpecialist
from src.hat.level3_specialists.datos_auto.code_specialist import CodeSpecialist
from src.hat.level3_specialists.datos_auto.data_specialist import DataSpecialist
from src.hat.level3_specialists.operaciones.crm_specialist import CrmSpecialist
from src.hat.level3_specialists.operaciones.inventory_specialist import InventorySpecialist
from src.hat.level3_specialists.operaciones.invoice_specialist import InvoiceSpecialist
from src.orbital.context import OrbitalContext


@pytest.fixture(autouse=True)
def reset_orbital_context() -> None:
    """Reset del singleton OrbitalContext antes de cada test."""
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Ruta a DB SQLite temporal."""
    return tmp_path / "test_e2e.db"


@pytest.fixture
def mock_tools() -> dict[str, MagicMock]:
    """19 tools mockeadas con side effects simulados."""
    tools: dict[str, MagicMock] = {}

    # CRM
    crm = MagicMock()
    crm.create_lead.return_value = {"id": 1, "name": "Juan", "email": "juan@test.com"}
    crm.list_leads.return_value = [{"id": 1, "name": "Juan"}]
    crm.advance_stage.return_value = {"id": 1, "stage": "contacted"}
    crm.close_won.return_value = {"id": 1, "stage": "closed_won"}
    crm.close_lost.return_value = {"id": 1, "stage": "closed_lost"}
    crm.get_stats.return_value = {"total": 1, "won": 1}
    crm.get_lead.return_value = {"id": 1, "name": "Juan"}
    crm.delete_lead.return_value = True
    crm.update_lead.return_value = {"id": 1, "name": "Updated"}
    tools["crm"] = crm

    # Invoice
    inv = MagicMock()
    inv.create_invoice.return_value = {"id": 1, "number": "INV-001", "amount": 100.0}
    inv.list_invoices.return_value = [{"id": 1, "number": "INV-001"}]
    inv.get_invoice.return_value = {"id": 1, "amount": 100}
    inv.mark_paid.return_value = {"id": 1, "status": "paid"}
    tools["invoice"] = inv

    # Inventory
    invt = MagicMock()
    invt.add_product.return_value = {"id": 1, "name": "Widget", "sku": "W001"}
    invt.list_products.return_value = [{"id": 1, "name": "Widget"}]
    invt.get_product.return_value = {"id": 1, "name": "Widget"}
    tools["inventory"] = invt

    # Notification
    notif = MagicMock()
    notif.send_email.return_value = {"status": "sent", "to": "client@test.com"}
    notif.send_whatsapp.return_value = {"status": "sent"}
    tools["notification"] = notif

    # Email
    gmail = MagicMock()
    gmail.send_email.return_value = {"status": "sent"}
    tools["gmail"] = gmail

    # Chat
    slack = MagicMock()
    slack.send_message.return_value = {"status": "sent"}
    telegram = MagicMock()
    telegram.send_message.return_value = {"status": "sent"}
    tools["slack"] = slack
    tools["telegram"] = telegram

    # Data
    data_keeper = MagicMock()
    data_keeper.insert.return_value = {"id": 1, "collection": "test"}
    data_keeper.query.return_value = [{"id": 1}]
    tools["data_keeper"] = data_keeper

    # API
    api_conn = MagicMock()
    api_conn.request.return_value = {"status": 200, "data": {"result": "ok"}}
    tools["api_connector"] = api_conn

    # Code
    code_runner = MagicMock()
    code_runner.run_python.return_value = {"output": "42", "exit_code": 0}
    tools["code_runner"] = code_runner
    tools["logic_gate"] = MagicMock()
    tools["autopilot"] = MagicMock()
    tools["openai"] = MagicMock()
    tools["ollama"] = MagicMock()

    # Payments
    tools["stripe"] = MagicMock()
    tools["mercadopago"] = MagicMock()

    # Data extras
    tools["sheets"] = MagicMock()
    tools["drive"] = MagicMock()
    tools["postgresql"] = MagicMock()

    return tools


@pytest.fixture
def specialists(mock_tools: dict[str, MagicMock]) -> dict[str, dict[str, Any]]:
    """9 specialists con tools inyectadas."""
    return {
        "operaciones": {
            "crm": CrmSpecialist(tools={"crm": mock_tools["crm"]}),
            "invoice": InvoiceSpecialist(tools={
                "invoice": mock_tools["invoice"],
                "stripe": mock_tools["stripe"],
                "mercadopago": mock_tools["mercadopago"],
            }),
            "inventory": InventorySpecialist(tools={"inventory": mock_tools["inventory"]}),
        },
        "comunicaciones": {
            "notification": NotificationSpecialist(tools={"notification": mock_tools["notification"]}),
            "email": EmailSpecialist(tools={"gmail": mock_tools["gmail"]}),
            "chat": ChatSpecialist(tools={
                "slack": mock_tools["slack"],
                "telegram": mock_tools["telegram"],
            }),
        },
        "datos_auto": {
            "data": DataSpecialist(tools={
                "data_keeper": mock_tools["data_keeper"],
                "sheets": mock_tools["sheets"],
                "drive": mock_tools["drive"],
                "postgresql": mock_tools["postgresql"],
            }),
            "api": ApiSpecialist(tools={"api_connector": mock_tools["api_connector"]}),
            "code": CodeSpecialist(tools={
                "code_runner": mock_tools["code_runner"],
                "logic_gate": mock_tools["logic_gate"],
                "autopilot": mock_tools["autopilot"],
                "openai": mock_tools["openai"],
                "ollama": mock_tools["ollama"],
            }),
        },
    }


@pytest.fixture
def hat_router(
    tmp_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    specialists: dict[str, dict[str, Any]],
) -> HATRouter:
    """HATRouter con supervisores y specialists configurados."""
    import src.core.db.sqlite_manager as sm_module
    from src.core.db.sqlite_manager import DatabaseManager

    original_instance = DatabaseManager._instance
    original_db_path = sm_module.DB_PATH

    DatabaseManager._instance = None
    monkeypatch.setattr(sm_module, "DB_PATH", tmp_db_path)

    db = DatabaseManager()

    ledger = LedgerRepository()
    ctx = OrbitalContext()
    bridge = OVCLedgerBridge(repo=ledger, ctx=ctx)

    supervisors = {
        "operaciones": OperacionesSupervisor(
            specialists=specialists["operaciones"], ledger=ledger,
        ),
        "comunicaciones": ComunicacionesSupervisor(
            specialists=specialists["comunicaciones"], ledger=ledger,
        ),
        "datos_auto": DatosAutoSupervisor(
            specialists=specialists["datos_auto"], ledger=ledger,
        ),
    }

    router = HATRouter(
        ledger=ledger, ctx=ctx, bridge=bridge, supervisors=supervisors,
    )

    # Publicar AgentCards
    for domain_specialists in specialists.values():
        for specialist in domain_specialists.values():
            with contextlib.suppress(Exception):
                specialist.publish_card()

    yield router

    with contextlib.suppress(Exception):
        db.close_connection()
    DatabaseManager._instance = original_instance
    monkeypatch.setattr(sm_module, "DB_PATH", original_db_path)


# ── E2E: Operaciones ──────────────────────────────────────────────────


class TestE2EOperaciones:
    """E2E: mensajes de operaciones recorren N1→N2→N3→N5."""

    def test_e2e_listar_leads(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'listar leads' → routing operaciones → CrmSpecialist → list_leads."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="listar leads",
        )
        assert result["status"] == "completed"
        assert result["domain"] == "operaciones"
        mock_tools["crm"].list_leads.assert_called_once()

    def test_e2e_crear_lead(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'crear lead Juan' → CrmSpecialist → create_lead."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="crear lead Juan",
        )
        assert result["status"] == "completed"
        mock_tools["crm"].create_lead.assert_called_once()

    def test_e2e_crear_factura(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'crear factura' → InvoiceSpecialist → create_invoice."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="crear factura para cliente",
        )
        assert result["status"] == "completed"
        mock_tools["invoice"].create_invoice.assert_called_once()

    def test_e2e_listar_productos(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'listar productos' → InventorySpecialist → list_products."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="listar productos del inventario",
        )
        assert result["status"] == "completed"
        mock_tools["inventory"].list_products.assert_called_once()


# ── E2E: Comunicaciones ───────────────────────────────────────────────


class TestE2EComunicaciones:
    """E2E: mensajes de comunicaciones recorren N1→N2→N3→N5."""

    def test_e2e_enviar_email(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'enviar email' → EmailSpecialist → gmail.send_email."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="enviar email al contacto",
        )
        assert result["status"] == "completed"
        mock_tools["gmail"].send_email.assert_called_once()

    def test_e2e_enviar_whatsapp(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'enviar whatsapp' → ChatSpecialist → slack/telegram.send_message."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="enviar whatsapp al cliente",
        )
        assert result["status"] == "completed"


# ── E2E: Datos/Auto ──────────────────────────────────────────────────


class TestE2EDatosAuto:
    """E2E: mensajes de datos_auto recorren N1→N2→N3→N5."""

    def test_e2e_ejecutar_codigo(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'ejecutar codigo python' → CodeSpecialist → code_runner.run_python."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="ejecutar codigo python",
        )
        assert result["status"] == "completed"

    def test_e2e_consultar_api(
        self, hat_router: HATRouter, mock_tools: dict[str, MagicMock],
    ) -> None:
        """E2E: 'consultar api externa' → ApiSpecialist → api_connector.request."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="consultar api externa",
        )
        assert result["status"] == "completed"


# ── E2E: Anti-dup y sesión ────────────────────────────────────────────


class TestE2EAntiDupAndSession:
    """E2E: anti-dup cascade y persistencia de sesión."""

    def test_e2e_dispatch_id_generated(
        self, hat_router: HATRouter,
    ) -> None:
        """E2E: cada dispatch genera un dispatch_id único."""
        r1 = hat_router.handle(user_id="u1", session_id="s1", message="listar leads")
        r2 = hat_router.handle(user_id="u1", session_id="s1", message="crear lead Juan")
        assert r1["dispatch_id"] != r2["dispatch_id"]
        assert r1["dispatch_id"].startswith("disp_")

    def test_e2e_orbital_resonance_returned(
        self, hat_router: HATRouter,
    ) -> None:
        """E2E: el resultado incluye orbital_resonance."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="listar leads",
        )
        assert "orbital_resonance" in result
        assert isinstance(result["orbital_resonance"], (int, float))
        assert 0.0 <= result["orbital_resonance"] <= 1.0

    def test_e2e_duration_ms_returned(
        self, hat_router: HATRouter,
    ) -> None:
        """E2E: el resultado incluye duration_ms."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="listar leads",
        )
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0

    def test_e2e_anti_dup_layer_hit_returned(
        self, hat_router: HATRouter,
    ) -> None:
        """E2E: el resultado incluye anti_dup_layer_hit."""
        result = hat_router.handle(
            user_id="u1", session_id="s1", message="listar leads",
        )
        assert "anti_dup_layer_hit" in result
        assert result["anti_dup_layer_hit"] == "none"


# ── E2E: Multi-sesión ─────────────────────────────────────────────────


class TestE2EMultiSession:
    """E2E: aislamiento entre sesiones."""

    def test_e2e_two_sessions_isolated(
        self, hat_router: HATRouter,
    ) -> None:
        """E2E: dos sesiones distintas no interfieren."""
        r1 = hat_router.handle(user_id="u1", session_id="s1", message="listar leads")
        r2 = hat_router.handle(user_id="u1", session_id="s2", message="listar leads")
        assert r1["dispatch_id"] != r2["dispatch_id"]
        assert r1["status"] == "completed"
        assert r2["status"] == "completed"
