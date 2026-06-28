"""Sync data models — Package format and configuration for E2E encrypted cloud sync."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SyncAction(Enum):
    """Type of sync operation."""
    EXPORT = "export"
    IMPORT = "import"
    PUSH = "push"
    PULL = "pull"


class SyncStatus(Enum):
    """Status of a sync operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"


class ConflictStrategy(Enum):
    """Conflict resolution strategy."""
    TIMESTAMP_WINS = "timestamp_wins"
    VERSION_WINS = "version_wins"
    KEEP_BOTH = "keep_both"


@dataclass
class SyncPackage:
    """An encrypted sync package containing workflow definitions and metadata.

    The package contains:
    - Metadata: source instance, timestamp, version vector
    - Payload: workflow definitions (encrypted)
    - Signature: HMAC for integrity verification
    """
    package_id: str = ""
    source_instance_id: str = ""
    source_version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    payload_encrypted: str = ""  # AES-256-GCM encrypted JSON
    payload_iv: str = ""  # IV/nonce for decryption
    payload_tag: str = ""  # Auth tag for integrity
    key_version: int = 1
    hmac_signature: str = ""  # HMAC-SHA256 for tamper detection
    workflow_count: int = 0
    items: list[SyncItem] = field(default_factory=list)
    conflicts: list[SyncConflict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.package_id:
            self.package_id = f"syncpkg-{uuid.uuid4().hex[:12]}"


@dataclass
class SyncItem:
    """A single item in a sync operation (one workflow)."""
    item_id: str = ""
    workflow_id: int = 0
    workflow_name: str = ""
    workflow_data: dict[str, Any] = field(default_factory=dict)
    source_updated_at: str = ""
    checksum: str = ""  # SHA-256 of serialized workflow
    version: int = 1

    def __post_init__(self) -> None:
        if not self.item_id:
            self.item_id = f"syncitem-{uuid.uuid4().hex[:8]}"
        if not self.checksum and self.workflow_data:
            self.checksum = hashlib.sha256(
                json.dumps(self.workflow_data, sort_keys=True).encode()
            ).hexdigest()


@dataclass
class SyncConflict:
    """A conflict detected during sync."""
    conflict_id: str = ""
    workflow_id: int = 0
    local_version: int = 0
    remote_version: int = 0
    local_checksum: str = ""
    remote_checksum: str = ""
    resolved: bool = False
    resolution: str = ""  # "keep_local", "keep_remote", "keep_both"

    def __post_init__(self) -> None:
        if not self.conflict_id:
            self.conflict_id = f"syncconf-{uuid.uuid4().hex[:8]}"


@dataclass
class SyncConfig:
    """Configuration for sync operations (per-tenant, optional, E2E encrypted)."""
    config_id: str = ""
    tenant_id: str = ""
    enabled: bool = False
    sync_interval_minutes: int = 60
    conflict_strategy: ConflictStrategy = ConflictStrategy.TIMESTAMP_WINS
    encryption_key_b64: str = ""  # AES-256 key (32 bytes, base64)
    target_url: str = ""
    target_api_key: str = ""  # Encrypted with tenant key
    last_sync_at: float = 0.0
    last_sync_status: str = "never"
    auto_sync: bool = False
    include_credentials: bool = False  # Strip credentials from exported workflows
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.config_id:
            self.config_id = f"synccfg-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, masking secrets."""
        return {
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "enabled": self.enabled,
            "sync_interval_minutes": self.sync_interval_minutes,
            "conflict_strategy": self.conflict_strategy.value,
            "has_encryption_key": bool(self.encryption_key_b64),
            "target_url": self.target_url,
            "has_target_api_key": bool(self.target_api_key),
            "last_sync_at": self.last_sync_at,
            "last_sync_status": self.last_sync_status,
            "auto_sync": self.auto_sync,
            "include_credentials": self.include_credentials,
        }


@dataclass
class SyncHistoryEntry:
    """An entry in the sync history log."""
    entry_id: str = ""
    action: SyncAction = SyncAction.PUSH
    status: SyncStatus = SyncStatus.PENDING
    workflow_count: int = 0
    duration_ms: int = 0
    error_message: str = ""
    timestamp: float = field(default_factory=time.time)
    package_id: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            self.entry_id = f"synchist-{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "action": self.action.value,
            "status": self.status.value,
            "workflow_count": self.workflow_count,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "package_id": self.package_id,
        }
