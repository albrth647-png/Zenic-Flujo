"""
DDE v3 — Pipeline Orquestador (Etapas 1-12)

Orquesta las etapas del pipeline NLU determinista:
1. Normalizer
2. Tokenizer
3. LanguageRouter
4. EntityExtractor
5. IntentClassifier
6. SlotFiller
7. Disambiguator
8. ClarifyDialog
9. WorkflowCompiler
10. Validator
11. Explainer
12. DryRunSimulator

El pipeline ofrece tres modos:
- process() → NLUResult (etapas 1-6: análisis)
- compile() → CompileResult (etapas 7-11: compilación completa)
- simulate() → DryRunResult (etapa 12: simulación sin ejecutar)

Determinista: misma entrada → misma salida.
"""
from __future__ import annotations
from src.nlu.entities.base import Token, Entity, IntentMatch, Slot, NLUResult, CompileResult
from src.nlu.normalizer import normalize
from src.nlu.tokenizer import tokenize
from src.nlu.language_router import LanguageRouter
from src.nlu.entities.extractor import EntityExtractor
from src.nlu.entities.money import MoneyExtractor
from src.nlu.entities.quantity import QuantityExtractor
from src.nlu.entities.duration import DurationExtractor
from src.nlu.entities.condition import ConditionExtractor
from src.nlu.intent_classifier import IntentClassifier
from src.nlu.slot_filler import SlotFiller
from src.nlu.disambiguator import Disambiguator
from src.nlu.compiler import WorkflowCompiler
from src.nlu.validator import WorkflowValidator
from src.nlu.explainer import Explainer
from src.nlu.dry_run import DryRunSimulator


