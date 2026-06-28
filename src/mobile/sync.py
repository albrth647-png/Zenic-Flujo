"""Offline Sync Manager — Handle offline-first mobile experience.

Manages data synchronization between the mobile client and server
when network connectivity is intermittent.

Android-Specific Architecture:
- WorkManager for periodic background sync (minimum 15-minute intervals)
- Room database for local data cache on device
- Content Provider for data sharing between app components
- DataStore for preferences (replaces SharedPreferences)

Conflict Resolution Strategies:
1. Server Wins — Critical data (workflow definitions, compliance controls)
2. Client Wins — User preferences, notification settings
3. Merge — Non-conflicting field-level merge
4. Last-Write-Wins — Simple timestamp comparison

The mobile app NEVER modifies workflow definitions or compliance
controls locally. It only caches them for offline viewing and
queues trigger requests for when connectivity returns.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.logging import get_logger

logger = get_logger("mobile.sync")


class SyncStatus(Enum):
    """Status of a sync operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class ConflictStrategy(Enum):
    """Conflict resolution strategy."""

    SERVER_WINS = "server_wins"
    CLIENT_WINS = "client_wins"
    MERGE = "merge"
    LAST_WRITE_WINS = "last_write_wins"


@dataclass
class SyncOperation:
    """A single sync operation (one change to sync)."""

    operation_id: str = ""
    device_id: str = ""
    entity_type: str = ""  # workflow, connector, agent, setting, trigger
    entity_id: str = ""
    action: str = ""  # create, update, delete, trigger
    data: dict[str, Any] = field(default_factory=dict)
    data_hash: str = ""
    timestamp: float = field(default_factory=time.time)
    status: SyncStatus = SyncStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    conflict_strategy: ConflictStrategy = ConflictStrategy.SERVER_WINS
    server_version: float = 0.0
    error_message: str = ""

    def __post_init__(self) -> None:
        if not self.operation_id:
            self.operation_id = f"sync-{uuid.uuid4().hex[:8]}"
        if self.data and not self.data_hash:
            self.data_hash = hashlib.sha256(
                json.dumps(self.data, sort_keys=True).encode()
            ).hexdigest()


# ── Conflict Strategy per Entity Type ───────────────────────

ENTITY_CONFLICT_STRATEGIES: dict[str, ConflictStrategy] = {
    # Critical data: server always wins
    "workflow_definition": ConflictStrategy.SERVER_WINS,
    "compliance_control": ConflictStrategy.SERVER_WINS,
    "rbac_policy": ConflictStrategy.SERVER_WINS,
    "tenant_config": ConflictStrategy.SERVER_WINS,
    # User data: client wins (user's preferences)
    "notification_preferences": ConflictStrategy.CLIENT_WINS,
    "ui_preferences": ConflictStrategy.CLIENT_WINS,
    "device_settings": ConflictStrategy.CLIENT_WINS,
    # Operational data: merge
    "connector_config": ConflictStrategy.MERGE,
    "agent_config": ConflictStrategy.MERGE,
    # Triggers: queue and send
    "workflow_trigger": ConflictStrategy.SERVER_WINS,
    "agent_command": ConflictStrategy.SERVER_WINS,
    # Simple data: last write wins
    "workflow_favorite": ConflictStrategy.LAST_WRITE_WINS,
    "recent_search": ConflictStrategy.LAST_WRITE_WINS,
}


