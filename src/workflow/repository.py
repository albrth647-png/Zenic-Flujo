"""
ORBITAL — WorkflowRepository (Fase 3: Integrado con ORBITAL)
=============================================================

CRUD de definiciones y ejecuciones de workflows en SQLite.
Mantiene compatibilidad total con la DB existente.
Agrega conversion automatica a definiciones orbitales via OrbitalRepository.
"""

import json
from datetime import datetime

from src.core.config import FREE_TIER_MAX_WORKFLOWS
from src.core.db import DatabaseManager, build_update_query
from src.core.logging import setup_logging
from src.core.utils import now_iso
from typing import Any

logger = setup_logging(__name__)


class WorkflowDefinition:
    """Representa la definición de un workflow."""

    def __init__(
        self,
        id: int | None = None,
        name: str = "",
        description: str = "",
        trigger_type: str = "",
        trigger_config: dict[str, Any] | None = None,
        steps: list[dict] | None = None,
        status: str = "active",
        created_at: str | None = None,
        updated_at: str | None = None,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.trigger_type = trigger_type
        self.trigger_config = trigger_config or {}
        self.steps = steps or []
        self.status = status
        self.created_at = created_at or now_iso()
        self.updated_at = updated_at or now_iso()

    def to_dict(self) -> dict[str, Any]:
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
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinition":
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
    # legítimo: parsea JSON dinámico, retorno puede ser dict/list/str/etc.
    def _safe_json_loads(value: dict | list | str) -> dict | list | str:
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


class WorkflowRepository:
    """Repositorio para operaciones CRUD de workflows."""

    def __init__(self):
        self._db = DatabaseManager()

    # ── Workflow Definitions ─────────────────────────────────

    def create(self, definition: WorkflowDefinition, user_id: int | None = None) -> WorkflowDefinition:
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
               (name, description, trigger_type, trigger_config, steps, status, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                definition.name,
                definition.description,
                definition.trigger_type,
                json.dumps(definition.trigger_config),
                json.dumps(definition.steps),
                definition.status,
                user_id or 1,
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

    def list_all(self, status: str | None = None, user_id: int | None = None) -> list[WorkflowDefinition]:
        """Lista todos los workflows, opcionalmente filtrados por estado y usuario."""
        if status and user_id:
            rows = self._db.fetchall(
                "SELECT * FROM workflow_definitions WHERE status = ? AND user_id = ? ORDER BY updated_at DESC",
                (status, user_id),
            )
        elif status:
            rows = self._db.fetchall(
                "SELECT * FROM workflow_definitions WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            )
        elif user_id:
            rows = self._db.fetchall(
                "SELECT * FROM workflow_definitions WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            )
        else:
            rows = self._db.fetchall("SELECT * FROM workflow_definitions ORDER BY updated_at DESC")
        return [WorkflowDefinition.from_dict(r) for r in rows]

    def update(
        self,
        workflow_id: int,
        updates: dict[str, Any],
        create_version: bool = False,
        change_summary: str = "",
        user_id: int | None = None,
    ) -> WorkflowDefinition | None:
        """
        Actualiza campos de una definición de workflow.

        Si ``create_version=True`` (Sprint 9), crea automáticamente una nueva
        versión en ``workflow_versions`` con un snapshot del estado resultante.
        Esto permite rollback y auditoría sin acoplar el llamador al sistema de versioning.
        """
        allowed_fields = {"name", "description", "trigger_type", "trigger_config", "steps", "status", "updated_at"}
        # Pre-procesar fields: serializar trigger_config y steps como JSON
        processed_fields = {}
        for key, value in updates.items():
            if key in allowed_fields:
                if key in ("trigger_config", "steps"):
                    value = json.dumps(value)
                processed_fields[key] = value

        result = build_update_query(
            "workflow_definitions",
            allowed_fields,
            processed_fields,
            extra_set={"updated_at": now_iso()},
        )
        if result is None:
            return self.get(workflow_id)
        sql, params = result

        self._db.execute(sql, (*params, workflow_id))
        self._db.commit()
        self._db.audit("workflow.updated", f"Workflow ID {workflow_id} actualizado")

        # Sprint 9: crear versión si se solicitó
        if create_version:
            updated = self.get(workflow_id)
            if updated:
                try:
                    from src.workflow.versioning import WorkflowVersionRepository

                    version_repo = WorkflowVersionRepository(self._db)
                    version_repo.create_version(
                        workflow_id=workflow_id,
                        name=updated.name,
                        description=updated.description,
                        trigger_type=updated.trigger_type,
                        trigger_config=updated.trigger_config,
                        steps=updated.steps,
                        change_summary=change_summary or f"Update de campos: {', '.join(updates.keys())}",
                        created_by=user_id or 1,
                    )
                except Exception as exc:
                    # El versioning no debe romper el update principal
                    logger.warning(f"versioning falló en update de workflow {workflow_id}: {exc}")

        return self.get(workflow_id)

    def delete(self, workflow_id: int) -> bool:
        """Elimina una definición de workflow y sus ejecuciones."""
        self._db.execute(
            "DELETE FROM workflow_step_logs WHERE execution_id IN "
            "(SELECT id FROM workflow_executions WHERE workflow_id = ?)",
            (workflow_id,),
        )
        self._db.execute("DELETE FROM workflow_executions WHERE workflow_id = ?", (workflow_id,))
        self._db.execute("DELETE FROM event_subscriptions WHERE workflow_id = ?", (workflow_id,))
        self._db.execute("DELETE FROM workflow_definitions WHERE id = ?", (workflow_id,))
        self._db.commit()
        self._db.audit("workflow.deleted", f"Workflow ID {workflow_id} eliminado")
        return True

    def count(self, user_id: int | None = None) -> int:
        """Retorna el número total de workflows."""
        if user_id:
            row = self._db.fetchone("SELECT COUNT(*) as count FROM workflow_definitions WHERE user_id = ?", (user_id,))
        else:
            row = self._db.fetchone("SELECT COUNT(*) as count FROM workflow_definitions")
        return row["count"] if row else 0

    # ── Workflow Executions ──────────────────────────────────

    def create_execution(self, workflow_id: int, trigger_data: dict[str, Any] | None = None) -> WorkflowExecution:
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

    def complete_execution(self, execution_id: int, duration_ms: int, error_message: str | None = None) -> None:
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

    # ── Step Logs ────────────────────────────────────────────

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

    # ── Export / Import ───────────────────────────────────────

    def export_workflow(self, workflow_id: int) -> dict[str, Any] | None:
        """Exporta un workflow completo como dict JSON-serializable.

        Incluye definición, pasos, trigger config y ejecuciones.
        Usar import_workflow() para restaurar.
        """
        wf = self.get(workflow_id)
        if not wf:
            return None

        executions = self.list_executions(workflow_id, limit=100)
        now_str = datetime.now().isoformat()

        return {
            "export_version": "1.0",
            "exported_at": now_str,
            "name": wf.name,
            "description": wf.description,
            "trigger_type": wf.trigger_type,
            "trigger_config": wf.trigger_config,
            "steps": wf.steps,
            "status": wf.status,
            "executions": [e.to_dict() for e in executions],
        }

    def import_workflow(self, data: dict[str, Any]) -> WorkflowDefinition:
        """Importa un workflow desde un dict generado por export_workflow().

        Valida campos requeridos, sanitiza IDs, y crea un nuevo workflow
        con estado 'active'. Las ejecuciones NO se importan.
        """
        name = (data.get("name") or "").strip()
        if not name:
            name = "Workflow importado"

        trigger_type = data.get("trigger_type", "manual")
        trigger_config = data.get("trigger_config") or {}
        steps = data.get("steps")

        if steps is not None and not isinstance(steps, list):
            raise ValueError("campo 'steps' debe ser una lista")

        steps = steps or []
        # Sanitizar: resetear IDs de pasos (sin mutar el dict original)
        steps = [{**step, "id": i + 1} if isinstance(step, dict) else step for i, step in enumerate(steps)]

        # Advertir sobre tools desconocidas (no bloqueante)
        known_tools = {
            "crm",
            "invoice",
            "inventory",
            "notification",
            "system",
            "autopilot",
            "logic_gate",
            "api_connector",
            "data_keeper",
        }
        for step in steps:
            tool = step.get("tool", "")
            if tool and tool not in known_tools:
                logger.warning(
                    f"Import: tool desconocida '{tool}' en paso {step.get('id')} - "
                    "se importará igual, pero puede fallar en ejecución"
                )

        wf = self.create(
            WorkflowDefinition(
                name=name,
                description=data.get("description", ""),
                trigger_type=trigger_type,
                trigger_config=trigger_config,
                steps=steps,
            )
        )
        logger.info(f"Workflow importado: {wf.name} (ID: {wf.id})")
        return wf

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

    def create_from_dict(self, data: dict[str, Any]) -> WorkflowDefinition:
        """Create a workflow from a dict (used by sync import)."""
        import copy
        wf_data = copy.deepcopy(data)
        wf_data.pop("id", None)
        return self.create(WorkflowDefinition(
            name=wf_data.get("name", "Imported Workflow"),
            description=wf_data.get("description", ""),
            trigger_type=wf_data.get("trigger_type", "manual"),
            trigger_config=wf_data.get("trigger_config", {}),
            steps=wf_data.get("steps", []),
        ))

    def get_stats(self, user_id: int | None = None) -> dict[str, Any]:
        """Retorna estadísticas para el dashboard, opcionalmente filtradas por usuario."""
        if user_id:
            total = self._db.fetchone(
                "SELECT COUNT(*) as count FROM workflow_definitions WHERE user_id = ?",
                (user_id,),
            )
            by_status_raw = self._db.fetchall(
                "SELECT status, COUNT(*) as count FROM workflow_definitions WHERE user_id = ? GROUP BY status",
                (user_id,),
            )
        else:
            total = self._db.fetchone("SELECT COUNT(*) as count FROM workflow_definitions")
            by_status_raw = self._db.fetchall(
                "SELECT status, COUNT(*) as count FROM workflow_definitions GROUP BY status"
            )
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
            "orbital_mode": True,
        }

    # ── Conversion Orbital ──────────────────────────────────

    def to_orbital(self, workflow_id: int) -> dict[str, Any] | None:
        """
        Convierte una definicion de workflow lineal a orbital.

        Usa OrbitalRepository para la conversion y guarda en tablas orbitales.
        Retorna la definicion orbital o None si no se encuentra.
        """
        definition = self.get(workflow_id)
        if not definition:
            return None

        from src.orbital.orbital_repository import OrbitalRepository

        orbital_repo = OrbitalRepository()
        orbital_def = orbital_repo.convert_linear_to_orbital(definition.to_dict())
        orbital_repo.save_orbital_workflow(orbital_def)
        orbital_repo.close()

        return orbital_def.to_dict()

    def get_orbital_stats(self) -> dict[str, Any]:
        """Retorna estadisticas de las tablas orbitales."""
        from src.orbital.db import OrbitalDB

        orbital_db = OrbitalDB()
        stats = orbital_db.get_stats()
        orbital_db.close()
        return stats
