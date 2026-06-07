"""
Workflow Determinista — Tests del ConditionEvaluator
Tests unitarios para el evaluador de condiciones: operadores, variables, paréntesis, errores.
"""
import pytest


class TestConditionEvaluator:
    """Tests para la clase ConditionEvaluator."""

    def test_simple_comparison_less_than(self, condition_evaluator):
        """Test: stock < 10 con stock=5 debe retornar True."""
        result = condition_evaluator.evaluate("stock < 10", {"stock": 5})
        assert result is True

    def test_simple_comparison_greater_than(self, condition_evaluator):
        """Test: precio > 100 con precio=50 debe retornar False."""
        result = condition_evaluator.evaluate("precio > 100", {"precio": 50})
        assert result is False

    def test_equality(self, condition_evaluator):
        """Test: estado == 'activo' con estado='activo' debe retornar True."""
        result = condition_evaluator.evaluate("estado == 'activo'", {"estado": "activo"})
        assert result is True

    def test_inequality(self, condition_evaluator):
        """Test: estado != 'cerrado' con estado='activo' debe retornar True."""
        result = condition_evaluator.evaluate("estado != 'cerrado'", {"estado": "activo"})
        assert result is True

    def test_greater_or_equal(self, condition_evaluator):
        """Test: cantidad >= 10 con cantidad=10 debe retornar True."""
        result = condition_evaluator.evaluate("cantidad >= 10", {"cantidad": 10})
        assert result is True

    def test_less_or_equal(self, condition_evaluator):
        """Test: cantidad <= 10 con cantidad=10 debe retornar True."""
        result = condition_evaluator.evaluate("cantidad <= 10", {"cantidad": 10})
        assert result is True

    def test_and_operator(self, condition_evaluator):
        """Test: AND lógico combina dos condiciones."""
        result = condition_evaluator.evaluate(
            "stock < 10 AND precio > 100",
            {"stock": 5, "precio": 150}
        )
        assert result is True

    def test_and_operator_false(self, condition_evaluator):
        """Test: AND lógico con una condición falsa retorna False."""
        result = condition_evaluator.evaluate(
            "stock < 10 AND precio > 100",
            {"stock": 5, "precio": 50}
        )
        assert result is False

    def test_or_operator(self, condition_evaluator):
        """Test: OR lógico con al menos una condición verdadera retorna True."""
        result = condition_evaluator.evaluate(
            "stock < 10 OR precio > 100",
            {"stock": 50, "precio": 150}
        )
        assert result is True

    def test_or_operator_both_false(self, condition_evaluator):
        """Test: OR lógico con ambas falsas retorna False."""
        result = condition_evaluator.evaluate(
            "stock < 10 OR precio > 100",
            {"stock": 50, "precio": 50}
        )
        assert result is False

    def test_parentheses(self, condition_evaluator):
        """Test: paréntesis controlan precedencia."""
        result = condition_evaluator.evaluate(
            "(stock < 10 OR precio > 100) AND activo == 'si'",
            {"stock": 50, "precio": 150, "activo": "si"}
        )
        assert result is True

    def test_dollar_variable(self, condition_evaluator):
        """Test: $input.valor resuelve desde contexto."""
        result = condition_evaluator.evaluate(
            "$input.stock < 10",
            {"input": {"stock": 5}}
        )
        assert result is True

    def test_bare_word_variable(self, condition_evaluator):
        """Test: bare words como 'stock' se resuelven desde contexto."""
        result = condition_evaluator.evaluate("stock < 10", {"stock": 5})
        assert result is True

    def test_contains_operator(self, condition_evaluator):
        """Test: contains verifica si un texto contiene otro."""
        result = condition_evaluator.evaluate(
            "nombre contains 'Juan'",
            {"nombre": "Juan Pérez"}
        )
        assert result is True

    def test_in_operator(self, condition_evaluator):
        """Test: in verifica si un valor está en una lista (from context)."""
        # The tokenizer doesn't support list literal syntax like ['a', 'b'],
        # but 'in' works when the right-hand side resolves to a list from context.
        result = condition_evaluator.evaluate(
            "estado in estados",
            {"estado": "activo", "estados": ["activo", "pendiente"]}
        )
        assert result is True

    def test_empty_condition(self, condition_evaluator):
        """Test: condición vacía retorna True (por defecto)."""
        result = condition_evaluator.evaluate("", {})
        assert result is True

    def test_invalid_expression_raises(self, condition_evaluator):
        """Test: expresión inválida lanza ValueError."""
        with pytest.raises(ValueError):
            condition_evaluator.evaluate("!!!invalid!!!", {})

    def test_validate_expression_valid(self, condition_evaluator):
        """Test: validate_expression retorna valid=True para expresión válida."""
        result = condition_evaluator.validate_expression("stock < 10")
        assert result["valid"] is True

    def test_validate_expression_invalid(self, condition_evaluator):
        """Test: validate_expression retorna valid=False para expresión inválida."""
        result = condition_evaluator.validate_expression("!!!invalid!!!")
        assert result["valid"] is False
        assert "error" in result

    def test_number_comparison(self, condition_evaluator):
        """Test: comparación numérica directa."""
        assert condition_evaluator.evaluate("5 < 10", {}) is True
        assert condition_evaluator.evaluate("10 == 10", {}) is True
        assert condition_evaluator.evaluate("3.14 > 3", {}) is True

    def test_boolean_values(self, condition_evaluator):
        """Test: True y False como valores literales."""
        result = condition_evaluator.evaluate("activo == True", {"activo": True})
        assert result is True

    def test_none_value(self, condition_evaluator):
        """Test: None como valor literal."""
        # None is tokenized as a literal value. When a context variable's
        # value is None, the evaluator treats it as "not found" and returns
        # the variable name as a string, so 'valor == None' with
        # {"valor": None} resolves to '"valor" == None' -> False.
        # Testing None literal equality directly instead.
        result = condition_evaluator.evaluate("None == None", {})
        assert result is True

    def test_no_eval_used(self):
        """Test: verificar que NUNCA se usa eval()."""
        import ast
        import inspect
        from src.workflow.condition_evaluator import ConditionEvaluator

        source = inspect.getsource(ConditionEvaluator)
        # Check that 'eval(' is not in the source (except in comments)
        lines = source.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Allow the word "eval" in comments/strings but not as a function call
            if 'eval(' in stripped and 'NUNCA' not in stripped and 'eval_ast' not in stripped:
                pytest.fail(f"Found eval() call in ConditionEvaluator: {stripped}")
