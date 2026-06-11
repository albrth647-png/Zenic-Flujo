"""
DDE v3 — Tests del EntityExtractor (Etapa 4)
"""


class TestEntityExtractor:
    """Tests para EntityExtractor v2."""

    def test_extract_email(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("juan@email.com")
        assert len(entities) == 1
        assert entities[0].type == "email"
        assert entities[0].value == "juan@email.com"

    def test_extract_phone(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("+535551234")
        assert any(e.type == "phone" for e in entities)

    def test_extract_number(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("Total: 150")
        assert any(e.type == "number" for e in entities)
        num = next(e for e in entities if e.type == "number")
        assert num.value == 150

    def test_extract_currency(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("$299.99")
        assert any(e.type == "money" for e in entities)

    def test_extract_date(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("2024-01-15")
        assert any(e.type == "date" for e in entities)

    def test_extract_no_entities(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("hola mundo")
        assert len(entities) == 0

    def test_entities_are_entity_type(self):
        from src.nlu.entities.base import Entity
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("juan@email.com")
        assert all(isinstance(e, Entity) for e in entities)

    def test_entities_have_span(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        entities = extractor.extract_all("juan@email.com")
        assert entities[0].span == (0, 14)

    def test_trigger_type_event(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        ttype, _config = extractor.extract_trigger_type("Cuando un nuevo cliente")
        assert ttype == "event"

    def test_trigger_type_schedule(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        ttype, _config = extractor.extract_trigger_type("Cada dia a las 9")
        assert ttype == "schedule"

    def test_trigger_type_webhook(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        ttype, _config = extractor.extract_trigger_type("Webhook HTTP")
        assert ttype == "webhook"

    def test_trigger_type_manual_default(self):
        from src.nlu.entities.extractor import EntityExtractor

        extractor = EntityExtractor()
        ttype, _config = extractor.extract_trigger_type("Generar backup")
        assert ttype == "manual"
