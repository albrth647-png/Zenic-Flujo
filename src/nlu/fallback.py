"""
DDE v3 — NLU Fallback Hierarchy (Fase 3)

Cadena formal de fallback para el pipeline NLU.

Niveles de la jerarquía:
1. DETERMINISTIC   → Pipeline NLU original (13 etapas) — máxima precisión
2. ORBITAL         → OrbitalCompiler (resonancia) — más rápido, menos preciso
3. AI_GENERATOR    → WorkflowAIGenerator (LLM) — flexible, requiere API
4. TEMPLATE_FALLBACK → Respuesta por template genérico — siempre disponible

Cada nivel reporta:
- confidence: float (0.0-1.0)
- fallback_reason: str (por qué se activó este nivel)
- processing_time_ms: int (latencia del nivel)

Estadísticas de fallback:
- El manager acumula métricas de qué nivel se usó y por qué
- Permite tuning de thresholds basado en uso real

Ejemplo de flujo:
    usuario escribe: "haz algo con la base de datos"
    → Nivel 1: confidence=0.15 (< 0.3) → pasa a Nivel 2
    → Nivel 2: resonance=0.08 (< 0.2) → pasa a Nivel 3
    → Nivel 3: no hay IA configurada → pasa a Nivel 4
    → Nivel 4: template genérico "No entendí, ¿puedes ser más específico?"
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class FallbackLevel(IntEnum):
    """Niveles de la jerarquía de fallback (menor = mejor)."""

    DETERMINISTIC = 1  # Pipeline NLU original
    ORBITAL = 2        # Compilador orbital
    AI_GENERATOR = 3   # Generación con LLM
    TEMPLATE_FALLBACK = 4  # Respuesta genérica siempre disponible


FALLBACK_REASONS = {
    "no_intents_detected": "No se detectaron intenciones en el texto",
    "confidence_too_low": "Confianza por debajo del umbral mínimo",
    "ambiguous_intents": "Múltiples intenciones con scores similares",
    "no_ai_configured": "No hay proveedor IA configurado",
    "ai_generation_failed": "La generación IA falló",
    "orchestration_error": "Error en la orquestación del nivel",
    "empty_result": "El nivel retornó resultado vacío",
    "template_unavailable": "No hay template disponible para esta intención",
}


@dataclass
class FallbackAttempt:
    """Resultado de un intento individual en la cadena de fallback."""

    level: FallbackLevel
    success: bool
    confidence: float
    # legítimo: resultado dinámico de dispatch HAT, tipo depende del especialista
    result: Any | None = None
    reason: str = ""
    processing_time_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class FallbackResult:
    """Resultado final de la cadena de fallback."""

    success: bool
    final_level: FallbackLevel
    attempts: list[FallbackAttempt]
    # legítimo: resultado dinámico de dispatch HAT, tipo depende del especialista
    result: Any | None = None
    explanation: str = ""
    total_time_ms: float = 0.0

    @property
    def used_fallback(self) -> bool:
        """True si se usó un nivel de fallback (no el determinista)."""
        return self.final_level != FallbackLevel.DETERMINISTIC

    @property
    def fallback_depth(self) -> int:
        """Cuántos niveles se recorrieron antes de éxito (0 = determinista)."""
        return self.final_level - 1

    @property
    def last_attempt(self) -> FallbackAttempt | None:
        if not self.attempts:
            return None
        return self.attempts[-1]


# ──────────────────────────────────────────────
#  CONFIGURACIÓN DE LA JERARQUÍA
# ──────────────────────────────────────────────


@dataclass
class FallbackConfig:
    """Configuración de thresholds y comportamiento de la cadena."""

    # Confianza mínima para aceptar resultado determinista
    min_confidence_deterministic: float = 0.3

    # Confianza mínima para aceptar resultado orbital
    min_confidence_orbital: float = 0.2

    # Confianza mínima para aceptar resultado de IA
    min_confidence_ai: float = 0.1

    # Umbral de ambigüedad (diferencia entre 1er y 2do score)
    ambiguity_threshold: float = 0.15

    # Tiempo máximo por nivel (ms)
    max_time_per_level_ms: float = 5000.0

    # Template de fallback final
    fallback_template_name: str = "ayuda_generica"

    # Idioma por defecto
    lang: str = "es"

    # ¿Permitir IA como fallback?
    allow_ai_fallback: bool = True

    # ¿Permitir orbital como fallback?
    allow_orbital_fallback: bool = True


# ──────────────────────────────────────────────
#  ANALIZADOR DE RESULTADOS
# ──────────────────────────────────────────────


class FallbackAnalyzer:
    """Analiza resultados NLU para decidir si activar fallback."""

    def __init__(self, config: FallbackConfig | None = None):
        self.config = config or FallbackConfig()

    def should_fallback_deterministic(
        self,
        intents: tuple[Any, ...],
        compile_result: Any | None = None,
    ) -> tuple[bool, str]:
        """Decide si el resultado determinista es confiable."""
        if not intents:
            return True, FALLBACK_REASONS["no_intents_detected"]

        if compile_result:
            status = getattr(compile_result, "status", "")
            if status in ("unknown", "ambiguous", "needs_clarification"):
                if status == "unknown":
                    return True, FALLBACK_REASONS["no_intents_detected"]
                if status == "ambiguous":
                    # Verificar si realmente es ambigüedad o bajo score
                    if len(intents) >= 2:
                        diff = intents[0].score - intents[1].score
                        if diff < self.config.ambiguity_threshold:
                            return True, FALLBACK_REASONS["ambiguous_intents"]
                    return True, FALLBACK_REASONS["ambiguous_intents"]
                return True, FALLBACK_REASONS["confidence_too_low"]

        # Verificar confianza del mejor intent
        if intents:
            best_score = intents[0].score
            if best_score < self.config.min_confidence_deterministic:
                return True, FALLBACK_REASONS["confidence_too_low"]

        return False, ""

    def should_fallback_orbital(
        self,
        intent_name: str,
        confidence: float,
    ) -> tuple[bool, str]:
        """Decide si el resultado orbital es confiable."""
        if not intent_name or intent_name == "general":
            return True, FALLBACK_REASONS["no_intents_detected"]
        if confidence < self.config.min_confidence_orbital:
            return True, FALLBACK_REASONS["confidence_too_low"]
        return False, ""


# ──────────────────────────────────────────────
#  TEMPLATE DE FALLBACK GENÉRICO
# ──────────────────────────────────────────────


# Mensajes de fallback multilingües
FALLBACK_MESSAGES: dict[str, dict[str, str]] = {
    "ayuda_generica": {
        "es": (
            "No entendí bien tu solicitud. ¿Puedes ser más específico?\n\n"
            "Ejemplos de lo que puedo hacer:\n"
            "• \"Registra un nuevo cliente\"\n"
            "• \"Enviar email de bienvenida cuando alguien se registre\"\n"
            "• \"Alertar cuando el stock esté bajo\"\n"
            "• \"Factura automática los lunes\""
        ),
        "en": (
            "I didn't quite understand your request. Could you be more specific?\n\n"
            "Examples of what I can do:\n"
            "• \"Register a new customer\"\n"
            "• \"Send a welcome email when someone registers\"\n"
            "• \"Alert when stock is low\"\n"
            "• \"Auto-invoice every Monday\""
        ),
    },
    "demasiado_generico": {
        "es": (
            "Tu solicitud es muy general. Prueba con algo como:\n"
            "• \"Cuando un cliente nuevo se registre, guardarlo y enviar email\"\n"
            "• \"Revisar inventario cada mañana y avisar si falta algo\""
        ),
        "en": (
            "Your request is too broad. Try something like:\n"
            "• \"When a new customer registers, save them and send an email\"\n"
            "• \"Check inventory every morning and alert if something is missing\""
        ),
    },
    "sin_ia_disponible": {
        "es": (
            "No pude procesar tu solicitud de forma determinista, "
            "y no hay un asistente de IA configurado. "
            "Puedes activar Ollama, OpenAI o Anthropic en Configuración, "
            "o intentar ser más específico con tu solicitud."
        ),
        "en": (
            "I couldn't process your request deterministically, "
            "and no AI assistant is configured. "
            "You can enable Ollama, OpenAI, or Anthropic in Settings, "
            "or try being more specific with your request."
        ),
    },
    "error_interno": {
        "es": (
            "Ocurrió un error interno procesando tu solicitud. "
            "Por favor intenta de nuevo o contacta al administrador."
        ),
        "en": (
            "An internal error occurred while processing your request. "
            "Please try again or contact the administrator."
        ),
    },
}


def get_fallback_message(template_name: str, lang: str = "es") -> str:
    """Obtiene el mensaje de fallback en el idioma solicitado."""
    template = FALLBACK_MESSAGES.get(template_name, FALLBACK_MESSAGES["ayuda_generica"])
    return template.get(lang, template["es"])


# ──────────────────────────────────────────────
#  FALLBACK ORCHESTRATOR
# ──────────────────────────────────────────────


class FallbackOrchestrator:
    """Orquesta la jerarquía de fallback del pipeline NLU.

    Flujo de decisión:
    1. Ejecuta pipeline determinista
    2. Si confianza < threshold → intenta orbital
    3. Si orbital falla → intenta IA generator (si configurado)
    4. Si todo falla → template de fallback genérico
    """

    def __init__(self, config: FallbackConfig | None = None):
        self.config = config or FallbackConfig()
        self._analyzer = FallbackAnalyzer(config)

        # Estadísticas de fallback
        self._stats: dict[str, int] = {
            "total_processed": 0,
            "deterministic_ok": 0,
            "orbital_fallback": 0,
            "ai_fallback": 0,
            "template_fallback": 0,
            "total_failures": 0,
        }

    def process(
        self,
        text: str,
        deterministic_func: Callable[..., Any],
        orbital_func: Callable[..., Any] | None = None,
        ai_func: Callable[..., Any] | None = None,
        lang: str | None = None,
    ) -> FallbackResult:
        """Ejecuta la cadena de fallback completa.

        Args:
            text: Texto del usuario
            deterministic_func: Función del pipeline NLU determinista
            orbital_func: Función del OrbitalCompiler (opcional)
            ai_func: Función del AI WorkflowGenerator (opcional)
            lang: Idioma detectado

        Returns:
            FallbackResult con el mejor resultado disponible
        """
        self._stats["total_processed"] += 1
        start_total = time.monotonic()
        attempts: list[FallbackAttempt] = []
        effective_lang = lang or "es"

        # ── NIVEL 1: Determinista ────────────────
        level1_start = time.monotonic()
        try:
            compile_result = deterministic_func(text, effective_lang)
            level1_time = (time.monotonic() - level1_start) * 1000

            # Extraer intents del compile_result (Fix B-01).
            # ANTES (bug): getattr(compile_result, "nlu_result", None) devolvía el
            # NLUResult object (no la tupla de intents), causando TypeError al
            # indexar intents[0].score en should_fallback_deterministic.
            # DESPUÉS: extraer correctamente los intents del NLUResult.
            nlu_result = getattr(compile_result, "nlu_result", None)
            if nlu_result is not None and hasattr(nlu_result, "intents"):
                intents = nlu_result.intents
            else:
                intents = getattr(compile_result, "intents", ())

            should_fallback, reason = self._analyzer.should_fallback_deterministic(
                intents or (),
                compile_result,
            )

            attempts.append(FallbackAttempt(
                level=FallbackLevel.DETERMINISTIC,
                success=not should_fallback,
                confidence=float(getattr(compile_result, "confidence", 0) or
                                 getattr(getattr(compile_result, "nlu_result", None), "confidence", 0)),
                result=compile_result,
                reason=reason,
                processing_time_ms=round(level1_time, 2),
            ))

            if not should_fallback:
                self._stats["deterministic_ok"] += 1
                return FallbackResult(
                    success=True,
                    final_level=FallbackLevel.DETERMINISTIC,
                    attempts=attempts,
                    result=compile_result,
                    explanation=getattr(compile_result, "explanation", ""),
                    total_time_ms=round((time.monotonic() - start_total) * 1000, 2),
                )

        except Exception as e:
            attempts.append(FallbackAttempt(
                level=FallbackLevel.DETERMINISTIC,
                success=False,
                confidence=0.0,
                reason=f"Error: {e}",
                processing_time_ms=round((time.monotonic() - level1_start) * 1000, 2),
            ))

        # ── NIVEL 2: Orbital ─────────────────────
        if self.config.allow_orbital_fallback and orbital_func:
            level2_start = time.monotonic()
            try:
                orbital_result = orbital_func(text, {"lang": effective_lang})

                # El resultado orbital tiene intent, confidence, etc.
                orbital_intent = getattr(orbital_result, "intent", "")
                orbital_confidence = getattr(orbital_result, "confidence", 0.0)

                should_fallback, reason = self._analyzer.should_fallback_orbital(
                    orbital_intent,
                    orbital_confidence,
                )

                attempts.append(FallbackAttempt(
                    level=FallbackLevel.ORBITAL,
                    success=not should_fallback,
                    confidence=orbital_confidence,
                    result=orbital_result,
                    reason=reason,
                    processing_time_ms=round((time.monotonic() - level2_start) * 1000, 2),
                ))

                if not should_fallback:
                    self._stats["orbital_fallback"] += 1
                    return FallbackResult(
                        success=True,
                        final_level=FallbackLevel.ORBITAL,
                        attempts=attempts,
                        result=orbital_result,
                        explanation=getattr(orbital_result, "explanation", ""),
                        total_time_ms=round((time.monotonic() - start_total) * 1000, 2),
                    )

            except Exception as e:
                attempts.append(FallbackAttempt(
                    level=FallbackLevel.ORBITAL,
                    success=False,
                    confidence=0.0,
                    reason=f"Error: {e}",
                    processing_time_ms=round((time.monotonic() - level2_start) * 1000, 2),
                ))
        else:
            attempts.append(FallbackAttempt(
                level=FallbackLevel.ORBITAL,
                success=False,
                confidence=0.0,
                reason="Orbital fallback disabled",
                processing_time_ms=0.0,
            ))

        # ── NIVEL 3: AI Generator ────────────────
        if self.config.allow_ai_fallback and ai_func:
            level3_start = time.monotonic()
            try:
                ai_result = ai_func(text, effective_lang)
                ai_validated = getattr(ai_result, "validated", False)
                ai_confidence = 0.5 if ai_validated else 0.0

                attempts.append(FallbackAttempt(
                    level=FallbackLevel.AI_GENERATOR,
                    success=ai_validated,
                    confidence=ai_confidence,
                    result=ai_result,
                    reason="" if ai_validated else FALLBACK_REASONS["ai_generation_failed"],
                    processing_time_ms=round((time.monotonic() - level3_start) * 1000, 2),
                    details={"provider": getattr(ai_result, "provider", "")},
                ))

                if ai_validated:
                    self._stats["ai_fallback"] += 1
                    return FallbackResult(
                        success=True,
                        final_level=FallbackLevel.AI_GENERATOR,
                        attempts=attempts,
                        result=ai_result,
                        explanation=getattr(ai_result, "explanation", ""),
                        total_time_ms=round((time.monotonic() - start_total) * 1000, 2),
                    )

            except Exception as e:
                attempts.append(FallbackAttempt(
                    level=FallbackLevel.AI_GENERATOR,
                    success=False,
                    confidence=0.0,
                    reason=f"Error: {e}",
                    processing_time_ms=round((time.monotonic() - level3_start) * 1000, 2),
                ))
        else:
            attempts.append(FallbackAttempt(
                level=FallbackLevel.AI_GENERATOR,
                success=False,
                confidence=0.0,
                reason="AI fallback disabled or not configured",
                processing_time_ms=0.0,
            ))

        # ── NIVEL 4: Template Fallback ───────────
        self._stats["template_fallback"] += 1
        fallback_msg = get_fallback_message(self.config.fallback_template_name, effective_lang)
        attempts.append(FallbackAttempt(
            level=FallbackLevel.TEMPLATE_FALLBACK,
            success=True,
            confidence=0.0,
            reason="All higher levels failed, using generic fallback",
            processing_time_ms=0.0,
        ))

        return FallbackResult(
            success=True,
            final_level=FallbackLevel.TEMPLATE_FALLBACK,
            attempts=attempts,
            result={
                "fallback_message": fallback_msg,
                "template": self.config.fallback_template_name,
            },
            explanation=fallback_msg,
            total_time_ms=round((time.monotonic() - start_total) * 1000, 2),
        )

    def get_stats(self) -> dict[str, Any]:
        """Retorna estadísticas de uso de la jerarquía de fallback."""
        total = self._stats["total_processed"]
        return {
            **self._stats,
            "pct_deterministic": round(self._stats["deterministic_ok"] / total * 100, 1) if total else 0,
            "pct_fallback": round((total - self._stats["deterministic_ok"]) / total * 100, 1) if total else 0,
        }

    def reset_stats(self) -> None:
        """Reinicia las estadísticas."""
        for key in self._stats:
            self._stats[key] = 0
