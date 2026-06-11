"""
Tests de Integración — ORBITAL ↔ WorkflowEngine
================================================

Verifica que el motor ORBITAL funciona correctamente con el workflow engine.
Usa mocks para las herramientas de negocio.

Ejecutar con: pytest src/tests/test_orbital_integration.py -v
"""

import math
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.orbital.context import OrbitalContext
from src.orbital.engine import OrbitalEngine

# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset todos los singletons antes y después de cada test."""
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def mock_tool():
    """Tool mockeadada que simula una herramienta de negocio."""
    tool = MagicMock()
    tool.create_lead.return_value = {"id": 1, "name": "Test Lead", "status": "created"}
    tool.send_email.return_value = {"sent": True, "to": "test@example.com"}
    tool.create_invoice.return_value = {"id": 100, "total": 500.0}
    tool.update_stock.return_value = {"product_id": "P001", "new_stock": 50}
    return tool


@pytest.fixture
def orbital_engine():
    """Motor ORBITAL con variables de ejemplo."""
    engine = OrbitalEngine()
    engine.create_variable("Demanda", theta=0.0, amplitude=10.0, velocity=0.15)
    engine.create_variable("Precio", theta=0.3, amplitude=50.0, velocity=0.08)
    engine.create_variable("Oferta", theta=0.5, amplitude=8.0, velocity=0.12)
    engine.create_cycle("Economico", ["Demanda", "Precio", "Oferta"], threshold=0.5)
    return engine


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalContext ↔ OrbitalEngine
# ══════════════════════════════════════════════════════════════


class TestOrbitalContextEngineIntegration:
    """Verifica la integración entre OrbitalContext y OrbitalEngine."""

    def test_context_shares_ovc_with_engine(self):
        """OrbitalContext comparte OVC con OrbitalEngine."""
        ctx = OrbitalContext()
        assert id(ctx.ovc) == id(ctx.engine._ovc)

    def test_context_shares_all_pillars(self):
        """OrbitalContext comparte los 5 pilares."""
        ctx = OrbitalContext()
        assert id(ctx.tor) == id(ctx.engine._tor)
        assert id(ctx.rcc) == id(ctx.engine._rcc)
        assert id(ctx.cod) == id(ctx.engine._cod)
        assert id(ctx.espectro) == id(ctx.engine._espectro)

    def test_variables_created_in_ctx_visible_in_engine(self):
        """Variables creadas en el contexto son visibles en el engine."""
        ctx = OrbitalContext()
        ctx.ovc.create_variable("Test1", theta=0.0, amplitude=5.0)
        var = ctx.engine.get_variable("Test1")
        assert var is not None
        assert var.amplitude == 5.0

    def test_variables_created_in_engine_visible_in_ctx(self):
        """Variables creadas en el engine son visibles en el contexto."""
        ctx = OrbitalContext()
        ctx.engine.create_variable("Test2", theta=1.0, amplitude=3.0)
        var = ctx.ovc.get_variable("Test2")
        assert var is not None
        assert var.amplitude == 3.0

    def test_run_tick_updates_all_pillars(self):
        """Un tick actualiza los 5 pilares."""
        ctx = OrbitalContext()
        ctx.ovc.create_variable("A", theta=0.0, amplitude=5.0, velocity=0.1)
        ctx.ovc.create_variable("B", theta=0.3, amplitude=5.0, velocity=0.1)
        ctx.engine.create_cycle("C1", ["A", "B"], threshold=0.01)

        result = ctx.run_tick()
        assert result.tick == 1
        assert len(result.tor_results) > 0
        assert len(result.rcc_results) > 0
        assert len(result.cod_results) > 0

    def test_multiple_ticks_increment_tick(self):
        """Ticks múltiples incrementan el tick global."""
        ctx = OrbitalContext()
        ctx.ovc.create_variable("X", theta=0.0, amplitude=1.0)
        ctx.run_tick()
        ctx.run_tick()
        ctx.run_tick()
        assert ctx.engine.tick == 3

    def test_snapshot_shows_shared_state(self):
        """El snapshot muestra el estado compartido."""
        ctx = OrbitalContext()
        ctx.ovc.create_variable("A", theta=0.5, amplitude=2.0)
        snapshot = ctx.get_snapshot()
        assert snapshot["ovc_variables"] == 1
        assert snapshot["engine_tick"] == 0

    def test_status_summary_includes_all_pillars(self):
        """El status summary incluye todos los pilares."""
        ctx = OrbitalContext()
        ctx.ovc.create_variable("A", theta=0.0, amplitude=1.0)
        summary = ctx.status_summary()
        assert "ORBITAL CONTEXT" in summary
        assert "Variables orbitales" in summary


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalEngine con herramientas mockeadas
# ══════════════════════════════════════════════════════════════


