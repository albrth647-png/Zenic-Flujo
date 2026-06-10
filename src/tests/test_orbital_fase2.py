"""
FASE 2: Testing y Cobertura — Tests del motor ORBITAL
======================================================

Tests para:
- COD con amplitudes extremas (1, 10, 100, 1000, 10000)
- OrbitalAdapter con tools mockeadas
- OrbitalCompiler con 50+ frases
- EventBus orbital con OrbitalContext
- Integración ORBITAL ↔ WorkflowEngine
- Cobertura total del módulo orbital

Skills: test-driven-development, doubt-driven-development
MCPs: analyzer (cobertura), expert-mcp (edge cases)
"""
import math
import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.orbital.context import OrbitalContext


# ══════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_context():
    """Reset OrbitalContext singleton antes de cada test."""
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def mock_crm():
    class MockCRM:
        def create_lead(self, name="", email=""):
            return {"id": 1, "name": name, "email": email}
        def update_lead(self, lead_id=0, **kwargs):
            return {"id": lead_id, "updated": True}
        def list_leads(self, stage=None):
            return [{"id": 1, "name": "Test"}]
    return MockCRM()


@pytest.fixture
def mock_notification():
    class MockNotification:
        def send_email(self, to="", subject="", body=""):
            return {"status": "sent", "to": to}
        def send_whatsapp(self, to="", message=""):
            return {"status": "sent", "to": to}
    return MockNotification()


@pytest.fixture
def mock_invoice():
    class MockInvoice:
        def create_invoice(self, client_name="", items=None, **kwargs):
            return {"id": 1, "number": "INV-001", "total": 100.0}
        def list_invoices(self, status=None):
            return [{"id": 1, "number": "INV-001"}]
    return MockInvoice()


# ══════════════════════════════════════════════════════════════
# 2.3: COD con amplitudes extremas
# ══════════════════════════════════════════════════════════════

class TestCODExtremeAmplitudes:
    """Verificar que COD converge SIEMPRE sin importar la escala de amplitudes."""

    def _run_cod_with_amplitude(self, amplitude: float, name: str = "Test"):
        """Helper: crear engine con amplitud dada y ejecutar un tick."""
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable(f"{name}_A", theta=0.0, amplitude=amplitude, velocity=0.1)
        engine.create_variable(f"{name}_B", theta=0.5, amplitude=amplitude, velocity=0.1)
        engine.create_cycle(f"cycle_{name}", [f"{name}_A", f"{name}_B"], threshold=0.5)
        result = engine.run_tick()
        return result, engine

    def test_cod_converge_amplitude_1(self):
        result, engine = self._run_cod_with_amplitude(1.0, "A1")
        assert result is not None
        assert len(result.cod_results) > 0

    def test_cod_converge_amplitude_10(self):
        result, engine = self._run_cod_with_amplitude(10.0, "A10")
        assert result is not None
        assert len(result.cod_results) > 0

    def test_cod_converge_amplitude_100(self):
        result, engine = self._run_cod_with_amplitude(100.0, "A100")
        assert result is not None
        # Verificar que no divergió
        snap = engine.get_value_snapshot()
        for name, val in snap.items():
            assert abs(val) < 1000, f"Variable {name} divergió con amplitud 100: {val}"

    def test_cod_converge_amplitude_1000(self):
        result, engine = self._run_cod_with_amplitude(1000.0, "A1K")
        assert result is not None
        snap = engine.get_value_snapshot()
        for name, val in snap.items():
            assert abs(val) < 10000, f"Variable {name} divergió con amplitud 1000: {val}"

    def test_cod_converge_amplitude_10000(self):
        result, engine = self._run_cod_with_amplitude(10000.0, "A10K")
        assert result is not None
        # Con amplitudes extremas, el COD debe mantener valores acotados
        snap = engine.get_value_snapshot()
        for name, val in snap.items():
            assert abs(val) < 100000, f"Variable {name} divergió con amplitud 10000: {val}"

    def test_cod_converge_mixed_amplitudes(self):
        """Amplitudes muy diferentes entre sí — sistema heterogéneo."""
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable("big", theta=0.0, amplitude=10000.0, velocity=0.1)
        engine.create_variable("small", theta=0.5, amplitude=0.001, velocity=0.1)
        engine.create_cycle("mixed", ["big", "small"], threshold=0.5)
        result = engine.run_tick()
        assert result is not None
        snap = engine.get_value_snapshot()
        for name, val in snap.items():
            assert abs(val) < 1e8, f"Variable {name} divergió: {val}"

    def test_cod_multiple_ticks_stability(self):
        """10 ticks consecutivos — el sistema debe permanecer estable."""
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable("X", theta=0.0, amplitude=500.0, velocity=0.1)
        engine.create_variable("Y", theta=1.0, amplitude=500.0, velocity=0.1)
        engine.create_cycle("stab", ["X", "Y"], threshold=0.5)

        for i in range(10):
            result = engine.run_tick()
            snap = engine.get_value_snapshot()
            for name, val in snap.items():
                assert abs(val) < 1e6, f"Tick {i}: variable {name} divergió: {val}"


