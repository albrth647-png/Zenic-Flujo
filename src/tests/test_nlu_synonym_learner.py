"""
Tests para SynonymLearner (Sprint 4, Tarea 2).
"""
import pytest
from src.nlu.synonym_learner import SynonymLearner, Synonym


@pytest.fixture
def learner():
    return SynonymLearner()  # in-memory


class TestSynonymLearner:

    def test_learn_creates_synonym(self, learner):
        s = learner.learn("facturar", "factura", "factura_automatica")
        assert isinstance(s, Synonym)
        assert s.word == "facturar"
        assert s.synonym_of == "factura"
        assert s.intent == "factura_automatica"

    def test_get_synonyms_returns_learned(self, learner):
        learner.learn("facturar", "factura", "factura_automatica")
        learner.learn("cobrar", "cobro", "factura_vencida")
        all_syns = learner.get_synonyms()
        assert len(all_syns) == 2

    def test_get_synonyms_filter_by_intent(self, learner):
        learner.learn("facturar", "factura", "factura_automatica")
        learner.learn("registrar", "registro", "registro_cliente")
        filtered = learner.get_synonyms("factura_automatica")
        assert len(filtered) == 1
        assert filtered[0].word == "facturar"

    def test_no_duplicates(self, learner):
        learner.learn("facturar", "factura", "factura_automatica")
        learner.learn("facturar", "factura", "factura_automatica")
        all_syns = learner.get_synonyms()
        assert len(all_syns) == 1

    def test_get_keywords_for_intent(self, learner):
        learner.learn("facturar", "factura", "factura_automatica")
        learner.learn("cobrar", "cobro", "factura_automatica")
        keywords = learner.get_keywords_for_intent("factura_automatica")
        assert "facturar" in keywords
        assert "cobrar" in keywords

    def test_remove_synonym(self, learner):
        learner.learn("facturar", "factura", "factura_automatica")
        removed = learner.remove_synonym("facturar", "factura_automatica")
        assert removed is True
        assert len(learner.get_synonyms()) == 0

    def test_remove_nonexistent_returns_false(self, learner):
        removed = learner.remove_synonym("noexiste", "nointent")
        assert removed is False

    def test_import_bulk(self, learner):
        data = [
            {"word": "facturar", "synonym_of": "factura", "intent": "factura_automatica"},
            {"word": "cobrar", "synonym_of": "cobro", "intent": "factura_vencida"},
            {"word": "registrar", "synonym_of": "registro", "intent": "registro_cliente"},
        ]
        count = learner.import_bulk(data)
        assert count == 3
        assert len(learner.get_synonyms()) == 3

    def test_import_bulk_skips_incomplete(self, learner):
        data = [
            {"word": "facturar", "synonym_of": "factura", "intent": "factura_automatica"},
            {"word": "sin_completo"},  # missing keys
        ]
        count = learner.import_bulk(data)
        assert count == 1

    def test_case_insensitive(self, learner):
        learner.learn("FACTURAR", "Factura", "Factura_Automatica")
        syns = learner.get_synonyms()
        assert syns[0].word == "facturar"
        assert syns[0].synonym_of == "factura"
        assert syns[0].intent == "factura_automatica"
