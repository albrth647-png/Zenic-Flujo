"""
Test de verificación para bug B-01 — FallbackOrchestrator descarta resultado determinista.

Antes del fix: ``getattr(compile_result, "nlu_result", None)`` devolvía ``None`` porque
``CompileResult`` no tenía atributo ``nlu_result``. Como consecuencia, ``intents`` quedaba
en ``()`` y ``FallbackOrchestrator.should_fallback_deterministic`` siempre devolvía
``(True, "no_intents_detected")``, forzando el paso al Nivel 2 (ORBITAL) aunque el
pipeline determinista hubiera generado un workflow válido.

Después del fix: ``CompileResult`` expone ``nlu_result`` y ``Pipeline.compile()`` lo propaga
en todas sus branches. ``FallbackOrchestrator`` inspecciona ``nlu_result.intents`` y, si
la confianza del mejor intent supera el umbral, retorna el resultado DETERMINISTA.
``Pipeline.smart_compile()`` por tanto retorna el workflow determinista cuando está
disponible, sin caer innecesariamente al orbital.
"""

from __future__ import annotations

from typing import ClassVar

from src.nlu.entities.base import CompileResult, IntentMatch, NLUResult
from src.nlu.fallback import FallbackLevel, FallbackOrchestrator
from src.nlu.pipeline import Pipeline


class TestBugB01CompileResultContract:
    """CompileResult debe exponer nlu_result para que FallbackOrchestrator pueda usarlo."""

    def test_compile_result_has_nlu_result_attribute(self) -> None:
        """El dataclass CompileResult debe aceptar y exponer el atributo nlu_result."""
        nlu = NLUResult(
            text="registro cliente",
            lang="es",
            tokens=(),
            entities=(),
            intents=(IntentMatch(intent="registro_cliente", score=0.85, evidence=["cliente"]),),
            slots=(),
            confidence=0.85,
            trace=(),
        )
        cr = CompileResult(
            workflow={"name": "wf", "steps": []},
            explanation="ok",
            missing_slots=(),
            status="ready",
            nlu_result=nlu,
        )
        # Debe estar expuesto y ser el NLUResult pasado.
        assert cr.nlu_result is nlu
        # Y debe permitir acceder a los intents sin TypeError.
        assert cr.nlu_result.intents[0].score == 0.85


class TestBugB01PipelinePropagatesNLUResult:
    """Pipeline.compile() debe poblar nlu_result en el CompileResult retornado."""

    def test_compile_propagates_nlu_result_for_simple_phrase(self) -> None:
        """Para una frase determinista bien formada, compile() debe poblar nlu_result."""
        pipe = Pipeline()
        cr = pipe.compile("Quiero registrar un nuevo cliente")
        assert cr.nlu_result is not None, (
            "Pipeline.compile() no propagó nlu_result. Sin esto, FallbackOrchestrator "
            "siempre cae al Nivel 2 (ORBITAL) por type confusion."
        )
        assert isinstance(cr.nlu_result, NLUResult)
        # Y los intents deben ser una tupla indexable.
        assert hasattr(cr.nlu_result, "intents")
        assert len(cr.nlu_result.intents) >= 1
        # Y el score debe ser accesible (esto es lo que rompía antes con TypeError).
        assert cr.nlu_result.intents[0].score > 0


