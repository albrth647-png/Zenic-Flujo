"""
DDE v3 — Tests del DurationExtractor (cron normalization)
"""


class TestDurationExtractor:
    """Tests para DurationExtractor."""

    def test_daily(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("cada día")
        assert len(entities) == 1
        assert entities[0].type == "cron"
        assert entities[0].value == "0 0 * * *"

    def test_diario(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("diario")
        assert len(entities) == 1
        assert entities[0].value == "0 0 * * *"

    def test_weekly(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("semanal")
        assert len(entities) == 1
        assert entities[0].value == "0 0 * * 0"

    def test_every_15_minutes(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("cada 15 minutos")
        assert len(entities) == 1
        assert entities[0].value == "*/15 * * * *"

    def test_every_2_hours(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("every 2 hours")
        assert len(entities) == 1
        assert entities[0].value == "0 */2 * * *"

    def test_at_9am(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("a las 9")
        assert len(entities) >= 1
        cron = [e for e in entities if e.type == "cron"]
        assert len(cron) >= 1
        assert cron[0].value == "0 9 * * *"

    def test_at_9pm(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("a las 9pm")
        cron = [e for e in entities if e.type == "cron"]
        assert cron[0].value == "0 21 * * *"

    def test_cada_lunes(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("cada lunes")
        cron = [e for e in entities if e.type == "cron"]
        assert len(cron) >= 1
        assert "1" in cron[0].value  # lunes = day 1

    def test_no_duration(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        entities = ext.extract("hola mundo")
        assert len(entities) == 0

    def test_determinista(self):
        from src.nlu.entities.duration import DurationExtractor
        ext = DurationExtractor()
        r1 = ext.extract("cada día")
        r2 = ext.extract("cada día")
        assert r1[0].value == r2[0].value
