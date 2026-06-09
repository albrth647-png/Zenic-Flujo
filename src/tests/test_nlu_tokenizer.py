"""
DDE v3 — Tests del Tokenizer + Stemmer (Etapa 2)
"""
import pytest


class TestStemmerSpanish:
    """Tests para el stemmer en español."""

    def test_stem_verb_ar(self):
        from src.nlu.tokenizer import stem_spanish
        assert stem_spanish("registrar") == "registr"

    def test_stem_verb_er(self):
        from src.nlu.tokenizer import stem_spanish
        assert stem_spanish("vender") == "vend"

    def test_stem_verb_ir(self):
        from src.nlu.tokenizer import stem_spanish
        assert stem_spanish("recibir") == "recib"

    def test_stem_conjugation_ando(self):
        from src.nlu.tokenizer import stem_spanish
        result = stem_spanish("registrando")
        assert "registr" in result

    def test_stem_conjugation_ado(self):
        from src.nlu.tokenizer import stem_spanish
        result = stem_spanish("registrado")
        assert "registr" in result

    def test_stem_short_words_unchanged(self):
        from src.nlu.tokenizer import stem_spanish
        assert stem_spanish("el") == "el"
        assert stem_spanish("un") == "un"

    def test_stem_plural_es(self):
        from src.nlu.tokenizer import stem_spanish
        result = stem_spanish("clientes")
        # "clientes" -> quita "es" -> "client" (la keyword del template es "client")
        assert result == "client"

    def test_stem_plural_s(self):
        from src.nlu.tokenizer import stem_spanish
        result = stem_spanish("perros")
        # "perros" -> quita "s" -> "perro"
        assert result == "perro"

    def test_stem_femenino_as(self):
        from src.nlu.tokenizer import stem_spanish
        result = stem_spanish("hermanas")
        assert "herman" in result


class TestStemmerEnglish:
    """Tests para el stemmer en inglés."""

    def test_stem_ing(self):
        from src.nlu.tokenizer import stem_english
        result = stem_english("running")
        assert result == "running"[:len("running")-3]  # "runn"

    def test_stem_ed(self):
        from src.nlu.tokenizer import stem_english
        result = stem_english("created")
        assert result == "creat"

    def test_stem_ly(self):
        from src.nlu.tokenizer import stem_english
        result = stem_english("quickly")
        assert result == "quick"

    def test_stem_er(self):
        from src.nlu.tokenizer import stem_english
        result = stem_english("register")
        assert result == "regist"

    def test_stem_customer(self):
        from src.nlu.tokenizer import stem_english
        result = stem_english("customer")
        assert result == "custom"

    def test_stem_tion(self):
        from src.nlu.tokenizer import stem_english
        result = stem_english("automation")
        assert result == "automa"  # "tion" -> "" -> "automa"

    def test_stem_short_words_unchanged(self):
        from src.nlu.tokenizer import stem_english
        assert stem_english("the") == "the"
        assert stem_english("is") == "is"


class TestTokenizer:
    """Tests para tokenize()."""

    def test_tokenize_simple_spanish(self):
        from src.nlu.tokenizer import tokenize
        tokens = tokenize("hola mundo", "es")
        assert len(tokens) == 2
        assert tokens[0].raw == "hola"
        assert tokens[1].raw == "mundo"

    def test_tokenize_stems_spanish(self):
        from src.nlu.tokenizer import tokenize
        tokens = tokenize("registrando clientes", "es")
        lemmas = [t.lemma for t in tokens]
        assert any("registr" in l for l in lemmas)
        assert any("client" in l for l in lemmas)

    def test_tokenize_with_positions(self):
        from src.nlu.tokenizer import tokenize
        tokens = tokenize("a b c", "es")
        assert tokens[0].pos == 0
        assert tokens[1].pos == 1
        assert tokens[2].pos == 2

    def test_tokenize_empty(self):
        from src.nlu.tokenizer import tokenize
        tokens = tokenize("", "es")
        assert len(tokens) == 0

    def test_tokenize_special_chars_stripped(self):
        from src.nlu.tokenizer import tokenize
        tokens = tokenize("hola, mundo!", "es")
        assert len(tokens) == 2
        assert tokens[0].raw == "hola"

    def test_tokenize_determinista(self):
        from src.nlu.tokenizer import tokenize
        t1 = tokenize("registrar nuevo cliente", "es")
        t2 = tokenize("registrar nuevo cliente", "es")
        assert [t.lemma for t in t1] == [t.lemma for t in t2]

    def test_tokenize_irregular_root(self):
        from src.nlu.tokenizer import tokenize
        tokens = tokenize("haciendo", "es")
        assert tokens[0].lemma == "hacer"
