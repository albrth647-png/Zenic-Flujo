"""AsyncExecutionService — ejecución asíncrona de workflows.

Extraído de WorkflowEngine.execute_async() para mantener
engine.py esbelto (~300 líneas).
"""

from __future__ import annotations

from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class AsyncExecutionService:
    """Servicio para encolar workflows en la WorkQueue (Sprint 7-8)."""

    def __init__(self, repository):
        self._repository = repository

    def execute(self, workflow_id: int, trigger_data: dict[str, Any] | None = None, priority: int = 0) -> dict[str, Any]:
        """Encola un workflow para ejecución asíncrona via WorkQueue.

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
            raise ValueError(f"Workflow '{definition.name}' no esta activo (estado: {definition.status})")

        from src.events.work_queue import WorkQueue

        queue = WorkQueue()
        item = queue.enqueue(
            workflow_id=workflow_id,
            trigger_data=trigger_data,
            priority=priority,
        )

        logger.info(f"Workflow {workflow_id} encolado asincronamente (#queue{item.id}, prioridad {priority})")
        return {
            "status": "queued",
            "queue_id": item.id,
            "workflow_id": workflow_id,
            "priority": priority,
        }
