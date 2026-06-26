"""
Durable Heartbeat — Heartbeat management for durable execution
===============================================================

Extraído de durable.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.workflow.durable_models import HEARTBEAT_TIMEOUT_SECONDS

logger = setup_logging(__name__)


def send_heartbeat(db: DatabaseManager, execution_id: int, step_id: int,
                   worker_id: str, progress: float = 0.0) -> None:
    """Envía un heartbeat para un paso en ejecución."""
    now = datetime.now(UTC).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO workflow_heartbeats (execution_id, step_id, worker_id, last_heartbeat, progress) "
        "VALUES (?, ?, ?, ?, ?)",
        (execution_id, step_id, worker_id, now, progress))
    db.commit()


def check_heartbeats(db: DatabaseManager) -> list[dict]:
    """Detecta pasos colgados (sin heartbeat reciente)."""
    timeout_cutoff = datetime.now(UTC).timestamp() - HEARTBEAT_TIMEOUT_SECONDS
    rows = db.fetchall("SELECT * FROM workflow_heartbeats")
    hung_steps = []
    for row in rows:
        try:
            hb_time = datetime.fromisoformat(row["last_heartbeat"]).timestamp()
        except (ValueError, TypeError):
            continue
        if hb_time < timeout_cutoff:
            hung_steps.append({
                "execution_id": row["execution_id"], "step_id": row["step_id"],
                "worker_id": row["worker_id"], "last_heartbeat": row["last_heartbeat"],
                "progress": row["progress"],
                "hung_for_seconds": int(datetime.now(UTC).timestamp() - hb_time),
            })
    if hung_steps:
        logger.warning(f"check_heartbeats: {len(hung_steps)} paso(s) hung detectados")
    return hung_steps
