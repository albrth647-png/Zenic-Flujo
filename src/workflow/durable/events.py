"""
Durable Events — Event sourcing para ejecución duradera
========================================================

Extraído de durable.py para mantener DurableExecutor como orquestador delgado.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.workflow.durable_models import EventType, WorkflowEvent, WorkflowState

logger = setup_logging(__name__)


def append_event(db: DatabaseManager, execution_id: int, event_type: str,
                 step_id: int | None = None, data: dict[str, Any] | None = None) -> int:
    """Append un evento al log de event sourcing."""
    now = datetime.now(UTC).isoformat()
    cursor = db.execute(
        "INSERT INTO workflow_events (execution_id, event_type, step_id, data, timestamp) VALUES (?, ?, ?, ?, ?)",
        (execution_id, event_type, step_id, json.dumps(data or {}), now),
    )
    db.commit()
    return cursor.lastrowid


def get_event_log(db: DatabaseManager, execution_id: int) -> list[WorkflowEvent]:
    """Obtiene el log completo de eventos para una ejecución."""
    rows = db.fetchall(
        "SELECT * FROM workflow_events WHERE execution_id = ? ORDER BY id ASC", (execution_id,))
    events = []
    for row in rows:
        events.append(WorkflowEvent(
            id=row["id"], execution_id=row["execution_id"], event_type=row["event_type"],
            step_id=row["step_id"], data=json.loads(row["data"]) if row.get("data") else {},
            timestamp=row["timestamp"],
        ))
    return events


def replay_events(db: DatabaseManager, execution_id: int) -> WorkflowState:
    """Reconstruye el estado a partir del log de eventos."""
    events = get_event_log(db, execution_id)
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
