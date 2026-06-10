"""
DDE v3 — Tests del WorkflowValidator
"""


class TestWorkflowValidator:
    """Tests para WorkflowValidator.validate()."""

    def test_validate_workflow_valido(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "description": "Test workflow",
            "trigger_type": "event",
            "trigger_config": {"event": "test.event"},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}},
                {"id": 2, "tool": "notification", "action": "send_email",
                 "params": {"to": "test@test.com"}},
            ],
        }
        result = validator.validate(workflow)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_vacio(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        result = validator.validate({})
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_trigger_invalido(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "trigger_type": "invalid_type",
            "trigger_config": {},
            "steps": [],
        }
        result = validator.validate(workflow)
        assert result.valid is False
        assert any("inválido" in e for e in result.errors)

    def test_validate_steps_sin_tool(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "trigger_type": "event",
            "trigger_config": {"event": "test"},
            "steps": [
                {"id": 1, "tool": "", "action": "do_something", "params": {}},
            ],
        }
        result = validator.validate(workflow)
        assert result.valid is False

    def test_validate_ids_duplicados(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "trigger_type": "event",
            "trigger_config": {"event": "test"},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}},
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}},
            ],
        }
        result = validator.validate(workflow)
        assert result.valid is False
        assert any("duplicado" in e for e in result.errors)

    def test_validate_unresolved_slot_refs(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "trigger_type": "event",
            "trigger_config": {"event": "test"},
            "steps": [
                {"id": 1, "tool": "notification", "action": "send_email",
                 "params": {"to": "$slot.email_sin_resolver"}},
            ],
        }
        result = validator.validate(workflow)
        assert result.valid is False
        assert any("$slot" in e for e in result.errors)

    def test_validate_warnings_tool_desconocida(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "trigger_type": "manual",
            "trigger_config": {},
            "steps": [
                {"id": 1, "tool": "tool_inexistente", "action": "run", "params": {}},
            ],
        }
        result = validator.validate(workflow)
        # Tool desconocida es warning, no error
        assert result.valid is True
        assert len(result.warnings) > 0

    def test_validate_determinista(self):
        from src.nlu.validator import WorkflowValidator

        validator = WorkflowValidator()
        workflow = {
            "name": "Test",
            "trigger_type": "event",
            "trigger_config": {"event": "test"},
            "steps": [
                {"id": 1, "tool": "crm", "action": "create_lead", "params": {}},
            ],
        }
        r1 = validator.validate(workflow)
        r2 = validator.validate(workflow)
        assert r1.valid == r2.valid
        assert r1.errors == r2.errors