class TestOrbitalEngineWithTools:
    """Verifica que el motor ORBITAL funciona con herramientas de negocio."""

    def test_engine_variables_from_tool_actions(self):
        """Las acciones de herramientas crean variables orbitales."""
        engine = OrbitalEngine()
        engine.create_variable("crm", theta=0.0, amplitude=1.0)
        engine.create_variable("notification", theta=0.5, amplitude=1.0)
        engine.create_cycle("workflow", ["crm", "notification"], threshold=0.01)

        result = engine.run_tick()
        assert len(result.variables) >= 2

    def test_engine_tension_between_tools(self):
        """Las herramientas generan tensión entre sí."""
        engine = OrbitalEngine()
        engine.create_variable("crm", theta=0.0, amplitude=10.0)
        engine.create_variable("invoice", theta=0.1, amplitude=5.0)

        tor = engine.tor.calculate("crm", "invoice")
        assert isinstance(tor.tor_value, float)
        assert tor.tor_value > 0  # Fases cercanas → TOR positivo

    def test_engine_resonance_detection(self):
        """El motor detecta resonancia entre herramientas alineadas."""
        engine = OrbitalEngine()
        engine.create_variable("A", theta=0.0, amplitude=10.0)
        engine.create_variable("B", theta=0.01, amplitude=10.0)
        engine.create_cycle("Aligned", ["A", "B"], threshold=0.01)

        result = engine.run_tick()
        resonant = [r for r in result.rcc_results if r.is_resonant]
        assert len(resonant) > 0

    def test_engine_collapse_deterministic(self):
        """El colapso es determinista: mismo input → mismo output."""

        def run_from_scratch():
            e = OrbitalEngine()
            e.create_variable("X", theta=0.0, amplitude=5.0, velocity=0.01)
            e.create_variable("Y", theta=0.3, amplitude=5.0, velocity=0.01)
            e.create_cycle("C", ["X", "Y"], threshold=0.01)
            _result = e.run_tick()
            return e.get_value_snapshot()

        val1 = run_from_scratch()
        val2 = run_from_scratch()
        for k in val1:
            assert math.isclose(val1[k], val2[k], abs_tol=1e-10)

    def test_engine_retrofeedback_cycle(self):
        """La retroalimentación cierra el ciclo."""
        engine = OrbitalEngine()
        engine.create_variable("Input", theta=0.0, amplitude=10.0, velocity=0.1)
        engine.create_variable("Output", theta=0.5, amplitude=5.0, velocity=0.1)
        engine.create_cycle("Loop", ["Input", "Output"], threshold=0.01)

        # Ejecutar varios ticks
        for _ in range(5):
            _result = engine.run_tick(retrofeed_damping=0.3)

        # El espectro debe haber retroalimentado
        assert engine.espectro.history_length >= 5

    def test_engine_status_summary(self):
        """El status summary es completo y legible."""
        engine = OrbitalEngine()
        engine.create_variable("A", theta=0.0, amplitude=1.0)
        engine.create_variable("B", theta=0.5, amplitude=2.0)
        engine.create_cycle("Test", ["A", "B"], threshold=0.5)
        engine.run_tick()

        summary = engine.status_summary()
        assert "ORBITAL" in summary
        assert "A" in summary
        assert "B" in summary


# ══════════════════════════════════════════════════════════════
# TESTS: OrbitalCompiler integration
# ══════════════════════════════════════════════════════════════


class TestOrbitalCompilerIntegration:
    """Verifica que el compiler orbital produce resultados válidos."""

    def test_compiler_produces_valid_workflow(self):
        """El compiler produce un workflow válido."""
        from src.orbital.orbital_compiler import OrbitalCompiler

        compiler = OrbitalCompiler()
        result = compiler.compile("Quiero registrar un cliente nuevo")
        assert result.status == "ready"
        assert "steps" in result.workflow
        assert len(result.workflow["steps"]) > 0

    def test_compiler_deterministic(self):
        """El compiler es determinista: mismo texto → mismo resultado."""
        from src.orbital.orbital_compiler import OrbitalCompiler

        OrbitalContext._reset()
        c1 = OrbitalCompiler()
        r1 = c1.compile("Enviar email de notificación")

        OrbitalContext._reset()
        c2 = OrbitalCompiler()
        r2 = c2.compile("Enviar email de notificación")

        assert r1.intent == r2.intent
        assert r1.workflow == r2.workflow

    def test_compiler_multiple_intents(self):
        """El compiler distingue diferentes intenciones."""
        from src.orbital.orbital_compiler import OrbitalCompiler

        OrbitalContext._reset()
        compiler = OrbitalCompiler()

        r1 = compiler.compile("Registrar un cliente")
        r2 = compiler.compile("Enviar email")
        r3 = compiler.compile("Generar factura")
        r4 = compiler.compile("Stock bajo")

        # Al menos 2 de los 4 deben tener intents diferentes
        intents = {r1.intent, r2.intent, r3.intent, r4.intent}
        assert len(intents) >= 2

    def test_compiler_empty_text(self):
        """El compiler maneja texto vacío."""
        from src.orbital.orbital_compiler import OrbitalCompiler

        OrbitalContext._reset()
        compiler = OrbitalCompiler()
        result = compiler.compile("")
        assert result.status == "error"

    def test_compiler_with_entities(self):
        """El compiler extrae entidades simples."""
        from src.orbital.orbital_compiler import OrbitalCompiler

        OrbitalContext._reset()
        compiler = OrbitalCompiler()
        result = compiler.compile("Enviar email a test@example.com con 5 productos")
        assert len(result.entities) >= 1
