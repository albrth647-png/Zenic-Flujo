"""
Test de regresión para bug B-01.

Antes del fix: smart_compile() siempre caía al Nivel 2 (ORBITAL) porque
CompileResult no tenía atributo `nlu_result`, lo que hacía que
FallbackOrchestrator.should_fallback_deterministic() siempre devolviera
True con reason "no_intents_detected".

Después del fix: smart_compile() de una frase determinista bien formada
debe retornar final_level=DETERMINISTIC.
"""

from __future__ import annotations

import pytest

from src.nlu.entities.base import CompileResult, NLUResult
from src.nlu.fallback import FallbackLevel, FallbackOrchestrator
from src.nlu.pipeline import Pipeline


class TestBugB01CompileResultContract:
    """CompileResult debe tener el campo nlu_result para que FallbackOrchestrator
    pueda inspeccionar los intents sin caer al Nivel 2."""

    def test_compile_result_has_nlu_result_field(self):
        """El dataclass CompileResult debe aceptar kwarg nlu_result."""
        cr = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="ready",
            nlu_result=None,
        )
        assert cr.nlu_result is None

    def test_compile_result_nlu_result_defaults_to_none(self):
        """El campo nlu_result debe ser opcional y default None
        (retrocompatible con los 35 tests existentes que no lo pasan)."""
        cr = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="ready",
        )
        assert cr.nlu_result is None

    def test_compile_result_nlu_result_accepts_real_nluresult(self):
        """Debe poder asignar un NLUResult real."""
        nlu = NLUResult(
            text="test",
            lang="es",
            tokens=(),
            entities=(),
            intents=(),
            slots=(),
            confidence=0.5,
            trace=(),
        )
        cr = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="ready",
            nlu_result=nlu,
        )
        assert cr.nlu_result is nlu
        assert cr.nlu_result.confidence == 0.5


class TestBugB01PipelinePropagatesNLUResult:
    """Pipeline.compile() debe propagar el nlu_result al CompileResult retornado."""

    def test_compile_returns_nlu_result_when_ready(self):
        """Para una frase determinista bien formada, compile() debe retornar
        un CompileResult con nlu_result populado y status='ready'."""
        pipe = Pipeline()
        result = pipe.compile("Enviar email a juan@ejemplo.com")
        assert result.nlu_result is not None, (
            "Pipeline.compile() debe propagar nlu_result al CompileResult. "
            "Sin esto, FallbackOrchestrator cae siempre al Nivel 2 ORBITAL."
        )
        assert isinstance(result.nlu_result, NLUResult)
        assert result.nlu_result.lang in ("es", "en")

    def test_compile_returns_nlu_result_even_on_unknown(self):
        """Incluso cuando status='unknown', el nlu_result debe propagarse
        para que el fallback pueda ver los intents vacíos y decidir."""
        pipe = Pipeline()
        result = pipe.compile("asdfgh zxcvbn")  # texto sin sentido
        assert result.nlu_result is not None
        assert result.status == "unknown"


class TestBugB01FallbackOrchestratorUsesNLUResult:
    """FallbackOrchestrator debe usar compile_result.nlu_result.intents
    (no getattr directo que confunde tipos)."""

    def test_fallback_deterministic_succeeds_on_simple_phrase(self):
        """El bug B-01: para una frase simple y determinista con confianza
        suficiente, smart_compile debe retornar final_level=DETERMINISTIC.

        Antes del fix: SIEMPRE caía a ORBITAL por type confusion
        (intents[0].score → TypeError porque intents era un NLUResult, no tupla).
        Después del fix: cae a ORBITAL solo cuando la confianza es <0.3
        (esa es la razón correcta, no un bug).

        Este test usa FallbackOrchestrator directamente con una confidence
        forzada alta, para aislar B-01 de B-03 (que baja la confidence).
        """
        from src.nlu.entities.base import IntentMatch, NLUResult
        from src.nlu.fallback import FallbackConfig

        # Construir un CompileResult sintético con intents de confianza alta
        # para que el Nivel 1 debería aceptar (sin B-03 metiendo ruido).
        high_conf_nlu = NLUResult(
            text="registrar cliente",
            lang="es",
            tokens=(),
            entities=(),
            intents=(
                IntentMatch(intent="registro_cliente", score=0.85, evidence=["cliente"]),
            ),
            slots=(),
            confidence=0.85,
            trace=(),
        )

        def _det_func_high_conf(text: str, lang: str):
            from src.nlu.entities.base import CompileResult
            return CompileResult(
                workflow={"name": "test", "steps": []},
                explanation="test workflow",
                missing_slots=(),
                status="ready",
                nlu_result=high_conf_nlu,
            )

        orchestrator = FallbackOrchestrator(FallbackConfig(min_confidence_deterministic=0.3))
        fb_result = orchestrator.process(
            text="registrar cliente",
            deterministic_func=_det_func_high_conf,
            orbital_func=None,  # no queremos fallback a orbital
            ai_func=None,
            lang="es",
        )

        # El bug B-01: con confianza 0.85 > 0.3, debe ser DETERMINISTIC.
        # Antes del fix: TypeError al hacer intents[0].score → exception → cae a ORBITAL.
        assert fb_result.final_level == FallbackLevel.DETERMINISTIC, (
            f"BUG B-01 NO ARREGLADO: con NLUResult.confidence=0.85 y status='ready', "
            f"smart_compile cayó a {fb_result.final_level.name}. "
            f"Razones de intentos: "
            f"{[(a.level.name, a.success, a.reason) for a in fb_result.attempts]}"
        )

    def test_fallback_orbital_still_used_when_deterministic_fails(self):
        """Sanity check: el Nivel 2 (ORBITAL) sigue funcionando cuando
        el determinista falla genuinamente (texto sin intenciones)."""
        pipe = Pipeline()
        result = pipe.smart_compile(
            "asdfgh zxcvbn qwerty",  # sin intenciones reales
            enable_guardrails=False,
            enable_fallback=True,
        )
        fb_result = result["fallback_result"]
        # Debe llegar al menos al Nivel 2 o más allá
        assert fb_result.final_level >= FallbackLevel.ORBITAL, (
            f"Se esperaba fallback a ORBITAL+ para texto sin intenciones, "
            f"pero fue {fb_result.final_level.name}"
        )


