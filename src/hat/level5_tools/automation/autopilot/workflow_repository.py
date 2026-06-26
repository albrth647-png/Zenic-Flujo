"""
ORBITAL — WorkflowRepository (Fachada Pública)
================================================

Punto de entrada único para CRUD de workflows. Delega en 3 submódulos:

• :mod:`._definitions_repo` — WorkflowDefinition + CRUD de definiciones
• :mod:`._executions_repo`  — WorkflowExecution + ejecuciones + step logs
• :mod:`._orbital_adapter`  — Conversión Orbital

Retrocompatible: todas las importaciones existentes siguen funcionando.
    from ...workflow_repository import WorkflowDefinition, WorkflowExecution, WorkflowRepository

Evolución: 1 archivo (545 L) → 4 archivos (150 L c/u)
"""

from src.hat.level5_tools.automation.autopilot._definitions_repo import (
    WorkflowDefinition,
    WorkflowDefinitionRepository,
)
from src.hat.level5_tools.automation.autopilot._executions_repo import (
    WorkflowExecution,
    WorkflowExecutionRepository,
)
from src.hat.level5_tools.automation.autopilot._orbital_adapter import (
    WorkflowOrbitalAdapter,
)
from src.core.logging import setup_logging
from src.core.db import DatabaseManager

logger = setup_logging(__name__)


class WorkflowRepository:
    """Repositorio unificado — delega en repos específicos.

    API pública (retrocompatible):
    - create / get / list_all / update / delete / count
    - export_workflow / import_workflow / create_from_dict
    - get_active_scheduled / get_active_webhooks / get_stats
    - create_execution / complete_execution / get_execution / list_executions
    - save_step_log / get_step_logs
    - to_orbital / get_orbital_stats
    """

    def __init__(self):
        self._db = DatabaseManager()
        self._definitions = WorkflowDefinitionRepository(db=self._db)
        self._executions = WorkflowExecutionRepository(db=self._db)
        self._orbital = WorkflowOrbitalAdapter(db=self._db)

    # ── Workflow Definitions ─────────────────────────────────────────

    def create(self, definition: WorkflowDefinition, user_id: int | None = None) -> WorkflowDefinition:
        return self._definitions.create(definition, user_id=user_id)

    def get(self, workflow_id: int) -> WorkflowDefinition | None:
        return self._definitions.get(workflow_id)

    def list_all(self, status: str | None = None, user_id: int | None = None) -> list[WorkflowDefinition]:
        return self._definitions.list_all(status=status, user_id=user_id)

    def update(
        self,
        workflow_id: int,
        updates: dict,
        create_version: bool = False,
        change_summary: str = "",
        user_id: int | None = None,
    ) -> WorkflowDefinition | None:
        return self._definitions.update(
            workflow_id, updates,
            create_version=create_version,
            change_summary=change_summary,
            user_id=user_id,
        )

    def delete(self, workflow_id: int) -> bool:
        return self._definitions.delete(workflow_id)

    def count(self, user_id: int | None = None) -> int:
        return self._definitions.count(user_id=user_id)

    def export_workflow(self, workflow_id: int) -> dict | None:
        return self._definitions.export_workflow(workflow_id)

    def import_workflow(self, data: dict) -> WorkflowDefinition:
        return self._definitions.import_workflow(data)

    def create_from_dict(self, data: dict) -> WorkflowDefinition:
        return self._definitions.create_from_dict(data)

    def get_active_scheduled(self) -> list[WorkflowDefinition]:
        return self._definitions.get_active_scheduled()

    def get_active_webhooks(self) -> list[WorkflowDefinition]:
        return self._definitions.get_active_webhooks()

    def get_stats(self, user_id: int | None = None) -> dict:
        return self._definitions.get_stats(user_id=user_id)

    # ── Workflow Executions ──────────────────────────────────────────

    def create_execution(self, workflow_id: int, trigger_data: dict | None = None) -> WorkflowExecution:
        return self._executions.create_execution(workflow_id, trigger_data=trigger_data)

    def complete_execution(
        self,
        execution_id: int,
        duration_ms: int,
        error_message: str | None = None,
    ) -> None:
        return self._executions.complete_execution(execution_id, duration_ms, error_message=error_message)

    def get_execution(self, execution_id: int) -> WorkflowExecution | None:
        return self._executions.get_execution(execution_id)

    def list_executions(self, workflow_id: int, limit: int = 50) -> list[WorkflowExecution]:
        return self._executions.list_executions(workflow_id, limit=limit)

    def save_step_log(self, **kwargs) -> None:
        return self._executions.save_step_log(**kwargs)

    def get_step_logs(self, execution_id: int) -> list[dict]:
        return self._executions.get_step_logs(execution_id)

    # ── Orbital Conversion ───────────────────────────────────────────

    def to_orbital(self, workflow_id: int) -> dict | None:
        return self._orbital.to_orbital(workflow_id, definition_getter=self._get_for_orbital)

    def get_orbital_stats(self) -> dict:
        return self._orbital.get_orbital_stats()

    def _get_for_orbital(self, workflow_id: int) -> dict | None:
        """Obtiene dict para conversión orbital (compat con WorkflowOrbitalAdapter)."""
        wf = self._definitions.get(workflow_id)
        return wf.to_dict() if wf else None

    def __repr__(self) -> str:
        return f"<WorkflowRepository delegating to defs+execs+orbital>"
