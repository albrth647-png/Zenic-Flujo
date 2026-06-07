"""
Workflow Determinista — Tests del BranchHandler, LoopHandler, ErrorHandler
Tests unitarios para los handlers de flujo de control del workflow engine.
"""
import pytest
from unittest.mock import MagicMock


class TestBranchHandler:
    """Tests para la clase BranchHandler."""

    def test_evaluate_if_else_first_branch(self, branch_handler):
        """Test: se toma la primera rama cuando su condición es True."""
        step = {
            "branches": [
                {"name": "low_stock", "condition": "stock < 10", "steps": [{"id": 1, "tool": "notification", "action": "send_email", "params": {}}]},
                {"name": "ok", "condition": "True", "steps": []},
            ],
        }
        result = branch_handler.evaluate(step, {"stock": 5})
        assert result.branch_taken == "low_stock"
        assert len(result.steps) == 1

    def test_evaluate_if_else_default_branch(self, branch_handler):
        """Test: se toma la rama default cuando ninguna condición se cumple."""
        step = {
            "branches": [
                {"name": "critical", "condition": "stock == 0", "steps": [{"id": 1}]},
                {"name": "default", "condition": "True", "steps": [{"id": 2}]},
            ],
        }
        result = branch_handler.evaluate(step, {"stock": 50})
        assert result.branch_taken == "default"

    def test_evaluate_no_match_raises(self, branch_handler):
        """Test: si ninguna rama coincide y no hay default, lanza ValueError."""
        step = {
            "branches": [
                {"name": "only", "condition": "stock == 0", "steps": []},
            ],
        }
        with pytest.raises(ValueError, match="Ninguna condición"):
            branch_handler.evaluate(step, {"stock": 5})

    def test_evaluate_empty_branches_raises(self, branch_handler):
        """Test: branch sin ramas definidas lanza ValueError."""
        step = {"branches": []}
        with pytest.raises(ValueError, match="sin ramas"):
            branch_handler.evaluate(step, {})

    def test_evaluate_switch_matches_case(self, branch_handler):
        """Test: switch evalúa correctamente un case que coincide."""
        cases = [
            {"value": "new", "steps": [{"id": 1}]},
            {"value": "vip", "steps": [{"id": 2}]},
            {"default": True, "steps": [{"id": 3}]},
        ]
        result = branch_handler.evaluate_switch("$input.stage", cases, {"input": {"stage": "vip"}})
        assert result.branch_taken == "case_vip"

    def test_evaluate_switch_default_fallback(self, branch_handler):
        """Test: switch retorna default cuando ningún case coincide."""
        cases = [
            {"value": "new", "steps": [{"id": 1}]},
            {"value": "vip", "steps": [{"id": 2}]},
            {"default": True, "steps": [{"id": 3}]},
        ]
        result = branch_handler.evaluate_switch("$input.stage", cases, {"input": {"stage": "inactive"}})
        assert result.branch_taken == "default"

    def test_evaluate_switch_no_default_raises(self, branch_handler):
        """Test: switch sin default y sin match lanza ValueError."""
        cases = [
            {"value": "new", "steps": []},
            {"value": "vip", "steps": []},
        ]
        with pytest.raises(ValueError, match="ningún case coincide"):
            branch_handler.evaluate_switch("$input.stage", cases, {"input": {"stage": "unknown"}})

    def test_evaluate_switch_default_checked_last(self, branch_handler):
        """Test: default se evalúa al final, no primero (bug fix verification)."""
        cases = [
            {"default": True, "steps": [{"id": 99}]},
            {"value": "specific", "steps": [{"id": 1}]},
        ]
        result = branch_handler.evaluate_switch("$input.val", cases, {"input": {"val": "specific"}})
        # Should match "specific" case, not default
        assert result.branch_taken == "case_specific"


