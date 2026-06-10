"""
Tests — OrbitalAdapter y OrbitalCompiler (Fase 2)
==================================================

- OrbitalAdapter: envuelve tools de negocio con logica orbital
- OrbitalCompiler: compila texto a workflow con resonancia orbital (50+ frases)

Ejecutar con: pytest src/tests/test_orbital_adapter_compiler.py -v
"""

import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.orbital.context import OrbitalContext
from src.orbital.orbital_adapter import OrbitalAdapter, OrbitalToolResult
from src.orbital.orbital_compiler import OrbitalCompiler


# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_singletons():
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def mock_crm():
    tool = MagicMock()
    tool.create_lead.return_value = {"id": 1, "name": "Juan"}
    tool.update_lead.return_value = {"id": 1, "stage": "qualified"}
    return tool


@pytest.fixture
def mock_notification():
    tool = MagicMock()
    tool.send_email.return_value = {"sent": True, "to": "a@b.com"}
    return tool


@pytest.fixture
def adapter():
    return OrbitalAdapter()


@pytest.fixture
def compiler():
    return OrbitalCompiler()


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalAdapter
# ══════════════════════════════════════════════════════════════

class TestOrbitalAdapter:
    def test_register_tool(self, adapter):
        adapter.register_tool("crm", MagicMock())
        assert "crm" in adapter._tools

    def test_register_tools_batch(self, adapter):
        adapter.register_tools_batch({"crm": MagicMock(), "invoice": MagicMock()})
        assert len(adapter._tools) == 2

    def test_execute_success(self, adapter, mock_crm):
        adapter.register_tool("crm", mock_crm)
        result = adapter.execute_action("crm", "create_lead", {"name": "Juan"})
        assert isinstance(result, OrbitalToolResult)
        assert result.status == "completed"
        assert result.data["name"] == "Juan"
        assert result.orbital_theta >= 0

    def test_execute_failure(self, adapter):
        bad_tool = MagicMock()
        bad_tool.fail_action.side_effect = RuntimeError("Tool failed")
        adapter.register_tool("bad", bad_tool)
        result = adapter.execute_action("bad", "fail_action", {})
        assert result.status == "failed"
        assert "error" in result.data

    def test_execute_unregistered_tool(self, adapter):
        result = adapter.execute_action("ghost", "do_something", {})
        assert result.status == "failed"
        assert "no registrada" in result.data["error"]

    def test_execute_missing_action(self, adapter):
        # Crear tool real sin la accion (no MagicMock que crea attrs)
        class RealTool:
            pass
        adapter.register_tool("crm", RealTool())
        result = adapter.execute_action("crm", "nonexistent_action", {})
        assert result.status == "failed"
        assert "no encontrada" in result.data["error"]

    def test_orbital_variable_created(self, adapter, mock_crm):
        adapter.register_tool("crm", mock_crm)
        var = adapter._ovc.get_variable("crm")
        assert var is not None
        assert var.orbit_group == "business_tools"

    def test_phase_advances_on_success(self, adapter, mock_crm):
        adapter.register_tool("crm", mock_crm)
        theta_before = adapter.get_tool_phase("crm")
        adapter.execute_action("crm", "create_lead", {"name": "Test"})
        theta_after = adapter.get_tool_phase("crm")
        assert theta_after != theta_before

    def test_tool_alignment(self, adapter, mock_crm, mock_notification):
        adapter.register_tool("crm", mock_crm)
        adapter.register_tool("notification", mock_notification)
        alignment = adapter.get_tool_alignment("crm", "notification")
        assert alignment is not None
        assert -1 <= alignment <= 1

    def test_orbital_snapshot(self, adapter, mock_crm):
        adapter.register_tool("crm", mock_crm)
        snap = adapter.get_orbital_snapshot()
        assert "crm" in snap["tools_registered"]
        assert "crm" in snap["phases"]

    def test_recommendations(self, adapter, mock_crm, mock_notification):
        adapter.register_tool("crm", mock_crm)
        adapter.register_tool("notification", mock_notification)
        adapter.register_tool("invoice", MagicMock())
        recs = adapter.get_tool_recommendations("crm")
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_orbital_summary(self, adapter, mock_crm):
        adapter.register_tool("crm", mock_crm)
        summary = adapter.orbital_summary()
        assert "crm" in summary

    def test_repr(self, adapter):
        r = repr(adapter)
        assert "OrbitalAdapter" in r


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalCompiler — 50+ frases
# ══════════════════════════════════════════════════════════════

