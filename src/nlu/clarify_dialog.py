"""
DDE v3 — ClarifyDialog (Etapa 8)

Máquina de estados determinista para hacer preguntas al usuario
cuando falta información obligatoria o hay ambigüedad.

Estados:
  IDLE        → esperando input
  AMBIGUOUS   → dos intenciones empatan, pregunta cuál
  MISSING_SLOT → falta un slot obligatorio
  CONFIRM     → confirma el workflow antes de compilar
  DONE        → todo completo, listo para compilar

Determinista: mismo estado + mismo input → misma transición.
"""
from __future__ import annotations
from src.nlu.entities.base import Slot, IntentMatch, CompileResult


MAX_QUESTIONS = 3


class ClarifyDialog:
    """Máquina de estados para diálogo de clarificación."""

    def __init__(self):
        self._state: str = "IDLE"
        self._question_count: int = 0
        self._history: list[dict[str, object]] = []

    # ── Propiedades ─────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    @property
    def question_count(self) -> int:
        return self._question_count

    # ── Iniciar diálogo ─────────────────────────────────

    def start(
        self,
        intents: tuple[IntentMatch, ...],
        slots: tuple[Slot, ...],
        ambiguous_candidates: tuple[str, ...],
    ) -> tuple[str, str | None]:
        """Inicia o continúa el diálogo.

        Args:
            intents: Intenciones detectadas
            slots: Slots disponibles
            ambiguous_candidates: Candidatos ambiguos

        Returns:
            (pregunta, tipo): Texto de la pregunta y su tipo
            ('', None) si no hay nada que preguntar
        """
        self._history.append({
            "state": self._state,
            "intents": [i.intent for i in intents[:3]],
            "ambiguous": ambiguous_candidates,
            "question_count": self._question_count,
        })

        if self._question_count >= MAX_QUESTIONS:
            return ("", None)

        # 1. Ambigüedad
        if len(ambiguous_candidates) > 1:
            self._state = "AMBIGUOUS"
            self._question_count += 1
            options = " / ".join(ambiguous_candidates[:3])
            return (
                f"¿A cuál te refieres? {options}",
                "ambiguous",
            )

        if not intents:
            return (
                "No entendí tu solicitud. ¿Puedes ser más específico?",
                "unknown",
            )

        # 2. Slots obligatorios faltantes
        missing = [s for s in slots if s.required and not s.filled]
        if missing:
            self._state = "MISSING_SLOT"
            self._question_count += 1
            slot_names_es = {
                "nombre": "nombre del cliente",
                "email_destino": "correo electrónico",
                "email_cliente": "correo del cliente",
                "telefono": "teléfono",
                "url_webhook": "URL del webhook",
                "frecuencia": "frecuencia del schedule",
            }
            slot_name = missing[0].name
            label = slot_names_es.get(slot_name, slot_name)
            return (
                f"¿Cuál es el {label}?",
                "missing_slot",
            )

        # 3. Confirmar
        self._state = "CONFIRM"
        self._question_count += 1
        return (
            "¿Confirmas que quieres crear este workflow?",
            "confirm",
        )

    def process_reply(
        self,
        reply: str,
        intent_name: str | None = None,
    ) -> tuple[str, str | None]:
        """Procesa la respuesta del usuario.

        Args:
            reply: Texto de la respuesta
            intent_name: Si se está resolviendo ambigüedad, la intención elegida

        Returns:
            (siguiente_pregunta, tipo) o ('', None) si terminó
        """
        self._history.append({
            "state": self._state,
            "reply": reply,
            "intent_choice": intent_name,
        })

        if self._state == "AMBIGUOUS" and intent_name:
            self._state = "MISSING_SLOT"
            return self._next_question()

        if self._state == "MISSING_SLOT":
            self._state = "CONFIRM"
            return (
                "¿Confirmas que quieres crear este workflow?",
                "confirm",
            )

        if self._state == "CONFIRM":
            if reply.lower() in ("si", "sí", "yes", "ok", "confirmar", ""):
                self._state = "DONE"
                return (
                    "Workflow listo para compilar.",
                    "done",
                )
            else:
                self._state = "IDLE"
                return (
                    "Ok, cancela la operación. ¿Qué necesitas?",
                    "cancelled",
                )

        return ("", None)

    def _next_question(self) -> tuple[str, str | None]:
        """Genera la siguiente pregunta."""
        return (
            "¿Qué más necesitas especificar?",
            "missing_slot",
        )

    def to_compile_result(self, status: str = "needs_clarification") -> CompileResult:
        """Convierte el estado actual a CompileResult."""
        return CompileResult(
            workflow={},
            explanation="",
            missing_slots=(),
            status=status,
        )

    def reset(self) -> None:
        """Reinicia el diálogo."""
        self._state = "IDLE"
        self._question_count = 0
        self._history = []
