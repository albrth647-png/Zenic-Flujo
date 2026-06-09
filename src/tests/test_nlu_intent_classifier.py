"""
DDE v3 — Tests del IntentClassifier TF-IDF (Etapa 5)
"""
import pytest


class TestIntentClassifier:
    """Tests para IntentClassifier v2."""

    def test_classify_spanish_client_registration(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("Quiero registrar un nuevo cliente")
        tokens = tokenize(text, "es")
        results = classifier.classify(tokens, "es")

        assert len(results) > 0
        assert results[0].intent == "registro_cliente"
        assert results[0].score > 0

    def test_classify_english_client_registration(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("Register a new customer")
        tokens = tokenize(text, "en")
        results = classifier.classify(tokens, "en")

        assert len(results) > 0
        assert results[0].intent == "registro_cliente"

    def test_classify_stock_alert(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("Alerta de inventario bajo")
        tokens = tokenize(text, "es")
        results = classifier.classify(tokens, "es")

        assert len(results) > 0
        assert results[0].intent == "alerta_stock_bajo"

    def test_classify_invoice(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("Generar factura semanal")
        tokens = tokenize(text, "es")
        results = classifier.classify(tokens, "es")

        assert len(results) > 0
        assert results[0].intent == "factura_automatica"

    def test_classify_empty_text(self):
        from src.nlu.intent_classifier import IntentClassifier
        classifier = IntentClassifier()
        results = classifier.classify([], "es")
        assert len(results) == 0

    def test_classify_gibberish_returns_low_score(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("xyz abc qwerty")
        tokens = tokenize(text, "es")
        results = classifier.classify(tokens, "es")

        # Should return results with low score
        if results:
            assert all(r.score < 0.3 for r in results)

    def test_classify_text_helper(self):
        from src.nlu.intent_classifier import IntentClassifier
        classifier = IntentClassifier()
        results = classifier.classify_text("Quiero registrar un nuevo cliente")

        assert len(results) > 0
        assert results[0].intent == "registro_cliente"

    def test_classify_sorted_by_score(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("Registrar cliente nuevo en CRM")
        tokens = tokenize(text, "es")
        results = classifier.classify(tokens, "es")

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_classify_tiene_evidencia(self):
        from src.nlu.intent_classifier import IntentClassifier
        from src.nlu.tokenizer import tokenize
        from src.nlu.normalizer import normalize

        classifier = IntentClassifier()
        text = normalize("Registrar cliente nuevo")
        tokens = tokenize(text, "es")
        results = classifier.classify(tokens, "es")

        if results:
            assert len(results[0].evidence) > 0
