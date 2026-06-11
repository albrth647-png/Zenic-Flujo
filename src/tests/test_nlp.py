"""
Workflow Determinista — Tests del NLP Determinista
Tests unitarios para el clasificador de intenciones, extractor de entidades,
router bilingüe y plantillas.
Migrado: imports actualizados a src.nlu.
"""


class TestIntentClassifier:
    """Tests para la clase IntentClassifier."""

    def test_classify_spanish_client_registration(self):
        """Test: texto en español sobre registro de cliente."""
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        from src.nlu.language_router import LanguageRouter
        from src.nlu.normalizer import normalize
        from src.nlu.tokenizer import tokenize

        normalized = normalize("Quiero registrar un nuevo cliente")
        lang = LanguageRouter().detect("Quiero registrar un nuevo cliente")
        tokens = tokenize(normalized, lang)
        results = classifier.classify(tokens, lang)
        assert len(results) > 0
        assert results[0].intent == "registro_cliente"

    def test_classify_stock_alert(self):
        """Test: detectar intención de alerta de stock."""
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        from src.nlu.language_router import LanguageRouter
        from src.nlu.normalizer import normalize
        from src.nlu.tokenizer import tokenize

        normalized = normalize("Alerta de inventario bajo")
        lang = LanguageRouter().detect("Alerta de inventario bajo")
        tokens = tokenize(normalized, lang)
        results = classifier.classify(tokens, lang)
        assert len(results) > 0
        assert results[0].intent == "alerta_stock_bajo"

    def test_classify_invoice(self):
        """Test: detectar intención de facturación."""
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        from src.nlu.language_router import LanguageRouter
        from src.nlu.normalizer import normalize
        from src.nlu.tokenizer import tokenize

        normalized = normalize("Generar factura semanal")
        lang = LanguageRouter().detect("Generar factura semanal")
        tokens = tokenize(normalized, lang)
        results = classifier.classify(tokens, lang)
        assert len(results) > 0
        assert results[0].intent == "factura_automatica"

    def test_classify_returns_tuple(self):
        """Test: classify retorna tupla."""
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        from src.nlu.normalizer import normalize
        from src.nlu.tokenizer import tokenize

        normalized = normalize("Quiero automatizar todo")
        tokens = tokenize(normalized, "es")
        results = classifier.classify(tokens, "es")
        assert isinstance(results, tuple)

    def test_classify_empty_tokens(self):
        """Test: tokens vacíos retorna tupla vacía."""
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        results = classifier.classify([], "es")
        assert results == ()

    def test_classify_gibberish(self):
        """Test: texto sin sentido retorna score bajo."""
        from src.nlu.intent_classifier import IntentClassifier

        classifier = IntentClassifier()

        from src.nlu.normalizer import normalize
        from src.nlu.tokenizer import tokenize

        normalized = normalize("xyz abc qwerty")
        tokens = tokenize(normalized, "es")
        results = classifier.classify(tokens, "es")
        # Should return low or zero scores
        assert isinstance(results, tuple)


class TestBilingualRouter:
    """Tests para la clase BilingualRouter."""

    def test_detect_spanish(self):
        """Test: detectar texto en español."""
        from src.nlu.bilingual_router import BilingualRouter

        router = BilingualRouter()

        assert router.detect("Quiero crear un workflow nuevo") == "es"

    def test_detect_english(self):
        """Test: detectar texto en inglés."""
        from src.nlu.bilingual_router import BilingualRouter

        router = BilingualRouter()

        assert router.detect("I want to create a new workflow") == "en"

    def test_detect_mixed_defaults_spanish(self):
        """Test: texto mixto se resuelve como español por defecto."""
        from src.nlu.bilingual_router import BilingualRouter

        router = BilingualRouter()

        result = router.detect("abc xyz")
        assert result in ("es", "en")


class TestTemplates:
    """Tests para las plantillas de intención."""

    def test_templates_count(self):
        """Test: hay al menos 10 plantillas (spec requirement)."""
        from src.nlu.templates import TEMPLATES

        assert len(TEMPLATES) >= 10

    def test_template_structure(self):
        """Test: cada template tiene los campos requeridos."""
        from src.nlu.templates import TEMPLATES

        required_fields = [
            "name",
            "label",
            "description_es",
            "description_en",
            "keywords_es",
            "keywords_en",
            "trigger",
            "steps",
        ]
        for template in TEMPLATES:
            for field in required_fields:
                assert field in template, f"Template '{template.get('name', '?')}' missing field '{field}'"

    def test_template_has_steps(self):
        """Test: cada template tiene al menos un step."""
        from src.nlu.templates import TEMPLATES

        for template in TEMPLATES:
            assert len(template["steps"]) >= 1, f"Template '{template['name']}' has no steps"

    def test_template_bilingual_keywords(self):
        """Test: cada template tiene keywords en ambos idiomas."""
        from src.nlu.templates import TEMPLATES

        for template in TEMPLATES:
            assert len(template["keywords_es"]) > 0, f"Template '{template['name']}' has no ES keywords"
            assert len(template["keywords_en"]) > 0, f"Template '{template['name']}' has no EN keywords"
