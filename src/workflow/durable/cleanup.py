"""
Durable Cleanup — Limpieza de eventos y checkpoints antiguos
=============================================================

Extraído de durable.py.
"""

from __future__ import annotations

from src.core.db import DatabaseManager
from src.core.logging import setup_logging

logger = setup_logging(__name__)


def cleanup_old_events(db: DatabaseManager, execution_id: int, keep_last: int = 100) -> int:
    """Elimina eventos antiguos manteniendo solo los últimos keep_last."""
    row = db.fetchone("SELECT COUNT(*) as total FROM workflow_events WHERE execution_id = ?", (execution_id,))
    total = row["total"] if row else 0
    if total <= keep_last:
        return 0
    delete_count = total - keep_last
    db.execute(
        "DELETE FROM workflow_events WHERE execution_id = ? AND id NOT IN "
        "(SELECT id FROM workflow_events WHERE execution_id = ? ORDER BY id DESC LIMIT ?)",
        (execution_id, execution_id, keep_last))
    db.commit()
    logger.info(f"cleanup_old_events: {delete_count} eventos eliminados para execution_id={execution_id}")
    return delete_count


def cleanup_old_checkpoints(db: DatabaseManager, execution_id: int, keep_last: int = 5) -> int:
    """Elimina checkpoints antiguos manteniendo solo los últimos keep_last."""
    row = db.fetchone("SELECT COUNT(*) as total FROM workflow_checkpoints WHERE execution_id = ?", (execution_id,))
    total = row["total"] if row else 0
    if total <= keep_last:
        return 0
    delete_count = total - keep_last
    db.execute(
        "DELETE FROM workflow_checkpoints WHERE execution_id = ? AND id NOT IN "
        "(SELECT id FROM workflow_checkpoints WHERE execution_id = ? ORDER BY id DESC LIMIT ?)",
        (execution_id, execution_id, keep_last))
    db.commit()
    logger.info(f"cleanup_old_checkpoints: {delete_count} checkpoints eliminados para execution_id={execution_id}")
    return delete_count
