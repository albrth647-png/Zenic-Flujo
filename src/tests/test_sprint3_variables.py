"""
Tests para Sprint 3 del Roadmap Competitivo.
Cubre: WorkflowVariables — set, get, delete, exists, transform functions,
math functions, aggregators, y StepExecutor system action integration.
"""

import pytest

from src.workflow.step_executor import StepExecutor
from src.workflow.workflow_variables import WorkflowVariables

# ===================================================================
# WorkflowVariables — Variable Operations
# ===================================================================


class TestVariableOperations:
    """Tests para set, get, delete, exists."""

    def test_set_simple_value(self):
        """set_variable con valor string."""
        ctx = {}
        result = WorkflowVariables.set_variable("name", "Juan", ctx)
        assert result["status"] == "set"
        assert result["value"] == "Juan"
        assert ctx["name"] == "Juan"

    def test_set_numeric_value(self):
        """set_variable con valor numérico."""
        ctx = {}
        WorkflowVariables.set_variable("total", 42, ctx)
        assert ctx["total"] == 42

    def test_set_list_value(self):
        """set_variable con lista."""
        ctx = {}
        WorkflowVariables.set_variable("items", [1, 2, 3], ctx)
        assert ctx["items"] == [1, 2, 3]

    def test_set_dict_value(self):
        """set_variable con dict."""
        ctx = {}
        WorkflowVariables.set_variable("user", {"name": "Ana", "age": 30}, ctx)
        assert ctx["user"]["name"] == "Ana"
        assert ctx["user"]["age"] == 30

    def test_set_overwrites_existing(self):
        """set_variable sobreescribe valor existente."""
        ctx = {"name": "old"}
        WorkflowVariables.set_variable("name", "new", ctx)
        assert ctx["name"] == "new"

    def test_get_simple_value(self):
        """get_variable existente."""
        ctx = {"name": "Juan"}
        result = WorkflowVariables.get_variable("name", ctx)
        assert result["found"] is True
        assert result["value"] == "Juan"

    def test_get_nonexistent_value(self):
        """get_variable no existente retorna default."""
        ctx = {"name": "Juan"}
        result = WorkflowVariables.get_variable("age", ctx)
        assert result["found"] is False
        assert result["value"] is None

    def test_get_with_custom_default(self):
        """get_variable con default personalizado."""
        ctx = {}
        result = WorkflowVariables.get_variable("missing", ctx, default=0)
        assert result["found"] is False
        assert result["value"] == 0

    def test_get_dotted_path(self):
        """get_variable con notación de puntos."""
        ctx = {"user": {"address": {"city": "Lima"}}}
        result = WorkflowVariables.get_variable("user.address.city", ctx)
        assert result["found"] is True
        assert result["value"] == "Lima"

    def test_delete_existing(self):
        """delete_variable elimina existente."""
        ctx = {"name": "Juan", "other": "keep"}
        result = WorkflowVariables.delete_variable("name", ctx)
        assert result["status"] == "deleted"
        assert result["existed"] is True
        assert "name" not in ctx
        assert "other" in ctx

    def test_delete_nonexistent(self):
        """delete_variable no existente no falla."""
        ctx = {"name": "Juan"}
        result = WorkflowVariables.delete_variable("age", ctx)
        assert result["status"] == "deleted"
        assert result["existed"] is False

    def test_exists_yes(self):
        """exists_variable con variable existente."""
        ctx = {"name": "Juan"}
        result = WorkflowVariables.exists_variable("name", ctx)
        assert result["exists"] is True

    def test_exists_no(self):
        """exists_variable con variable no existente."""
        ctx = {"name": "Juan"}
        result = WorkflowVariables.exists_variable("age", ctx)
        assert result["exists"] is False


# ===================================================================
# WorkflowVariables — Transform Functions
# ===================================================================