class Pipeline:
    """Orquestador del pipeline NLU determinista (etapas 1-11)."""

    def __init__(self):
        # Etapas 1-5
        self._router = LanguageRouter()
        self._extractor = EntityExtractor()
        self._money_ext = MoneyExtractor()
        self._qty_ext = QuantityExtractor()
        self._duration_ext = DurationExtractor()
        self._condition_ext = ConditionExtractor()
        self._classifier = IntentClassifier()

        # Etapas 6-12
        self._slot_filler = SlotFiller()
        self._disambiguator = Disambiguator()
        self._compiler = WorkflowCompiler()
        self._validator = WorkflowValidator()
        self._explainer = Explainer()
        self._dry_run = DryRunSimulator()

    def process(self, text: str, lang: str | None = None) -> NLUResult:
        """Ejecuta el pipeline NLU (etapas 1-6).

        Args:
            text: Texto en lenguaje natural del usuario
            lang: Idioma forzado (auto-detect si None)

        Returns:
            NLUResult con tokens, entidades, intenciones, slots y traza
        """
        trace: list[str] = []

        # ── Etapa 1: Normalizer ───────────────────────────
        normalized = normalize(text)
        trace.append(f"[1] Normalize: '{text}' → '{normalized}'")

        # ── Etapa 3: LanguageRouter (se necesita antes de tokenizar) ──
        detected_lang = lang or self._router.detect(text)
        trace.append(f"[3] Language: detected '{detected_lang}'")

        # ── Etapa 2: Tokenizer ────────────────────────────
        tokens = tokenize(normalized, detected_lang)
        trace.append(f"[2] Tokenize: {len(tokens)} tokens")

        # ── Etapa 4: EntityExtractor ──────────────────────
        entities = list(self._extractor.extract_all(text))
        entities.extend(self._money_ext.extract(text))
        entities.extend(self._qty_ext.extract(text))
        entities.extend(self._duration_ext.extract(text))
        entities.extend(self._condition_ext.extract(text))
        entities.sort(key=lambda e: e.span[0])
        entities = self._extractor._resolve_overlaps(entities)
        trace.append(f"[4] Entities: {len(entities)} found ({[e.type for e in entities]})")

        # ── Etapa 5: IntentClassifier ─────────────────────
        intents = self._classifier.classify(tokens, detected_lang)
        trace.append(f"[5] Intents: {len(intents)} found")
        for i in intents[:3]:
            trace.append(f"    - {i.intent}: score={i.score}")

        # ── Etapa 6: SlotFiller ───────────────────────────
        slots = self._slot_filler.fill(intents, tuple(entities))
        trace.append(f"[6] Slots: {len(slots)} ({[s.name for s in slots]})")

        # ── Confidence: usar el score de la mejor intención ──
        confidence = intents[0].score if intents else 0.0

        return NLUResult(
            text=text,
            lang=detected_lang,
            tokens=tuple(tokens),
            entities=tuple(entities),
            intents=tuple(intents),
            slots=tuple(slots),
            confidence=confidence,
            trace=tuple(trace),
        )

    def simulate(
        self,
        text: str,
        lang: str | None = None,
        context: dict | None = None,
    ):
        """Ejecuta el pipeline completo + simulación (etapas 1-12).

        Args:
            text: Texto en lenguaje natural del usuario
            lang: Idioma forzado (auto-detect si None)
            context: Datos de contexto para la simulación

        Returns:
            DryRunResult con el reporte de simulación
        """
        compile_result = self.compile(text, lang)
        if compile_result.status != "ready" or not compile_result.workflow:
            from src.nlu.dry_run import DryRunResult
            return DryRunResult(
                workflow_name="",
                trigger_type="",
                trigger_config={},
                steps=(),
                total_steps=0,
                steps_that_would_succeed=0,
                steps_that_would_fail=0,
                warnings=(f"No se pudo compilar: {compile_result.status}",),
                overall_feasible=False,
                summary=f"Simulación abortada: {compile_result.status}",
            )
        return self._dry_run.simulate(compile_result.workflow, context)

    def compile(
        self,
        text: str,
        lang: str | None = None,
    ) -> CompileResult:
        """Ejecuta el pipeline completo (etapas 1-11).

        Analiza el texto, llena slots, desambigua, compila, valida y explica.

        Args:
            text: Texto en lenguaje natural del usuario
            lang: Idioma forzado (auto-detect si None)

        Returns:
            CompileResult con workflow, explanation y status
        """
        # Etapas 1-6: NLU analysis
        nlu_result = self.process(text, lang)

        # Etapa 7: Disambiguator
        best_intent, is_ambiguous, candidates = self._disambiguator.resolve(
            nlu_result.intents
        )

        # ── Caso: sin intenciones detectadas ──────────────
        if not nlu_result.intents:
            return CompileResult(
                workflow={},
                explanation=self._explainer.explain(
                    CompileResult(workflow={}, explanation="", missing_slots=(), status="unknown"),
                    nlu_result.lang,
                ),
                missing_slots=(),
                status="unknown",
            )

        # ── Caso: score 0.0 = ninguna keyword matcheo ─────
        if not best_intent or best_intent.score == 0.0:
            return CompileResult(
                workflow={},
                explanation=self._explainer.explain(
                    CompileResult(workflow={}, explanation="", missing_slots=(), status="unknown"),
                    nlu_result.lang,
                ),
                missing_slots=(),
                status="unknown",
            )

        # ── Caso: ambigüedad entre múltiples intenciones ──
        if is_ambiguous:
            return CompileResult(
                workflow={},
                explanation=self._explainer.explain(
                    CompileResult(workflow={}, explanation="", missing_slots=(), status="ambiguous"),
                    nlu_result.lang,
                ),
                missing_slots=(),
                status="ambiguous",
            )

        # ── Caso normal: compilar workflow ─────────────────
        # Etapa 9: WorkflowCompiler
        compile_result = self._compiler.compile(
            intent_name=best_intent.intent,
            slots=nlu_result.slots,
            entities=nlu_result.entities,
            lang=nlu_result.lang,
        )

        # Si faltan slots, retornar con status needs_clarification
        if compile_result.status == "needs_clarification":
            explanation = self._explainer.explain(compile_result, nlu_result.lang)
            return CompileResult(
                workflow={},
                explanation=explanation,
                missing_slots=compile_result.missing_slots,
                status="needs_clarification",
            )

        # Etapa 10: Validator
        validation = self._validator.validate(compile_result.workflow)
        if not validation.valid:
            errors_str = "; ".join(validation.errors)
            return CompileResult(
                workflow=compile_result.workflow,
                explanation=f"Errores de validación: {errors_str}",
                missing_slots=compile_result.missing_slots,
                status="validation_error",
            )

        # Etapa 11: Explainer
        explanation = compile_result.explanation or self._explainer.explain(
            compile_result, nlu_result.lang
        )

        return CompileResult(
            workflow=compile_result.workflow,
            explanation=explanation,
            missing_slots=(),
            status="ready",
        )


# ── Funciones de conveniencia ──────────────────────────

def understand(text: str) -> NLUResult:
    """Función rápida para análisis NLU (etapas 1-6).

    Args:
        text: Texto en lenguaje natural

    Returns:
        NLUResult completo
    """
    return Pipeline().process(text)


def compile_workflow(text: str) -> CompileResult:
    """Función rápida para compilar un workflow desde lenguaje natural.

    Args:
        text: Texto en lenguaje natural

    Returns:
        CompileResult con workflow, explanation y status
    """
    return Pipeline().compile(text)


def simulate_workflow(text: str, context: dict | None = None):
    """Función rápida para simular un workflow desde lenguaje natural.

    Args:
        text: Texto en lenguaje natural
        context: Datos de contexto para la simulación

    Returns:
        DryRunResult con el reporte de simulación
    """
    return Pipeline().simulate(text, context=context)
