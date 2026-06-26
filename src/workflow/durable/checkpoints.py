"""
Durable Checkpoints — Checkpoint/snapshot para ejecución duradera
==================================================================

Extraído de durable.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.workflow.durable_models import WorkflowState

logger = setup_logging(__name__)


def save_checkpoint(db: DatabaseManager, state: WorkflowState) -> int:
    """Guarda un checkpoint del estado actual."""
    now = datetime.now(UTC).isoformat()
    state_json = json.dumps(state.to_dict(), default=_json_default)
    cursor = db.execute(
        "INSERT INTO workflow_checkpoints (execution_id, step_index, state, timestamp) VALUES (?, ?, ?, ?)",
        (state.execution_id, state.current_step_index, state_json, now),
    )
    db.commit()
    logger.debug(f"Checkpoint guardado: execution_id={state.execution_id}, step={state.current_step_index}")
    return cursor.lastrowid


def load_latest_checkpoint(db: DatabaseManager, execution_id: int) -> WorkflowState | None:
    """Carga el checkpoint más reciente para una ejecución."""
    row = db.fetchone(
        "SELECT * FROM workflow_checkpoints WHERE execution_id = ? ORDER BY step_index DESC LIMIT 1",
        (execution_id,))
    if not row:
        return None
    return WorkflowState.from_dict(json.loads(row["state"]))


def create_snapshot(db: DatabaseManager, execution_id: int) -> int:
    """Crea un snapshot forzado del estado actual."""
    from src.workflow.durable.events import replay_events
    state = replay_events(db, execution_id)
    return save_checkpoint(db, state)


def get_state(db: DatabaseManager, execution_id: int) -> WorkflowState | None:
    """Obtiene el estado actual, desde checkpoint o event replay."""
    state = load_latest_checkpoint(db, execution_id)
    if state:
        return state
    from src.workflow.durable.events import replay_events
    state = replay_events(db, execution_id)
    if state.execution_id == 0:
        return None
    save_checkpoint(db, state)
    return state


def _json_default(obj: Any) -> str:
    """Serializa objetos no-JSON por defecto."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