class TestTransformFunctions:
    """Tests para transform functions: upper, lower, trim, replace,
    split, join, substring, length."""

    def test_upper(self):
        r = WorkflowVariables.transform_upper("hola")
        assert r["result"] == "HOLA"

    def test_upper_non_string(self):
        r = WorkflowVariables.transform_upper(42)
        assert r["result"] == "42"

    def test_lower(self):
        r = WorkflowVariables.transform_lower("HOLA")
        assert r["result"] == "hola"

    def test_trim(self):
        r = WorkflowVariables.transform_trim("  hola mundo  ")
        assert r["result"] == "hola mundo"

    def test_replace_basic(self):
        r = WorkflowVariables.transform_replace("hello world", "world", "there")
        assert r["result"] == "hello there"

    def test_replace_with_count(self):
        r = WorkflowVariables.transform_replace("a b c d", " ", ",", count=2)
        assert r["result"] == "a,b,c d"

    def test_replace_no_match(self):
        r = WorkflowVariables.transform_replace("hello", "x", "y")
        assert r["result"] == "hello"

    def test_split_default(self):
        r = WorkflowVariables.transform_split("a,b,c")
        assert r["result"] == ["a", "b", "c"]

    def test_split_custom_delimiter(self):
        r = WorkflowVariables.transform_split("a|b|c", delimiter="|")
        assert r["result"] == ["a", "b", "c"]

    def test_split_no_delimiter(self):
        r = WorkflowVariables.transform_split("abc")
        assert r["result"] == ["abc"]

    def test_join_default(self):
        r = WorkflowVariables.transform_join(["a", "b", "c"])
        assert r["result"] == "a,b,c"

    def test_join_custom_delimiter(self):
        r = WorkflowVariables.transform_join(["a", "b", "c"], delimiter=" | ")
        assert r["result"] == "a | b | c"

    def test_join_numbers(self):
        r = WorkflowVariables.transform_join([1, 2, 3], delimiter="-")
        assert r["result"] == "1-2-3"

    def test_substring_basic(self):
        r = WorkflowVariables.transform_substring("hello world", 0, 5)
        assert r["result"] == "hello"

    def test_substring_no_end(self):
        r = WorkflowVariables.transform_substring("hello world", 6)
        assert r["result"] == "world"

    def test_substring_negative_start(self):
        r = WorkflowVariables.transform_substring("hello", -3)
        assert r["result"] == "llo"

    def test_length_string(self):
        r = WorkflowVariables.transform_length("hello")
        assert r["result"] == 5

    def test_length_list(self):
        r = WorkflowVariables.transform_length([1, 2, 3])
        assert r["result"] == 3

    def test_length_dict(self):
        r = WorkflowVariables.transform_length({"a": 1, "b": 2})
        assert r["result"] == 2


# ===================================================================
# WorkflowVariables — Math Functions
# ===================================================================


class TestMathFunctions:
    """Tests para math: add, subtract, multiply, divide, floor, ceil,
    round, abs, min, max, power, sqrt, modulo."""

    def test_add(self):
        r = WorkflowVariables.math_add(5, 3)
        assert r["result"] == 8.0

    def test_add_float(self):
        r = WorkflowVariables.math_add(1.5, 2.5)
        assert r["result"] == 4.0

    def test_subtract(self):
        r = WorkflowVariables.math_subtract(10, 3)
        assert r["result"] == 7.0

    def test_multiply(self):
        r = WorkflowVariables.math_multiply(4, 5)
        assert r["result"] == 20.0

    def test_divide(self):
        r = WorkflowVariables.math_divide(10, 3)
        assert abs(r["result"] - 3.33333) < 0.001

    def test_divide_by_zero(self):
        r = WorkflowVariables.math_divide(10, 0)
        assert r["result"] is None
        assert r["error"] == "division_by_zero"

    def test_floor(self):
        r = WorkflowVariables.math_floor(3.7)
        assert r["result"] == 3

    def test_ceil(self):
        r = WorkflowVariables.math_ceil(3.2)
        assert r["result"] == 4

    def test_round_basic(self):
        r = WorkflowVariables.math_round(3.14159, 2)
        assert r["result"] == 3.14

    def test_round_no_decimals(self):
        r = WorkflowVariables.math_round(3.7)
        assert r["result"] == 4.0

    def test_abs_positive(self):
        r = WorkflowVariables.math_abs(5)
        assert r["result"] == 5.0

    def test_abs_negative(self):
        r = WorkflowVariables.math_abs(-5)
        assert r["result"] == 5.0

    def test_min(self):
        r = WorkflowVariables.math_min(3, 7)
        assert r["result"] == 3.0

    def test_max(self):
        r = WorkflowVariables.math_max(3, 7)
        assert r["result"] == 7.0

    def test_power(self):
        r = WorkflowVariables.math_power(2, 3)
        assert r["result"] == 8.0

    def test_sqrt(self):
        r = WorkflowVariables.math_sqrt(9)
        assert r["result"] == 3.0

    def test_sqrt_negative(self):
        r = WorkflowVariables.math_sqrt(-1)
        assert r["result"] is None
        assert r["error"] == "negative_sqrt"

    def test_modulo(self):
        r = WorkflowVariables.math_modulo(10, 3)
        assert r["result"] == 1.0


