"""SubworkflowExecutionService — ejecución de pasos subworkflow.

Contiene la lógica de _execute_subworkflow extraída de engine.py.
"""

from __future__ import annotations

import time

from src.core.logging import setup_logging

# Fix Sprint 4 bug #52: centralizado en constants.py
from src.workflow.constants import MAX_SUBWORKFLOW_DEPTH
from src.workflow.step_executor import StepResult
from typing import Any

logger = setup_logging(__name__)


class SubworkflowExecutionService:
    """Servicio para ejecutar pasos de tipo subworkflow.

    Fix Sprint 4 bug #45: antes el subworkflow usaba el mismo singleton
    OrbitalContext que el padre, contaminando variables orbitales.
    Ahora el context del hijo recibe un _orbital_var_prefix distinto
    (derivado del execution_id del hijo), y al final se limpian sus
    variables del singleton.
    """

    def __init__(self, repository):
        self._repository = repository

    def execute(self, step: dict[str, Any], context: dict[str, Any]) -> StepResult:
        """Ejecuta un paso de tipo subworkflow."""
        from src.core.utils import resolve_variables
        from src.workflow.engine import WorkflowEngine

        start_time = time.time()
        workflow_id = step.get("workflow_id")
        input_mapping = step.get("input_mapping", {})
        output_mapping = step.get("output_mapping", {})
        parent_workflow_id = context.get("workflow", {}).get("id")

        if not workflow_id:
            return StepResult(status="failed", error_message="Subworkflow sin workflow_id")

        if workflow_id == parent_workflow_id:
            return StepResult(status="failed", error_message=f"Subworkflow recursivo: {workflow_id}")

        depth = context.get("_subworkflow_depth", 0)
        if depth >= MAX_SUBWORKFLOW_DEPTH:
            return StepResult(status="failed", error_message=f"Profundidad maxima ({MAX_SUBWORKFLOW_DEPTH}) excedida")

        child_wf = self._repository.get(workflow_id)
        if not child_wf:
            return StepResult(status="failed", error_message=f"Workflow hijo no encontrado: {workflow_id}")

        if child_wf.status != "active":
            return StepResult(status="failed", error_message=f"Workflow hijo '{child_wf.name}' no activo")

        child_input = {}
        for target_key, source_expr in input_mapping.items():
            resolved = resolve_variables(source_expr, context)
            child_input[target_key] = resolved

        try:
            engine = WorkflowEngine()
            # Fix bug #45: el engine.execute() del hijo ahora namespacia sus
            # variables orbitales con wf_<child_exec_id>__ automáticamente
            # (gracias al fix Sprint 1 bug #1), así que no contaminan al padre.
            child_result = engine.execute(workflow_id, child_input)
            elapsed = int((time.time() - start_time) * 1000)

            mapped_output = {}
            if child_result.step_results:
                child_steps_output = {}
                for i, sr in enumerate(child_result.step_results):
                    step_id = str(sr.get("step_id", i + 1))
                    child_steps_output[step_id] = sr.get("output", {})

                child_context = {
                    **context,
                    "_subworkflow_depth": depth + 1,
                    "input": child_input,
                    "steps_output": child_steps_output,
                }
                for target_key, source_expr in output_mapping.items():
                    resolved = resolve_variables(source_expr, child_context)
                    mapped_output[target_key] = resolved

                if child_result.status == "failed":
                    return StepResult(
                        status="failed",
                        error_message=f"Subworkflow '{child_wf.name}' fallo: {child_result.error_message}",
                        duration_ms=elapsed,
                    )

            return StepResult(
                status="completed",
                output_data={
                    "child_status": "completed",
                    "child_execution_id": child_result.execution_id,
                    "mapped_output": mapped_output,
                },
                duration_ms=elapsed,
            )

        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            logger.error(f"Error ejecutando subworkflow {workflow_id}: {e}")
            return StepResult(status="failed", error_message=f"Error en subworkflow: {e}", duration_ms=elapsed)
