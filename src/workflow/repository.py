"""
Workflow Determinista — WorkflowRepository
CRUD de definiciones y ejecuciones de workflows en SQLite.
"""
import json
from datetime import datetime
from typing import Any

from src.data.database_manager import DatabaseManager
from src.utils.helpers import generate_id, now_iso
from src.utils.logger import setup_logging
from src.config import FREE_TIER_MAX_WORKFLOWS, FREE_TIER_ALLOWED_TOOLS

logger = setup_logging(__name__)


class WorkflowDefinition:
    """Representa la definición de un workflow."""

    def __init__(self, id: int | None = None, name: str = "", description: str = "",
                 trigger_type: str = "", trigger_config: dict | None = None,
                 steps: list[dict] | None = None, status: str = "active",
                 created_at: str | None = None, updated_at: str | None = None):
        self.id = id
        self.name = name
        self.description = description
        self.trigger_type = trigger_type
        self.trigger_config = trigger_config or {}
        self.steps = steps or []
        self.status = status
        self.created_at = created_at or now_iso()
        self.updated_at = updated_at or now_iso()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type,
            "trigger_config": self.trigger_config,
            "steps": self.steps,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowDefinition":
        return cls(
            id=data.get("id"),
            name=data.get("name", ""),
            description=data.get("description", ""),
            trigger_type=data.get("trigger_type", ""),
            trigger_config=cls._safe_json_loads(data.get("trigger_config", "{}")),
            steps=cls._safe_json_loads(data.get("steps", "[]")),
            status=data.get("status", "active"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value


class WorkflowExecution:
    """Representa una ejecución de workflow."""

    def __init__(self, id: int | None = None, workflow_id: int = 0,
                 status: str = "pending", trigger_data: dict | None = None,
                 started_at: str | None = None, completed_at: str | None = None,
                 duration_ms: int | None = None, error_message: str | None = None):
        self.id = id
        self.workflow_id = workflow_id
        self.status = status
        self.trigger_data = trigger_data or {}
        self.started_at = started_at or now_iso()
        self.completed_at = completed_at
        self.duration_ms = duration_ms
        self.error_message = error_message

    def to_dict(self) -> dict:
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


class WorkflowRepository:
    """Repositorio para operaciones CRUD de workflows."""

    def __init__(self):
        self._db = DatabaseManager()

    # ── Workflow Definitions ─────────────────────────────────

    def create(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Crea una nueva definición de workflow."""
        # Verificar límite de free tier
        count = self.count()
        if count >= FREE_TIER_MAX_WORKFLOWS:
            # Verificar si tiene licencia válida
            from src.license.validator import LicenseValidator
            validator = LicenseValidator()
            license_info = validator.get_license_info()

            if license_info["type"] == "free" and count >= FREE_TIER_MAX_WORKFLOWS:
                raise ValueError(
                    f"Límite de {FREE_TIER_MAX_WORKFLOWS} workflows en versión gratuita. "
                    "Compra una licencia para crear más workflows."
                )

        cursor = self._db.execute(
            """INSERT INTO workflow_definitions 
               (name, description, trigger_type, trigger_config, steps, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                definition.name,
                definition.description,
                definition.trigger_type,
                json.dumps(definition.trigger_config),
                json.dumps(definition.steps),
                definition.status,
            ),
        )
        self._db.commit()
        definition.id = cursor.lastrowid
        self._db.audit("workflow.created", f"Workflow '{definition.name}' creado (ID: {definition.id})")
        logger.info(f"Workflow creado: {definition.name} (ID: {definition.id})")
        return definition

    def get(self, workflow_id: int) -> WorkflowDefinition | None:
        """Obtiene una definición de workflow por ID."""
        row = self._db.fetchone(
            "SELECT * FROM workflow_definitions WHERE id = ?",
            (workflow_id,),
        )
        return WorkflowDefinition.from_dict(row) if row else None

    def list_all(self, status: str | None = None) -> list[WorkflowDefinition]:
        """Lista todos los workflows, opcionalmente filtrados por estado."""
        if status:
            rows = self._db.fetchall(
                "SELECT * FROM workflow_definitions WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM workflow_definitions ORDER BY updated_at DESC"
            )
        return [WorkflowDefinition.from_dict(r) for r in rows]

    def update(self, workflow_id: int, updates: dict) -> WorkflowDefinition | None:
        """Actualiza campos de una definición de workflow."""
        allowed_fields = {"name", "description", "trigger_type", "trigger_config",
                          "steps", "status"}
        set_parts = []
        params = []

        for key, value in updates.items():
            if key in allowed_fields:
                set_parts.append(f"{key} = ?")
                if key in ("trigger_config", "steps"):
                    params.append(json.dumps(value))
                else:
                    params.append(value)

        if not set_parts:
            return self.get(workflow_id)

        set_parts.append("updated_at = ?")
        params.append(now_iso())
        params.append(workflow_id)

        self._db.execute(
            f"UPDATE workflow_definitions SET {', '.join(set_parts)} WHERE id = ?",
            tuple(params),
        )
        self._db.commit()
        self._db.audit("workflow.updated", f"Workflow ID {workflow_id} actualizado")
        return self.get(workflow_id)

    def delete(self, workflow_id: int) -> bool:
        """Elimina una definición de workflow y sus ejecuciones."""
        self._db.execute("DELETE FROM workflow_step_logs WHERE execution_id IN "
                        "(SELECT id FROM workflow_executions WHERE workflow_id = ?)",
                        (workflow_id,))
        self._db.execute("DELETE FROM workflow_executions WHERE workflow_id = ?",
                        (workflow_id,))
        self._db.execute("DELETE FROM event_subscriptions WHERE workflow_id = ?",
                        (workflow_id,))
        self._db.execute("DELETE FROM workflow_definitions WHERE id = ?",
                        (workflow_id,))
        self._db.commit()
        self._db.audit("workflow.deleted", f"Workflow ID {workflow_id} eliminado")
        return True

    def count(self) -> int:
        """Retorna el número total de workflows."""
        row = self._db.fetchone("SELECT COUNT(*) as count FROM workflow_definitions")
        return row["count"] if row else 0

    # ── Workflow Executions ──────────────────────────────────

    def create_execution(self, workflow_id: int, trigger_data: dict | None = None) -> WorkflowExecution:
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
        logger.info(f"Ejecución creada: ID {execution.id} para workflow {workflow_id}")
        return execution

    def complete_execution(self, execution_id: int, duration_ms: int,
                           error_message: str | None = None) -> None:
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
                id=r["id"], workflow_id=r["workflow_id"], status=r["status"],
                trigger_data=json.loads(r["trigger_data"]) if r.get("trigger_data") else {},
                started_at=r["started_at"], completed_at=r["completed_at"],
                duration_ms=r["duration_ms"], error_message=r["error_message"],
            )
            for r in rows
        ]

    # ── Step Logs ────────────────────────────────────────────

    def save_step_log(self, execution_id: int, step_id: int, tool: str,
                      action: str, input_data: dict, output_data: dict | None,
                      status: str, duration_ms: int,
                      error_message: str | None = None, retry_count: int = 0) -> None:
        """Guarda el log de un paso ejecutado."""
        self._db.execute(
            """INSERT INTO workflow_step_logs 
               (execution_id, step_id, tool, action, input_data, output_data,
                status, started_at, completed_at, duration_ms, error_message, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id, step_id, tool, action,
                json.dumps(input_data), json.dumps(output_data or {}),
                status, now_iso(), now_iso(), duration_ms,
                error_message, retry_count,
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

    # ── Dashboard ────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Retorna estadísticas para el dashboard."""
        total = self._db.fetchone("SELECT COUNT(*) as count FROM workflow_definitions")
        by_status_raw = self._db.fetchall(
            "SELECT status, COUNT(*) as count FROM workflow_definitions GROUP BY status"
        )
        # Garantizar que los 4 estados aparezcan en el dict (con 0 si no hay)
        by_status = {"active": 0, "paused": 0, "archived": 0, "failed": 0}
        for r in by_status_raw:
            by_status[r["status"]] = r["count"]

        recent = self._db.fetchall(
            """SELECT we.id, wf.name, we.status, we.started_at
               FROM workflow_executions we
               JOIN workflow_definitions wf ON we.workflow_id = wf.id
               ORDER BY we.started_at DESC LIMIT 10"""
        )

        return {
            "total": total["count"] if total else 0,
            "by_status": by_status,
            "recent_executions": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "status": r["status"],
                    "started_at": r["started_at"],
                }
                for r in recent
            ],
        }

    # ── Schedule helpers ─────────────────────────────────────

    def get_active_scheduled(self) -> list[WorkflowDefinition]:
        """Obtiene todos los workflows activos con trigger de tipo schedule."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_definitions 
               WHERE status = 'active' AND trigger_type = 'schedule'"""
        )
        return [WorkflowDefinition.from_dict(r) for r in rows]

    def get_active_webhooks(self) -> list[WorkflowDefinition]:
        """Obtiene todos los workflows activos con trigger de tipo webhook."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_definitions 
               WHERE status = 'active' AND trigger_type = 'webhook'"""
        )
        return [WorkflowDefinition.from_dict(r) for r in rows]
