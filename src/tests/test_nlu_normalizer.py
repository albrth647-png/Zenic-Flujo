"""
DDE v3 — Tests del Normalizer (Etapa 1)
"""


class TestNormalizer:
    """Tests para la función normalize."""

    def test_lowercase(self):
        from src.nlu.normalizer import normalize
        assert normalize("HOLA MUNDO") == "hola mundo"

    def test_remove_accents(self):
        from src.nlu.normalizer import normalize
        result = normalize("canción pública")
        assert "cancion publica" in result

    def test_nfkd_spanish(self):
        from src.nlu.normalizer import normalize
        result = normalize("acción única ínfima")
        assert result == "accion unica infima"

    def test_expand_numbers_spanish(self):
        from src.nlu.normalizer import normalize
        result = normalize("quinientos", lang="es")
        assert result == "500"

    def test_expand_numbers_english(self):
        from src.nlu.normalizer import normalize
        result = normalize("twenty five", lang="en")
        assert result == "20 5"

    def test_expand_multiple_numbers(self):
        from src.nlu.normalizer import normalize
        result = normalize("uno dos tres", lang="es")
        assert result == "1 2 3"

    def test_remove_irrelevant_punctuation(self):
        from src.nlu.normalizer import normalize
        result = normalize("¡Hola, mundo! ¿Cómo estás?")
        assert result == "hola mundo como estas"

    def test_preserve_email(self):
        from src.nlu.normalizer import normalize
        result = normalize("juan@email.com")
        assert "juan@email.com" in result

    def test_preserve_dates(self):
        from src.nlu.normalizer import normalize
        result = normalize("2024-01-15")
        assert "2024-01-15" in result

    def test_normalize_pura_determinista(self):
        from src.nlu.normalizer import normalize
        input_text = "Regístrar un Nuevo Cliente"
        r1 = normalize(input_text)
        r2 = normalize(input_text)
        assert r1 == r2

    def test_empty_text(self):
        from src.nlu.normalizer import normalize
        assert normalize("") == ""

    def test_only_punctuation(self):
        from src.nlu.normalizer import normalize
        result = normalize("!¡?¿,.;:")
        assert result == ""
