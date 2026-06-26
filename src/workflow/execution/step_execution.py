"""StepExecutionService — maneja la ejecución de un paso individual.

Extraído de WorkflowEngine._execute_step() para mantener
engine.py esbelto (~300 líneas).
"""

from __future__ import annotations

from src.core.logging import setup_logging
from src.workflow.execution.subworkflow import SubworkflowExecutionService
from src.workflow.step_executor import StepResult

logger = setup_logging(__name__)


class StepExecutionService:
    """Servicio que ejecuta un paso delegando a handlers especializados.

    Recibe los handlers por inyección de dependencias desde el engine.
    """

    def __init__(self, branch_handler, loop_handler, fork_handler, join_handler,
                 step_executor, condition_evaluator, error_handler,
                 repository, orbital_engine, ctx):
        self._branch_handler = branch_handler
        self._loop_handler = loop_handler
        self._fork_handler = fork_handler
        self._join_handler = join_handler
        self._step_executor = step_executor
        self._condition_evaluator = condition_evaluator
        self._error_handler = error_handler
        self._repository = repository
        self._orbital_engine = orbital_engine
        self._ctx = ctx

    def execute_step(self, step: dict, context: dict) -> StepResult:
        """Ejecuta un paso individual, manejando branches, loops y errores orbitalmente."""
        step_type = step.get("type", "action")

        # Verificar condicion del paso por resonancia
        condition = step.get("condition")
        if condition:
            try:
                if not self._condition_evaluator.evaluate(condition, context):
                    logger.info(f"Paso {step.get('id')} saltado por condicion: {condition}")
                    return StepResult(status="skipped", output_data={"skipped": True})
            except ValueError as e:
                logger.warning(f"Error evaluando condicion del paso {step.get('id')}: {e}")

        # Branch step → OrbitalDivergence
        if step_type == "branch":
            branch_result = self._branch_handler.evaluate(step, context)
            branch_outputs = []
            for branch_step in branch_result.steps:
                result = self.execute_step(branch_step, context)
                branch_outputs.append({
                    "step_id": branch_step.get("id"),
                    "status": result.status,
                    "output": result.output_data,
                })
            return StepResult(
                status="completed",
                output_data={
                    "branch_taken": branch_result.branch_taken,
                    "steps": branch_outputs,
                },
            )

        # Loop step → OrbitalConvergence
        if step_type in ("foreach", "for", "while"):
            loop_result = self._loop_handler.execute(step, context, self._step_executor)
            return StepResult(
                status="completed",
                output_data={
                    "iterations": loop_result.iterations,
                    "outputs": loop_result.outputs,
                    "converged": getattr(loop_result, "converged", False),
                    "convergence_delta": getattr(loop_result, "convergence_delta", 0.0),
                },
            )

        # Parallel / Fork step (DAG)
        if step_type == "parallel":
            fork_result = self._fork_handler.execute_parallel(step, context)
            join_result = self._join_handler.join(fork_result, step, context)
            return StepResult(
                status=fork_result.status if fork_result.status == "completed" else "failed",
                output_data={
                    "parallel": fork_result.branches,
                    "merged": join_result.merged_output,
                    "merge_strategy": fork_result.merge_strategy,
                },
                duration_ms=fork_result.duration_ms,
                error_message=fork_result.error_message,
            )

        # Fork step (mismos steps, diferentes datos)
        if step_type == "fork":
            fork_result = self._fork_handler.execute_fork(step, context)
            join_result = self._join_handler.join(fork_result, step, context)
            return StepResult(
                status="completed" if fork_result.status == "completed" else "failed",
                output_data={
                    "fork": fork_result.branches,
                    "merged": join_result.merged_output,
                    "merge_strategy": fork_result.merge_strategy,
                },
                duration_ms=fork_result.duration_ms,
                error_message=fork_result.error_message,
            )

        # Join step (explícito, para después de parallel/fork)
        if step_type == "join":
            fork_result_data = context.get(f"_join_{step.get('id', 0)}")
            if fork_result_data:
                return StepResult(status="completed", output_data={"joined": fork_result_data})
            return StepResult(status="completed", output_data={"joined": context.get("output", {})})

        # Subworkflow step
        if step_type == "subworkflow":
            return self._execute_subworkflow(step, context)

        # Action step normal → StepExecutor orbital
        try:
            result = self._step_executor.execute(step, context)
            return result
        except Exception as e:
            error_result = self._error_handler.handle(step, e, context, self._step_executor)
            if error_result.status == "recovered":
                return StepResult(status="completed", output_data=error_result.output_data or {}, duration_ms=0)
            return StepResult(status="failed", error_message=error_result.error_message)

    def _execute_subworkflow(self, step: dict, context: dict) -> StepResult:
        """Delega la ejecución de subworkflow a SubworkflowExecutionService."""
        subworkflow_service = SubworkflowExecutionService(self._repository)
        return subworkflow_service.execute(step, context)
