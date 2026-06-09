"""
Workflow Determinista — WorkflowEngine
Motor principal que ejecuta workflows paso a paso manejando su ciclo de vida completo.
"""
import threading
import time
from src.workflow.step_executor import StepExecutor, StepResult
from src.workflow.condition_evaluator import ConditionEvaluator
from src.workflow.branch_handler import BranchHandler
from src.workflow.loop_handler import LoopHandler
from src.workflow.error_handler import ErrorHandler
from src.workflow.repository import WorkflowRepository, WorkflowDefinition
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# Profundidad máxima de anidamiento de subworkflows para evitar recursión infinita
MAX_SUBWORKFLOW_DEPTH = 10


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
    Motor de ejecución de workflows (Singleton).
    
    Ciclo de vida de un workflow:
    CREADO → ACTIVO → EN EJECUCIÓN → COMPLETADO
                                → FALLIDO
             → PAUSADO → ACTIVO
             → ARCHIVADO
    """

    _instance: "WorkflowEngine | None" = None
    _lock = threading.RLock()

    def __new__(cls) -> "WorkflowEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        with self._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True
            self._repository = WorkflowRepository()
            self._step_executor = StepExecutor()
            self._condition_evaluator = ConditionEvaluator()
            self._branch_handler = BranchHandler()
            self._loop_handler = LoopHandler()
            self._error_handler = ErrorHandler()
            self._tools: dict[str, object] = {}

    # ── Registro de herramientas ──────────────────────────────

    def register_tool(self, tool_name: str, tool_instance: object) -> None:
        """Registra una herramienta de negocio en el motor.
        
        tool_instance debe ser un objeto con métodos llamables que coincidan
        con las acciones definidas en los pasos del workflow.
        """
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

        # Subworkflow step
        if step_type == "subworkflow":
            return self._execute_subworkflow(step, context)

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

    def _execute_subworkflow(self, step: dict, context: dict) -> StepResult:
        """
        Ejecuta un paso de tipo subworkflow.

        Formato del paso:
        {
            "type": "subworkflow",
            "workflow_id": 2,
            "input_mapping": {"nombre": "$input.nombre"},
            "output_mapping": {"resultado": "steps_output.1.message"}
        }

        Args:
            step: Definición del paso subworkflow
            context: Contexto de ejecución del padre

        Returns:
            StepResult con el resultado del subworkflow
        """
        start_time = time.time()
        workflow_id = step.get("workflow_id")
        input_mapping = step.get("input_mapping", {})
        output_mapping = step.get("output_mapping", {})
        parent_workflow_id = context.get("workflow", {}).get("id")
        from src.utils.helpers import resolve_variables

        # 1. Validar workflow_id
        if not workflow_id:
            return StepResult(
                status="failed",
                error_message="Subworkflow sin workflow_id",
                duration_ms=self._elapsed(start_time),
            )

        # 2. Detectar recursión
        if workflow_id == parent_workflow_id:
            return StepResult(
                status="failed",
                error_message=f"Subworkflow recursivo detectado: workflow {workflow_id} se llama a sí mismo",
                duration_ms=self._elapsed(start_time),
            )

        # 3. Verificar profundidad máxima
        depth = context.get("_subworkflow_depth", 0)
        if depth >= MAX_SUBWORKFLOW_DEPTH:
            return StepResult(
                status="failed",
                error_message=f"Profundidad máxima de subworkflows ({MAX_SUBWORKFLOW_DEPTH}) excedida",
                duration_ms=self._elapsed(start_time),
            )

        # 4. Cargar el workflow hijo
        child_wf = self._repository.get(workflow_id)
        if not child_wf:
            return StepResult(
                status="failed",
                error_message=f"Workflow hijo no encontrado: {workflow_id}",
                duration_ms=self._elapsed(start_time),
            )

        if child_wf.status != "active":
            return StepResult(
                status="failed",
                error_message=f"Workflow hijo '{child_wf.name}' no está activo (estado: {child_wf.status})",
                duration_ms=self._elapsed(start_time),
            )

        # 5. Resolver input_mapping desde el contexto del padre
        child_input = {}
        for target_key, source_expr in input_mapping.items():
            resolved = resolve_variables(source_expr, context)
            child_input[target_key] = resolved

        # 6. Ejecutar el workflow hijo con contexto incrementado
        child_context = {
            **context,
            "_subworkflow_depth": depth + 1,
            "input": child_input,
            "_parent_execution": {
                "workflow_id": parent_workflow_id,
                "step_id": step.get("id"),
            },
        }

        try:
            child_result = self.execute(workflow_id, child_input)

            elapsed = self._elapsed(start_time)

            # 7. Mapear outputs si hay output_mapping
            mapped_output = {}
            if child_result.step_results:
                # Construir steps_output del hijo para resolver expresiones
                child_steps_output = {}
                for i, sr in enumerate(child_result.step_results):
                    step_id = str(sr.get("step_id", i + 1))
                    child_steps_output[step_id] = sr.get("output", {})

                child_context["steps_output"] = child_steps_output

                for target_key, source_expr in output_mapping.items():
                    resolved = resolve_variables(source_expr, child_context)
                    mapped_output[target_key] = resolved

                if child_result.status == "failed":
                    return StepResult(
                        status="failed",
                        error_message=f"Subworkflow '{child_wf.name}' falló: {child_result.error_message}",
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
            elapsed = self._elapsed(start_time)
            logger.error(f"Error ejecutando subworkflow {workflow_id}: {e}")
            return StepResult(
                status="failed",
                error_message=f"Error en subworkflow: {e}",
                duration_ms=elapsed,
            )

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

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

    # ── Reset para testing ──────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (útil para tests)."""
        cls._instance = None

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