# ══════════════════════════════════════════════════════════════
# 2.4: OrbitalAdapter con tools mockeadas
# ══════════════════════════════════════════════════════════════

class TestOrbitalAdapterMocks:
    """Tests del adaptador orbital con herramientas mockeadas."""

    def test_register_tool(self):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm := type("", (), {"create_lead": lambda self, **kw: {"ok": True}})())
        assert "crm" in adapter._tools

    def test_register_tools_batch(self):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tools_batch({"crm": object(), "notification": object()})
        assert len(adapter._tools) == 2

    def test_execute_success(self, mock_crm):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        result = adapter.execute_action("crm", "create_lead", {"name": "Juan"})
        assert result.status == "completed"
        assert result.data["name"] == "Juan"

    def test_execute_failure(self):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", object())  # sin create_lead
        result = adapter.execute_action("crm", "create_lead", {})
        assert result.status == "failed"
        assert "error" in result.data

    def test_execute_unregistered_tool(self):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        result = adapter.execute_action("nonexistent", "action", {})
        assert result.status == "failed"
        assert "no registrada" in result.data["error"]

    def test_execute_missing_action(self):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", type("", (), {})())
        result = adapter.execute_action("crm", "nonexistent_action", {})
        assert result.status == "failed"

    def test_orbital_variable_created(self, mock_crm):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        adapter.execute_action("crm", "create_lead", {"name": "Test"})
        var = adapter._ovc.get_variable("crm")
        assert var is not None

    def test_phase_advances_on_success(self, mock_crm):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        adapter.execute_action("crm", "create_lead", {"name": "A"})
        phase1 = adapter.get_tool_phase("crm")
        adapter.execute_action("crm", "create_lead", {"name": "B"})
        phase2 = adapter.get_tool_phase("crm")
        assert phase2 != phase1  # La fase debe haber avanzado

    def test_tool_alignment(self, mock_crm, mock_notification):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        adapter.register_tool("notification", mock_notification)
        alignment = adapter.get_tool_alignment("crm", "notification")
        assert alignment is not None
        assert -1 <= alignment <= 1

    def test_orbital_snapshot(self, mock_crm):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        snapshot = adapter.get_orbital_snapshot()
        assert "tools_registered" in snapshot
        assert "phases" in snapshot
        assert "values" in snapshot

    def test_recommendations(self, mock_crm, mock_notification):
        from src.orbital.orbital_adapter import OrbitalAdapter
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        adapter.register_tool("notification", mock_notification)
        adapter.execute_action("crm", "create_lead", {"name": "Test"})
        recs = adapter.get_tool_recommendations("crm")
        assert isinstance(recs, list)
        assert "notification" in recs


# ══════════════════════════════════════════════════════════════
# 2.5: OrbitalCompiler con 50+ frases
# ══════════════════════════════════════════════════════════════

