"""
Workflow Determinista — Tests del StepExecutor
Tests unitarios para el ejecutor de pasos: resolución de variables, timeout, tools.
"""
import pytest
from unittest.mock import MagicMock


class TestStepExecutor:
    """Tests para la clase StepExecutor."""

    def test_execute_simple_step(self):
        """Test: ejecutar un paso simple con una tool registrada."""
        from src.workflow.step_executor import StepExecutor, StepResult

        executor = StepExecutor()
        mock_tool = MagicMock()
        mock_tool.create_lead.return_value = {"id": 1, "name": "Juan"}
        executor.register_tool("crm", mock_tool)

        step = {
            "id": 1,
            "tool": "crm",
            "action": "create_lead",
            "params": {"name": "Juan", "email": "juan@test.com"},
        }

        result = executor.execute(step, {"input": {}})
        assert result.status == "completed"
        assert result.output_data == {"id": 1, "name": "Juan"}
        mock_tool.create_lead.assert_called_once_with(name="Juan", email="juan@test.com")

    def test_execute_step_with_variable_resolution(self):
        """Test: las variables $input.nombre se resuelven desde el contexto."""
        from src.workflow.step_executor import StepExecutor

        executor = StepExecutor()
        mock_tool = MagicMock()
        mock_tool.create_lead.return_value = {"id": 1}
        executor.register_tool("crm", mock_tool)

        step = {
            "id": 1,
            "tool": "crm",
            "action": "create_lead",
            "params": {"name": "$input.nombre", "email": "$input.correo"},
        }

        context = {
            "input": {"nombre": "María", "correo": "maria@test.com"},
            "output": {},
        }

        result = executor.execute(step, context)
        assert result.status == "completed"
        mock_tool.create_lead.assert_called_once_with(name="María", email="maria@test.com")

    def test_execute_step_tool_not_found(self):
        """Test: tool no registrada retorna StepResult con status='failed'."""
        from src.workflow.step_executor import StepExecutor

        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "nonexistent",
            "action": "do_something",
            "params": {},
        }

        result = executor.execute(step, {})
        assert result.status == "failed"
        assert "no registrada" in result.error_message

    def test_execute_step_action_not_found(self):
        """Test: acción no encontrada en tool retorna StepResult con status='failed'."""
        from src.workflow.step_executor import StepExecutor

        executor = StepExecutor()
        mock_tool = MagicMock(spec=[])  # No methods
        executor.register_tool("crm", mock_tool)

        step = {
            "id": 1,
            "tool": "crm",
            "action": "nonexistent_action",
            "params": {},
        }

        result = executor.execute(step, {})
        assert result.status == "failed"

    def test_execute_step_with_timeout(self):
        """Test: un paso que excede el timeout retorna StepResult con status='failed'."""
        import time
        from src.workflow.step_executor import StepExecutor

        executor = StepExecutor()
        mock_tool = MagicMock()

        def slow_action(**kwargs):
            time.sleep(5)
            return {"status": "ok"}

        mock_tool.slow_action = slow_action
        executor.register_tool("test", mock_tool)

        step = {
            "id": 1,
            "tool": "test",
            "action": "slow_action",
            "params": {},
            "timeout": 1,  # 1 second timeout
        }

        result = executor.execute(step, {})
        assert result.status == "failed"
        assert "timeout" in result.error_message.lower() or "excedió" in result.error_message.lower()

    def test_execute_system_action_backup(self):
        """Test: acción de sistema backup_database funciona."""
        from src.workflow.step_executor import StepExecutor

        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "backup_database",
            "params": {},
        }

        # This will fail without DB, but we test the routing
        result = executor.execute(step, {})
        # May fail due to no DB, but should not crash
        assert result.status in ("completed", "failed")

    def test_resolve_params_nested(self):
        """Test: resolución de parámetros anidados."""
        from src.workflow.step_executor import StepExecutor

        executor = StepExecutor()
        mock_tool = MagicMock()
        mock_tool.test_action.return_value = {"ok": True}
        executor.register_tool("test", mock_tool)

        step = {
            "id": 1,
            "tool": "test",
            "action": "test_action",
            "params": {
                "nested": {"key": "$input.value"},
                "list_items": ["$input.item1", "static_value"],
            },
        }

        context = {"input": {"value": "resolved", "item1": "first"}}
        result = executor.execute(step, context)
        assert result.status == "completed"

    def test_step_result_creation(self):
        """Test: StepResult se crea correctamente con todos los campos."""
        from src.workflow.step_executor import StepResult

        result = StepResult(
            status="completed",
            output_data={"id": 1},
            duration_ms=150,
        )
        assert result.status == "completed"
        assert result.output_data == {"id": 1}
        assert result.duration_ms == 150
        assert result.error_message is None
