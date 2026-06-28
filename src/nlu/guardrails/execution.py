"""
DDE v3 — Guardrails: Limites de Ejecucion
==========================================

Controla limites de ejecucion para workflows generados:
numero de pasos, complejidad, tamano, ciclos infinitos y budget.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from src.nlu.guardrails.result import GuardrailResult, RiskLevel


class ExecutionGuardrails:
    """Limites de ejecucion para workflows generados.

    Controla:
    - Numero maximo de pasos por workflow
    - Complejidad (profundidad de fork/join/loops)
    - Tamano maximo de definicion del workflow (bytes)
    - Ciclo infinito detection
    - Budget de ejecucion (para multi-tenant billing)
    """

    MAX_STEPS: ClassVar[int] = 50
    MAX_DEFINITION_SIZE: ClassVar[int] = 100_000  # 100KB
    MAX_NESTED_DEPTH: ClassVar[int] = 5
    MAX_BUDGET_EXECUTIONS: ClassVar[int] = 1_000  # por tenant/dia
    MAX_FORK_BRANCHES: ClassVar[int] = 10
    MAX_RETRY_ATTEMPTS: ClassVar[int] = 10

    LOOP_LIMIT_PATTERNS: ClassVar[list[str]] = [
        "while true",
        "while 1",
        "loop forever",
        "bucle infinito",
        "para siempre",
        "unlimited",
        "sin limite",
        "no limit",
        "999999",
    ]

    def __init__(self, lang: str = "es"):
        self.lang = lang

    def check_workflow_definition(self, workflow: dict[str, Any]) -> GuardrailResult:
        """Valida la definicion del workflow contra limites de ejecucion.

        Args:
            workflow: Definicion completa del workflow

        Returns:
            GuardrailResult con la decision
        """
        if not workflow:
            return GuardrailResult.block(
                self._msg("Workflow vacio", "Empty workflow"),
                RiskLevel.HIGH,
                {"reason": "empty_workflow"},
            )

        # 1. Tamano de definicion
        try:
            wf_size = len(json.dumps(workflow))
        except (TypeError, ValueError):
            wf_size = len(str(workflow))

        if wf_size > self.MAX_DEFINITION_SIZE:
            return GuardrailResult.block(
                self._msg(
                    f"Workflow demasiado grande ({wf_size} bytes, maximo {self.MAX_DEFINITION_SIZE})",
                    f"Workflow too large ({wf_size} bytes, max {self.MAX_DEFINITION_SIZE})",
                ),
                RiskLevel.MEDIUM,
                {"reason": "workflow_too_large", "size": wf_size, "max": self.MAX_DEFINITION_SIZE},
            )

        # 2. Numero de pasos
        steps = workflow.get("steps", [])
        if len(steps) > self.MAX_STEPS:
            return GuardrailResult.block(
                self._msg(
                    f"Demasiados pasos ({len(steps)}, maximo {self.MAX_STEPS})",
                    f"Too many steps ({len(steps)}, max {self.MAX_STEPS})",
                ),
                RiskLevel.MEDIUM,
                {"reason": "too_many_steps", "steps": len(steps), "max": self.MAX_STEPS},
            )

        # 3. Detectar bucles infinitos
        for step in steps:
            params_str = str(step.get("params", {}))
            for pattern in self.LOOP_LIMIT_PATTERNS:
                if pattern in params_str.lower():
                    return GuardrailResult.block(
                        self._msg(
                            f"Posible bucle infinito detectado en paso {step.get('id', '?')}: '{pattern}'",
                            f"Possible infinite loop detected in step {step.get('id', '?')}: '{pattern}'",
                        ),
                        RiskLevel.HIGH,
                        {"reason": "infinite_loop_detected", "step_id": step.get("id"), "pattern": pattern},
                    )

        # 4. Verificar profundidad de fork/join
        max_depth = self._compute_max_depth(steps)
        if max_depth > self.MAX_NESTED_DEPTH:
            return GuardrailResult.block(
                self._msg(
                    f"Workflow demasiado anidado (profundidad {max_depth}, maximo {self.MAX_NESTED_DEPTH})",
                    f"Workflow too deeply nested (depth {max_depth}, max {self.MAX_NESTED_DEPTH})",
                ),
                RiskLevel.MEDIUM,
                {"reason": "too_deep_nesting", "depth": max_depth, "max": self.MAX_NESTED_DEPTH},
            )

        return GuardrailResult.allow(
            self._msg(
                "Workflow dentro de limites de ejecucion",
                "Workflow within execution limits",
            ),
        )

    def _compute_max_depth(self, steps: list[dict], current_depth: int = 0, visited: set | None = None) -> int:
        """Computa la profundidad maxima de nesting de un workflow."""
        if visited is None:
            visited = set()
        if current_depth > self.MAX_NESTED_DEPTH:
            return current_depth

        max_depth = current_depth
        for step in steps:
            step_id = step.get("id")
            if step_id and step_id in visited:
                continue
            if step_id:
                visited.add(step_id)

            # legítimo: steps dinámicos del guardrail, tipo depende del AST
            sub_steps: Any = step.get("params", {}).get("steps", [])
            if isinstance(sub_steps, list) and sub_steps:
                depth = self._compute_max_depth(sub_steps, current_depth + 1, visited)
                max_depth = max(max_depth, depth)

        return max_depth

    def check_execution_budget(self, tenant_id: str, executions_today: int) -> GuardrailResult:
        """Verifica el budget de ejecuciones para un tenant."""
        if executions_today >= self.MAX_BUDGET_EXECUTIONS:
            return GuardrailResult.block(
                self._msg(
                    f"Limite de ejecuciones diarias alcanzado ({executions_today}/{self.MAX_BUDGET_EXECUTIONS})",
                    f"Daily execution limit reached ({executions_today}/{self.MAX_BUDGET_EXECUTIONS})",
                ),
                RiskLevel.HIGH,
                {"reason": "budget_exceeded", "tenant_id": tenant_id, "executions_today": executions_today},
            )

        return GuardrailResult.allow(
            self._msg(
                f"Budget disponible ({self.MAX_BUDGET_EXECUTIONS - executions_today} ejecuciones restantes)",
                f"Budget available ({self.MAX_BUDGET_EXECUTIONS - executions_today} executions remaining)",
            ),
        )

    def _msg(self, es: str, en: str) -> str:
        return es if self.lang == "es" else en
