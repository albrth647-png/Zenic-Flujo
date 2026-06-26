"""
WorkflowDefinition model + WorkflowDefinitionRepository
========================================================

Extraído de workflow_repository.py — responsabilidad única: CRUD de
definiciones de workflows.

- WorkflowDefinition → modelo inmutable-por-convención
- WorkflowDefinitionRepository → operaciones sobre workflow_definitions
"""

import json
from datetime import datetime

from src.core.config import FREE_TIER_MAX_WORKFLOWS
from src.core.db import DatabaseManager, build_update_query
from src.core.logging import setup_logging
from src.core.utils import now_iso

logger = setup_logging(__name__)


class WorkflowDefinition:
    """Representa la definición de un workflow."""

    def __init__(
        self,
        id: int | None = None,
        name: str = "",
        description: str = "",
        trigger_type: str = "",
        trigger_config: dict | None = None,
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
    def _safe_json_loads(value: dict | list | str) -> dict | list | str:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    def __repr__(self) -> str:
        return f"<WorkflowDefinition #{self.id} '{self.name}'>"


class WorkflowDefinitionRepository:
    """CRUD de definiciones de workflows sobre SQLite."""

    def __init__(self, db: DatabaseManager | None = None):
        self._db = db or DatabaseManager()

    def create(self, definition: WorkflowDefinition, user_id: int | None = None) -> WorkflowDefinition:
        """Crea una nueva definición de workflow."""
        count = self.count()
        if count >= FREE_TIER_MAX_WORKFLOWS:
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
        logger.info("Workflow creado: %s (ID: %s)", definition.name, definition.id)
        return definition

    def get(self, workflow_id: int) -> WorkflowDefinition | None:
        """Obtiene una definición de workflow por ID."""
        row = self._db.fetchone(
            "SELECT * FROM workflow_definitions WHERE id = ?",
            (workflow_id,),
        )
        return WorkflowDefinition.from_dict(row) if row else None

    def list_all(
        self,
        status: str | None = None,
        user_id: int | None = None,
    ) -> list[WorkflowDefinition]:
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
        updates: dict,
        create_version: bool = False,
        change_summary: str = "",
        user_id: int | None = None,
    ) -> WorkflowDefinition | None:
        """Actualiza campos de una definición de workflow.

        Si ``create_version=True``, crea snapshot en workflow_versions.
        """
        allowed_fields = {"name", "description", "trigger_type", "trigger_config", "steps", "status", "updated_at"}
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

        if create_version:
            updated = self.get(workflow_id)
            if updated:
                try:
                    from src.hat.level5_tools.automation.autopilot.workflow_versioning import WorkflowVersionRepository
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
                    logger.warning("versioning falló en update de workflow %s: %s", workflow_id, exc)

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
            row = self._db.fetchone(
                "SELECT COUNT(*) as count FROM workflow_definitions WHERE user_id = ?", (user_id,)
            )
        else:
            row = self._db.fetchone("SELECT COUNT(*) as count FROM workflow_definitions")
        return row["count"] if row else 0

    def export_workflow(self, workflow_id: int) -> dict | None:
        """Exporta un workflow completo como dict JSON-serializable."""
        wf = self.get(workflow_id)
        if not wf:
            return None
        return {
            "export_version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "name": wf.name,
            "description": wf.description,
            "trigger_type": wf.trigger_type,
            "trigger_config": wf.trigger_config,
            "steps": wf.steps,
            "status": wf.status,
        }

    def import_workflow(self, data: dict) -> WorkflowDefinition:
        """Importa un workflow desde un dict generado por export_workflow()."""
        name = (data.get("name") or "").strip()
        if not name:
            name = "Workflow importado"

        trigger_type = data.get("trigger_type", "manual")
        trigger_config = data.get("trigger_config") or {}
        steps = data.get("steps")

        if steps is not None and not isinstance(steps, list):
            raise ValueError("campo 'steps' debe ser una lista")

        steps = steps or []
        steps = [{**step, "id": i + 1} if isinstance(step, dict) else step for i, step in enumerate(steps)]

        known_tools = {
            "crm", "invoice", "inventory", "notification", "system",
            "autopilot", "logic_gate", "api_connector", "data_keeper",
        }
        for step in steps:
            tool = step.get("tool", "")
            if tool and tool not in known_tools:
                logger.warning(
                    "Import: tool desconocida '%s' en paso %s - "
                    "se importará igual, pero puede fallar en ejecución",
                    tool, step.get("id"),
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
        logger.info("Workflow importado: %s (ID: %s)", wf.name, wf.id)
        return wf

    def create_from_dict(self, data: dict) -> WorkflowDefinition:
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

    def get_active_scheduled(self) -> list[WorkflowDefinition]:
        """Obtiene todos los workflows activos con trigger schedule."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_definitions
               WHERE status = 'active' AND trigger_type = 'schedule'"""
        )
        return [WorkflowDefinition.from_dict(r) for r in rows]

    def get_active_webhooks(self) -> list[WorkflowDefinition]:
        """Obtiene todos los workflows activos con trigger webhook."""
        rows = self._db.fetchall(
            """SELECT * FROM workflow_definitions
               WHERE status = 'active' AND trigger_type = 'webhook'"""
        )
        return [WorkflowDefinition.from_dict(r) for r in rows]

    def get_stats(self, user_id: int | None = None) -> dict:
        """Retorna estadísticas para el dashboard."""
        if user_id:
            total = self._db.fetchone(
                "SELECT COUNT(*) as count FROM workflow_definitions WHERE user_id = ?", (user_id,)
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
                {"id": r["id"], "name": r["name"], "status": r["status"], "started_at": r["started_at"]}
                for r in recent
            ],
            "orbital_mode": True,
        }
