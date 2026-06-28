"""
DDE v3 — Guardrails: Resultados y Tipos
=========================================

Define los tipos base del sistema de guardrails:
RiskLevel, GuardrailAction, GuardrailResult, y CompositeGuardrailResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardrailAction(StrEnum):
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class GuardrailResult:
    """Resultado de una evaluacion de guardrail."""

    passed: bool
    risk: RiskLevel
    action: GuardrailAction
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def allow(cls, message: str = "", details: dict[str, Any] | None = None) -> GuardrailResult:
        return cls(
            passed=True,
            risk=RiskLevel.LOW,
            action=GuardrailAction.ALLOW,
            message=message or "Paso todas las verificaciones",
            details=details or {},
        )

    @classmethod
    def warn(cls, message: str, risk: RiskLevel = RiskLevel.MEDIUM, details: dict[str, Any] | None = None) -> GuardrailResult:
        return cls(
            passed=True,
            risk=risk,
            action=GuardrailAction.WARN,
            message=message,
            details=details or {},
        )

    @classmethod
    def block(cls, message: str, risk: RiskLevel = RiskLevel.HIGH, details: dict[str, Any] | None = None) -> GuardrailResult:
        return cls(
            passed=False,
            risk=risk,
            action=GuardrailAction.BLOCK,
            message=message,
            details=details or {},
        )


@dataclass
class CompositeGuardrailResult:
    """Resultado agregado de todas las capas de guardrail."""

    overall_passed: bool
    overall_action: GuardrailAction
    checks: dict[str, GuardrailResult]
    risk: RiskLevel = RiskLevel.LOW

    @property
    def blocked(self) -> bool:
        return self.overall_action == GuardrailAction.BLOCK

    @property
    def warnings(self) -> list[GuardrailResult]:
        return [r for r in self.checks.values() if r.action == GuardrailAction.WARN and r.passed]

    @property
    def blocks(self) -> list[GuardrailResult]:
        return [r for r in self.checks.values() if r.action == GuardrailAction.BLOCK]