# ===================================================================
# WorkflowVariables — Aggregators
# ===================================================================


class TestAggregators:
    """Tests para aggregate: sum, avg, count, min, max."""

    def test_aggregate_sum(self):
        r = WorkflowVariables.aggregate_sum([1, 2, 3, 4, 5])
        assert r["result"] == 15.0
        assert r["count"] == 5

    def test_aggregate_sum_empty(self):
        r = WorkflowVariables.aggregate_sum([])
        assert r["result"] == 0.0

    def test_aggregate_avg(self):
        r = WorkflowVariables.aggregate_avg([1, 2, 3, 4, 5])
        assert r["result"] == 3.0

    def test_aggregate_avg_empty(self):
        r = WorkflowVariables.aggregate_avg([])
        assert r["error"] == "empty_list"

    def test_aggregate_count(self):
        r = WorkflowVariables.aggregate_count([1, 2, 3, 4, 5])
        assert r["result"] == 5

    def test_aggregate_count_empty(self):
        r = WorkflowVariables.aggregate_count([])
        assert r["result"] == 0

    def test_aggregate_min(self):
        r = WorkflowVariables.aggregate_min([5, 2, 8, 1, 9])
        assert r["result"] == 1.0

    def test_aggregate_min_empty(self):
        r = WorkflowVariables.aggregate_min([])
        assert r["error"] == "empty_list"

    def test_aggregate_max(self):
        r = WorkflowVariables.aggregate_max([5, 2, 8, 1, 9])
        assert r["result"] == 9.0

    def test_aggregate_max_empty(self):
        r = WorkflowVariables.aggregate_max([])
        assert r["error"] == "empty_list"


# ===================================================================
# WorkflowVariables — Dispatch (execute)
# ===================================================================


class TestDispatch:
    """Tests para el dispatcher WorkflowVariables.execute()."""

    def test_dispatch_set(self):
        ctx = {}
        r = WorkflowVariables.execute({"operation": "set", "name": "x", "value": 100}, ctx)
        assert r["status"] == "set"
        assert ctx["x"] == 100

    def test_dispatch_get(self):
        ctx = {"x": 42}
        r = WorkflowVariables.execute({"operation": "get", "name": "x"}, ctx)
        assert r["found"] is True
        assert r["value"] == 42

    def test_dispatch_delete(self):
        ctx = {"x": 42}
        WorkflowVariables.execute({"operation": "delete", "name": "x"}, ctx)
        assert "x" not in ctx

    def test_dispatch_exists(self):
        ctx = {"x": 42}
        r = WorkflowVariables.execute({"operation": "exists", "name": "x"}, ctx)
        assert r["exists"] is True
        r2 = WorkflowVariables.execute({"operation": "exists", "name": "y"}, ctx)
        assert r2["exists"] is False

    def test_dispatch_transform_upper(self):
        r = WorkflowVariables.execute({"operation": "transform", "transform": "upper", "value": "hello"}, {})
        assert r["result"] == "HELLO"

    def test_dispatch_transform_split(self):
        r = WorkflowVariables.execute(
            {"operation": "transform", "transform": "split", "value": "a,b,c", "delimiter": ","}, {}
        )
        assert r["result"] == ["a", "b", "c"]

    def test_dispatch_math_add(self):
        r = WorkflowVariables.execute({"operation": "math", "math": "add", "a": 10, "b": 20}, {})
        assert r["result"] == 30.0

    def test_dispatch_math_sqrt(self):
        r = WorkflowVariables.execute({"operation": "math", "math": "sqrt", "a": 16}, {})
        assert r["result"] == 4.0

    def test_dispatch_aggregate_sum(self):
        r = WorkflowVariables.execute({"operation": "aggregate", "aggregate": "sum", "values": [1, 2, 3, 4, 5]}, {})
        assert r["result"] == 15.0

    def test_dispatch_aggregate_avg(self):
        r = WorkflowVariables.execute({"operation": "aggregate", "aggregate": "avg", "values": [10, 20, 30]}, {})
        assert r["result"] == 20.0

    def test_dispatch_unknown_operation(self):
        with pytest.raises(ValueError, match="Operación desconocida"):
            WorkflowVariables.execute({"operation": "invalid"}, {})

    def test_dispatch_unknown_transform(self):
        with pytest.raises(ValueError, match="Transform desconocido"):
            WorkflowVariables.execute({"operation": "transform", "transform": "invalid", "value": "test"}, {})

    def test_dispatch_unknown_math(self):
        with pytest.raises(ValueError, match="Math desconocido"):
            WorkflowVariables.execute({"operation": "math", "math": "invalid", "a": 1}, {})

    def test_dispatch_unknown_aggregate(self):
        with pytest.raises(ValueError, match="Aggregate desconocido"):
            WorkflowVariables.execute({"operation": "aggregate", "aggregate": "invalid", "values": []}, {})


