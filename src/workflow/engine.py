"""
ORBITAL — WorkflowEngine Orbital (Motor Unico — OVC Compartido)
================================================================

WorkflowEngine con retroalimentacion circular usando OVC compartido via OrbitalContext.

MEJORA vs version anterior:
- Ahora usa OrbitalContext → OVC compartido con StepExecutor, EventBus, etc.
- Lo que un paso retroalimenta, el bus lo ve, y viceversa
- Estado orbital unificado: una sola fuente de verdad

Compatibilidad: mantiene la misma API que el WorkflowEngine original.
"""

from __future__ import annotations

import hashlib
import threading
import time

from src.orbital.context import OrbitalContext
from src.orbital.models import (
    DEFAULT_THRESHOLD,
    RETROFEEDBACK_DAMPING,
    TWO_PI,
    OrbitalResult,
)
from src.utils.logger import setup_logging
from src.workflow.branch_handler import BranchHandler
from src.workflow.condition_evaluator import ConditionEvaluator
from src.workflow.fork_handler import ForkHandler, JoinHandler
from src.workflow.loop_handler import LoopHandler
from src.workflow.repository import WorkflowDefinition, WorkflowRepository
from src.workflow.step_executor import StepExecutor, StepResult

logger = setup_logging(__name__)

MAX_SUBWORKFLOW_DEPTH = 10


class ExecutionResult:
    """Resultado completo de una ejecucion de workflow (compatible + enriquecido)."""

    def __init__(
        self,
        execution_id: int,
        workflow_id: int,
        status: str,
        duration_ms: int,
        step_results: list[dict] | None = None,
        error_message: str | None = None,
        orbital_espectro: dict | None = None,
        orbital_variables: int = 0,
        orbital_resonance: float = 0.0,
    ):
        self.execution_id = execution_id
        self.workflow_id = workflow_id
        self.status = status
        self.duration_ms = duration_ms
        self.step_results = step_results or []
        self.error_message = error_message
        self.orbital_espectro = orbital_espectro
        self.orbital_variables = orbital_variables
        self.orbital_resonance = orbital_resonance

    def to_dict(self) -> dict:
        d = {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "step_results": self.step_results,
            "error_message": self.error_message,
        }
        if self.orbital_espectro:
            d["orbital"] = {
                "espectro": self.orbital_espectro,
                "variables": self.orbital_variables,
                "resonance": self.orbital_resonance,
            }
        return d