class TestOrbitalCompilerPhrases:
    """Verificar compilación correcta con 50+ frases en español e inglés."""

    def _compile(self, text):
        from src.orbital.orbital_compiler import OrbitalCompiler
        compiler = OrbitalCompiler()
        return compiler.compile(text)

    # ── Frases de registro de cliente ──
    def test_phrase_registrar_cliente_1(self):
        r = self._compile("Quiero registrar un cliente nuevo")
        assert r.status == "ready"
        assert r.intent in ("registro_cliente", "notificacion", "general")

    def test_phrase_registrar_cliente_2(self):
        r = self._compile("Crear un lead en el CRM")
        assert r.status == "ready"

    def test_phrase_registrar_cliente_3(self):
        r = self._compile("Agregar contacto nuevo a la base de datos")
        assert r.status == "ready"

    def test_phrase_registrar_cliente_4(self):
        r = self._compile("Guardar nuevo cliente con nombre y email")
        assert r.status == "ready"

    def test_phrase_registrar_cliente_5(self):
        r = self._compile("Register a new customer in the CRM")
        assert r.status == "ready"

    # ── Frases de facturación ──
    def test_phrase_factura_1(self):
        r = self._compile("Generar factura semanal")
        assert r.status == "ready"

    def test_phrase_factura_2(self):
        r = self._compile("Crear factura para el cliente")
        assert r.status == "ready"

    def test_phrase_factura_3(self):
        r = self._compile("Cobrar al cliente por los servicios")
        assert r.status == "ready"

    def test_phrase_factura_4(self):
        r = self._compile("Generar una factura pendiente")
        assert r.status == "ready"

    def test_phrase_factura_5(self):
        r = self._compile("Send an invoice to the client")
        assert r.status == "ready"

    # ── Frases de stock/inventario ──
    def test_phrase_stock_1(self):
        r = self._compile("Alerta de stock bajo en inventario")
        assert r.status == "ready"

    def test_phrase_stock_2(self):
        r = self._compile("Revisar el inventario diariamente")
        assert r.status == "ready"

    def test_phrase_stock_3(self):
        r = self._compile("Producto con stock cero necesita reabastecimiento")
        assert r.status == "ready"

    def test_phrase_stock_4(self):
        r = self._compile("Check low stock products")
        assert r.status == "ready"

    def test_phrase_stock_5(self):
        r = self._compile("Alertar cuando el inventario esté bajo")
        assert r.status == "ready"

    # ── Frases de notificación ──
    def test_phrase_notificacion_1(self):
        r = self._compile("Enviar email de bienvenida")
        assert r.status == "ready"

    def test_phrase_notificacion_2(self):
        r = self._compile("Notificar al equipo por correo")
        assert r.status == "ready"

    def test_phrase_notificacion_3(self):
        r = self._compile("Enviar mensaje de felicitación")
        assert r.status == "ready"

    def test_phrase_notificacion_4(self):
        r = self._compile("Send notification to admin")
        assert r.status == "ready"

    def test_phrase_notificacion_5(self):
        r = self._compile("Avisar al administrador del sistema")
        assert r.status == "ready"

    # ── Frases generales / ambiguas ──
    def test_phrase_general_1(self):
        r = self._compile("Hola, ¿cómo estás?")
        assert r.status in ("ready", "error")

    def test_phrase_general_2(self):
        r = self._compile("Necesito automatizar algo")
        assert r.status in ("ready", "error")

    def test_phrase_general_3(self):
        r = self._compile("Ayúdame con mi negocio")
        assert r.status in ("ready", "error")

    def test_phrase_general_4(self):
        r = self._compile("Quiero hacer todo más eficiente")
        assert r.status in ("ready", "error")

    def test_phrase_general_5(self):
        r = self._compile("Help me automate my workflow")
        assert r.status in ("ready", "error")

    # ── Frases con entidades ──
    def test_phrase_with_email(self):
        r = self._compile("Enviar email a juan@correo.com")
        assert r.status == "ready"
        assert len(r.entities) >= 1

    def test_phrase_with_number(self):
        r = self._compile("Actualizar stock a 500 unidades")
        assert r.status == "ready"

    # ── Frases en inglés ──
    def test_phrase_english_1(self):
        r = self._compile("Create a new lead in CRM")
        assert r.status == "ready"

    def test_phrase_english_2(self):
        r = self._compile("Generate weekly invoice")
        assert r.status == "ready"

    def test_phrase_english_3(self):
        r = self._compile("Send birthday email to customers")
        assert r.status == "ready"

    def test_phrase_english_4(self):
        r = self._compile("Alert when inventory is low")
        assert r.status == "ready"

    def test_phrase_english_5(self):
        r = self._compile("Notify admin about new file")
        assert r.status == "ready"

    # ── Frases con sinónimos ──
    def test_phrase_synonym_1(self):
        r = self._compile("Ingresar datos del nuevo lead")
        assert r.status == "ready"

    def test_phrase_synonym_2(self):
        r = self._compile("Cargar información del cliente recién llegado")
        assert r.status == "ready"

    def test_phrase_synonym_3(self):
        r = self._compile("Registrar a la persona que nos contactó")
        assert r.status == "ready"

    # ── Frases vacías / edge cases ──
    def test_empty_text(self):
        r = self._compile("")
        assert r.status == "error"

    def test_single_word(self):
        r = self._compile("cliente")
        assert r.status in ("ready", "error")

    def test_numbers_only(self):
        r = self._compile("12345")
        assert r.status in ("ready", "error")

    # ── Determinismo ──
    def test_determinism_same_text(self):
        from src.orbital.orbital_compiler import OrbitalCompiler
        compiler = OrbitalCompiler()
        r1 = compiler.compile("registrar cliente nuevo")
        r2 = compiler.compile("registrar cliente nuevo")
        assert r1.intent == r2.intent

    def test_compilation_count(self):
        from src.orbital.orbital_compiler import OrbitalCompiler
        compiler = OrbitalCompiler()
        assert compiler.compilation_count == 0
        compiler.compile("test")
        assert compiler.compilation_count == 1
        compiler.compile("test 2")
        assert compiler.compilation_count == 2