# ===================================================================
# StepExecutor — System Action Integration
# ===================================================================


class TestStepExecutorIntegration:
    """Tests para la integración con StepExecutor system action."""

    def test_set_variable_via_executor(self):
        """Variable set via StepExecutor system action."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {
                "operation": "set",
                "name": "total",
                "value": 42,
            },
        }
        context = {}
        result = executor.execute(step, context)
        assert result.status == "completed"
        assert result.output_data.get("name") == "total"
        assert context.get("total") == 42

    def test_get_variable_via_executor(self):
        """Variable get via StepExecutor."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {
                "operation": "get",
                "name": "name",
            },
        }
        context = {"name": "Juan"}
        result = executor.execute(step, context)
        assert result.status == "completed"
        assert result.output_data.get("value") == "Juan"

    def test_transform_upper_via_executor(self):
        """Transform upper via StepExecutor."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {
                "operation": "transform",
                "transform": "upper",
                "value": "hola mundo",
            },
        }
        result = executor.execute(step, {})
        assert result.status == "completed"
        assert result.output_data.get("result") == "HOLA MUNDO"

    def test_math_add_via_executor(self):
        """Math add via StepExecutor."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {
                "operation": "math",
                "math": "add",
                "a": 15,
                "b": 7,
            },
        }
        result = executor.execute(step, {})
        assert result.status == "completed"
        assert result.output_data.get("result") == 22.0

    def test_aggregate_sum_via_executor(self):
        """Aggregate sum via StepExecutor."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {
                "operation": "aggregate",
                "aggregate": "sum",
                "values": [10, 20, 30, 40],
            },
        }
        result = executor.execute(step, {})
        assert result.status == "completed"
        assert result.output_data.get("result") == 100.0

    def test_set_and_get_chain(self):
        """Set then get una variable en ejecución secuencial."""
        executor = StepExecutor()
        context = {}

        # Set name
        step1 = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {"operation": "set", "name": "user", "value": "Ana"},
        }
        r1 = executor.execute(step1, context)
        assert r1.status == "completed"
        assert context["user"] == "Ana"

        # Get name should see it
        step2 = {"id": 2, "tool": "system", "action": "variable", "params": {"operation": "get", "name": "user"}}
        r2 = executor.execute(step2, context)
        assert r2.status == "completed"
        assert r2.output_data.get("value") == "Ana"

    def test_transform_set_pipeline(self):
        """Pipeline: set → transform → get."""
        executor = StepExecutor()
        context = {}

        # Set raw name
        executor.execute(
            {
                "id": 1,
                "tool": "system",
                "action": "variable",
                "params": {"operation": "set", "name": "raw", "value": "  Juan Pérez  "},
            },
            context,
        )
        assert context["raw"] == "  Juan Pérez  "

        # Transform upper
        r = executor.execute(
            {
                "id": 2,
                "tool": "system",
                "action": "variable",
                "params": {"operation": "transform", "transform": "upper", "value": "  Juan Pérez  "},
            },
            context,
        )
        assert r.output_data.get("result") == "  JUAN PÉREZ  "

    def test_variable_error_propagates(self):
        """Error en operation incorrecta falla el step."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "system",
            "action": "variable",
            "params": {"operation": "invalid"},
        }
        result = executor.execute(step, {})
        assert result.status == "failed"
        assert "Operación desconocida" in (result.error_message or "")
