"""
DDE v3 — Pipeline Orquestador (Etapas 1-13 + Fase 3 Upgrades)

Orquesta las etapas del pipeline NLU determinista + IA:
1. Normalizer
2. Tokenizer
3. LanguageRouter
4. EntityExtractor
5. IntentClassifier
6. SlotFiller
7. Disambiguator
8. WorkflowCompiler
9. Validator
10. Explainer
11. DryRunSimulator
12. AI WorkflowGenerator (opcional)

Fase 3 — Mejoras:
- Guardrails: ContentGuardrails en prompts, ExecutionGuardrails + PIIGuardrails en workflows
- Fallback Hierarchy: determinista → orbital → IA → template genérico
- Modo smart_compile(): ejecuta cadena de fallback automática

El pipeline ofrece cinco modos:
- process() → NLUResult (etapas 1-6: análisis)
- compile() → CompileResult (etapas 7-11: compilación completa)
- simulate() → DryRunResult (etapa 12: simulación sin ejecutar)
- ai_generate() → AIGenerationResult (etapa 13: generación con IA)
- smart_compile() → NLU con guardrails + fallback hierarchy (Fase 3)

Determinista: misma entrada → misma salida.
IA: complemento opcional que genera workflows desde texto libre.
"""

from __future__ import annotations

from src.core.logging import setup_logging
from src.nlu.ai_generator import AIGenerationResult, WorkflowAIGenerator
from src.nlu.compiler import WorkflowCompiler
from src.nlu.disambiguator import Disambiguator
from src.nlu.dry_run import DryRunSimulator
from src.nlu.entities.base import CompileResult, NLUResult
from src.nlu.entities.condition import ConditionExtractor
from src.nlu.entities.duration import DurationExtractor
from src.nlu.entities.extractor import EntityExtractor
from src.nlu.entities.money import MoneyExtractor
from src.nlu.entities.quantity import QuantityExtractor
from src.nlu.explainer import Explainer
from src.nlu.fallback import FallbackConfig, FallbackOrchestrator
from src.nlu.guardrails import GuardrailManager
from src.nlu.intent_classifier import IntentClassifier
from src.nlu.language_router import LanguageRouter
from src.nlu.normalizer import normalize
from src.nlu.slot_filler import SlotFiller
from src.nlu.tokenizer import tokenize
from src.nlu.validator import WorkflowValidator
from typing import Any

logger = setup_logging(__name__)