class TestLoopHandler:
    """Tests para la clase LoopHandler."""

    def test_execute_foreach(self, loop_handler):
        """Test: foreach ejecuta steps por cada item de la colección."""
        step = {
            "type": "foreach",
            "collection": "$input.items",
            "item_var": "item",
            "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}}],
        }
        mock_executor = MagicMock()
        from src.workflow.step_executor import StepResult
        mock_executor.execute.return_value = StepResult(status="completed", output_data={"ok": True})

        context = {"input": {"items": ["Alice", "Bob", "Charlie"]}, "output": {}}
        result = loop_handler.execute(step, context, mock_executor)
        assert result.iterations == 3
        assert mock_executor.execute.call_count == 3

    def test_execute_for_loop(self, loop_handler):
        """Test: for loop ejecuta steps N veces."""
        step = {
            "type": "for",
            "start": 0,
            "end": 3,
            "step": 1,
            "index_var": "i",
            "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {"name": "Test"}}],
        }
        mock_executor = MagicMock()
        from src.workflow.step_executor import StepResult
        mock_executor.execute.return_value = StepResult(status="completed", output_data={"ok": True})

        context = {"input": {}, "output": {}}
        result = loop_handler.execute(step, context, mock_executor)
        assert result.iterations == 3

    def test_execute_while_loop(self, loop_handler):
        """Test: while loop con max_iterations."""
        step = {
            "type": "while",
            "condition": "True",  # Always true
            "max_iterations": 3,
            "steps": [{"id": 1, "tool": "system", "action": "get_setting", "params": {"key": "test"}}],
        }
        mock_executor = MagicMock()
        from src.workflow.step_executor import StepResult
        mock_executor.execute.return_value = StepResult(status="completed", output_data={"ok": True})

        context = {"input": {}, "output": {}}
        result = loop_handler.execute(step, context, mock_executor)
        assert result.iterations == 3  # Stopped by max_iterations

    def test_execute_unknown_type_raises(self, loop_handler):
        """Test: tipo de loop desconocido lanza ValueError."""
        step = {"type": "unknown_loop"}
        with pytest.raises(ValueError):
            loop_handler.execute(step, {}, MagicMock())


class TestErrorHandler:
    """Tests para la clase ErrorHandler."""

    def test_handle_retry_success(self, error_handler):
        """Test: un paso que falla y luego se recupera en retry."""
        from src.workflow.step_executor import StepResult

        mock_executor = MagicMock()
        # Fail first, then succeed
        mock_executor.execute.side_effect = [
            StepResult(status="completed", output_data={"recovered": True}),
        ]

        result = error_handler.handle(
            step={"id": 1, "tool": "crm", "action": "test", "params": {}, "retry": {"max_attempts": 1, "base_delay": 0}},
            error=Exception("Test error"),
            context={"input": {}},
            step_executor=mock_executor,
        )
        assert result.status == "recovered"
        assert result.retries == 1

    def test_handle_dead_letter(self, db_manager, error_handler):
        """Test: si se exceden los reintentos, va a dead letter."""
        from src.workflow.step_executor import StepResult

        mock_executor = MagicMock()
        mock_executor.execute.return_value = StepResult(status="failed", error_message="Persistent error")

        result = error_handler.handle(
            step={"id": 1, "tool": "crm", "action": "test", "params": {}, "retry": {"max_attempts": 1, "base_delay": 0}},
            error=Exception("Test error"),
            context={"input": {}},
            step_executor=mock_executor,
        )
        assert result.status == "dead_letter"

    def test_handle_with_skip_fallback(self, db_manager, error_handler):
        """Test: fallback skip retorna resultado skipped."""
        from src.workflow.step_executor import StepResult

        mock_executor = MagicMock()
        mock_executor.execute.return_value = StepResult(status="failed", error_message="Error")

        result = error_handler.handle(
            step={
                "id": 1, "tool": "crm", "action": "test", "params": {},
                "retry": {"max_attempts": 1, "base_delay": 0},
                "fallback": "skip",
            },
            error=Exception("Test error"),
            context={"input": {}},
            step_executor=mock_executor,
        )
        assert result.status == "recovered"
        assert result.output_data.get("status") == "skipped"

    def test_has_fallback_string(self, error_handler):
        """Test: _has_fallback con string action name."""
        step = {"fallback": "skip"}
        assert error_handler._has_fallback(step) is True

    def test_has_fallback_dict(self, error_handler):
        """Test: _has_fallback con dict config."""
        step = {"fallback": {"action": "skip"}}
        assert error_handler._has_fallback(step) is True

    def test_has_fallback_none(self, error_handler):
        """Test: _has_fallback sin fallback."""
        step = {}
        assert error_handler._has_fallback(step) is False

    def test_register_fallback(self, error_handler):
        """Test: registrar una acción de fallback."""
        fallback_fn = MagicMock(return_value={"fallback": True})
        error_handler.register_fallback("custom_action", fallback_fn)
        assert "custom_action" in error_handler._fallback_actions
