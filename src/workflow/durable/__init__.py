"""
Durable Workflow Execution — Motor de Ejecucion Duradera
==========================================================

NOTA: Este archivo es el __init__.py del subpackage durable/ que contiene
DurableExecutor. La lógica de eventos, checkpoints, heartbeats y cleanup
está separada en: events.py, checkpoints.py, heartbeat.py, cleanup.py.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.workflow.durable.checkpoints import (
    create_snapshot,
    get_state,
    load_latest_checkpoint,
    save_checkpoint,
)
from src.workflow.durable.cleanup import cleanup_old_checkpoints, cleanup_old_events
from src.workflow.durable.events import append_event, get_event_log, replay_events
from src.workflow.durable.heartbeat import check_heartbeats, send_heartbeat
from src.workflow.durable_models import (
    DURABLE_ENABLED,
    SNAPSHOT_INTERVAL_STEPS,
    EventType,
    WorkflowState,
)

logger = setup_logging(__name__)


class DurableExecutor:
    """
    Motor de ejecucion duradera que envuelve WorkflowEngine.

    Delegación:
    - Event sourcing: events.py
    - Checkpoints: checkpoints.py
    - Heartbeats: heartbeat.py
    - Cleanup: cleanup.py
    """

    _instance: DurableExecutor | None = None
    _lock = threading.RLock()

    def __new__(cls) -> DurableExecutor:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        with self._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._ensure_tables()
            self._worker_id: str = uuid.uuid4().hex[:12]
            self._step_counter: dict[int, int] = {}
            logger.info(f"DurableExecutor inicializado (worker_id={self._worker_id})")

    def _ensure_tables(self) -> None:
        """Crea las tablas necesarias para ejecución duradera."""
        conn = self._db.get_connection()
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS workflow_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id    INTEGER NOT NULL,
                event_type      TEXT NOT NULL,
                step_id         INTEGER,
                data            TEXT NOT NULL DEFAULT '{}',
                timestamp       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_events_execution ON workflow_events(execution_id);
            CREATE INDEX IF NOT EXISTS idx_workflow_events_type ON workflow_events(event_type);
            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id    INTEGER NOT NULL,
                step_index      INTEGER NOT NULL,
                state           TEXT NOT NULL,
                timestamp       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_execution ON workflow_checkpoints(execution_id);
            CREATE TABLE IF NOT EXISTS workflow_heartbeats (
                execution_id    INTEGER NOT NULL,
                step_id         INTEGER NOT NULL,
                worker_id       TEXT NOT NULL,
                last_heartbeat  TEXT NOT NULL,
                progress        REAL DEFAULT 0.0,
                PRIMARY KEY (execution_id, step_id, worker_id)
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_heartbeats_execution ON workflow_heartbeats(execution_id);
            -- Fix Sprint 4 bug #48: telemetry_config table eliminada.
            -- Antes se creaba aquí pero nunca se usaba en este módulo (leftover).
            -- Si se necesita telemetría config, usar src/observability/telemetry.py.
        """)
        conn.commit()
        logger.debug("Tablas de durable execution verificadas/creadas")

    # ── Event Sourcing ───────────────────────────────────────

    def get_event_log(self, execution_id: int):
        return get_event_log(self._db, execution_id)

    # ── Checkpointing ────────────────────────────────────────

    def create_snapshot(self, execution_id: int) -> int:
        return create_snapshot(self._db, execution_id)

    def get_state(self, execution_id: int) -> WorkflowState | None:
        return get_state(self._db, execution_id)

    # ── Ejecucion duradera ───────────────────────────────────

    def start_workflow(self, workflow_id: int, trigger_data: dict[str, Any] | None = None) -> int:
        if not DURABLE_ENABLED:
            return self._start_non_durable(workflow_id, trigger_data)

        from src.workflow.repository import WorkflowRepository
        repo = WorkflowRepository()
        definition = repo.get(workflow_id)
        if not definition:
            raise ValueError(f"Workflow no encontrado: {workflow_id}")
        if definition.status != "active":
            raise ValueError(f"Workflow '{definition.name}' no esta activo (estado: {definition.status})")

        execution = repo.create_execution(workflow_id, trigger_data)
        state = WorkflowState(
            workflow_id=workflow_id, execution_id=execution.id, current_step_index=0,
            variables={"input": trigger_data or {}}, step_results=[], status="running",
            trigger_data=trigger_data or {},
        )
        append_event(self._db, execution.id, EventType.WORKFLOW_STARTED, data={
            "workflow_id": workflow_id, "trigger_data": trigger_data or {}, "variables": state.variables,
        })
        save_checkpoint(self._db, state)
        self._step_counter[execution.id] = 0
        logger.info(f"DurableWorkflow: Workflow {workflow_id} iniciado (execution_id={execution.id})")
        self._execute_durable(state, definition.steps)
        return execution.id

    def _execute_durable(self, state: WorkflowState, steps: list[dict[str, Any]]) -> WorkflowState:
        from src.workflow.engine import WorkflowEngine
        from src.workflow.step_executor import StepResult

        engine = WorkflowEngine()
        context = self._build_context(state)

        while state.current_step_index < len(steps):
            step = steps[state.current_step_index]
            step_id = step.get("id", state.current_step_index)
            append_event(self._db, state.execution_id, EventType.STEP_STARTED, step_id=step_id,
                         data={"tool": step.get("tool"), "action": step.get("action")})
            send_heartbeat(self._db, state.execution_id, step_id, self._worker_id, 0.0)
            try:
                step_result: StepResult = engine._execute_step(step, context)
                result_data = {
                    "step_id": step_id, "tool": step.get("tool", ""), "action": step.get("action", ""),
                    "status": step_result.status, "output": step_result.output_data,
                    "duration_ms": step_result.duration_ms,
                }
                self._complete_step(state, step_id, result_data)
                context["steps_output"][str(step_id)] = step_result.output_data

                if step_result.status == "failed" and not context.get("workflow", {}).get("continue_on_error", False):
                    state.status = "failed"
                    state.error_message = step_result.error_message
                    append_event(self._db, state.execution_id, EventType.WORKFLOW_COMPLETED,
                                 data={"final_status": "failed", "error": step_result.error_message})
                    break
            except Exception as e:
                error_msg = str(e)
                self._fail_step(state, step_id, error_msg)
                append_event(self._db, state.execution_id, EventType.WORKFLOW_COMPLETED,
                             data={"final_status": "failed", "error": error_msg})
                break

            exec_id = state.execution_id
            self._step_counter[exec_id] = self._step_counter.get(exec_id, 0) + 1
            if self._step_counter[exec_id] % SNAPSHOT_INTERVAL_STEPS == 0:
                self.create_snapshot(state.execution_id)

        if state.current_step_index >= len(steps) and state.status == "running":
            state.status = "completed"
            append_event(self._db, state.execution_id, EventType.WORKFLOW_COMPLETED,
                         data={"final_status": "completed"})
        save_checkpoint(self._db, state)
        self._complete_durable_execution(state)
        logger.info(f"DurableWorkflow: Workflow {state.workflow_id} finalizado "
                    f"(execution_id={state.execution_id}, status={state.status})")
        return state

    def execute_step(self, execution_id: int, step: dict[str, Any]) -> dict[str, Any]:
        state = self.get_state(execution_id)
        if not state:
            raise ValueError(f"Ejecucion no encontrada: {execution_id}")
        from src.workflow.engine import WorkflowEngine
        from src.workflow.step_executor import StepResult
        step_id = step.get("id", 0)
        context = self._build_context(state)
        append_event(self._db, execution_id, EventType.STEP_STARTED, step_id=step_id,
                     data={"tool": step.get("tool"), "action": step.get("action")})
        try:
            engine = WorkflowEngine()
            step_result: StepResult = engine._execute_step(step, context)
            result_data = {
                "step_id": step_id, "tool": step.get("tool", ""), "action": step.get("action", ""),
                "status": step_result.status, "output": step_result.output_data, "duration_ms": step_result.duration_ms,
            }
            self._complete_step(state, step_id, result_data)
            return result_data
        except Exception as e:
            self._fail_step(state, step_id, str(e))
            return {"step_id": step_id, "status": "failed", "error": str(e)}

    # ── Gestión de pasos ─────────────────────────────────────

    def _complete_step(self, state: WorkflowState, step_id: int, result: dict[str, Any]) -> None:
        append_event(self._db, state.execution_id, EventType.STEP_COMPLETED, step_id=step_id, data=result)
        state.step_results.append(result)
        state.current_step_index = max(state.current_step_index, step_id + 1)
        save_checkpoint(self._db, state)

    def _fail_step(self, state: WorkflowState, step_id: int, error: str) -> None:
        append_event(self._db, state.execution_id, EventType.STEP_FAILED, step_id=step_id, data={"error": error})
        state.status = "failed"
        state.error_message = error
        save_checkpoint(self._db, state)

    # ── Heartbeats ───────────────────────────────────────────

    def send_heartbeat(self, execution_id: int, step_id: int, progress: float = 0.0) -> None:
        send_heartbeat(self._db, execution_id, step_id, self._worker_id, progress)

    def check_heartbeats(self) -> list[dict[str, Any]]:
        return check_heartbeats(self._db)

    # ── Recuperacion ─────────────────────────────────────────

    def recover_pending(self) -> list[dict[str, Any]]:
        from src.workflow.durable_models import HEARTBEAT_TIMEOUT_SECONDS

        if not DURABLE_ENABLED:
            logger.info("recover_pending: durabilidad deshabilitada, nada que recuperar")
            return []
        running_executions = self._db.fetchall(
            "SELECT we.id, we.workflow_id, we.started_at FROM workflow_executions we "
            "WHERE we.status = 'running' ORDER BY we.started_at ASC")
        recovered = []
        timeout_cutoff = datetime.now(UTC).timestamp() - HEARTBEAT_TIMEOUT_SECONDS
        for exec_row in running_executions:
            execution_id = exec_row["id"]
            workflow_id = exec_row["workflow_id"]
            hb_row = self._db.fetchone(
                "SELECT MAX(last_heartbeat) as latest_heartbeat FROM workflow_heartbeats WHERE execution_id = ?",
                (execution_id,))
            is_hung = True
            if hb_row and hb_row["latest_heartbeat"]:
                try:
                    hb_time = datetime.fromisoformat(hb_row["latest_heartbeat"]).timestamp()
                    if hb_time >= timeout_cutoff:
                        is_hung = False
                except (ValueError, TypeError):
                    pass
            if not is_hung:
                continue
            state = self.get_state(execution_id)
            if not state:
                logger.warning(f"recover_pending: sin checkpoint para execution_id={execution_id}")
                continue
            state.status = "recovering"
            save_checkpoint(self._db, state)
            recovered.append({
                "execution_id": execution_id, "workflow_id": workflow_id,
                "current_step_index": state.current_step_index, "status": "recovering",
                "trigger_data": state.trigger_data,
            })
            logger.info(f"recover_pending: execution_id={execution_id} marcada para recuperacion "
                        f"(step_index={state.current_step_index})")
        if recovered:
            logger.info(f"recover_pending: {len(recovered)} ejecucion(es) recuperada(s)")
        return recovered

    # ── Helpers ──────────────────────────────────────────────

    def _start_non_durable(self, workflow_id: int, trigger_data: dict[str, Any] | None = None) -> int:
        from src.workflow.engine import WorkflowEngine
        engine = WorkflowEngine()
        result = engine.execute(workflow_id, trigger_data)
        return result.execution_id

    def _build_context(self, state: WorkflowState) -> dict[str, Any]:
        context = {
            "input": state.trigger_data, "workflow": {"id": state.workflow_id, "continue_on_error": False},
            "output": {}, "steps_output": {}, "settings": {}, "_execution_id": state.execution_id,
        }
        for result in state.step_results:
            step_id = str(result.get("step_id", 0))
            context["steps_output"][step_id] = result.get("output", {})
        return context

    def _complete_durable_execution(self, state: WorkflowState) -> None:
        duration_ms = sum(result.get("duration_ms", 0) for result in state.step_results)
        self._db.execute(
            "UPDATE workflow_executions SET status = ?, completed_at = ?, duration_ms = ?, error_message = ? WHERE id = ?",
            (state.status, datetime.now(UTC).isoformat(), duration_ms, state.error_message, state.execution_id))
        self._db.commit()

    # ── Limpieza ─────────────────────────────────────────────

    def cleanup_old_events(self, execution_id: int, keep_last: int = 100) -> int:
        return cleanup_old_events(self._db, execution_id, keep_last)

    def cleanup_old_checkpoints(self, execution_id: int, keep_last: int = 5) -> int:
        return cleanup_old_checkpoints(self._db, execution_id, keep_last)

    @classmethod
    def _reset(cls) -> None:
        cls._instance = None


__all__ = [
    "DurableExecutor",
    "append_event",
    "check_heartbeats",
    "cleanup_old_checkpoints",
    "cleanup_old_events",
    "create_snapshot",
    "get_event_log",
    "get_state",
    "load_latest_checkpoint",
    "replay_events",
    "save_checkpoint",
    "send_heartbeat",
]
