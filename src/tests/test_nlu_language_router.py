"""
DDE v3 — Tests del LanguageRouter (Etapa 3)
"""
import pytest


class TestLanguageRouter:
    """Tests para LanguageRouter."""

    def test_detect_spanish(self):
        from src.nlu.language_router import LanguageRouter
        router = LanguageRouter()
        assert router.detect("Quiero crear un workflow nuevo") == "es"

    def test_detect_english(self):
        from src.nlu.language_router import LanguageRouter
        router = LanguageRouter()
        assert router.detect("I want to create a new workflow") == "en"

    def test_detect_spanish_with_accents(self):
        from src.nlu.language_router import LanguageRouter
        router = LanguageRouter()
        # NFKD inside should handle accents
        assert router.detect("Creación de facturas") == "es"
