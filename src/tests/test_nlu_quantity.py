"""
DDE v3 — Tests del QuantityExtractor
"""


class TestQuantityExtractor:
    """Tests para QuantityExtractor."""

    def test_simple_number(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        entities = ext.extract("10 unidades")
        assert len(entities) == 1
        assert entities[0].type == "qty"
        assert entities[0].value["value"] == 10
        assert entities[0].value["op"] == "=="

    def test_more_than(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        entities = ext.extract("más de 50 unidades")
        qty = [e for e in entities if e.type == "qty"]
        assert len(qty) >= 1
        assert qty[0].value["op"] == ">="
        assert qty[0].value["value"] == 50

    def test_less_than(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        entities = ext.extract("menos de 5 items")
        qty = [e for e in entities if e.type == "qty"]
        assert qty[0].value["op"] == "<="

    def test_at_least(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        entities = ext.extract("al menos 100 unidades")
        qty = [e for e in entities if e.type == "qty"]
        assert qty[0].value["op"] == ">="

    def test_greater_than_symbol(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        entities = ext.extract("stock > 10")
        qty = [e for e in entities if e.type == "qty"]
        assert qty[0].value["op"] == ">"

    def test_no_qty(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        entities = ext.extract("hola mundo")
        assert len(entities) == 0

    def test_determinista(self):
        from src.nlu.entities.quantity import QuantityExtractor
        ext = QuantityExtractor()
        r1 = ext.extract("10 unidades")
        r2 = ext.extract("10 unidades")
        assert r1[0].value == r2[0].value
