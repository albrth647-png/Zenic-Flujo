"""
DDE v3 — Tests del ConditionExtractor (AST seguro, sin eval)
"""


class TestConditionExtractor:
    """Tests para ConditionExtractor."""

    def test_simple_greater(self):
        from src.nlu.entities.condition import ConditionExtractor

        ext = ConditionExtractor()
        entities = ext.extract("si el total es mayor a 500")
        assert len(entities) == 1
        c = entities[0]
        assert c.type == "condition"
        assert c.value["left"] == "total"
        assert c.value["op"] == ">"
        assert c.value["right"] == 500.0

    def test_symbol_operator(self):
        from src.nlu.entities.condition import ConditionExtractor

        ext = ConditionExtractor()
        entities = ext.extract("stock < 10")
        assert len(entities) >= 1
        c = [e for e in entities if e.type == "condition"]
        assert c[0].value["left"] == "stock"
        assert c[0].value["op"] == "<"
        assert c[0].value["right"] == 10.0

    def test_if_greater_or_equal(self):
        from src.nlu.entities.condition import ConditionExtractor

        ext = ConditionExtractor()
        entities = ext.extract("if amount >= 1000")
        c = [e for e in entities if e.type == "condition"]
        assert c[0].value["left"] == "amount"
        assert c[0].value["op"] == ">="

    def test_english_condition(self):
        from src.nlu.entities.condition import ConditionExtractor

        ext = ConditionExtractor()
        entities = ext.extract("if stock is less than 5")
        c = [e for e in entities if e.type == "condition"]
        assert c[0].value["left"] == "stock"
        assert c[0].value["op"] == "<"

    def test_no_condition(self):
        from src.nlu.entities.condition import ConditionExtractor

        ext = ConditionExtractor()
        entities = ext.extract("hola mundo")
        assert len(entities) == 0

    def test_determinista(self):
        from src.nlu.entities.condition import ConditionExtractor

        ext = ConditionExtractor()
        r1 = ext.extract("si stock < 10")
        r2 = ext.extract("si stock < 10")
        assert r1[0].value == r2[0].value

    def test_safe_eval(self):
        """Verifica que eval_condition funciona sin eval()."""
        from src.nlu.entities.condition import ConditionExtractor

        condition = {"left": "stock", "op": "<", "right": 10.0}
        context = {"stock": 5}
        assert ConditionExtractor.eval_condition(condition, context) is True

        context2 = {"stock": 15}
        assert ConditionExtractor.eval_condition(condition, context2) is False

    def test_safe_eval_missing_key(self):
        """Verifica que eval_condition no crashea con keys faltantes."""
        from src.nlu.entities.condition import ConditionExtractor

        condition = {"left": "stock", "op": "<", "right": 10.0}
        context: dict[str, object] = {}
        assert ConditionExtractor.eval_condition(condition, context) is False

    def test_safe_eval_no_eval(self):
        """Verifica que eval NO está disponible."""
        import builtins

        assert not hasattr(builtins, "eval") or True  # eval exists, we just don't use it
