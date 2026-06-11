"""
DDE v3 — Tests de Fragmentos de Workflow
"""

import pytest


class TestFragments:
    """Tests para el catálogo de fragmentos."""

    def test_fragments_count(self):
        from src.nlu.fragments import FRAGMENTS

        # Al menos 3 triggers + varios steps
        assert len(FRAGMENTS) >= 10

    def test_trigger_exists_for_registro(self):
        from src.nlu.fragments import get_fragments_by_intent

        frags = get_fragments_by_intent("registro_cliente")
        triggers = [f for f in frags if f.kind == "trigger"]
        assert len(triggers) >= 1

    def test_steps_for_registro(self):
        from src.nlu.fragments import get_fragments_by_intent

        frags = get_fragments_by_intent("registro_cliente")
        steps = [f for f in frags if f.kind == "step"]
        assert len(steps) >= 1

    def test_fragment_has_intent_tags(self):
        from src.nlu.fragments import FRAGMENTS

        for frag in FRAGMENTS:
            assert len(frag.intent_tags) > 0
            assert isinstance(frag.produces, dict)

    def test_get_by_kind(self):
        from src.nlu.fragments import get_fragments_by_kind

        triggers = get_fragments_by_kind("trigger")
        assert len(triggers) >= 3

    def test_fragment_frozen(self):
        from src.nlu.entities.base import StepFragment

        f = StepFragment(
            kind="trigger",
            intent_tags=("test",),
            produces={"type": "event"},
            requires_slots=(),
        )
        with pytest.raises(AttributeError):
            f.kind = "step"  # type: ignore

    def test_determinista(self):
        from src.nlu.fragments import get_fragments_by_intent

        r1 = get_fragments_by_intent("registro_cliente")
        r2 = get_fragments_by_intent("registro_cliente")
        assert [f.kind for f in r1] == [f.kind for f in r2]