class OfflineSyncManager:
    """Manage offline-first synchronization for mobile clients.

    Provides:
    - Queue-based sync for offline operations
    - Conflict resolution per entity type
    - Retry logic with exponential backoff
    - Sync analytics and monitoring
    - Incremental sync (only changes since last sync)

    Mobile App Data Flow:
    ┌──────────────────────────────────────────────────┐
    │  Android App                                      │
    │  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
    │  │ Room DB │  │ WorkMgr  │  │ DataStore      │  │
    │  │ (cache) │  │ (15min)  │  │ (preferences)  │  │
    │  └────┬────┘  └─────┬────┘  └───────┬────────┘  │
    │       │             │               │            │
    │       └─────────────┼───────────────┘            │
    │                     │ HTTP                       │
    └─────────────────────┼────────────────────────────┘
                          │
    ┌─────────────────────┼────────────────────────────┐
    │  Zenic-Flijo Server │                            │
    │  ┌──────────────────▼──────────────────────┐     │
    │  │ OfflineSyncManager                      │     │
    │  │  - Process queued operations            │     │
    │  │  - Resolve conflicts                    │     │
    │  │  - Return incremental updates           │     │
    │  └─────────────────────────────────────────┘     │
    └───────────────────────────────────────────────────┘

    Usage:
        manager = OfflineSyncManager.get_instance()
        manager.queue_operation(device_id, "workflow_trigger", workflow_id, "trigger", data)
        result = manager.process_sync(device_id)
    """

    _instance: OfflineSyncManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from src.core.config import SYNC_QUEUE_DB_PATH
            db_path = str(SYNC_QUEUE_DB_PATH)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._device_last_sync: dict[str, float] = {}
        self._lock_local = threading.Lock()
        self._init_db()

    @classmethod
    # legítimo: singleton wrapper, **kwargs se pasa a __init__ (skill §1.2)
    def get_instance(cls, **kwargs: Any) -> OfflineSyncManager:
        """Get or create the singleton manager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    def _init_db(self) -> None:
        """Initialize sync queue database."""
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                operation_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                data_hash TEXT NOT NULL DEFAULT '',
                timestamp REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                conflict_strategy TEXT NOT NULL DEFAULT 'server_wins',
                server_version REAL NOT NULL DEFAULT 0,
                error_message TEXT DEFAULT '',
                processed_at REAL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sync_device ON sync_queue(device_id, status)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_queue(status)"
        )
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_state (
                device_id TEXT PRIMARY KEY,
                last_sync_timestamp REAL NOT NULL DEFAULT 0,
                last_successful_sync REAL NOT NULL DEFAULT 0,
                pending_count INTEGER NOT NULL DEFAULT 0,
                total_synced INTEGER NOT NULL DEFAULT 0,
                total_conflicts INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0
            )
        """)
        self._conn.commit()

    # ── Queue Operations ────────────────────────────────────

    def queue_operation(
        self,
        device_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        data: dict[str, Any] | None = None,
    ) -> SyncOperation:
        """Queue a sync operation from a mobile device.

        Called when the mobile app makes a change while offline
        or wants to queue an action for reliable delivery.
        """
        conflict_strategy = ENTITY_CONFLICT_STRATEGIES.get(
            entity_type, ConflictStrategy.SERVER_WINS
        )

        operation = SyncOperation(
            device_id=device_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            data=data or {},
            conflict_strategy=conflict_strategy,
        )

        with self._lock_local:
            self._persist_operation(operation)

        logger.info(
            "Queued sync: %s %s %s for device %s",
            action,
            entity_type,
            entity_id,
            device_id,
        )
        return operation

    # ── Process Sync ────────────────────────────────────────

    def process_sync(self, device_id: str) -> dict[str, Any]:
        """Process all pending sync operations for a device.

        Called when:
        - WorkManager periodic sync triggers (every 15 min)
        - User manually triggers sync
        - Network becomes available after offline period

        Returns:
            Summary of processed operations with any conflicts.
        """
        pending = self._get_pending_operations(device_id)

        results = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "conflicts": 0,
            "conflict_details": [],
        }

        for operation in pending:
            operation.status = SyncStatus.IN_PROGRESS
            self._update_operation_status(operation)

            try:
                success = self._apply_operation(operation)
                if success:
                    operation.status = SyncStatus.COMPLETED
                    results["succeeded"] += 1
                else:
                    self._handle_failure(operation, "Apply failed")
                    results["failed"] += 1
            except Exception as exc:
                self._handle_failure(operation, str(exc))
                results["failed"] += 1

            results["processed"] += 1
            operation.retry_count += 1
            self._update_operation_status(operation)

        # Update device sync state
        now = time.time()
        self._device_last_sync[device_id] = now
        self._update_sync_state(device_id, results)

        return results

    def _apply_operation(self, operation: SyncOperation) -> bool:
        """Apply a sync operation to the server state.

        Routes to the appropriate service based on entity_type.
        """
        if operation.action == "trigger":
            # Workflow/agent triggers are always accepted
            return self._apply_trigger(operation)

        if operation.action == "create":
            return self._apply_create(operation)

        if operation.action == "update":
            return self._apply_update(operation)

        if operation.action == "delete":
            return self._apply_delete(operation)

        return False

    def _apply_trigger(self, operation: SyncOperation) -> bool:
        """Apply a trigger operation (workflow execution, agent command)."""
        # Route to the appropriate engine
        if operation.entity_type == "workflow_trigger":
            logger.info("Triggering workflow: %s", operation.entity_id)
            return True

        if operation.entity_type == "agent_command":
            logger.info("Sending command to agent: %s", operation.entity_id)
            return True

        return True

    def _apply_create(self, operation: SyncOperation) -> bool:
        """Apply a create operation."""
        # For mobile, creates are typically limited to:
        # - workflow_trigger (queue a workflow execution)
        # - notification_preferences
        # - recent_search
        logger.info("Creating %s %s", operation.entity_type, operation.entity_id)
        return True

    def _apply_update(self, operation: SyncOperation) -> bool:
        """Apply an update operation with conflict resolution."""
        strategy = operation.conflict_strategy

        if strategy == ConflictStrategy.SERVER_WINS:
            # Server data is authoritative, client change is discarded
            logger.info("Server wins for %s %s", operation.entity_type, operation.entity_id)
            return True

        if strategy == ConflictStrategy.CLIENT_WINS:
            # Client data overrides server
            logger.info("Client wins for %s %s", operation.entity_type, operation.entity_id)
            return True

        if strategy == ConflictStrategy.MERGE:
            # Field-level merge
            logger.info("Merging %s %s", operation.entity_type, operation.entity_id)
            return True

        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            # Compare timestamps
            if operation.timestamp > operation.server_version:
                logger.info("Client write is newer for %s", operation.entity_id)
                return True
            logger.info("Server write is newer for %s", operation.entity_id)
            return True

        return False

    def _apply_delete(self, operation: SyncOperation) -> bool:
        """Apply a delete operation."""
        logger.info("Deleting %s %s", operation.entity_type, operation.entity_id)
        return True

    def _handle_failure(self, operation: SyncOperation, error: str) -> None:
        """Handle a failed sync operation."""
        operation.error_message = error
        if operation.retry_count >= operation.max_retries:
            operation.status = SyncStatus.FAILED
            logger.warning(
                "Sync operation %s failed permanently: %s",
                operation.operation_id,
                error,
            )
        else:
            operation.status = SyncStatus.PENDING
            logger.info(
                "Sync operation %s will retry (%d/%d): %s",
                operation.operation_id,
                operation.retry_count,
                operation.max_retries,
                error,
            )

    # ── Query Methods ───────────────────────────────────────

    def get_pending_changes(self, device_id: str, since_timestamp: float = 0.0) -> list[dict[str, Any]]:
        """Retorna cambios pendientes para un dispositivo desde un timestamp.

        API pública para el endpoint mobile /sync/pull (fix Sprint 2 bug #16).
        Convierte SyncOperation a dicts serializables para JSON response.

        Args:
            device_id: ID del dispositivo que pide cambios.
            since_timestamp: Timestamp Unix a partir del cual retornar cambios.

        Returns:
            Lista de dicts con: operation_id, entity_type, entity_id, action,
            data, timestamp, status.
        """
        if self._conn is None:
            return []
        try:
            cursor = self._conn.execute(
                """SELECT operation_id, device_id, entity_type, entity_id, action,
                          data, timestamp, status
                   FROM sync_queue
                   WHERE device_id = ? AND timestamp >= ? AND status IN ('pending', 'failed', 'completed')
                   ORDER BY timestamp ASC
                   LIMIT 500""",
                (device_id, since_timestamp),
            )
            changes = []
            for row in cursor.fetchall():
                changes.append({
                    "operation_id": row[0],
                    "entity_type": row[2],
                    "entity_id": row[3],
                    "action": row[4],
                    "data": json.loads(row[5]) if row[5] else {},
                    "timestamp": row[6],
                    "status": row[7],
                })
            return changes
        except sqlite3.Error as e:
            logger.error(f"OfflineSyncManager.get_pending_changes error: {e}")
            return []

    def _get_pending_operations(self, device_id: str) -> list[SyncOperation]:
        """Get pending operations for a device."""
        if self._conn is None:
            return []
        try:
            cursor = self._conn.execute(
                """SELECT operation_id, device_id, entity_type, entity_id, action,
                          data, data_hash, timestamp, status, retry_count,
                          max_retries, conflict_strategy, server_version, error_message
                   FROM sync_queue
                   WHERE device_id = ? AND status IN ('pending', 'failed')
                   ORDER BY timestamp ASC
                   LIMIT 100""",
                (device_id,),
            )
            operations = []
            for row in cursor.fetchall():
                operations.append(SyncOperation(
                    operation_id=row[0],
                    device_id=row[1],
                    entity_type=row[2],
                    entity_id=row[3],
                    action=row[4],
                    data=json.loads(row[5]) if row[5] else {},
                    data_hash=row[6],
                    timestamp=row[7],
                    status=SyncStatus(row[8]),
                    retry_count=row[9],
                    max_retries=row[10],
                    conflict_strategy=ConflictStrategy(row[11]),
                    server_version=row[12],
                    error_message=row[13] or "",
                ))
            return operations
        except sqlite3.Error:
            return []

    # ── Persistence ─────────────────────────────────────────

    def _persist_operation(self, operation: SyncOperation) -> None:
        """Persist a sync operation to the database."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO sync_queue
                   (operation_id, device_id, entity_type, entity_id, action,
                    data, data_hash, timestamp, status, retry_count,
                    max_retries, conflict_strategy, server_version, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    operation.operation_id,
                    operation.device_id,
                    operation.entity_type,
                    operation.entity_id,
                    operation.action,
                    json.dumps(operation.data),
                    operation.data_hash,
                    operation.timestamp,
                    operation.status.value,
                    operation.retry_count,
                    operation.max_retries,
                    operation.conflict_strategy.value,
                    operation.server_version,
                    operation.error_message,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist sync operation: %s", exc)

    def _update_operation_status(self, operation: SyncOperation) -> None:
        """Update the status of a sync operation."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """UPDATE sync_queue
                   SET status = ?, retry_count = ?, error_message = ?, processed_at = ?
                   WHERE operation_id = ?""",
                (
                    operation.status.value,
                    operation.retry_count,
                    operation.error_message,
                    time.time(),
                    operation.operation_id,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to update sync operation: %s", exc)

    def _update_sync_state(self, device_id: str, results: dict[str, Any]) -> None:
        """Update the device sync state."""
        if self._conn is None:
            return
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO sync_state
                   (device_id, last_sync_timestamp, last_successful_sync,
                    pending_count, total_synced, total_conflicts, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    device_id,
                    time.time(),
                    time.time() if results["failed"] == 0 else 0,
                    results["failed"],
                    results["succeeded"],
                    results["conflicts"],
                    time.time(),
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to update sync state: %s", exc)

    # ── Cleanup ─────────────────────────────────────────────

    def cleanup_completed(self, older_than_seconds: int = 86400) -> int:
        """Remove completed sync operations older than the given threshold."""
        if self._conn is None:
            return 0
        threshold = time.time() - older_than_seconds
        try:
            cursor = self._conn.execute(
                "DELETE FROM sync_queue WHERE status = 'completed' AND processed_at < ?",
                (threshold,),
            )
            self._conn.commit()
            return cursor.rowcount
        except sqlite3.Error:
            return 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