class TestBugB01SmartCompileReturnsDeterministic:
    """Smart_compile() debe retornar el workflow determinista cuando esté disponible.

    Este es el test clave del bug B-01: anteriormente, smart_compile SIEMPRE
    caía al Nivel 2 (ORBITAL) porque el NLUResult no se propagaba. Ahora debe
    retornar el resultado DETERMINISTA cuando la confianza es suficiente.
    """

    def test_smart_compile_returns_deterministic_for_simple_phrase(self) -> None:
        """Para una frase con confianza > umbral, smart_compile debe usar Nivel 1."""
        pipe = Pipeline()
        result = pipe.smart_compile("Quiero registrar un nuevo cliente")
        assert result["success"] is True
        fb = result["fallback_result"]
        # El bug B-01: con confianza suficiente, debe ser DETERMINISTIC, no ORBITAL.
        assert fb.final_level == FallbackLevel.DETERMINISTIC, (
            f"BUG B-01: smart_compile cayó a {fb.final_level.name} para una frase "
            f"determinista bien formada. Se esperaba DETERMINISTIC. "
            f"Attempts: {[(a.level.name, a.success, a.reason) for a in fb.attempts]}"
        )
        # Y el resultado debe ser un workflow con steps (no el resultado orbital).
        workflow = result["result"]
        assert isinstance(workflow, dict)
        assert workflow.get("steps"), (
            "smart_compile no retornó un workflow con steps — el resultado determinista "
            "se descartó a favor del orbital."
        )

    def test_smart_compile_does_not_always_fall_to_orbital(self) -> None:
        """Sanity check: en múltiples llamadas deterministas, Nivel 1 debe ganar a veces.

        Antes del fix, smart_compile SIEMPRE caía a ORBITAL. Ahora debe
        retornar DETERMINISTIC para al menos una frase simple.
        """
        pipe = Pipeline()
        frases = [
            "Quiero registrar un nuevo cliente",
            "Registrar un cliente nuevo",
            "Registrar cliente",
        ]
        niveles = []
        for frase in frases:
            result = pipe.smart_compile(frase)
            fb = result["fallback_result"]
            niveles.append(fb.final_level)
        # Al menos una de las frases debe ser DETERMINISTIC (no todas ORBITAL).
        assert FallbackLevel.DETERMINISTIC in niveles, (
            f"BUG B-01: ninguna frase determinista retornó DETERMINISTIC. "
            f"Niveles obtenidos: {[n.name for n in niveles]}. "
            f"Se esperaba al menos uno DETERMINISTIC."
        )


class TestBugB01FallbackOrchestratorRespectsNLUResult:
    """FallbackOrchestrator debe usar nlu_result.intents para decidir el fallback."""

    def test_orchestrator_returns_deterministic_when_nlu_result_has_high_confidence(self) -> None:
        """Con nlu_result.confidence alta, debe retornar DETERMINISTIC sin ir a ORBITAL."""
        nlu_high = NLUResult(
            text="registrar cliente",
            lang="es",
            tokens=(),
            entities=(),
            intents=(IntentMatch(intent="registro_cliente", score=0.85, evidence=["cliente"]),),
            slots=(),
            confidence=0.85,
            trace=(),
        )

        def _det_func(_text: str, _lang: str) -> CompileResult:
            return CompileResult(
                workflow={"name": "test", "steps": [{"id": 1, "tool": "crm", "action": "create_lead", "params": {}}]},
                explanation="test workflow",
                missing_slots=(),
                status="ready",
                nlu_result=nlu_high,
            )

        orchestrator = FallbackOrchestrator()
        fb = orchestrator.process(
            text="registrar cliente",
            deterministic_func=_det_func,
            orbital_func=None,  # No debe llegar a ORBITAL.
            ai_func=None,
            lang="es",
        )
        assert fb.final_level == FallbackLevel.DETERMINISTIC
        assert fb.success is True

    def test_orchestrator_falls_back_when_nlu_result_is_none(self) -> None:
        """Si nlu_result es None (retrocompatibilidad), debe caer a ORBITAL.

        Este test protege el contrato: aunque el fix B-01 propague nlu_result,
        si algún caller legacy pasa un CompileResult sin nlu_result, el
        Orchestrator debe seguir funcionando (graceful degradation).
        """
        # CompileResult sin nlu_result (default None).
        cr_no_nlu = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="unknown",
        )

        def _det_func(_text: str, _lang: str) -> CompileResult:
            return cr_no_nlu

        # Orbital simulado que retorna un workflow válido.
        class _FakeOrbital:
            # ClassVar: anotacion para que ruff no marque como mutable default.
            intent: ClassVar[str] = "registro_cliente"
            confidence: ClassVar[float] = 0.85
            explanation: ClassVar[str] = "orbital workflow"
            workflow: ClassVar[dict] = {"name": "orbital", "steps": []}

        def _orbital_func(_text: str, _ctx: dict | None = None) -> _FakeOrbital:
            return _FakeOrbital()

        orchestrator = FallbackOrchestrator()
        fb = orchestrator.process(
            text="registrar cliente",
            deterministic_func=_det_func,
            orbital_func=_orbital_func,
            ai_func=None,
            lang="es",
        )
        # Debe caer al Nivel 2 porque nlu_result es None (status unknown).
        assert fb.final_level == FallbackLevel.ORBITAL
        assert fb.success is True
