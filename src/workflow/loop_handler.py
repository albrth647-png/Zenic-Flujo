"""
Workflow Determinista — LoopHandler
Maneja bucles (for/while/for each) en workflows.
"""
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class LoopResult:
    """Resultado de la ejecución de un bucle."""

    def __init__(self, iterations: int, outputs: list[dict]):
        self.iterations = iterations
        self.outputs = outputs  # Resultados de cada iteración


class LoopHandler:
    """
    Ejecuta bucles en workflows.
    
    Formato de un step loop:
    
    For Each:
    {
        "id": 3,
        "type": "foreach",
        "collection": "$input.items",  # Variable que contiene la lista
        "item_var": "item",            # Nombre de la variable de iteración
        "steps": [...]                 # Pasos a ejecutar por cada elemento
    }
    
    For (rango numérico):
    {
        "id": 3,
        "type": "for",
        "start": 0,
        "end": 10,
        "step": 1,
        "index_var": "i",
        "steps": [...]
    }
    
    While:
    {
        "id": 3,
        "type": "while",
        "condition": "stock > 0",
        "max_iterations": 100,
        "steps": [...]
    }
    """

    MAX_ITERATIONS_DEFAULT = 1000

    def execute(self, step: dict, context: dict, step_executor) -> LoopResult:
        """
        Ejecuta un bucle según su tipo.
        
        Args:
            step: Definición del step loop
            context: Contexto de ejecución (se modificará con variables de iteración)
            step_executor: StepExecutor para ejecutar los pasos internos
        
        Returns:
            LoopResult con número de iteraciones y outputs
        """
        loop_type = step.get("type", "foreach")
        outputs = []

        if loop_type == "foreach":
            return self._execute_foreach(step, context, step_executor)
        elif loop_type == "for":
            return self._execute_for(step, context, step_executor)
        elif loop_type == "while":
            return self._execute_while(step, context, step_executor)
        else:
            raise ValueError(f"Tipo de bucle no soportado: {loop_type}")

    def _execute_foreach(self, step: dict, context: dict, step_executor) -> LoopResult:
        collection_ref = step.get("collection", "")
        item_var = step.get("item_var", "item")
        index_var = step.get("index_var", "index")
        inner_steps = step.get("steps", [])
        max_iter = step.get("max_iterations", self.MAX_ITERATIONS_DEFAULT)

        from src.utils.helpers import resolve_variables, safe_get
        collection_str = resolve_variables(collection_ref, context)

        # Intentar parsear como JSON si es string
        import json
        collection = collection_str
        if isinstance(collection_str, str):
            # Si el string es igual a la referencia sin resolver, buscar directo en contexto
            if collection_str == f"${{{collection_ref.lstrip('$')}}}":
                path = collection_ref.lstrip("$")
                collection = safe_get(context, path, None)
            else:
                try:
                    collection = json.loads(collection_str)
                except (json.JSONDecodeError, TypeError):
                    # Podría ser un string plano, no una colección
                    pass

        if not isinstance(collection, (list, tuple)):
            # Último recurso: buscar con el path completo
            path = collection_ref.lstrip("$")
            collection = safe_get(context, path) or []

        if not isinstance(collection, (list, tuple)):
            collection = [collection]

        if len(collection) > max_iter:
            logger.warning(f"Colección truncada de {len(collection)} a {max_iter} iteraciones")
            collection = collection[:max_iter]

        outputs = []
        for idx, item in enumerate(collection):
            iter_context = dict(context)
            iter_context[item_var] = item
            iter_context[index_var] = idx

            iteration_results = self._execute_inner_steps(inner_steps, iter_context, step_executor)
            outputs.append({
                "index": idx,
                item_var: item,
                "results": iteration_results,
            })

        logger.info(f"Foreach completado: {len(outputs)} iteraciones")
        return LoopResult(iterations=len(outputs), outputs=outputs)

    def _execute_for(self, step: dict, context: dict, step_executor) -> LoopResult:
        start = step.get("start", 0)
        end = step.get("end", 10)
        step_size = step.get("step", 1)
        index_var = step.get("index_var", "i")
        inner_steps = step.get("steps", [])
        max_iter = step.get("max_iterations", self.MAX_ITERATIONS_DEFAULT)

        count = 0
        outputs = []
        i = start

        while (step_size > 0 and i < end) or (step_size < 0 and i > end):
            if count >= max_iter:
                logger.warning(f"Bucle for terminado por límite de {max_iter} iteraciones")
                break

            iter_context = dict(context)
            iter_context[index_var] = i

            iteration_results = self._execute_inner_steps(inner_steps, iter_context, step_executor)
            outputs.append({
                "index": count,
                "value": i,
                "results": iteration_results,
            })

            i += step_size
            count += 1

        logger.info(f"Bucle for completado: {count} iteraciones")
        return LoopResult(iterations=count, outputs=outputs)

    def _execute_while(self, step: dict, context: dict, step_executor) -> LoopResult:
        condition = step.get("condition", "True")
        inner_steps = step.get("steps", [])
        max_iter = step.get("max_iterations", self.MAX_ITERATIONS_DEFAULT)

        from src.workflow.condition_evaluator import ConditionEvaluator
        evaluator = ConditionEvaluator()

        count = 0
        outputs = []

        while evaluator.evaluate(condition, context):
            if count >= max_iter:
                logger.warning(f"Bucle while terminado por límite de {max_iter} iteraciones")
                break

            iteration_results = self._execute_inner_steps(inner_steps, context, step_executor)
            outputs.append({
                "index": count,
                "results": iteration_results,
            })
            count += 1

        logger.info(f"Bucle while completado: {count} iteraciones")
        return LoopResult(iterations=count, outputs=outputs)

    def _execute_inner_steps(self, steps: list[dict], context: dict, step_executor) -> list[dict]:
        """Ejecuta los pasos internos de una iteración."""
        results = []
        for inner_step in steps:
            result = step_executor.execute(inner_step, context)
            results.append({
                "step_id": inner_step.get("id"),
                "status": result.status,
                "output": result.output_data,
                "error": result.error_message,
            })
            if result.status == "failed":
                break
        return results