# ══════════════════════════════════════════════════════════════
# 2.6: EventBus orbital
# ══════════════════════════════════════════════════════════════

class TestEventBusOrbital:
    """Tests del EventBus con OrbitalContext."""

    def test_event_creates_orbital_variable(self):
        from src.events.bus import EventBus
        EventBus._reset()
        bus = EventBus()
        bus._ensure_orbital_variable("test.event")
        var = bus._ctx.ovc.get_variable("test.event")
        assert var is not None
        assert var.orbit_group == "event_bus"
        EventBus._reset()

    def test_event_phase_deterministic(self):
        from src.events.bus import EventBus
        EventBus._reset()
        bus = EventBus()
        bus._ensure_orbital_variable("crm.lead.created")
        phase1 = bus.get_event_phase("crm.lead.created")
        phase2 = bus.get_event_phase("crm.lead.created")
        assert math.isclose(phase1, phase2, abs_tol=1e-10)
        EventBus._reset()

    def test_event_resonance(self):
        from src.events.bus import EventBus
        EventBus._reset()
        bus = EventBus()
        bus._ensure_orbital_variable("crm.lead.created")
        bus._ensure_orbital_variable("invoice.created")
        resonance = bus.get_event_resonance("crm.lead.created", "invoice.created")
        assert resonance is not None
        assert -1 <= resonance <= 1
        EventBus._reset()

    def test_orbital_snapshot(self):
        from src.events.bus import EventBus
        EventBus._reset()
        bus = EventBus()
        bus._ensure_orbital_variable("test.event")
        snapshot = bus.get_orbital_snapshot()
        assert "variables" in snapshot
        assert "phases" in snapshot
        assert "orbital_mode" in snapshot
        assert snapshot["orbital_mode"] is True
        EventBus._reset()

    def test_system_events(self):
        from src.events.bus import EventBus
        EventBus._reset()
        bus = EventBus()
        events = bus.get_system_events()
        assert len(events) > 0
        EventBus._reset()


# ══════════════════════════════════════════════════════════════
# 2.2: Integración ORBITAL ↔ WorkflowEngine
# ══════════════════════════════════════════════════════════════

