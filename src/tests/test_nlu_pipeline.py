"""
DDE v3 — Tests del Pipeline Orquestador (Etapas 1-5)
"""


class TestPipeline:
    """Tests para Pipeline.process()."""

    def test_pipeline_basic(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("hola mundo")

        assert result.text == "hola mundo"
        assert result.lang == "es"
        assert len(result.tokens) >= 2
        assert isinstance(result.confidence, float)

    def test_pipeline_detect_intent(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("Quiero registrar un nuevo cliente")

        assert len(result.intents) > 0
        assert result.intents[0].intent == "registro_cliente"
        assert result.confidence > 0

    def test_pipeline_extract_email(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("enviar a juan@email.com")

        emails = [e for e in result.entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].value == "juan@email.com"

    def test_pipeline_tiene_traza(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("hola")

        assert len(result.trace) > 0
        assert any("[1] Normalize" in t for t in result.trace)
        assert any("[2] Tokenize" in t for t in result.trace)
        assert any("[3] Language" in t for t in result.trace)
        assert any("[4] Entities" in t for t in result.trace)
        assert any("[5] Intents" in t for t in result.trace)

    def test_pipeline_english(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("I want to register a new customer")

        assert result.lang == "en"
        assert len(result.intents) > 0

    def test_pipeline_sin_intencion(self):
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("xyz abc qwerty")

        assert result.confidence == 0.0

    def test_pipeline_entities_tuple(self):
        from src.nlu.entities.base import Entity
        from src.nlu.pipeline import Pipeline

        pipe = Pipeline()
        result = pipe.process("mi email es test@test.com")

        assert isinstance(result.entities, tuple)
        for e in result.entities:
            assert isinstance(e, Entity)

    def test_pipeline_understand_helper(self):
        from src.nlu.pipeline import understand

        result = understand("Registrar cliente")
        assert result is not None
        assert len(result.intents) > 0
