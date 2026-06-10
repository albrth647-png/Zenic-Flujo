"""
DDE v3 — Tests del MoneyExtractor
"""


class TestMoneyExtractor:
    """Tests para MoneyExtractor."""

    def test_simple_dollar(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("$500")
        assert len(entities) == 1
        assert entities[0].type == "money"
        assert entities[0].value["value"] == 500.0
        assert entities[0].value["op"] == "=="

    def test_pesos(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("500 pesos")
        assert len(entities) == 1
        assert entities[0].value["value"] == 500.0

    def test_more_than(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("más de $500")
        assert len(entities) >= 1
        money = [e for e in entities if e.type == "money"]
        assert len(money) >= 1
        assert money[0].value["op"] == ">="

    def test_less_than(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("menos de 1000 pesos")
        assert len(entities) >= 1
        money = [e for e in entities if e.type == "money"]
        assert money[0].value["op"] in ("<=",)
        assert money[0].value["value"] == 1000.0

    def test_greater_than_symbol(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("> $300")
        assert len(entities) >= 1
        money = [e for e in entities if e.type == "money"]
        assert money[0].value["op"] == ">"

    def test_usd_prefix(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("USD 500")
        assert len(entities) == 1
        assert entities[0].value["value"] == 500.0

    def test_determinista(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        r1 = ext.extract("$500")
        r2 = ext.extract("$500")
        assert len(r1) == len(r2)
        assert r1[0].value == r2[0].value

    def test_no_money(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("hola mundo")
        assert len(entities) == 0

    def test_at_least(self):
        from src.nlu.entities.money import MoneyExtractor
        ext = MoneyExtractor()
        entities = ext.extract("al menos $1000")
        money = [e for e in entities if e.type == "money"]
        assert len(money) >= 1
        assert money[0].value["op"] == ">="
