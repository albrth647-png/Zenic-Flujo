"""
DDE v3 — Tests del WorkflowCompiler
"""


class TestWorkflowCompiler:
    """Tests para WorkflowCompiler.compile()."""

    def test_compile_registro_cliente(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot, Entity

        compiler = WorkflowCompiler()
        # Los fragmentos de registro_cliente requieren: nombre, email_destino
        slots = (
            Slot(name="nombre", required=True, filled=True,
                 value="Juan Pérez", source="entity"),
            Slot(name="email_destino", required=True, filled=True,
                 value="juan@email.com", source="entity"),
            Slot(name="telefono", required=False, filled=True,
                 value="555-1234", source="entity"),
        )
        entities = (
            Entity(type="email", value="juan@email.com", raw="juan@email.com",
                   span=(0, 15), score=1.0),
        )
        result = compiler.compile("registro_cliente", slots, entities, "es")

        assert result.status == "ready"
        assert "name" in result.workflow
        assert result.workflow["trigger_type"] in ("event", "schedule", "manual")
        assert len(result.workflow["steps"]) >= 1
        assert len(result.explanation) > 0

    def test_compile_missing_slots(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot

        compiler = WorkflowCompiler()
        slots = (
            Slot(name="nombre", required=True, filled=False, value=None, source="entity"),
            Slot(name="email_destino", required=True, filled=False, value=None,
                 source="entity"),
        )
        entities = ()
        result = compiler.compile("registro_cliente", slots, entities, "es")

        assert result.status == "needs_clarification"
        assert len(result.missing_slots) > 0

    def test_compile_unknown_intent(self):
        from src.nlu.compiler import WorkflowCompiler

        compiler = WorkflowCompiler()
        slots = ()
        entities = ()
        result = compiler.compile("intencion_inexistente", slots, entities, "es")

        assert result.status == "unknown"

    def test_compile_alerta_stock(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot

        compiler = WorkflowCompiler()
        # El fragmento trigger de schedule requiere 'frecuencia'
        slots = (
            Slot(name="frecuencia", required=True, filled=True,
                 value="0 9 * * *", source="entity"),
            Slot(name="email_admin", required=False, filled=True,
                 value="admin@corp.com", source="default"),
            Slot(name="umbral_stock", required=False, filled=True,
                 value="10", source="default"),
        )
        entities = ()
        result = compiler.compile("alerta_stock_bajo", slots, entities, "es")

        assert result.status == "ready"
        assert result.workflow["trigger_type"] == "schedule"

    def test_compile_resuelve_slots_en_params(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot

        compiler = WorkflowCompiler()
        # Todos los slots requeridos por fragmentos + telefono (usado en params)
        slots = (
            Slot(name="nombre", required=True, filled=True,
                 value="Juan Pérez", source="entity"),
            Slot(name="email_destino", required=True, filled=True,
                 value="juan@email.com", source="entity"),
            Slot(name="telefono", required=False, filled=True,
                 value="555-1234", source="entity"),
        )
        entities = ()
        result = compiler.compile("registro_cliente", slots, entities, "es")

        assert result.status == "ready"
        steps = result.workflow.get("steps", [])
        # Verificar que los slots se resolvieron (no hay $slot.xxx)
        params_str = str(steps)
        assert "$slot." not in params_str, f"Slots sin resolver en: {params_str}"
        # Verificar que los valores de los slots aparecieron en los params
        assert "juan@email.com" in params_str
        assert "555-1234" in params_str

    def test_compile_resuelve_intent_event(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot

        compiler = WorkflowCompiler()
        slots = (
            Slot(name="nombre", required=True, filled=True,
                 value="Juan", source="entity"),
            Slot(name="email_destino", required=True, filled=True,
                 value="juan@test.com", source="entity"),
        )
        entities = ()
        result = compiler.compile("registro_cliente", slots, entities, "es")

        assert result.status == "ready"
        # El trigger debe tener el evento resuelto (no $intent_event literal)
        trigger_config = result.workflow.get("trigger_config", {})
        event_val = trigger_config.get("event", "")
        assert isinstance(event_val, str)
        assert "$" not in event_val
        assert event_val == "crm.lead.created"

    def test_compile_resuelve_settings_defaults(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot

        compiler = WorkflowCompiler()
        # alerta_stock_bajo requiere 'frecuencia' del trigger fragment
        # y tiene default email_admin=$settings.admin_email
        slots = (
            Slot(name="frecuencia", required=True, filled=True,
                 value="0 9 * * *", source="entity"),
            Slot(name="email_admin", required=False, filled=True,
                 value="$settings.admin_email", source="default"),
        )
        entities = ()
        result = compiler.compile("alerta_stock_bajo", slots, entities, "es")

        assert result.status == "ready"
        steps = result.workflow.get("steps", [])
        params_str = str(steps)
        # El $settings.admin_email debe haberse resuelto
        assert "$settings." not in params_str, f"$settings sin resolver en: {params_str}"

    def test_compile_determinista(self):
        from src.nlu.compiler import WorkflowCompiler
        from src.nlu.entities.base import Slot

        compiler = WorkflowCompiler()
        slots = (
            Slot(name="email_destino", required=True, filled=True,
                 value="test@test.com", source="entity"),
        )
        entities = ()
        r1 = compiler.compile("registro_cliente", slots, entities, "es")
        r2 = compiler.compile("registro_cliente", slots, entities, "es")

        assert r1.status == r2.status
        assert r1.workflow.get("name") == r2.workflow.get("name")