class TestOrbitalCompilerPhrases:
    """Tests de compilación con 50+ frases en español e inglés."""

    PHRASES_REGISTRO = [
        "Registrar un cliente nuevo",
        "Quiero agregar un lead",
        "Guardar contacto de Juan",
        "Añadir nuevo prospecto",
        "Crear lead para María",
        "Registra este cliente",
        "Agregar un nuevo prospecto al CRM",
        "Save a new lead",
        "Register new client",
        "Add a new contact",
    ]

    PHRASES_FACTURA = [
        "Generar una factura",
        "Facturar al cliente por servicios",
        "Crear invoice para el pedido",
        "Cobrar al cliente",
        "Emitir factura de $500",
        "Generar factura pendiente",
        "Create an invoice",
        "Bill the client",
        "Issue an invoice for the order",
    ]

    PHRASES_STOCK = [
        "Alerta de stock bajo",
        "El inventario está agotado",
        "Reabastecer producto",
        "Actualizar stock del producto",
        "Alert when stock is low",
        "Check inventory levels",
        "Reorder product when low",
    ]

    PHRASES_NOTIFICACION = [
        "Enviar email de bienvenida",
        "Notificar al cliente",
        "Mandar mensaje al equipo",
        "Enviar correo de confirmación",
        "Avisar al usuario",
        "Send notification email",
        "Alert the team",
        "Send confirmation message",
    ]

    PHRASES_MIXED = [
        "Quiero automatizar mi negocio",
        "Hacer un workflow de ventas",
        "Crear automatización diaria",
        "Programar tarea recurrente",
        "Ejecutar este proceso cada lunes",
        "Crear un workflow que envíe emails",
        "Automate my sales pipeline",
        "Set up a daily report",
        "Create a recurring task",
        "Build an automation for invoices",
    ]

    PHRASES_STOCK_EXTRA = [
        "Need to restock product",
        "Product is out of stock",
        "Refill inventory supplies",
        "Low inventory alert trigger",
    ]

    PHRASES_NOTIFICACION_EXTRA = [
        "Mandar email al equipo de ventas",
        "Notify admin about new order",
        "Send alert to support team",
        "Push notification to user",
        "Reminder email to client",
    ]

    PHRASES_MIXED_EXTRA = [
        "Crear un reporte diario de ventas",
        "Set up automatic billing",
        "Build a client onboarding flow",
        "Create an inventory sync task",
    ]

    ALL_PHRASES = (
        PHRASES_REGISTRO + PHRASES_FACTURA + PHRASES_STOCK +
        PHRASES_NOTIFICACION + PHRASES_MIXED +
        PHRASES_STOCK_EXTRA + PHRASES_NOTIFICACION_EXTRA + PHRASES_MIXED_EXTRA
    )

    @pytest.mark.parametrize("phrase", ALL_PHRASES, ids=range(len(ALL_PHRASES)))
    def test_compiler_handles_phrase(self, compiler, phrase):
        """Cada frase debe compilar sin errores."""
        result = compiler.compile(phrase)
        assert result.status in ("ready", "error")
        assert isinstance(result.intent, str)
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1

    def test_compiler_total_phrases(self, compiler):
        """Verificar que se prueban 50+ frases."""
        assert len(self.ALL_PHRASES) >= 50

    def test_all_phrases_compile(self, compiler):
        """Todas las frases deben compilar sin excepciones."""
        errors = []
        for phrase in self.ALL_PHRASES:
            try:
                result = compiler.compile(phrase)
                if result.status not in ("ready", "error"):
                    errors.append(f"'{phrase}' → status={result.status}")
            except Exception as e:
                errors.append(f"'{phrase}' → exception={e}")
        assert not errors, f"Phrases with errors: {errors}"

    def test_all_phrases_produce_workflow(self, compiler):
        """Las frases que matchean un template deben producir workflow."""
        no_workflow = []
        for phrase in self.ALL_PHRASES:
            result = compiler.compile(phrase)
            if result.status == "ready" and not result.workflow.get("steps"):
                no_workflow.append(phrase)
        # Al menos el 60% debe producir workflow
        match_rate = 1 - (len(no_workflow) / len(self.ALL_PHRASES))
        assert match_rate >= 0.6, f"Match rate {match_rate:.1%} < 60%. No workflow: {no_workflow[:5]}"

    def test_compiler_confidence_above_threshold(self, compiler):
        """La confianza debe estar sobre 0.3 para frases claras."""
        clear_phrases = [
            "Registrar un cliente nuevo",
            "Generar una factura",
            "Enviar email de notificación",
        ]
        for phrase in clear_phrases:
            result = compiler.compile(phrase)
            if result.status == "ready":
                assert result.confidence >= 0.3, f"Confianza muy baja para '{phrase}': {result.confidence}"

    def test_compiler_explanation_not_empty(self, compiler):
        """Las explicaciones no deben estar vacías."""
        for phrase in self.ALL_PHRASES[:10]:
            result = compiler.compile(phrase)
            if result.status == "ready":
                assert len(result.explanation) > 0

    def test_compiler_compilation_count(self, compiler):
        """El contador de compilaciones debe incrementarse."""
        initial = compiler.compilation_count
        compiler.compile("test")
        compiler.compile("test 2")
        assert compiler.compilation_count == initial + 2

    def test_compiler_reproducibility(self, compiler):
        """Mismas frases producen mismos resultados."""
        phrase = "Registrar un cliente nuevo"
        r1 = compiler.compile(phrase)
        r2 = compiler.compile(phrase)
        assert r1.intent == r2.intent
        assert r1.status == r2.status