class TestOrbitalWorkflowIntegration:
    """Tests de integración entre motor ORBITAL y WorkflowEngine."""

    def test_orbital_engine_completo(self):
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable("var_a", theta=0.0, amplitude=1.0, velocity=0.1)
        engine.create_variable("var_b", theta=1.5, amplitude=1.0, velocity=0.1)
        engine.create_cycle("test_cycle", ["var_a", "var_b"], threshold=0.3)
        result = engine.run_tick()
        assert result is not None
        assert len(result.tor_results) > 0
        assert result.espectro is not None

    def test_compiler_adapter_integration(self, mock_crm, mock_notification):
        from src.orbital.orbital_compiler import OrbitalCompiler
        from src.orbital.orbital_adapter import OrbitalAdapter
        compiler = OrbitalCompiler()
        compile_result = compiler.compile("registrar cliente nuevo")
        assert compile_result.status == "ready"
        adapter = OrbitalAdapter()
        adapter.register_tool("crm", mock_crm)
        adapter.register_tool("notification", mock_notification)
        crm_result = adapter.execute_action("crm", "create_lead", {"name": "Juan"})
        assert crm_result.status == "completed"
        recs = adapter.get_tool_recommendations("crm")
        assert isinstance(recs, list)

    def test_determinismo_multiples_ticks(self):
        from src.orbital.engine import OrbitalEngine
        def run_engine():
            engine = OrbitalEngine()
            engine.create_variable("x", theta=0.5, amplitude=1.0, velocity=0.1)
            engine.create_variable("y", theta=1.5, amplitude=2.0, velocity=0.2)
            engine.create_cycle("c1", ["x", "y"], threshold=0.3)
            return engine.run_tick()
        r1 = run_engine()
        r2 = run_engine()
        assert math.isclose(r1.tor_results[0].tor_value, r2.tor_results[0].tor_value, abs_tol=1e-10)

    def test_retroalimentacion_circular(self):
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable("var_a", theta=0.0, amplitude=1.0, velocity=0.1, orbit_group="test")
        engine.create_variable("var_b", theta=1.0, amplitude=1.0, velocity=0.1, orbit_group="test")
        engine.create_cycle("cycle_retro", ["var_a", "var_b"], threshold=0.3)
        initial_phases = {name: var.theta for name, var in engine.ovc.get_all_variables().items()}
        for _ in range(3):
            engine.run_tick()
        final_phases = {name: var.theta for name, var in engine.ovc.get_all_variables().items()}
        any_changed = any(
            not math.isclose(initial_phases.get(name, 0), final_phases.get(name, 0), abs_tol=1e-6)
            for name in final_phases
        )
        assert any_changed, "La retroalimentación circular no está funcionando"

    def test_cod_convergence(self):
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable("stable_a", theta=0.0, amplitude=1.0, velocity=0.01)
        engine.create_variable("stable_b", theta=0.5, amplitude=1.0, velocity=0.01)
        engine.create_cycle("conv", ["stable_a", "stable_b"], threshold=0.5)
        for _ in range(10):
            engine.run_tick()
        snap = engine.get_value_snapshot()
        for name, value in snap.items():
            assert abs(value) < 100, f"Variable {name} divergió: {value}"

    def test_espectro_multimodal(self):
        from src.orbital.engine import OrbitalEngine
        engine = OrbitalEngine()
        engine.create_variable("mode_a", theta=0.0, amplitude=2.0, velocity=0.1)
        engine.create_variable("mode_b", theta=1.0, amplitude=1.5, velocity=0.1)
        engine.create_variable("mode_c", theta=2.0, amplitude=1.0, velocity=0.1)
        engine.create_cycle("spectral", ["mode_a", "mode_b", "mode_c"], threshold=0.3)
        result = engine.run_tick()
        assert result.espectro is not None
        assert len(result.espectro.modes) > 0

    def test_step_executor_orbital(self, mock_crm):
        from src.workflow.step_executor import StepExecutor
        executor = StepExecutor()
        executor.register_tool("crm", mock_crm)
        step = {"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}}
        context = {"input": {"name": "Test"}, "steps_output": {}}
        result = executor.execute(step, context)
        assert result.status == "completed"
        assert executor.ovc.variable_count >= 1

    def test_condition_evaluator(self):
        from src.workflow.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("5 < 10", {}) is True
        assert evaluator.evaluate("stock < 10", {"stock": 5}) is True
        assert evaluator.evaluate("stock < 10", {"stock": 15}) is False
        assert evaluator.evaluate("", {}) is True
