"""
Workflow Determinista — WorkflowEngine
Motor principal que ejecuta workflows paso a paso manejando su ciclo de vida completo.
"""
import time
from typing import Any

from src.workflow.step_executor import StepExecutor, StepResult
from src.workflow.condition_evaluator import ConditionEvaluator
from src.workflow.branch_handler import BranchHandler
from src.workflow.loop_handler import LoopHandler
from src.workflow.error_handler import ErrorHandler
from src.workflow.repository import WorkflowRepository, WorkflowDefinition
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class ExecutionResult:
    """Resultado completo de una ejecución de workflow."""

    def __init__(self, execution_id: int, workflow_id: int, status: str,
                 duration_ms: int, step_results: list[dict] | None = None,
                 error_message: str | None = None):
        self.execution_id = execution_id
        self.workflow_id = workflow_id
        self.status = status
        self.duration_ms = duration_ms
        self.step_results = step_results or []
        self.error_message = error_message

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "step_results": self.step_results,
            "error_message": self.error_message,
        }


class WorkflowEngine:
    """
    Motor de ejecución de workflows.
    
    Ciclo de vida de un workflow:
    CREADO → ACTIVO → EN EJECUCIÓN → COMPLETADO
                                → FALLIDO
             → PAUSADO → ACTIVO
             → ARCHIVADO
    """

    def __init__(self):
        self._repository = WorkflowRepository()
        self._step_executor = StepExecutor()
        self._condition_evaluator = ConditionEvaluator()
        self._branch_handler = BranchHandler()
        self._loop_handler = LoopHandler()
        self._error_handler = ErrorHandler()
        self._tools: dict[str, Any] = {}

    # ── Registro de herramientas ──────────────────────────────

    def register_tool(self, tool_name: str, tool_instance: Any) -> None:
        """Registra una herramienta de negocio en el motor."""
        self._tools[tool_name] = tool_instance
        self._step_executor.register_tool(tool_name, tool_instance)
        logger.info(f"Tool registrada: {tool_name}")

    def get_registered_tools(self) -> list[str]:
        """Retorna la lista de herramientas registradas."""
        return list(self._tools.keys())

    # ── Ejecución ────────────────────────────────────────────

    def execute(self, workflow_id: int, trigger_data: dict | None = None) -> ExecutionResult:
        """
        Ejecuta un workflow completo.
        
        Args:
            workflow_id: ID de la definición del workflow
            trigger_data: Datos que dispararon el workflow
        
        Returns:
            ExecutionResult con el resultado completo
        """
        start_time = time.time()

        # 1. Cargar definición
        definition = self._repository.get(workflow_id)
        if not definition:
            raise ValueError(f"Workflow no encontrado: {workflow_id}")

        if definition.status != "active":
            raise ValueError(f"Workflow '{definition.name}' no está activo (estado: {definition.status})")

        logger.info(f"Ejecutando workflow: {definition.name} (ID: {workflow_id})")

        # 2. Crear ejecución
        execution = self._repository.create_execution(workflow_id, trigger_data)

        # 3. Preparar contexto
        context = {
            "input": trigger_data or {},
            "workflow": {
                "id": definition.id,
                "name": definition.name,
            },
            "output": {},
            "steps_output": {},
            "settings": self._load_settings(),
        }

        # 4. Ejecutar pasos
        step_results = []
        final_status = "completed"
        error_message = None

        try:
            for step in definition.steps:
                step_result = self._execute_step(step, context)

                step_results.append({
                    "step_id": step.get("id"),
                    "tool": step.get("tool"),
                    "action": step.get("action"),
                    "status": step_result.status,
                    "output": step_result.output_data,
                    "duration_ms": step_result.duration_ms,
                    "error": step_result.error_message,
                })

                # Guardar output en contexto
                step_id = str(step.get("id", 0))
                context["steps_output"][step_id] = step_result.output_data

                # Guardar log en base de datos
                self._repository.save_step_log(
                    execution_id=execution.id,
                    step_id=step.get("id", 0),
                    tool=step.get("tool", ""),
                    action=step.get("action", ""),
                    input_data=step.get("params", {}),
                    output_data=step_result.output_data,
                    status=step_result.status,
                    duration_ms=step_result.duration_ms,
                    error_message=step_result.error_message,
                )

                # Si un paso falla, el workflow falla
                if step_result.status == "failed":
                    final_status = "failed"
                    error_message = step_result.error_message
                    logger.error(f"Workflow {workflow_id} falló en paso {step.get('id')}: {error_message}")
                    break

        except Exception as e:
            final_status = "failed"
            error_message = str(e)
            logger.error(f"Workflow {workflow_id} falló con excepción: {e}")

        # 5. Finalizar ejecución
        duration = int((time.time() - start_time) * 1000)
        self._repository.complete_execution(execution.id, duration, error_message)

        # 6. Emitir evento de finalización
        self._emit_completion_event(definition, final_status, execution.id, duration)

        logger.info(f"Workflow {workflow_id} {final_status} en {duration}ms")

        return ExecutionResult(
            execution_id=execution.id,
            workflow_id=workflow_id,
            status=final_status,
            duration_ms=duration,
            step_results=step_results,
            error_message=error_message,
        )

    def _execute_step(self, step: dict, context: dict) -> StepResult:
        """Ejecuta un paso individual, manejando branches y loops."""
        step_type = step.get("type", "action")

        # Verificar condición del paso
        condition = step.get("condition")
        if condition:
            try:
                if not self._condition_evaluator.evaluate(condition, context):
                    logger.info(f"Paso {step.get('id')} saltado por condición: {condition}")
                    return StepResult(status="skipped", output_data={"skipped": True})
            except ValueError as e:
                logger.warning(f"Error evaluando condición del paso {step.get('id')}: {e}")

        # Branch step
        if step_type == "branch":
            branch_result = self._branch_handler.evaluate(step, context)
            # Ejecutar pasos de la rama seleccionada
            branch_outputs = []
            for branch_step in branch_result.steps:
                result = self._execute_step(branch_step, context)
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

        # Loop step
        if step_type in ("foreach", "for", "while"):
            loop_result = self._loop_handler.execute(step, context, self._step_executor)
            return StepResult(
                status="completed",
                output_data={
                    "iterations": loop_result.iterations,
                    "outputs": loop_result.outputs,
                },
            )

        # Action step normal
        try:
            result = self._step_executor.execute(step, context)
            return result
        except Exception as e:
            # Intentar manejar el error con ErrorHandler
            error_result = self._error_handler.handle(step, e, context, self._step_executor)
            if error_result.status == "recovered":
                return StepResult(
                    status="completed",
                    output_data=error_result.output_data or {},
                    duration_ms=0,
                )
            return StepResult(
                status="failed",
                error_message=error_result.error_message,
            )

    def _load_settings(self) -> dict:
        """Carga todas las settings del sistema en un dict."""
        from src.data.database_manager import DatabaseManager
        db = DatabaseManager()
        rows = db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    def _emit_completion_event(self, definition: WorkflowDefinition, status: str,
                                execution_id: int, duration_ms: int) -> None:
        """Emite evento de finalización del workflow."""
        from src.events.bus import EventBus
        event_bus = EventBus()
        event_type = "workflow.completed" if status == "completed" else "workflow.failed"
        event_bus.publish(event_type, {
            "workflow_id": definition.id,
            "execution_id": execution_id,
            "duration_ms": duration_ms,
            "status": status,
        })

    # ── Gestión de ciclo de vida ────────────────────────────

    def pause(self, workflow_id: int) -> bool:
        """Pausa un workflow (no responde a triggers)."""
        definition = self._repository.get(workflow_id)
        if not definition:
            return False

        self._repository.update(workflow_id, {"status": "paused"})
        self._remove_subscriptions(workflow_id)
        logger.info(f"Workflow {workflow_id} pausado")
        return True

    def resume(self, workflow_id: int) -> bool:
        """Reanuda un workflow pausado."""
        definition = self._repository.get(workflow_id)
        if not definition:
            return False

        self._repository.update(workflow_id, {"status": "active"})
        self._restore_subscriptions(definition)
        logger.info(f"Workflow {workflow_id} reanudado")
        return True

    def archive(self, workflow_id: int) -> bool:
        """Archiva un workflow (desactivación permanente)."""
        definition = self._repository.get(workflow_id)
        if not definition:
            return False

        self._repository.update(workflow_id, {"status": "archived"})
        self._remove_subscriptions(workflow_id)
        logger.info(f"Workflow {workflow_id} archivado")
        return True

    def get_status(self, workflow_id: int) -> dict:
        """Retorna el estado actual de un workflow + última ejecución."""
        definition = self._repository.get(workflow_id)
        if not definition:
            return {"error": "Workflow no encontrado"}

        executions = self._repository.list_executions(workflow_id, limit=1)
        last_execution = executions[0].to_dict() if executions else None

        return {
            "workflow": definition.to_dict(),
            "last_execution": last_execution,
            "is_active": definition.status == "active",
            "is_paused": definition.status == "paused",
        }

    def _remove_subscriptions(self, workflow_id: int) -> None:
        """Elimina las suscripciones a eventos de un workflow."""
        from src.events.bus import EventBus
        event_bus = EventBus()
        event_bus.unsubscribe_all(workflow_id)

    def _restore_subscriptions(self, definition: WorkflowDefinition) -> None:
        """Restaura las suscripciones a eventos de un workflow."""
        from src.events.bus import EventBus
        event_bus = EventBus()
        if definition.trigger_type == "event":
            event_config = definition.trigger_config
            event_type = event_config.get("event", "")
            if event_type:
                event_bus.subscribe(event_type, definition.id)