class WorkflowEngine:
    """
    Motor de Workflows Orbital — Motor unico con OVC compartido via OrbitalContext.

    Usa OrbitalContext para compartir el OVC con StepExecutor, EventBus,
    ConditionEvaluator, etc. Lo que un componente retroalimenta, todos lo ven.

    Singleton como el original.
    """

    _instance: WorkflowEngine | None = None
    _lock = threading.RLock()

    def __new__(cls) -> WorkflowEngine:
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
            from src.workflow.error_handler import ErrorHandler

            self._error_handler = ErrorHandler()
            self._fork_handler = ForkHandler(self._step_executor)
            self._join_handler = JoinHandler()
            self._tools: dict[str, object] = {}
            # ── ORBITAL COMPARTIDO ───────────────────
            self._ctx = OrbitalContext()
            self._orbital_results: list[OrbitalResult] = []

    # ── Registro de herramientas ────────────────────────────

    def register_tool(self, tool_name: str, tool_instance: object) -> None:
        """Registra una herramienta de negocio en el motor."""
        self._tools[tool_name] = tool_instance
        self._step_executor.register_tool(tool_name, tool_instance)
        logger.info(f"Tool registrada: {tool_name}")

    def get_registered_tools(self) -> list[str]:
        """Retorna la lista de herramientas registradas."""
        return list(self._tools.keys())

    # ── Ejecucion ORBITAL ───────────────────────────────────

    def execute(self, workflow_id: int, trigger_data: dict | None = None) -> ExecutionResult:
        """Ejecuta un workflow completo en modo orbital (OVC compartido)."""
        start_time = time.time()

        # 1. Cargar definicion
        definition = self._repository.get(workflow_id)
        if not definition:
            raise ValueError(f"Workflow no encontrado: {workflow_id}")

        if definition.status != "active":
            raise ValueError(f"Workflow '{definition.name}' no esta activo (estado: {definition.status})")

        logger.info(f"OrbitalWorkflowEngine: Ejecutando workflow '{definition.name}' (ID: {workflow_id})")

        # 2. Crear ejecucion
        execution = self._repository.create_execution(workflow_id, trigger_data)

        # 3. Usar OrbitalContext compartido
        orbital_engine = self._ctx.engine

        # 4. Preparar contexto (Sprint 4: continue_on_error, _execution_id)
        # continue_on_error se detecta a nivel de step individual.
        # Si algún step tiene la flag, el motor no detiene la ejecución
        # cuando ese step falla (el ErrorHandler maneja el skip).
        continue_on_error = False

        context = {
            "input": trigger_data or {},
            "workflow": {
                "id": definition.id,
                "name": definition.name,
                "continue_on_error": continue_on_error,
            },
            "output": {},
            "steps_output": {},
            "settings": self._load_settings(),
            "_execution_id": execution.id,
        }

        # 5. Convertir trigger_data a variables orbitales (OVC compartido)
        if trigger_data:
            self._inject_trigger_as_orbital(trigger_data)

        # 6. Convertir pasos del workflow a variables orbitales (OVC compartido)
        self._inject_steps_as_orbital(definition.steps)

        # 7. Ejecutar pasos con logica orbital
        step_results = []
        final_status = "completed"
        error_message = None

        try:
            for step in definition.steps:
                step_result = self._execute_step(step, context, orbital_engine)

                step_results.append(
                    {
                        "step_id": step.get("id"),
                        "tool": step.get("tool"),
                        "action": step.get("action"),
                        "status": step_result.status,
                        "output": step_result.output_data,
                        "duration_ms": step_result.duration_ms,
                        "error": step_result.error_message,
                        "orbital_theta": getattr(step_result, "orbital_theta", 0.0),
                        "orbital_tension": getattr(step_result, "orbital_tension", 0.0),
                    }
                )

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

                # Sprint 4: continue_on_error — no romper el flujo
                if step_result.status == "failed":
                    error_message = step_result.error_message
                    logger.error(f"Workflow {workflow_id} fallo en paso {step.get('id')}: {error_message}")
                    if not continue_on_error:
                        final_status = "failed"
                        break
                    logger.info(f"continue_on_error=True: continuando despues de paso {step.get('id')}")

                # Sprint 4: skipped por continue_on_error no es fallo
                if step_result.status == "skipped" and step_result.output_data.get("reason") == "continue_on_error":
                    logger.info(f"Paso {step.get('id')} skipped (continue_on_error)")

        except Exception as e:
            final_status = "failed"
            error_message = str(e)
            logger.error(f"Workflow {workflow_id} fallo con excepcion: {e}")

        # 8. Ejecutar tick orbital completo (RCC + COD + Espectro)
        orbital_result = None
        orbital_espectro = None
        orbital_resonance = 0.0

        try:
            step_var_names = list(self._ctx.ovc.get_variable_names())
            if len(step_var_names) >= 2:
                orbital_engine.create_cycle("workflow_cycle", step_var_names[:10], threshold=DEFAULT_THRESHOLD)

            orbital_result = orbital_engine.run_tick(dt=1.0, retrofeed_damping=RETROFEEDBACK_DAMPING)
            self._orbital_results.append(orbital_result)

            if orbital_result.espectro:
                orbital_espectro = orbital_result.espectro.to_dict()

            if orbital_result.rcc_results:
                orbital_resonance = sum(r.resonance_strength for r in orbital_result.rcc_results) / len(
                    orbital_result.rcc_results
                )

            logger.info(
                f"OrbitalWorkflowEngine: Workflow {workflow_id} completado — "
                f"TOR={len(orbital_result.tor_results)} "
                f"RCC={len(orbital_result.rcc_results)} "
                f"Espectro={len(orbital_result.espectro.modes) if orbital_result.espectro else 0} modos "
                f"Resonancia={orbital_resonance:.4f}"
            )
        except Exception as e:
            logger.warning(f"OrbitalWorkflowEngine: Error orbital (no bloqueante): {e}")

        # 9. Finalizar ejecucion
        duration = int((time.time() - start_time) * 1000)
        self._repository.complete_execution(execution.id, duration, error_message)

        # 10. Emitir evento de finalizacion via OrbitalBus
        self._emit_completion_event(definition, final_status, execution.id, duration)

        logger.info(f"Workflow {workflow_id} {final_status} en {duration}ms")

        return ExecutionResult(
            execution_id=execution.id,
            workflow_id=workflow_id,
            status=final_status,
            duration_ms=duration,
            step_results=step_results,
            error_message=error_message,
            orbital_espectro=orbital_espectro,
            orbital_variables=self._ctx.ovc.variable_count,
            orbital_resonance=orbital_resonance,
        )

    def _execute_step(self, step: dict, context: dict, orbital_engine) -> StepResult:
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
                result = self._execute_step(branch_step, context, orbital_engine)
                branch_outputs.append(
                    {
                        "step_id": branch_step.get("id"),
                        "status": result.status,
                        "output": result.output_data,
                    }
                )
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
            # Unir resultados automáticamente
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
                return StepResult(
                    status="completed",
                    output_data={"joined": fork_result_data},
                )
            return StepResult(
                status="completed",
                output_data={"joined": context.get("output", {})},
            )

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
        """Ejecuta un paso de tipo subworkflow."""
        start_time = time.time()
        workflow_id = step.get("workflow_id")
        input_mapping = step.get("input_mapping", {})
        output_mapping = step.get("output_mapping", {})
        parent_workflow_id = context.get("workflow", {}).get("id")
        from src.utils.helpers import resolve_variables

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

        child_context = {
            **context,
            "_subworkflow_depth": depth + 1,
            "input": child_input,
        }

        try:
            child_result = self.execute(workflow_id, child_input)
            elapsed = int((time.time() - start_time) * 1000)

            mapped_output = {}
            if child_result.step_results:
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

    # ── Inyeccion orbital (OVC compartido) ───────────────────

    def _inject_trigger_as_orbital(self, trigger_data: dict) -> None:
        """Convierte los datos del trigger en variables orbitales (OVC compartido)."""
        for key, value in trigger_data.items():
            if isinstance(value, (int, float)):
                try:
                    self._ctx.ovc.create_variable(
                        name=f"input_{key}",
                        theta=abs(value) % TWO_PI if value != 0 else 0.0,
                        amplitude=abs(value) if value != 0 else 1.0,
                        velocity=0.05,
                        orbit_group="trigger_data",
                        metadata={"source": "trigger", "original_key": key},
                    )
                except ValueError:
                    var = self._ctx.ovc.get_variable(f"input_{key}")
                    if var:
                        var.amplitude = abs(value) if value != 0 else 1.0

    def _inject_steps_as_orbital(self, steps: list[dict]) -> None:
        """Convierte los pasos del workflow en variables orbitales (OVC compartido)."""
        for step in steps:
            step_id = step.get("id", 0)
            tool = step.get("tool", "")
            action = step.get("action", "")
            var_name = f"step_{step_id}_{tool}"

            try:
                hash_val = int(hashlib.md5(f"{tool}.{action}".encode()).hexdigest()[:8], 16)
                theta = (hash_val % 1000) / 1000.0 * TWO_PI
                amplitude = 1.0
                if step.get("condition"):
                    amplitude += 0.5
                if step.get("type") in ("branch", "loop"):
                    amplitude += 1.0

                self._ctx.ovc.create_variable(
                    name=var_name,
                    theta=theta,
                    amplitude=min(amplitude, 5.0),
                    velocity=0.1,
                    orbit_group="workflow_steps",
                    metadata={"step_id": step_id, "tool": tool, "action": action},
                )
            except ValueError:
                pass  # Variable ya existe

    # ── Gestion de ciclo de vida ────────────────────────────

    def pause(self, workflow_id: int) -> bool:
        definition = self._repository.get(workflow_id)
        if not definition:
            return False
        self._repository.update(workflow_id, {"status": "paused"})
        self._remove_subscriptions(workflow_id)
        logger.info(f"Workflow {workflow_id} pausado")
        return True

    def resume(self, workflow_id: int) -> bool:
        definition = self._repository.get(workflow_id)
        if not definition:
            return False
        self._repository.update(workflow_id, {"status": "active"})
        self._restore_subscriptions(definition)
        logger.info(f"Workflow {workflow_id} reanudado")
        return True

    def archive(self, workflow_id: int) -> bool:
        definition = self._repository.get(workflow_id)
        if not definition:
            return False
        self._repository.update(workflow_id, {"status": "archived"})
        self._remove_subscriptions(workflow_id)
        logger.info(f"Workflow {workflow_id} archivado")
        return True

    def get_status(self, workflow_id: int) -> dict:
        definition = self._repository.get(workflow_id)
        if not definition:
            return {"error": "Workflow no encontrado"}

        executions = self._repository.list_executions(workflow_id, limit=1)
        last_execution = executions[0].to_dict() if executions else None

        status = {
            "workflow": definition.to_dict(),
            "last_execution": last_execution,
            "is_active": definition.status == "active",
            "is_paused": definition.status == "paused",
            "orbital_mode": True,
            "shared_context": True,
        }

        if self._orbital_results:
            last_orbital = self._orbital_results[-1]
            status["orbital_espectro"] = last_orbital.espectro.to_dict()

        return status

    # ── Helpers ─────────────────────────────────────────────

    def _load_settings(self) -> dict:
        from src.data.database_manager import DatabaseManager

        db = DatabaseManager()
        rows = db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    def _emit_completion_event(
        self, definition: WorkflowDefinition, status: str, execution_id: int, duration_ms: int
    ) -> None:
        from src.events.bus import EventBus

        event_bus = EventBus()
        event_type = "workflow.completed" if status == "completed" else "workflow.failed"
        event_bus.publish(
            event_type,
            {
                "workflow_id": definition.id,
                "execution_id": execution_id,
                "duration_ms": duration_ms,
                "status": status,
            },
        )

    def _remove_subscriptions(self, workflow_id: int) -> None:
        from src.events.bus import EventBus

        event_bus = EventBus()
        event_bus.unsubscribe_all(workflow_id)

    def _restore_subscriptions(self, definition: WorkflowDefinition) -> None:
        from src.events.bus import EventBus

        event_bus = EventBus()
        if definition.trigger_type == "event":
            event_config = definition.trigger_config
            event_type = event_config.get("event", "")
            if event_type:
                event_bus.subscribe(event_type, definition.id)

    # ── Consultas orbitales ─────────────────────────────────

    def get_orbital_results(self, limit: int = 10) -> list[dict]:
        return [r.to_dict() for r in self._orbital_results[-limit:]]

    def get_orbital_snapshot(self) -> dict:
        return {
            "orbital_mode": True,
            "shared_context": True,
            "ovc_variables": self._ctx.ovc.variable_count,
            "orbital_results_count": len(self._orbital_results),
            "tools_registered": self.get_registered_tools(),
        }

    def orbital_report(self) -> str:
        lines = ["=" * 60]
        lines.append("ORBITAL WORKFLOW ENGINE — Reporte (OVC Compartido)")
        lines.append("=" * 60)
        lines.append("  Modo: ORBITAL (OVC compartido)")
        lines.append(f"  OVC variables: {self._ctx.ovc.variable_count}")
        lines.append(f"  Tools registradas: {len(self.get_registered_tools())}")
        lines.append(f"  Ejecuciones orbitales: {len(self._orbital_results)}")
        if self._orbital_results:
            last = self._orbital_results[-1]
            lines.append(f"  Ultimo tick: {last.tick}")
            lines.append(f"  Variables orbitales: {len(last.variables)}")
            lines.append(f"  TOR pairs: {len(last.tor_results)}")
            lines.append(f"  RCC resultados: {len(last.rcc_results)}")
        lines.append("=" * 60)
        return "\n".join(lines)

    # ── Ejecucion Asincrona (Sprint 7-8) ───────────────────────

    def execute_async(self, workflow_id: int, trigger_data: dict | None = None, priority: int = 0) -> dict:
        """
        Encola un workflow para ejecución asíncrona via WorkQueue.

        Args:
            workflow_id: ID del workflow a ejecutar
            trigger_data: Datos de entrada
            priority: Prioridad (mayor = más prioritario)

        Returns:
            dict con status del encolamiento

        Raises:
            ValueError: Si el workflow no existe o no está activo
        """
        definition = self._repository.get(workflow_id)
        if not definition:
            raise ValueError(f"Workflow no encontrado: {workflow_id}")
        if definition.status != "active":
            raise ValueError(f"Workflow '{definition.name}' no está activo (estado: {definition.status})")

        from src.events.work_queue import WorkQueue

        queue = WorkQueue()
        item = queue.enqueue(
            workflow_id=workflow_id,
            trigger_data=trigger_data,
            priority=priority,
        )

        logger.info(f"Workflow {workflow_id} encolado asíncronamente (#queue{item.id}, prioridad {priority})")
        return {
            "status": "queued",
            "queue_id": item.id,
            "workflow_id": workflow_id,
            "priority": priority,
        }

    # ── Reset para testing ──────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None