class Pipeline:
    """Orquestador del pipeline NLU determinista (etapas 1-12 + 13 IA).

    Fase 3: Integra guardrails y fallback hierarchy.
    """

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

        # Etapa 13: AI Generator (opcional)
        self._ai_generator = WorkflowAIGenerator()

        # ── Fase 3: Guardrails ───────────────────────────
        self._guardrails = GuardrailManager(lang="es")

        # ── Fase 3: Fallback Hierarchy ───────────────────
        self._fallback_orchestrator = FallbackOrchestrator()

        # Orbital compiler para fallback (lazy import)
        self._orbital_compiler = None

    @property
    def _orbital(self):
        """Lazy import del OrbitalCompiler para evitar dependencia circular."""
        if self._orbital_compiler is None:
            from src.orbital.orbital_compiler import OrbitalCompiler

            self._orbital_compiler = OrbitalCompiler()
        return self._orbital_compiler

    @property
    def guardrails(self) -> GuardrailManager:
        """Acceso al gestor de guardrails."""
        return self._guardrails

    @property
    def fallback_stats(self) -> dict[str, Any]:
        """Estadísticas de la jerarquía de fallback."""
        return self._fallback_orchestrator.get_stats()

    # ── SMART COMPILE (Fase 3) ────────────────────────────

    def smart_compile(
        self,
        text: str,
        lang: str | None = None,
        enable_guardrails: bool = True,
        enable_fallback: bool = True,
    ) -> dict[str, Any]:
        """Pipeline inteligente con guardrails + fallback hierarchy (Fase 3).

        Flujo:
        1. ContentGuardrails: verificar prompt del usuario
        2. FallbackOrchestrator: determinista → orbital → IA → template
        3. ExecutionGuardrails + PIIGuardrails: verificar workflow generado
        4. Retornar resultado con metadata de guardrails y fallback

        Args:
            text: Texto en lenguaje natural del usuario
            lang: Idioma forzado (auto-detect si None)
            enable_guardrails: Si aplicar guardrails
            enable_fallback: Si activar la jerarquía de fallback

        Returns:
            Dict con: success, result, guardrails_result, fallback_result
        """
        result: dict[str, Any] = {
            "success": False,
            "result": None,
            "guardrails_result": None,
            "fallback_result": None,
            "explicacion": "",
        }

        detected_lang = lang or self._router.detect(text)

        # ── 1. ContentGuardrails ─────────────────────────
        if enable_guardrails:
            guardrails_result = self._guardrails.check_prompt(text)
            result["guardrails_result"] = guardrails_result

            if guardrails_result.blocked:
                # Si está bloqueado, buscar el primer mensaje de bloqueo
                block_messages = [r.message for r in guardrails_result.blocks]
                result["explicacion"] = block_messages[0] if block_messages else "Contenido bloqueado por guardrails"
                logger.warning(f"SmartCompile bloqueado por guardrails: {guardrails_result.blocks}")
                return result

            if guardrails_result.warnings:
                for w in guardrails_result.warnings:
                    logger.info(f"Guardrail warning: {w.message}")

        # ── 2. Fallback Hierarchy ────────────────────────
        if enable_fallback:
            fallback_config = FallbackConfig(lang=detected_lang)

            def _det_func(text_input: str, lang_input: str) -> CompileResult:
                return self.compile(text_input, lang_input)

            def _orbital_func(text_input: str, ctx: dict[str, Any] | None = None) -> object:
                return self._orbital.compile(text_input, ctx)

            def _ai_func(text_input: str, lang_input: str) -> AIGenerationResult:
                return self._ai_generator.generate(text_input, lang_input)

            # Crear orchestrator temporal para esta compilación
            orchestrator = FallbackOrchestrator(fallback_config)

            fb_result = orchestrator.process(
                text=text,
                deterministic_func=_det_func,
                orbital_func=_orbital_func if fallback_config.allow_orbital_fallback else None,
                ai_func=_ai_func if fallback_config.allow_ai_fallback else None,
                lang=detected_lang,
            )

            result["fallback_result"] = fb_result

            if not fb_result.success:
                result["explicacion"] = "No se pudo procesar la solicitud en ningún nivel de la jerarquía"
                return result

            # Extraer workflow del resultado, manejando diferentes tipos
            wf_result = fb_result.result
            workflow = {}

            if hasattr(wf_result, "workflow"):
                workflow = wf_result.workflow
            elif isinstance(wf_result, dict):
                workflow = wf_result

            if not workflow or not isinstance(workflow, dict) or not workflow.get("steps"):
                result["result"] = wf_result
                result["explicacion"] = fb_result.explanation
                result["success"] = True
                return result

            # ── 3. ExecutionGuardrails + PIIGuardrails ────
            if enable_guardrails and isinstance(workflow, dict) and workflow.get("steps"):
                wf_guardrails = self._guardrails.check_workflow(workflow)
                if wf_guardrails.blocked:
                    result["explicacion"] = "; ".join(r.message for r in wf_guardrails.blocks)
                    logger.warning(f"Workflow bloqueado por guardrails: {wf_guardrails.blocks}")
                    return result

            result["result"] = workflow
            result["explicacion"] = fb_result.explanation
            result["success"] = True

        else:
            # Modo sin fallback: usar determinista directamente
            compile_result = self.compile(text, lang)
            result["result"] = compile_result.workflow
            result["explicacion"] = compile_result.explanation
            result["success"] = compile_result.status == "ready"

        return result

    def ai_generate(self, text: str, lang: str = "es") -> AIGenerationResult:
        """Genera un workflow usando IA (etapa 13).

        La generación es complementaria al compilador determinista.
        Si el compilador falla o el usuario pide IA explícitamente, usa LLM.

        Args:
            text: Texto libre del usuario describiendo el workflow
            lang: Idioma para la explicación

        Returns:
            AIGenerationResult con el workflow y metadata
        """
        return self._ai_generator.generate(text, lang)

    def process(self, text: str, lang: str | None = None) -> NLUResult:
        """Ejecuta el pipeline NLU (etapas 1-6).

        Args:
            text: Texto en lenguaje natural del usuario
            lang: Idioma forzado (auto-detect si None)

        Returns:
            NLUResult con tokens, entidades, intenciones, slots y traza
        """
        import time as _time_mod
        _nlu_start = _time_mod.monotonic()
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

        result = NLUResult(
            text=text,
            lang=detected_lang,
            tokens=tuple(tokens),
            entities=tuple(entities),
            intents=tuple(intents),
            slots=tuple(slots),
            confidence=confidence,
            trace=tuple(trace),
        )

        # M10.4 — Metrics: best-effort, nunca romper el flujo principal.
        try:
            from src.core.observability.telemetry import TelemetryService
            intent_name = (
                intents[0].intent if intents else "unknown"
            )
            TelemetryService().record_nlu_result(
                intent=intent_name,
                confidence=float(confidence) if confidence is not None else 0.0,
                duration=float(_time_mod.monotonic() - _nlu_start),
            )
        except Exception:
            pass

        return result

    def simulate(
        self,
        text: str,
        lang: str | None = None,
        context: dict[str, Any] | None = None,
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
            CompileResult con workflow, explanation, status y nlu_result.
            El campo nlu_result (propagado desde la etapa 1) expone los
            intents detectados para que FallbackOrchestrator pueda decidir
            si activar el Nivel 2 (ORBITAL) sin reconstruir el NLUResult.
        """
        # Etapas 1-6: NLU analysis
        nlu_result = self.process(text, lang)

        # Etapa 7: Disambiguator
        best_intent, is_ambiguous, _candidates = self._disambiguator.resolve(nlu_result.intents)

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
                nlu_result=nlu_result,  # Fix B-01
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
                nlu_result=nlu_result,  # Fix B-01
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
                nlu_result=nlu_result,  # Fix B-01
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
                nlu_result=nlu_result,  # Fix B-01
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
                nlu_result=nlu_result,  # Fix B-01
            )

        # Etapa 11: Explainer
        explanation = compile_result.explanation or self._explainer.explain(compile_result, nlu_result.lang)

        return CompileResult(
            workflow=compile_result.workflow,
            explanation=explanation,
            missing_slots=(),
            status="ready",
            nlu_result=nlu_result,  # Fix B-01
        )

    def compile_with_guardrails(
        self,
        text: str,
        lang: str | None = None,
    ) -> dict[str, Any]:
        """Compila un workflow con guardrails (Fase 3).

        Igual que smart_compile pero sin fallback hierarchy.
        Útil cuando se quiere solo determinista + guardrails.
        """
        return self.smart_compile(text, lang, enable_guardrails=True, enable_fallback=False)

    def get_fallback_stats(self) -> dict[str, Any]:
        """Retorna estadísticas de la jerarquía de fallback."""
        return self._fallback_orchestrator.get_stats()

    def reset_fallback_stats(self) -> None:
        """Reinicia estadísticas de fallback."""
        self._fallback_orchestrator.reset_stats()


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


def simulate_workflow(text: str, context: dict[str, Any] | None = None):
    """Función rápida para simular un workflow desde lenguaje natural.

    Args:
        text: Texto en lenguaje natural
        context: Datos de contexto para la simulación

    Returns:
        DryRunResult con el reporte de simulación
    """
    return Pipeline().simulate(text, context=context)


def ai_generate_workflow(text: str, lang: str = "es") -> AIGenerationResult:
    """Función rápida para generar un workflow con IA desde texto libre.

    Args:
        text: Descripción del workflow que el usuario quiere
        lang: Idioma (es/en)

    Returns:
        AIGenerationResult con el workflow y metadata
    """
    return Pipeline().ai_generate(text, lang)
