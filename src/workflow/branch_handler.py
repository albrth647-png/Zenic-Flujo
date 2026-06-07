"""
Workflow Determinista — BranchHandler
Maneja bifurcaciones condicionales (if/else/switch) en workflows.
"""
from typing import Any

from src.workflow.condition_evaluator import ConditionEvaluator
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class BranchResult:
    """Resultado de la evaluación de una bifurcación."""

    def __init__(self, branch_taken: str, steps: list[dict]):
        self.branch_taken = branch_taken  # Nombre de la rama ejecutada
        self.steps = steps  # Pasos a ejecutar en esta rama


class BranchHandler:
    """
    Evalúa condiciones y determina qué rama del workflow seguir.
    
    Formato de un step branch:
    {
        "id": 2,
        "type": "branch",
        "branches": [
            {
                "name": "stock_bajo",
                "condition": "stock < 10",
                "steps": [...]  # Pasos para esta rama
            },
            {
                "name": "default",
                "condition": "True",  # Rama por defecto
                "steps": [...]
            }
        ]
    }
    """

    def __init__(self):
        self._evaluator = ConditionEvaluator()

    def evaluate(self, step: dict, context: dict) -> BranchResult:
        """
        Evalúa las condiciones de un step branch y retorna la rama a ejecutar.
        
        Args:
            step: Step de tipo branch con sus ramas
            context: Contexto de ejecución
        
        Returns:
            BranchResult con la rama seleccionada y sus pasos
        
        Raises:
            ValueError: Si ninguna condición se cumple y no hay rama default
        """
        branches = step.get("branches", [])
        if not branches:
            raise ValueError("Branch step sin ramas definidas")

        logger.info(f"Evaluando branch con {len(branches)} ramas")

        for branch in branches:
            condition = branch.get("condition", "True")
            try:
                result = self._evaluator.evaluate(condition, context)
                if result:
                    branch_name = branch.get("name", "unnamed")
                    logger.info(f"Rama seleccionada: {branch_name} (condición: {condition})")
                    return BranchResult(
                        branch_taken=branch_name,
                        steps=branch.get("steps", []),
                    )
            except ValueError as e:
                logger.warning(f"Error evaluando condición en rama '{branch.get('name', '?')}': {e}")
                continue

        raise ValueError(
            "Ninguna condición de branch se cumplió y no hay rama default. "
            "Asegúrate de incluir una rama con condition='True' como default."
        )

    def evaluate_switch(self, expression: str, cases: list[dict], context: dict) -> BranchResult:
        """
        Evalúa una expresión switch (equivalente a switch/case).
        
        cases: [
            {"value": "nuevo", "steps": [...]},
            {"value": "vip", "steps": [...]},
            {"default": True, "steps": [...]}
        ]
        """
        from src.utils.helpers import resolve_variables
        resolved_expr = resolve_variables(expression, context)

        logger.info(f"Evaluando switch: {expression} = {resolved_expr}")

        default_case = None
        for case in cases:
            if "default" in case and case["default"]:
                default_case = case
                continue  # Check other cases first, default is fallback
            case_value = resolve_variables(str(case.get("value", "")), context)
            if resolved_expr == case_value:
                return BranchResult(
                    branch_taken=f"case_{case_value}",
                    steps=case.get("steps", []),
                )

        # No case matched — use default if available
        if default_case:
            return BranchResult(branch_taken="default", steps=default_case.get("steps", []))

        raise ValueError(f"Switch: ningún case coincide con '{resolved_expr}' y no hay default")
