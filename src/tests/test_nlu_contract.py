"""
DDE v3 — Tests del Contrato de Datos

Verifica que las dataclasses frozen son inmutables y
que todas las estructuras tienen los campos correctos.
"""
import pytest


class TestTokenContract:
    """Tests para la dataclass Token."""

    def test_token_creation(self):
        from src.nlu.entities.base import Token
        t = Token(raw="clientes", lemma="cliente", pos=0)
        assert t.raw == "clientes"
        assert t.lemma == "cliente"
        assert t.pos == 0

    def test_token_is_frozen(self):
        from src.nlu.entities.base import Token
        t = Token(raw="test", lemma="test", pos=0)
        with pytest.raises(Exception):
            t.raw = "otro"  # type: ignore

    def test_token_hashable(self):
        from src.nlu.entities.base import Token
        t1 = Token(raw="test", lemma="test", pos=0)
        t2 = Token(raw="test", lemma="test", pos=0)
        assert hash(t1) == hash(t2)


class TestEntityContract:
    """Tests para la dataclass Entity."""

    def test_entity_creation(self):
        from src.nlu.entities.base import Entity
        e = Entity(type="email", value="a@b.com", raw="a@b.com", span=(0, 7), score=1.0)
        assert e.type == "email"
        assert e.value == "a@b.com"
        assert e.span == (0, 7)
        assert e.score == 1.0

    def test_entity_frozen(self):
        from src.nlu.entities.base import Entity
        e = Entity(type="email", value="a@b.com", raw="a@b.com", span=(0, 7), score=1.0)
        with pytest.raises(Exception):
            e.type = "phone"  # type: ignore


class TestIntentMatchContract:
    """Tests para la dataclass IntentMatch."""

    def test_intent_match_creation(self):
        from src.nlu.entities.base import IntentMatch
        im = IntentMatch(intent="registro_cliente", score=0.85, evidence=["registr", "client"])
        assert im.intent == "registro_cliente"
        assert im.score == 0.85
        assert "registr" in im.evidence


class TestSlotContract:
    """Tests para la dataclass Slot."""

    def test_slot_creation(self):
        from src.nlu.entities.base import Slot
        s = Slot(name="email", required=True, filled=True, value="a@b.com", source="entity")
        assert s.name == "email"
        assert s.required is True
        assert s.filled is True
        assert s.value == "a@b.com"

    def test_slot_empty(self):
        from src.nlu.entities.base import Slot
        s = Slot(name="email", required=True, filled=False, value=None, source="entity")
        assert s.filled is False
        assert s.value is None


class TestNLUResultContract:
    """Tests para la dataclass NLUResult."""

    def test_nlu_result_creation(self):
        from src.nlu.entities.base import Token, IntentMatch, Slot, NLUResult
        result = NLUResult(
            text="hola",
            lang="es",
            tokens=(Token(raw="hola", lemma="hola", pos=0),),
            entities=(),
            intents=(IntentMatch(intent="test", score=0.5, evidence=["hola"]),),
            slots=(Slot(name="test", required=False, filled=False, value=None, source="entity"),),
            confidence=0.5,
            trace=("[1] Normalize: ok",),
        )
        assert result.text == "hola"
        assert result.lang == "es"
        assert result.confidence == 0.5
        assert len(result.trace) == 1


class TestStepFragmentContract:
    """Tests para la dataclass StepFragment."""

    def test_fragment_creation(self):
        from src.nlu.entities.base import StepFragment
        f = StepFragment(
            kind="step",
            intent_tags=("registro_cliente",),
            produces={"tool": "crm", "action": "create_lead"},
            requires_slots=("email", "nombre"),
        )
        assert f.kind == "step"
        assert "registro_cliente" in f.intent_tags
        assert "email" in f.requires_slots


class TestCompileResultContract:
    """Tests para la dataclass CompileResult."""

    def test_compile_result_ready(self):
        from src.nlu.entities.base import CompileResult
        cr = CompileResult(
            workflow={"name": "test"},
            explanation="Test workflow",
            missing_slots=(),
            status="ready",
        )
        assert cr.status == "ready"
        assert cr.workflow["name"] == "test"
        assert len(cr.missing_slots) == 0
