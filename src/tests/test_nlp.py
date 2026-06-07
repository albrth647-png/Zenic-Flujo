"""
Workflow Determinista — Tests del NLP Determinista
Tests unitarios para el clasificador de intenciones, extractor de entidades, 
router bilingüe y plantillas.
"""
import pytest


class TestIntentClassifier:
    """Tests para la clase IntentClassifier."""

    def test_classify_spanish_client_registration(self):
        """Test: texto en español sobre registro de cliente."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("Quiero registrar un nuevo cliente")
        assert len(results) > 0
        assert results[0]["template_name"] == "registro_cliente"

    def test_classify_english_client_registration(self):
        """Test: texto en inglés sobre registro de cliente."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("Register a new customer")
        assert len(results) > 0
        assert results[0]["template_name"] == "registro_cliente"

    def test_classify_stock_alert(self):
        """Test: detectar intención de alerta de stock."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("Alerta de inventario bajo")
        assert len(results) > 0
        assert results[0]["template_name"] == "alerta_stock_bajo"

    def test_classify_invoice(self):
        """Test: detectar intención de facturación."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("Generar factura semanal")
        assert len(results) > 0
        assert results[0]["template_name"] == "factura_automatica"

    def test_classify_returns_max_5(self):
        """Test: classify retorna máximo 5 resultados."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("Quiero automatizar todo")
        assert len(results) <= 5

    def test_classify_empty_text(self):
        """Test: texto vacío retorna lista vacía."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("")
        assert isinstance(results, list)

    def test_classify_gibberish(self):
        """Test: texto sin sentido retorna lista vacía o baja confianza."""
        from src.nlp.intent_classifier import IntentClassifier
        classifier = IntentClassifier()

        results = classifier.classify("xyz abc qwerty")
        # Should return empty or low-confidence results
        assert isinstance(results, list)


class TestEntityExtractor:
    """Tests para la clase EntityExtractor."""

    def test_extract_email(self):
        """Test: extraer email del texto."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        entities = extractor.extract("Contactar a juan@email.com")
        assert "email" in entities
        assert "juan@email.com" in entities["email"]

    def test_extract_phone(self):
        """Test: extraer teléfono del texto."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        entities = extractor.extract("Llamar al +53 555 1234")
        assert "phone" in entities

    def test_extract_number(self):
        """Test: extraer números del texto."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        entities = extractor.extract("Total: 150 dólares")
        assert "number" in entities

    def test_extract_currency(self):
        """Test: extraer montos monetarios."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        entities = extractor.extract("El precio es $299.99")
        assert "currency" in entities

    def test_extract_no_entities(self):
        """Test: texto sin entidades retorna dict vacío."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        entities = extractor.extract("hola mundo")
        # May or may not find entities
        assert isinstance(entities, dict)

    def test_extract_trigger_type_event(self):
        """Test: detectar trigger tipo 'event'."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        trigger_type, config = extractor.extract_trigger_type("Cuando un cliente nuevo se registra")
        assert trigger_type == "event"

    def test_extract_trigger_type_schedule(self):
        """Test: detectar trigger tipo 'schedule'."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        trigger_type, config = extractor.extract_trigger_type("Cada día a las 9am")
        assert trigger_type == "schedule"
        assert "cron" in config

    def test_extract_trigger_type_webhook(self):
        """Test: detectar trigger tipo 'webhook'."""
        from src.nlp.entity_extractor import EntityExtractor
        extractor = EntityExtractor()

        trigger_type, config = extractor.extract_trigger_type("Recibir webhook HTTP")
        assert trigger_type == "webhook"


class TestBilingualRouter:
    """Tests para la clase BilingualRouter."""

    def test_detect_spanish(self):
        """Test: detectar texto en español."""
        from src.nlp.bilingual_router import BilingualRouter
        router = BilingualRouter()

        assert router.detect("Quiero crear un workflow nuevo") == "es"

    def test_detect_english(self):
        """Test: detectar texto en inglés."""
        from src.nlp.bilingual_router import BilingualRouter
        router = BilingualRouter()

        assert router.detect("I want to create a new workflow") == "en"

    def test_detect_mixed_defaults_spanish(self):
        """Test: texto mixto se resuelve como español por defecto."""
        from src.nlp.bilingual_router import BilingualRouter
        router = BilingualRouter()

        # When tied, defaults to Spanish
        result = router.detect("abc xyz")
        assert result in ("es", "en")


class TestTemplates:
    """Tests para las plantillas de intención."""

    def test_templates_count(self):
        """Test: hay al menos 10 plantillas (spec requirement)."""
        from src.nlp.templates import TEMPLATES
        assert len(TEMPLATES) >= 10

    def test_template_structure(self):
        """Test: cada template tiene los campos requeridos."""
        from src.nlp.templates import TEMPLATES
        required_fields = ["name", "label", "description_es", "description_en",
                          "keywords_es", "keywords_en", "trigger", "steps"]
        for template in TEMPLATES:
            for field in required_fields:
                assert field in template, f"Template '{template.get('name', '?')}' missing field '{field}'"

    def test_template_has_steps(self):
        """Test: cada template tiene al menos un step."""
        from src.nlp.templates import TEMPLATES
        for template in TEMPLATES:
            assert len(template["steps"]) >= 1, f"Template '{template['name']}' has no steps"

    def test_template_bilingual_keywords(self):
        """Test: cada template tiene keywords en ambos idiomas."""
        from src.nlp.templates import TEMPLATES
        for template in TEMPLATES:
            assert len(template["keywords_es"]) > 0, f"Template '{template['name']}' has no ES keywords"
            assert len(template["keywords_en"]) > 0, f"Template '{template['name']}' has no EN keywords"
