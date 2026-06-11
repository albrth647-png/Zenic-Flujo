"""
Durable Workflow Execution — Motor de Ejecucion Duradera
==========================================================

Permite que los workflows sobrevivan a caidas del proceso mediante:

- Event Sourcing: cada paso genera eventos inmutables (StepStarted, StepCompleted,
  StepFailed, WorkflowStarted, WorkflowCompleted) almacenados en SQLite.
- Checkpointing: despues de cada paso, el estado completo del workflow se serializa
  y persiste atomicamente en la tabla workflow_checkpoints.
- Recovery: al iniciar, se escanean ejecuciones incompletas (status='running' sin
  heartbeat reciente) y se reanudan desde el ultimo checkpoint.
- Heartbeats: los workers envian latidos periodicos; si un paso no recibe heartbeat
  por HEARTBEAT_TIMEOUT_SECONDS, se marca como hung y puede ser reintentado.

Feature flag: WFD_DURABLE_EXECUTION=true habilita la durabilidad.
Cuando esta deshabilitado, delega al WorkflowEngine existente (sin cambios).

Compatibilidad: todos los workflows existentes continuan funcionando sin cambios.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Configuracion via variables de entorno ────────────────────

DURABLE_ENABLED: bool = os.environ.get("WFD_DURABLE_EXECUTION", "false").lower() == "true"
HEARTBEAT_INTERVAL_SECONDS: int = int(os.environ.get("WFD_HEARTBEAT_INTERVAL_SECONDS", "30"))
HEARTBEAT_TIMEOUT_SECONDS: int = int(os.environ.get("WFD_HEARTBEAT_TIMEOUT_SECONDS", "300"))
SNAPSHOT_INTERVAL_STEPS: int = int(os.environ.get("WFD_SNAPSHOT_INTERVAL_STEPS", "5"))


# ── Tipos de eventos ─────────────────────────────────────────


class EventType(StrEnum):
    """Tipos de eventos del log de eventos."""

    WORKFLOW_STARTED = "WorkflowStarted"
    WORKFLOW_COMPLETED = "WorkflowCompleted"
    STEP_STARTED = "StepStarted"
    STEP_COMPLETED = "StepCompleted"
    STEP_FAILED = "StepFailed"


# ── Modelos de datos ─────────────────────────────────────────


@dataclass
class WorkflowEvent:
    """Evento inmutable en el log de eventos."""

    id: int | None = None
    execution_id: int = 0
    event_type: str = ""
    step_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowState:
    """Estado completo de una ejecucion de workflow."""

    workflow_id: int = 0
    execution_id: int = 0
    current_step_index: int = 0
    variables: dict[str, Any] = field(default_factory=dict)
    step_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed, recovering
    trigger_data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowState:
        return cls(
            workflow_id=data.get("workflow_id", 0),
            execution_id=data.get("execution_id", 0),
            current_step_index=data.get("current_step_index", 0),
            variables=data.get("variables", {}),
            step_results=data.get("step_results", []),
            status=data.get("status", "pending"),
            trigger_data=data.get("trigger_data", {}),
            error_message=data.get("error_message"),
        )


@dataclass
class HeartbeatInfo:
    """Informacion de heartbeat de un worker."""

    execution_id: int = 0
    step_id: int = 0
    worker_id: str = ""
    last_heartbeat: str = ""
    progress: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── DurableExecutor ──────────────────────────────────────────


class DurableExecutor:
    """
    Motor de ejecucion duradera que envuelve WorkflowEngine.

    Cuando WFD_DURABLE_EXECUTION=true, cada paso genera eventos,
    se hacen checkpoints atomicos, y las ejecuciones pueden
    sobrevivir caidas del proceso.

    Cuando esta deshabilitado, delega al WorkflowEngine existente
    sin ningun cambio en el comportamiento.
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
            self._step_counter: dict[int, int] = {}  # execution_id -> step count (para snapshots)
            logger.info(f"DurableExecutor inicializado (worker_id={self._worker_id})")

    # ── Creacion de tablas ───────────────────────────────────

    def _ensure_tables(self) -> None:
        """Crea las tablas de durable execution si no existen."""
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

            CREATE INDEX IF NOT EXISTS idx_workflow_events_execution
                ON workflow_events(execution_id);

            CREATE INDEX IF NOT EXISTS idx_workflow_events_type
                ON workflow_events(event_type);

            CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id    INTEGER NOT NULL,
                step_index      INTEGER NOT NULL,
                state           TEXT NOT NULL,
                timestamp       TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_execution
                ON workflow_checkpoints(execution_id);

            CREATE TABLE IF NOT EXISTS workflow_heartbeats (
                execution_id    INTEGER NOT NULL,
                step_id         INTEGER NOT NULL,
                worker_id       TEXT NOT NULL,
                last_heartbeat  TEXT NOT NULL,
                progress        REAL DEFAULT 0.0,
                PRIMARY KEY (execution_id, step_id, worker_id)
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_heartbeats_execution
                ON workflow_heartbeats(execution_id);

            -- Tabla de configuracion de telemetria (requisito del modulo observability)
            CREATE TABLE IF NOT EXISTS telemetry_config (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT DEFAULT 'default',
                config_key      TEXT NOT NULL,
                config_value    TEXT NOT NULL DEFAULT '{}',
                updated_at      TEXT NOT NULL,
                UNIQUE(tenant_id, config_key)
            );
        """)
        conn.commit()
        logger.debug("Tablas de durable execution verificadas/creadas")

    # ── Event Sourcing ───────────────────────────────────────

    def _append_event(
        self,
        execution_id: int,
        event_type: str,
        step_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> int:
        """Agrega un evento inmutable al log de eventos."""
        now = datetime.now(UTC).isoformat()
        cursor = self._db.execute(
            """INSERT INTO workflow_events (execution_id, event_type, step_id, data, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (execution_id, event_type, step_id, json.dumps(data or {}), now),
        )
        self._db.commit()
        return cursor.lastrowid

    def get_event_log(self, execution_id: int) -> list[WorkflowEvent]:
        """
        Retorna el log completo de eventos de una ejecucion.

        Args:
            execution_id: ID de la ejecucion

        Returns:
            Lista de WorkflowEvent ordenados por timestamp
        """
        rows = self._db.fetchall(
            "SELECT * FROM workflow_events WHERE execution_id = ? ORDER BY id ASC",
            (execution_id,),
        )
        events = []
        for row in rows:
            events.append(
                WorkflowEvent(
                    id=row["id"],
                    execution_id=row["execution_id"],
                    event_type=row["event_type"],
                    step_id=row["step_id"],
                    data=json.loads(row["data"]) if row.get("data") else {},
                    timestamp=row["timestamp"],
                )
            )
        return events

    def _replay_events(self, execution_id: int) -> WorkflowState:
        """
        Reconstruye el estado de una ejecucion repiendo los eventos.

        Args:
            execution_id: ID de la ejecucion

        Returns:
            WorkflowState reconstruido desde el log de eventos
        """
        events = self.get_event_log(execution_id)
        state = WorkflowState(execution_id=execution_id)

        for event in events:
            if event.event_type == EventType.WORKFLOW_STARTED:
                state.workflow_id = event.data.get("workflow_id", 0)
                state.status = "running"
                state.trigger_data = event.data.get("trigger_data", {})
                state.variables = event.data.get("variables", {})

            elif event.event_type == EventType.STEP_STARTED:
                state.current_step_index = event.step_id or 0

            elif event.event_type == EventType.STEP_COMPLETED:
                state.step_results.append(event.data.get("result", {}))
                state.current_step_index = (event.step_id or 0) + 1

            elif event.event_type == EventType.STEP_FAILED:
                state.status = "failed"
                state.error_message = event.data.get("error", "")

            elif event.event_type == EventType.WORKFLOW_COMPLETED:
                state.status = event.data.get("final_status", "completed")

        return state

    # ── Checkpointing ────────────────────────────────────────

    def _save_checkpoint(self, state: WorkflowState) -> int:
        """Persiste un checkpoint atomico del estado del workflow."""
        now = datetime.now(UTC).isoformat()
        state_json = json.dumps(state.to_dict(), default=self._json_default)
        cursor = self._db.execute(
            """INSERT INTO workflow_checkpoints (execution_id, step_index, state, timestamp)
               VALUES (?, ?, ?, ?)""",
            (state.execution_id, state.current_step_index, state_json, now),
        )
        self._db.commit()
        logger.debug(f"Checkpoint guardado: execution_id={state.execution_id}, step={state.current_step_index}")
        return cursor.lastrowid

    def _load_latest_checkpoint(self, execution_id: int) -> WorkflowState | None:
        """Carga el ultimo checkpoint de una ejecucion."""
        row = self._db.fetchone(
            """SELECT * FROM workflow_checkpoints
               WHERE execution_id = ?
               ORDER BY step_index DESC LIMIT 1""",
            (execution_id,),
        )
        if not row:
            return None
        state_data = json.loads(row["state"])
        return WorkflowState.from_dict(state_data)

    def create_snapshot(self, execution_id: int) -> int:
        """
        Fuerza la creacion de un snapshot/checkpoint para una ejecucion.

        Args:
            execution_id: ID de la ejecucion

        Returns:
            ID del checkpoint creado
        """
        state = self.get_state(execution_id)
        return self._save_checkpoint(state)

    # ── Ejecucion duradera ───────────────────────────────────

    def start_workflow(self, workflow_id: int, trigger_data: dict[str, Any] | None = None) -> int:
        """
        Inicia un workflow con persistencia duradera.

        Genera un evento WorkflowStarted y guarda el checkpoint inicial.
        Si WFD_DURABLE_EXECUTION=false, delega al WorkflowEngine directamente.

        Args:
            workflow_id: ID del workflow a ejecutar
            trigger_data: Datos de entrada del trigger

        Returns:
            execution_id de la nueva ejecucion
        """
        if not DURABLE_ENABLED:
            return self._start_non_durable(workflow_id, trigger_data)

        from src.workflow.repository import WorkflowRepository

        repo = WorkflowRepository()
        definition = repo.get(workflow_id)
        if not definition:
            raise ValueError(f"Workflow no encontrado: {workflow_id}")
        if definition.status != "active":
            raise ValueError(f"Workflow '{definition.name}' no esta activo (estado: {definition.status})")

        # Crear ejecucion en la tabla estandar
        execution = repo.create_execution(workflow_id, trigger_data)

        # Estado inicial
        state = WorkflowState(
            workflow_id=workflow_id,
            execution_id=execution.id,
            current_step_index=0,
            variables={"input": trigger_data or {}},
            step_results=[],
            status="running",
            trigger_data=trigger_data or {},
        )

        # Evento de inicio
        self._append_event(
            execution.id,
            EventType.WORKFLOW_STARTED,
            data={
                "workflow_id": workflow_id,
                "trigger_data": trigger_data or {},
                "variables": state.variables,
            },
        )

        # Checkpoint inicial
        self._save_checkpoint(state)
        self._step_counter[execution.id] = 0

        logger.info(f"DurableWorkflow: Workflow {workflow_id} iniciado (execution_id={execution.id})")

        # Ejecutar de forma duradera
        self._execute_durable(state, definition.steps)

        return execution.id

    def _execute_durable(self, state: WorkflowState, steps: list[dict[str, Any]]) -> WorkflowState:
        """
        Ejecuta los pasos de un workflow de forma duradera.

        Cada paso genera eventos StepStarted/StepCompleted (o StepFailed),
        se guarda un checkpoint despues de cada paso, y se envian heartbeats.
        """
        from src.workflow.engine import WorkflowEngine
        from src.workflow.step_executor import StepResult

        engine = WorkflowEngine()

        # Reconstruir contexto
        context = self._build_context(state)

        while state.current_step_index < len(steps):
            step = steps[state.current_step_index]
            step_id = step.get("id", state.current_step_index)

            # Evento: paso iniciado
            self._append_event(
                state.execution_id,
                EventType.STEP_STARTED,
                step_id=step_id,
                data={"tool": step.get("tool"), "action": step.get("action")},
            )

            # Enviar heartbeat inicial
            self.send_heartbeat(state.execution_id, step_id, self._worker_id, 0.0)

            try:
                # Ejecutar paso via WorkflowEngine._execute_step
                step_result: StepResult = engine._execute_step(step, context, engine._ctx.engine)

                # Completar paso
                result_data = {
                    "step_id": step_id,
                    "tool": step.get("tool", ""),
                    "action": step.get("action", ""),
                    "status": step_result.status,
                    "output": step_result.output_data,
                    "duration_ms": step_result.duration_ms,
                }
                self.complete_step(state.execution_id, step_id, result_data)

                # Actualizar estado
                state.step_results.append(result_data)
                state.current_step_index += 1
                context["steps_output"][str(step_id)] = step_result.output_data

                # Si el paso fallo y no hay continue_on_error, detener
                if step_result.status == "failed" and not context.get("workflow", {}).get("continue_on_error", False):
                    state.status = "failed"
                    state.error_message = step_result.error_message
                    self._append_event(
                        state.execution_id,
                        EventType.WORKFLOW_COMPLETED,
                        data={
                            "final_status": "failed",
                            "error": step_result.error_message,
                        },
                    )
                    break

            except Exception as e:
                error_msg = str(e)
                self.fail_step(state.execution_id, step_id, error_msg)
                state.status = "failed"
                state.error_message = error_msg
                self._append_event(
                    state.execution_id,
                    EventType.WORKFLOW_COMPLETED,
                    data={"final_status": "failed", "error": error_msg},
                )
                break

            # Contador de pasos para snapshots periodicos
            exec_id = state.execution_id
            self._step_counter[exec_id] = self._step_counter.get(exec_id, 0) + 1
            if self._step_counter[exec_id] % SNAPSHOT_INTERVAL_STEPS == 0:
                self.create_snapshot(state.execution_id)

        # Si completo todos los pasos
        if state.current_step_index >= len(steps) and state.status == "running":
            state.status = "completed"
            self._append_event(
                state.execution_id,
                EventType.WORKFLOW_COMPLETED,
                data={"final_status": "completed"},
            )

        # Checkpoint final
        self._save_checkpoint(state)

        # Actualizar ejecucion en tabla estandar
        self._complete_durable_execution(state)

        logger.info(
            f"DurableWorkflow: Workflow {state.workflow_id} finalizado "
            f"(execution_id={state.execution_id}, status={state.status})"
        )

        return state

    def execute_step(self, execution_id: int, step: dict[str, Any]) -> dict[str, Any]:
        """
        Ejecuta un paso individual con checkpointing.

        Args:
            execution_id: ID de la ejecucion
            step: Definicion del paso a ejecutar

        Returns:
            Resultado del paso ejecutado
        """
        state = self.get_state(execution_id)
        if not state:
            raise ValueError(f"Ejecucion no encontrada: {execution_id}")

        from src.workflow.engine import WorkflowEngine
        from src.workflow.step_executor import StepResult

        step_id = step.get("id", 0)
        context = self._build_context(state)

        # Evento: paso iniciado
        self._append_event(
            execution_id,
            EventType.STEP_STARTED,
            step_id=step_id,
            data={"tool": step.get("tool"), "action": step.get("action")},
        )

        try:
            engine = WorkflowEngine()
            step_result: StepResult = engine._execute_step(step, context, engine._ctx.engine)
            result_data = {
                "step_id": step_id,
                "tool": step.get("tool", ""),
                "action": step.get("action", ""),
                "status": step_result.status,
                "output": step_result.output_data,
                "duration_ms": step_result.duration_ms,
            }
            self.complete_step(execution_id, step_id, result_data)
            return result_data

        except Exception as e:
            self.fail_step(execution_id, step_id, str(e))
            return {"step_id": step_id, "status": "failed", "error": str(e)}

    def complete_step(self, execution_id: int, step_id: int, result: dict[str, Any]) -> None:
        """
        Persiste el resultado de un paso completado y guarda checkpoint.

        Args:
            execution_id: ID de la ejecucion
            step_id: ID del paso completado
            result: Resultado del paso
        """
        self._append_event(
            execution_id,
            EventType.STEP_COMPLETED,
            step_id=step_id,
            data=result,
        )

        # Actualizar estado y guardar checkpoint
        state = self.get_state(execution_id)
        if state:
            state.step_results.append(result)
            state.current_step_index = max(state.current_step_index, step_id + 1)
            self._save_checkpoint(state)

    def fail_step(self, execution_id: int, step_id: int, error: str) -> None:
        """
        Persiste un fallo de paso y guarda checkpoint.

        Args:
            execution_id: ID de la ejecucion
            step_id: ID del paso fallido
            error: Mensaje de error
        """
        self._append_event(
            execution_id,
            EventType.STEP_FAILED,
            step_id=step_id,
            data={"error": error},
        )

        state = self.get_state(execution_id)
        if state:
            state.status = "failed"
            state.error_message = error
            self._save_checkpoint(state)

    def get_state(self, execution_id: int) -> WorkflowState | None:
        """
        Obtiene el estado actual de una ejecucion.

        Primero intenta cargar desde el ultimo checkpoint. Si no hay
        checkpoint, reconstruye el estado repiendo eventos.

        Args:
            execution_id: ID de la ejecucion

        Returns:
            WorkflowState actual, o None si no existe
        """
        # Intentar cargar desde checkpoint
        state = self._load_latest_checkpoint(execution_id)
        if state:
            return state

        # Si no hay checkpoint, repiendo eventos
        state = self._replay_events(execution_id)
        if state.execution_id == 0:
            return None

        # Guardar checkpoint para futuras consultas
        self._save_checkpoint(state)
        return state

    # ── Heartbeats ───────────────────────────────────────────

    def send_heartbeat(self, execution_id: int, step_id: int, worker_id: str, progress: float = 0.0) -> None:
        """
        Actualiza el heartbeat de un worker para un paso en ejecucion.

        Args:
            execution_id: ID de la ejecucion
            step_id: ID del paso en ejecucion
            worker_id: Identificador del worker
            progress: Porcentaje de progreso (0.0-100.0)
        """
        now = datetime.now(UTC).isoformat()
        self._db.execute(
            """INSERT OR REPLACE INTO workflow_heartbeats
               (execution_id, step_id, worker_id, last_heartbeat, progress)
               VALUES (?, ?, ?, ?, ?)""",
            (execution_id, step_id, worker_id, now, progress),
        )
        self._db.commit()

    def check_heartbeats(self) -> list[dict[str, Any]]:
        """
        Busca pasos con heartbeat vencido (hung steps).

        Un paso se considera hung si no ha recibido heartbeat en
        HEARTBEAT_TIMEOUT_SECONDS segundos.

        Returns:
            Lista de diccionarios con informacion de pasos hung
        """
        timeout_cutoff = datetime.now(UTC).timestamp() - HEARTBEAT_TIMEOUT_SECONDS
        rows = self._db.fetchall("SELECT * FROM workflow_heartbeats")

        hung_steps = []
        for row in rows:
            try:
                hb_time = datetime.fromisoformat(row["last_heartbeat"]).timestamp()
            except (ValueError, TypeError):
                continue

            if hb_time < timeout_cutoff:
                hung_steps.append(
                    {
                        "execution_id": row["execution_id"],
                        "step_id": row["step_id"],
                        "worker_id": row["worker_id"],
                        "last_heartbeat": row["last_heartbeat"],
                        "progress": row["progress"],
                        "hung_for_seconds": int(datetime.now(UTC).timestamp() - hb_time),
                    }
                )

        if hung_steps:
            logger.warning(f"check_heartbeats: {len(hung_steps)} paso(s) hung detectados")

        return hung_steps

    # ── Recuperacion ─────────────────────────────────────────

    def recover_pending(self) -> list[dict[str, Any]]:
        """
        Escanea ejecuciones incompletas y las marca para recuperacion.

        Busca ejecuciones con status='running' que no tengan heartbeat
        reciente, carga su ultimo checkpoint y las prepara para reanudar.

        Returns:
            Lista de ejecuciones recuperadas con su estado
        """
        if not DURABLE_ENABLED:
            logger.info("recover_pending: durabilidad deshabilitada, nada que recuperar")
            return []

        # Buscar ejecuciones en estado 'running'
        running_executions = self._db.fetchall(
            """SELECT we.id, we.workflow_id, we.started_at
               FROM workflow_executions we
               WHERE we.status = 'running'
               ORDER BY we.started_at ASC"""
        )

        recovered = []
        timeout_cutoff = datetime.now(UTC).timestamp() - HEARTBEAT_TIMEOUT_SECONDS

        for exec_row in running_executions:
            execution_id = exec_row["id"]
            workflow_id = exec_row["workflow_id"]

            # Verificar heartbeat reciente
            hb_row = self._db.fetchone(
                """SELECT MAX(last_heartbeat) as latest_heartbeat
                   FROM workflow_heartbeats
                   WHERE execution_id = ?""",
                (execution_id,),
            )

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

            # Cargar estado desde checkpoint
            state = self.get_state(execution_id)
            if not state:
                logger.warning(f"recover_pending: sin checkpoint para execution_id={execution_id}")
                continue

            state.status = "recovering"
            self._save_checkpoint(state)

            recovered.append(
                {
                    "execution_id": execution_id,
                    "workflow_id": workflow_id,
                    "current_step_index": state.current_step_index,
                    "status": "recovering",
                    "trigger_data": state.trigger_data,
                }
            )

            logger.info(
                f"recover_pending: execution_id={execution_id} marcada para recuperacion "
                f"(step_index={state.current_step_index})"
            )

        if recovered:
            logger.info(f"recover_pending: {len(recovered)} ejecucion(es) recuperada(s)")

        return recovered

    # ── Helpers ──────────────────────────────────────────────

    def _start_non_durable(self, workflow_id: int, trigger_data: dict[str, Any] | None = None) -> int:
        """Delega la ejecucion al WorkflowEngine existente (sin durabilidad)."""
        from src.workflow.engine import WorkflowEngine

        engine = WorkflowEngine()
        result = engine.execute(workflow_id, trigger_data)
        return result.execution_id

    def _build_context(self, state: WorkflowState) -> dict[str, Any]:
        """Construye el contexto de ejecucion a partir del estado."""
        context = {
            "input": state.trigger_data,
            "workflow": {
                "id": state.workflow_id,
                "continue_on_error": False,
            },
            "output": {},
            "steps_output": {},
            "settings": {},
            "_execution_id": state.execution_id,
        }
        # Reconstruir steps_output desde step_results
        for result in state.step_results:
            step_id = str(result.get("step_id", 0))
            context["steps_output"][step_id] = result.get("output", {})
        return context

    def _complete_durable_execution(self, state: WorkflowState) -> None:
        """Actualiza la ejecucion en la tabla estandar al finalizar."""
        duration_ms = 0
        for result in state.step_results:
            duration_ms += result.get("duration_ms", 0)

        self._db.execute(
            """UPDATE workflow_executions
               SET status = ?, completed_at = ?, duration_ms = ?, error_message = ?
               WHERE id = ?""",
            (
                state.status,
                datetime.now(UTC).isoformat(),
                duration_ms,
                state.error_message,
                state.execution_id,
            ),
        )
        self._db.commit()

    @staticmethod
    def _json_default(obj: Any) -> str:
        """Serializador JSON por defecto para tipos no estandar."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    # ── Limpieza ─────────────────────────────────────────────

    def cleanup_old_events(self, execution_id: int, keep_last: int = 100) -> int:
        """
        Elimina eventos antiguos de una ejecucion, manteniendo los ultimos N.

        Args:
            execution_id: ID de la ejecucion
            keep_last: Numero de eventos a conservar

        Returns:
            Numero de eventos eliminados
        """
        row = self._db.fetchone(
            "SELECT COUNT(*) as total FROM workflow_events WHERE execution_id = ?",
            (execution_id,),
        )
        total = row["total"] if row else 0

        if total <= keep_last:
            return 0

        delete_count = total - keep_last
        self._db.execute(
            """DELETE FROM workflow_events
               WHERE execution_id = ? AND id NOT IN (
                   SELECT id FROM workflow_events
                   WHERE execution_id = ?
                   ORDER BY id DESC LIMIT ?
               )""",
            (execution_id, execution_id, keep_last),
        )
        self._db.commit()
        logger.info(f"cleanup_old_events: {delete_count} eventos eliminados para execution_id={execution_id}")
        return delete_count

    def cleanup_old_checkpoints(self, execution_id: int, keep_last: int = 5) -> int:
        """
        Elimina checkpoints antiguos de una ejecucion, manteniendo los ultimos N.

        Args:
            execution_id: ID de la ejecucion
            keep_last: Numero de checkpoints a conservar

        Returns:
            Numero de checkpoints eliminados
        """
        row = self._db.fetchone(
            "SELECT COUNT(*) as total FROM workflow_checkpoints WHERE execution_id = ?",
            (execution_id,),
        )
        total = row["total"] if row else 0

        if total <= keep_last:
            return 0

        delete_count = total - keep_last
        self._db.execute(
            """DELETE FROM workflow_checkpoints
               WHERE execution_id = ? AND id NOT IN (
                   SELECT id FROM workflow_checkpoints
                   WHERE execution_id = ?
                   ORDER BY id DESC LIMIT ?
               )""",
            (execution_id, execution_id, keep_last),
        )
        self._db.commit()
        logger.info(f"cleanup_old_checkpoints: {delete_count} checkpoints eliminados para execution_id={execution_id}")
        return delete_count

    # ── Reset para testing ───────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None