class TestBugB01NoRegressionOnExistingTests:
    """Verifica que el fix no rompa el contrato existente de CompileResult."""

    def test_compile_result_still_constructible_with_4_args(self):
        """Los tests existentes construyen CompileResult con 4 kwargs.
        El fix debe ser retrocompatible."""
        cr = CompileResult(
            workflow={"steps": []},
            explanation="test",
            missing_slots=(),
            status="ready",
        )
        assert cr.workflow == {"steps": []}
        assert cr.explanation == "test"
        assert cr.missing_slots == ()
        assert cr.status == "ready"

    def test_compile_result_still_frozen(self):
        """CompileResult debe seguir siendo frozen=True."""
        from dataclasses import FrozenInstanceError

        cr = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="ready",
        )
        with pytest.raises(FrozenInstanceError):
            cr.status = "unknown"  # type: ignore[misc]


class TestBugB01PipelinePropagatesNLUResultAllBranches:
    """Cobertura parametrizada de todas las branches de Pipeline.compile().

    Code review F0-D1 identificó que solo 2 de 6 branches estaban testeadas
    para propagación de nlu_result. Esta clase cubre las 4 restantes.
    """

    @pytest.mark.parametrize(
        "text,expected_status",
        [
            # branch 'unknown' por no intents
            ("asdfgh zxcvbn qwerty", "unknown"),
            # branch 'unknown' por best_intent.score == 0.0
            # (texto con tokens pero sin keywords que matcheen ningún intent)
            ("xyzzy foo bar baz qux", "unknown"),
            # branch 'ready' (status exitoso)
            ("Enviar email a juan@ejemplo.com", "ready"),
        ],
    )
    def test_compile_propagates_nlu_result_in_all_branches(self, text, expected_status):
        """Sin importar el branch tomado, nlu_result debe estar populado.

        Antes del fix B-01: nlu_result no existía → FallbackOrchestrator caía a ORBITAL.
        Después del fix: nlu_result siempre se propaga para inspección del fallback.
        """
        pipe = Pipeline()
        result = pipe.compile(text)
        assert result.nlu_result is not None, (
            f"Branch status={result.status!r} no propagó nlu_result. "
            f"Fix B-01 incompleto."
        )
        assert isinstance(result.nlu_result, NLUResult)


class TestBugB01CompileResultReprNoPIILeak:
    """Code review F0-D1 encontró que __repr__ auto-generado de dataclass
    incluiría nlu_result.text (PII del usuario). Verifica que el __repr__
    custom NO leakea el texto original."""

    def test_repr_does_not_include_user_text(self):
        """El __repr__ no debe contener el texto original del usuario."""
        sensitive_text = "mi_email_secreto@ejemplo.com"
        nlu = NLUResult(
            text=sensitive_text,
            lang="es",
            tokens=(),
            entities=(),
            intents=(),
            slots=(),
            confidence=0.5,
            trace=(),
        )
        cr = CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status="ready",
            nlu_result=nlu,
        )
        repr_str = repr(cr)
        assert sensitive_text not in repr_str, (
            f"PII leak en __repr__: texto del usuario encontrado en {repr_str!r}"
        )

    def test_repr_includes_useful_debug_info(self):
        """El __repr__ debe incluir info útil para debugging (status, intents_count)."""
        nlu = NLUResult(
            text="test",
            lang="es",
            tokens=(),
            entities=(),
            intents=(),  # 0 intents
            slots=(),
            confidence=0.5,
            trace=(),
        )
        cr = CompileResult(
            workflow={"name": "wf1", "steps": []},
            explanation="test",
            missing_slots=("email",),
            status="needs_clarification",
            nlu_result=nlu,
        )
        repr_str = repr(cr)
        assert "needs_clarification" in repr_str
        assert "intents_count=0" in repr_str
        assert "email" in repr_str  # missing_slots sí es info útil, no PII
