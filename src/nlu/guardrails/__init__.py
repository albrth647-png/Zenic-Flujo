"""
DDE v3 — Guardrails de IA (Fase 3)
====================================

Sistema de guardrails para seguridad y calidad en generacion de workflows.

Tres capas de guardrails componibles:
1. ContentGuardrails   — Filtra contenido peligroso, prompt injection, SQLi
2. ExecutionGuardrails — Limites de budget, pasos, complejidad, ciclos
3. PIIGuardrails       — Detecta y protege datos sensibles (emails, phones, IDs)

Cada guardrail retorna un GuardrailResult con:
- passed: bool
- risk: Literal["low", "medium", "high", "critical"]
- action: Literal["allow", "warn", "block"]
- message: str (explicacion en ES/EN)
- details: dict (evidencia del bloqueo)

Todas las capas siguen el principio de default-deny para contenido
sensible y default-allow para contenido seguro confirmado.
"""

from __future__ import annotations

from src.nlu.guardrails.content import ContentGuardrails
from src.nlu.guardrails.execution import ExecutionGuardrails
from src.nlu.guardrails.manager import GuardrailManager
from src.nlu.guardrails.pii import PIIGuardrails
from src.nlu.guardrails.result import (
    CompositeGuardrailResult,
    GuardrailAction,
    GuardrailResult,
    RiskLevel,
)

__all__ = [
    "CompositeGuardrailResult",
    "ContentGuardrails",
    "ExecutionGuardrails",
    "GuardrailAction",
    "GuardrailManager",
    "GuardrailResult",
    "PIIGuardrails",
    "RiskLevel",
]
