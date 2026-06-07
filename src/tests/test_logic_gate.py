"""
Workflow Determinista — Tests del LogicGate Service
Tests unitarios para evaluación y persistencia de reglas lógicas.
"""
import pytest


class TestLogicGateService:
    """Tests del LogicGateService."""

    def test_init(self, db_manager):
        """Verifica inicialización correcta."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        assert service._evaluator is not None
        assert service._db is not None

    def test_evaluate_rule_simple(self, db_manager):
        """Verifica evaluación de regla simple."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        assert service.evaluate_rule("stock < 10", {"stock": 5}) is True
        assert service.evaluate_rule("stock < 10", {"stock": 15}) is False

    def test_evaluate_rule_with_and(self, db_manager):
        """Verifica evaluación con AND."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        result = service.evaluate_rule("stock < 10 AND precio > 100", {"stock": 5, "precio": 150})
        assert result is True
        result = service.evaluate_rule("stock < 10 AND precio > 100", {"stock": 5, "precio": 50})
        assert result is False

    def test_evaluate_rule_with_or(self, db_manager):
        """Verifica evaluación con OR."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        result = service.evaluate_rule("stock < 10 OR precio > 100", {"stock": 15, "precio": 150})
        assert result is True

    def test_evaluate_rule_equality(self, db_manager):
        """Verifica evaluación con operador ==."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        assert service.evaluate_rule("stage == new", {"stage": "new"}) is True
        assert service.evaluate_rule("stage == new", {"stage": "closed"}) is False

    def test_validate_expression_valid(self, db_manager):
        """Verifica validación de expresión válida."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        result = service.validate_expression("stock < 10")
        assert result["valid"] is True

    def test_validate_expression_invalid(self, db_manager):
        """Verifica validación de expresión inválida."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        result = service.validate_expression("")
        assert result["valid"] is False

    def test_save_rule(self, db_manager):
        """Verifica que save_rule() persiste una regla."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        result = service.save_rule("low_stock", "stock < 10", "Alerta de stock bajo")
        assert result["name"] == "low_stock"
        assert result["expression"] == "stock < 10"
        assert result["description"] == "Alerta de stock bajo"

    def test_save_rule_invalid_expression(self, db_manager):
        """Verifica que save_rule() rechaza expresiones inválidas."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        with pytest.raises(ValueError, match="inválida"):
            service.save_rule("bad_rule", "", "Regla mala")

    def test_get_rule(self, db_manager):
        """Verifica que get_rule() recupera una regla guardada."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        service.save_rule("test_rule", "stock > 0", "Stock positivo")
        rule = service.get_rule("test_rule")
        assert rule is not None
        assert rule["name"] == "test_rule"
        assert rule["expression"] == "stock > 0"

    def test_get_rule_nonexistent(self, db_manager):
        """Verifica que get_rule() retorna None para regla inexistente."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        rule = service.get_rule("nonexistent_rule")
        assert rule is None

    def test_list_rules(self, db_manager):
        """Verifica que list_rules() retorna todas las reglas guardadas."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        service.save_rule("rule_a", "stock < 5", "A")
        service.save_rule("rule_b", "price > 100", "B")
        rules = service.list_rules()
        assert len(rules) >= 2
        names = [r["name"] for r in rules]
        assert "rule_a" in names
        assert "rule_b" in names

    def test_list_rules_empty(self, db_manager):
        """Verifica que list_rules() retorna lista vacía sin reglas."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        rules = service.list_rules()
        assert rules == []

    def test_delete_rule(self, db_manager):
        """Verifica que delete_rule() elimina una regla."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        service.save_rule("to_delete", "stock == 0", "Sin stock")
        result = service.delete_rule("to_delete")
        assert result is True
        assert service.get_rule("to_delete") is None

    def test_evaluate_saved_rule(self, db_manager):
        """Verifica que evaluate_saved_rule() evalúa una regla guardada."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        service.save_rule("check_stock", "stock < 10", "Verificar stock")
        assert service.evaluate_saved_rule("check_stock", {"stock": 5}) is True
        assert service.evaluate_saved_rule("check_stock", {"stock": 15}) is False

    def test_evaluate_saved_rule_nonexistent(self, db_manager):
        """Verifica que evaluate_saved_rule() lanza error con regla inexistente."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        with pytest.raises(ValueError, match="no encontrada"):
            service.evaluate_saved_rule("nonexistent", {"stock": 5})

    def test_save_rule_overwrite(self, db_manager):
        """Verifica que save_rule() sobreescribe regla existente."""
        from src.tools.logic_gate.service import LogicGateService
        service = LogicGateService()
        service.save_rule("overwrite_test", "stock < 10", "Original")
        service.save_rule("overwrite_test", "stock < 5", "Modificada")
        rule = service.get_rule("overwrite_test")
        assert rule["expression"] == "stock < 5"
        assert rule["description"] == "Modificada"
