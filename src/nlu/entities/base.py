"""
DDE v3 — Contracto de Datos Inmutable

Todas las estructuras son frozen dataclasses → determinismo garantizado.
Misma entrada → siempre misma salida.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    """Token individual con su lema."""

    raw: str  # "clientes"
    lemma: str  # "cliente"
    pos: int  # posición en la frase


@dataclass(frozen=True)
class Entity:
    """Entidad extraída con tipo y valor normalizado."""

    type: str  # 'email' | 'phone' | 'date' | 'time' | 'number' | 'money' | 'cron' | 'qty' | 'product' | 'condition'
    value: object  # valor normalizado (ej: email string, cron "0 9 * * 1")
    raw: str  # texto original ("juan@x.com")
    span: tuple  # (inicio, fin) en el texto original
    score: float  # confianza 0.0-1.0


@dataclass(frozen=True)
class IntentMatch:
    """Intención detectada con score y evidencia."""

    intent: str  # 'registro_cliente'
    score: float  # 0.0-1.0 normalizado
    evidence: list  # keywords/lemas que la activaron


@dataclass(frozen=True)
class Slot:
    """Slot de una intención (parámetro requerido u opcional)."""

    name: str  # 'email_destino'
    required: bool
    filled: bool
    value: object  # None si falta
    source: str  # 'entity' | 'default' | 'user_reply' | 'context'


@dataclass(frozen=True)
class NLUResult:
    """Resultado completo del pipeline NLU."""

    text: str
    lang: str
    tokens: tuple[Token, ...]
    entities: tuple[Entity, ...]
    intents: tuple[IntentMatch, ...]
    slots: tuple[Slot, ...]
    confidence: float
    trace: tuple[str, ...]  # log explicable de cada etapa


@dataclass(frozen=True)
class StepFragment:
    """Fragmento de un paso de workflow (unidad mínima reutilizable)."""

    kind: str  # 'trigger' | 'step' | 'condition' | 'loop'
    intent_tags: tuple[str, ...]
    produces: dict  # trigger o step a inyectar
    requires_slots: tuple[str, ...]


@dataclass(frozen=True)
class CompileResult:
    """Resultado del compilador de workflows."""

    workflow: dict  # WorkflowDefinition listo
    explanation: str  # en lenguaje natural
    missing_slots: tuple[str, ...]  # si hay → clarificación necesaria
    status: str  # 'ready' | 'needs_clarification' | 'ambiguous' | 'unknown'
