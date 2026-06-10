"""
ORBITAL — BranchHandler Orbital (OVC Compartido)
==================================================

BranchHandler con divergencia orbital usando OVC compartido via OrbitalContext.

MEJORA vs version anterior:
- Ahora usa OrbitalContext → OVC compartido con todos los demas componentes
- Las decisiones de branch retroalimentan al mismo OVC que los pasos del workflow

Compatibilidad: mantiene la misma API que BranchHandler.
"""

from __future__ import annotations

import hashlib

from src.orbital.models import TWO_PI
from src.orbital.context import OrbitalContext
from src.workflow.condition_evaluator import ConditionEvaluator
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class BranchResult:
    """Resultado de la evaluacion de una bifurcacion."""

    def __init__(self, branch_taken: str, steps: list[dict]):
        self.branch_taken = branch_taken
        self.steps = steps


class BranchHandler:
    """
    OrbitalDivergence — Bifurcaciones por divergencia orbital (OVC compartido).

    Usa OrbitalContext para compartir el OVC con todos los componentes.
    La rama con mayor alineacion orbital (TOR mas positivo) con el contexto
    es la que se ejecuta.
    """

    def __init__(self):
        self._evaluator = ConditionEvaluator()
        self._ctx = OrbitalContext()

    def evaluate(self, step: dict, context: dict) -> BranchResult:
        """Evalua las condiciones de un step branch y retorna la rama a ejecutar."""
        branches = step.get("branches", [])
        if not branches:
            raise ValueError("Branch step sin ramas definidas")

        logger.info(f"OrbitalDivergence: Evaluando branch con {len(branches)} ramas")

        # 1. Crear variable orbital para el contexto
        context_var_name = f"branch_ctx_{step.get('id', 0)}"
        self._ensure_context_variable(context_var_name, context)

        # 2. Crear variables orbitales para cada rama y calcular TOR
        branch_scores = []
        for branch in branches:
            branch_name = branch.get("name", "unnamed")
            condition = branch.get("condition", "True")

            branch_var_name = f"branch_{step.get('id', 0)}_{branch_name}"
            self._ensure_branch_variable(branch_var_name, branch)

            tor_value = 0.0
            try:
                tor_result = self._ctx.tor.calculate(branch_var_name, context_var_name)
                tor_value = tor_result.tor_value
            except KeyError:
                pass

            branch_scores.append({
                "branch": branch,
                "name": branch_name,
                "tor_value": tor_value,
                "condition": condition,
            })

        branch_scores.sort(key=lambda x: x["tor_value"], reverse=True)
        best = branch_scores[0] if branch_scores else None

        # 3. Priorizar evaluacion textual de condiciones (preciso)
        for branch in branches:
            branch_name = branch.get("name", "unnamed")
            condition = branch.get("condition", "True")

            if condition == "True" or condition is True:
                continue

            try:
                result = self._evaluator.evaluate(condition, context)
                if result:
                    logger.info(
                        f"OrbitalDivergence: Rama '{branch_name}' seleccionada "
                        f"(condicion: {condition})"
                    )
                    branch_var = self._ctx.ovc.get_variable(f"branch_{step.get('id', 0)}_{branch_name}")
                    if branch_var:
                        branch_var.advance(dt=1.0)
                    return BranchResult(
                        branch_taken=branch_name,
                        steps=branch.get("steps", []),
                    )
            except ValueError as e:
                logger.warning(f"Error evaluando condicion en rama '{branch_name}': {e}")
                continue

        # 4. Fallback orbital: seleccionar por TOR
        if best["tor_value"] > 0.1:
            logger.info(
                f"OrbitalDivergence: Rama '{best['name']}' seleccionada por resonancia "
                f"(TOR={best['tor_value']:.4f})"
            )
            selected_var = self._ctx.ovc.get_variable(f"branch_{step.get('id', 0)}_{best['name']}")
            if selected_var:
                selected_var.advance(dt=1.0)
            return BranchResult(
                branch_taken=best["name"],
                steps=best["branch"].get("steps", []),
            )

        # 5. Ultimo recurso: buscar rama default
        for score in branch_scores:
            condition = score["condition"]
            if condition == "True" or condition is True:
                logger.info(f"OrbitalDivergence: Rama '{score['name']}' seleccionada (default)")
                return BranchResult(
                    branch_taken=score["name"],
                    steps=score["branch"].get("steps", []),
                )

            try:
                result = self._evaluator.evaluate(condition, context)
                if result:
                    branch_var = self._ctx.ovc.get_variable(f"branch_{step.get('id', 0)}_{score['name']}")
                    if branch_var:
                        branch_var.advance(dt=1.0)
                    return BranchResult(
                        branch_taken=score["name"],
                        steps=score["branch"].get("steps", []),
                    )
            except ValueError as e:
                logger.warning(f"Error evaluando condicion en rama '{score['name']}': {e}")
                continue

        raise ValueError(
            "Ninguna condicion de branch se cumplio y no hay rama default. "
            "Asegurate de incluir una rama con condition='True' como default."
        )

    def evaluate_switch(self, expression: str, cases: list[dict], context: dict) -> BranchResult:
        """Evalua una expresion switch con divergencia orbital."""
        from src.utils.helpers import resolve_variables
        resolved_expr = resolve_variables(expression, context)

        logger.info(f"OrbitalDivergence: Evaluando switch: {expression} = {resolved_expr}")

        expr_var_name = f"switch_{hashlib.md5(str(resolved_expr).encode()).hexdigest()[:8]}"
        self._ensure_switch_variable(expr_var_name, str(resolved_expr))

        default_case = None
        best_case = None
        best_tor = -float("inf")

        for case in cases:
            if "default" in case and case["default"]:
                default_case = case
                continue

            case_value = resolve_variables(str(case.get("value", "")), context)
            case_var_name = f"case_{hashlib.md5(str(case_value).encode()).hexdigest()[:8]}"
            self._ensure_switch_variable(case_var_name, str(case_value))

            try:
                tor_result = self._ctx.tor.calculate(expr_var_name, case_var_name)
                if tor_result.tor_value > best_tor:
                    best_tor = tor_result.tor_value
                    best_case = case
            except KeyError:
                pass

            if resolved_expr == case_value:
                return BranchResult(
                    branch_taken=f"case_{case_value}",
                    steps=case.get("steps", []),
                )

        if best_case and best_tor > 0.1:
            return BranchResult(
                branch_taken=f"case_orbital_{best_tor:.2f}",
                steps=best_case.get("steps", []),
            )

        if default_case:
            return BranchResult(branch_taken="default", steps=default_case.get("steps", []))

        raise ValueError(f"Switch: ningun case coincide con '{resolved_expr}' y no hay default")

    # ── Helpers orbitales (OVC compartido) ───────────────────

    def _ensure_context_variable(self, var_name: str, context: dict) -> None:
        if self._ctx.ovc.get_variable(var_name) is None:
            hash_val = int(hashlib.md5(str(context).encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.05,
                orbit_group="branch_context",
                metadata={"source": "branch_handler"},
            )

    def _ensure_branch_variable(self, var_name: str, branch: dict) -> None:
        if self._ctx.ovc.get_variable(var_name) is None:
            condition = branch.get("condition", "True")
            hash_val = int(hashlib.md5(condition.encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.5,
                velocity=0.1,
                orbit_group="branch_options",
                metadata={"source": "branch_handler", "condition": condition},
            )

    def _ensure_switch_variable(self, var_name: str, value: str) -> None:
        if self._ctx.ovc.get_variable(var_name) is None:
            hash_val = int(hashlib.md5(value.encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.08,
                orbit_group="switch_values",
                metadata={"source": "switch", "value": value},
            )
