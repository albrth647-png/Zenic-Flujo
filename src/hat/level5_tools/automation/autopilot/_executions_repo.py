"""
WorkflowExecution model + WorkflowExecutionRepository
======================================================

Extraído de workflow_repository.py — responsabilidad única: gestión de
ejecuciones de workflows y step logs.

- WorkflowExecution → modelo de ejecución
- WorkflowExecutionRepository → operaciones sobre workflow_executions y step_logs
"""

import json

from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.core.utils import now_iso
from typing import Any

logger = setup_logging(__name__)


class WorkflowExecution:
    """Representa una ejecución de workflow."""

    def __init__(
        self,
        id: int | None = None,
        workflow_id: int = 0,
        status: str = "pending",
        trigger_data: dict[str, Any] | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        duration_ms: int | None = None,
        error_message: str | None = None,
    ):
        self.id = id
        self.workflow_id = workflow_id
        self.status = status
        self.trigger_data = trigger_data or {}
        self.started_at = started_at or now_iso()
        self.completed_at = completed_at
        self.duration_ms = duration_ms
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "trigger_data": self.trigger_data,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
        }

    def __repr__(self) -> str:
        return f"<WorkflowExecution #{self.id} wf={self.workflow_id} '{self.status}'>"


class WorkflowExecutionRepository:
    """Operaciones sobre ejecuciones de workflows y step logs."""

    def __init__(self, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager()

    def create_execution(
        self,
        workflow_id: int,
        trigger_data: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        """Crea un nuevo registro de ejecución."""
        cursor = self._db.execute(
            """INSERT INTO workflow_executions (workflow_id, status, trigger_data)
               VALUES (?, ?, ?)""",
            (workflow_id, "running", json.dumps(trigger_data or {})),
        )
        self._db.commit()
        execution = WorkflowExecution(
            id=cursor.lastrowid,
            workflow_id=workflow_id,
            status="running",
            trigger_data=trigger_data,
        )
        logger.info("Ejecución creada: ID %s para workflow %s", execution.id, workflow_id)
        return execution

    def complete_execution(
        self,
        execution_id: int,
        duration_ms: int,
        error_message: str | None = None,
    ) -> None:
        """Marca una ejecución como completada o fallida."""
        status = "failed" if error_message else "completed"
        self._db.execute(
            """UPDATE workflow_executions
               SET status = ?, completed_at = ?, duration_ms = ?, error_message = ?
               WHERE id = ?""",
            (status, now_iso(), duration_ms, error_message, execution_id),
        )
        self._db.commit()

    def get_execution(self, execution_id: int) -> WorkflowExecution | None:
        """Obtiene una ejecución por ID."""
        row = self._db.fetchone(
            "SELECT * FROM workflow_executions WHERE id = ?",
            (execution_id,),
        )
        if not row:
            return None
        return WorkflowExecution(
            id=row["id"],
            workflow_id=row["workflow_id"],
            status=row["status"],
            trigger_data=json.loads(row["trigger_data"]) if row.get("trigger_data") else {},
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            error_message=row["error_message"],
        )

    def list_executions(self, workflow_id: int, limit: int = 50) -> list[WorkflowExecution]:
        """Lista las ejecuciones de un workflow."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_executions
               WHERE workflow_id = ?
               ORDER BY started_at DESC LIMIT ?""",
            (workflow_id, limit),
        )
        return [
            WorkflowExecution(
                id=r["id"],
                workflow_id=r["workflow_id"],
                status=r["status"],
                trigger_data=json.loads(r["trigger_data"]) if r.get("trigger_data") else {},
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                duration_ms=r["duration_ms"],
                error_message=r["error_message"],
            )
            for r in rows
        ]

    def save_step_log(
        self,
        execution_id: int,
        step_id: int,
        tool: str,
        action: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None,
        status: str,
        duration_ms: int,
        error_message: str | None = None,
        retry_count: int = 0,
    ) -> None:
        """Guarda el log de un paso ejecutado."""
        self._db.execute(
            """INSERT INTO workflow_step_logs
               (execution_id, step_id, tool, action, input_data, output_data,
                status, started_at, completed_at, duration_ms, error_message, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id,
                step_id,
                tool,
                action,
                json.dumps(input_data),
                json.dumps(output_data or {}),
                status,
                now_iso(),
                now_iso(),
                duration_ms,
                error_message,
                retry_count,
            ),
        )
        self._db.commit()

    def get_step_logs(self, execution_id: int) -> list[dict]:
        """Obtiene los logs de pasos de una ejecución."""
        rows = self._db.fetchall(
            "SELECT * FROM workflow_step_logs WHERE execution_id = ? ORDER BY id",
            (execution_id,),
        )
        return [
            {
                "id": r["id"],
                "step_id": r["step_id"],
                "tool": r["tool"],
                "action": r["action"],
                "input_data": json.loads(r["input_data"]) if r.get("input_data") else {},
                "output_data": json.loads(r["output_data"]) if r.get("output_data") else {},
                "status": r["status"],
                "duration_ms": r["duration_ms"],
                "error_message": r["error_message"],
                "retry_count": r["retry_count"],
            }
            for r in rows
        ]
