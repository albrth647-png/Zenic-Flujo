"""
DDE v3 — Tests del Explainer
"""
import pytest


class TestExplainer:
    """Tests para Explainer."""

    def test_explain_intent_registro(self):
        from src.nlu.explainer import explain_intent
        text = explain_intent("registro_cliente", "es")
        assert len(text) > 0
        assert "cliente" in text.lower() or "regist" in text.lower()

    def test_explain_intent_unknown(self):
        from src.nlu.explainer import explain_intent
        text = explain_intent("intencion_inexistente", "es")
        assert len(text) > 0

    def test_explain_compile_result_ready(self):
        from src.nlu.explainer import Explainer
        from src.nlu.entities.base import CompileResult

        explainer = Explainer()
        result = CompileResult(
            workflow={
                "name": "Registro de cliente",
                "trigger_type": "event",
                "trigger_config": {"event": "crm.lead.created"},
                "steps": [
                    {"id": 1, "tool": "crm", "action": "create_lead", "params": {}},
                    {"id": 2, "tool": "notification", "action": "send_email",
                     "params": {"to": "cliente@x.com"}},
                ],
            },
            explanation="",
            missing_slots=(),
            status="ready",
        )
        text = explainer.explain(result, "es")
        assert "Workflow" in text or "Disparador" in text
        assert len(text) > 0

    def test_explain_unknown(self):
        from src.nlu.explainer import Explainer
        from src.nlu.entities.base import CompileResult

        explainer = Explainer()
        result = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="unknown",
        )
        text = explainer.explain(result, "es")
        assert len(text) > 0
        assert "No se pudo" in text or "Could not" in text

    def test_explain_needs_clarification(self):
        from src.nlu.explainer import Explainer
        from src.nlu.entities.base import CompileResult

        explainer = Explainer()
        result = CompileResult(
            workflow={},
            explanation="",
            missing_slots=("email_destino", "nombre"),
            status="needs_clarification",
        )
        text = explainer.explain(result, "es")
        assert "Falta" in text or "Missing" in text

    def test_explain_ambiguous(self):
        from src.nlu.explainer import Explainer
        from src.nlu.entities.base import CompileResult

        explainer = Explainer()
        result = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="ambiguous",
        )
        text = explainer.explain(result, "es")
        assert "posibles" in text or "several" in text

    def test_explain_in_english(self):
        from src.nlu.explainer import Explainer
        from src.nlu.entities.base import CompileResult

        explainer = Explainer()
        result = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="unknown",
        )
        text = explainer.explain(result, "en")
        assert "Could not" in text

    def test_explain_determinista(self):
        from src.nlu.explainer import explain_intent
        r1 = explain_intent("registro_cliente", "es")
        r2 = explain_intent("registro_cliente", "es")
        assert r1 == r2
