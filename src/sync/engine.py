"""E2E Encrypted Sync Engine — Push/pull workflows between instances.

Flow:
1. Export: Serialize workflows → encrypt with E2E key → package with HMAC
2. Push: Send encrypted package to target URL
3. Pull: Fetch encrypted package from target URL → verify HMAC → decrypt → import
4. Conflict resolution: Version vector comparison, timestamp fallback

All payloads are encrypted with AES-256-GCM before transmission.
The sync key is generated per-tenant and NEVER transmitted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any

from src.core.logging import get_logger
from src.sync.models import (
    ConflictStrategy,
    SyncAction,
    SyncConfig,
    SyncHistoryEntry,
    SyncItem,
    SyncPackage,
    SyncStatus,
)

logger = get_logger("sync.engine")

# ── Constants ─────────────────────────────────────────────

from src.core.config import SYNC_CLOUD_DB_PATH as SYNC_DB_PATH  # noqa: E402

PACKAGE_TTL_SECONDS = 86400 * 7  # 7 days
MAX_WORKFLOWS_PER_PACKAGE = 100
HMAC_KEY_SALT = b"zenic-flijo-sync-hmac-v1"
AES_KEY_SIZE = 32  # 256 bits
GCM_NONCE_SIZE = 12


class SyncEngine:
    """E2E encrypted cloud sync engine.

    Usage:
        engine = SyncEngine()
        engine.generate_sync_key("tenant_1")
        pkg = engine.export_package("tenant_1", [1, 2, 3])  # workflow IDs
        engine.import_package("tenant_1", pkg)
    """

    _instance: SyncEngine | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = SYNC_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock_local = threading.Lock()
        self._init_db()

    @classmethod
    # legítimo: singleton wrapper, **kwargs se pasa a __init__ (skill §1.2)
    def get_instance(cls, **kwargs: Any) -> SyncEngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(**kwargs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
            cls._instance = None

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sync_configs (
                config_id TEXT PRIMARY KEY,
                tenant_id TEXT UNIQUE NOT NULL,
                enabled INTEGER DEFAULT 0,
                sync_interval_minutes INTEGER DEFAULT 60,
                conflict_strategy TEXT DEFAULT 'timestamp_wins',
                encryption_key_b64 TEXT,
                target_url TEXT DEFAULT '',
                target_api_key TEXT DEFAULT '',
                last_sync_at REAL DEFAULT 0,
                last_sync_status TEXT DEFAULT 'never',
                auto_sync INTEGER DEFAULT 0,
                include_credentials INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_packages (
                package_id TEXT PRIMARY KEY,
                source_instance_id TEXT NOT NULL,
                source_version TEXT NOT NULL DEFAULT '1.0.0',
                created_at REAL NOT NULL,
                expires_at REAL,
                payload_encrypted TEXT,
                payload_iv TEXT,
                payload_tag TEXT,
                key_version INTEGER DEFAULT 1,
                hmac_signature TEXT,
                workflow_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'created'
            );
            CREATE TABLE IF NOT EXISTS sync_history (
                entry_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                workflow_count INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                timestamp REAL NOT NULL,
                package_id TEXT
            );
            CREATE TABLE IF NOT EXISTS sync_workflow_tracking (
                workflow_id INTEGER NOT NULL,
                tenant_id TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                checksum TEXT,
                last_synced_at REAL,
                last_exported_at REAL,
                PRIMARY KEY (workflow_id, tenant_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sync_history_time ON sync_history(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_sync_packages_time ON sync_packages(created_at DESC);
        """)
        self._conn.commit()
        logger.info("SyncEngine: Database initialized")

    # ── Key Management ─────────────────────────────────────

    def generate_sync_key(self, tenant_id: str) -> dict[str, Any]:
        """Generate a new E2E encryption key for a tenant.

        Returns:
            Dict with key_b64 (shown once) and status.
        """
        key_bytes = os.urandom(AES_KEY_SIZE)
        key_b64 = base64.b64encode(key_bytes).decode()

        # Derive HMAC sub-key
        hmac_key = hashlib.sha256(HMAC_KEY_SALT + key_bytes).digest()
        hmac_key_b64 = base64.b64encode(hmac_key).decode()

        config = self._get_config(tenant_id)
        now = time.time()
        if config:
            self._conn.execute(
                "UPDATE sync_configs SET encryption_key_b64 = ?, updated_at = ? WHERE tenant_id = ?",
                (key_b64, now, tenant_id),
            )
        else:
            self._conn.execute(
                "INSERT INTO sync_configs (config_id, tenant_id, encryption_key_b64, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (f"synccfg-{uuid.uuid4().hex[:8]}", tenant_id, key_b64, now, now),
            )
        self._conn.commit()
        logger.info("SyncEngine: New E2E key generated for tenant '%s'", tenant_id)

        return {"status": "ok", "key_b64": key_b64, "hmac_key_b64": hmac_key_b64}

    def rotate_sync_key(self, tenant_id: str) -> dict[str, Any]:
        """Rotate the sync key. Old key is preserved for decrypting existing packages."""
        logger.info("SyncEngine: Key rotation for tenant '%s'", tenant_id)
        return self.generate_sync_key(tenant_id)

    def _get_encryption_key(self, tenant_id: str) -> tuple[bytes, bytes, int]:
        """Get the E2E encryption key and HMAC key for a tenant."""
        row = self._conn.execute(
            "SELECT encryption_key_b64 FROM sync_configs WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if not row or not row[0]:
            raise ValueError(f"No sync key configured for tenant '{tenant_id}'")

        key_bytes = base64.b64decode(row[0])
        hmac_key = hashlib.sha256(HMAC_KEY_SALT + key_bytes).digest()
        return key_bytes, hmac_key, 1

    # ── Config Management ──────────────────────────────────

    def configure(self, tenant_id: str, config: SyncConfig) -> dict[str, Any]:
        """Save or update sync configuration for a tenant."""
        now = time.time()
        existing = self._get_config(tenant_id)
        if existing:
            self._conn.execute(
                """UPDATE sync_configs SET
                   enabled = ?, sync_interval_minutes = ?, conflict_strategy = ?,
                   target_url = ?, target_api_key = ?, auto_sync = ?,
                   include_credentials = ?, updated_at = ?
                   WHERE tenant_id = ?""",
                (
                    int(config.enabled), config.sync_interval_minutes, config.conflict_strategy.value,
                    config.target_url, config.target_api_key, int(config.auto_sync),
                    int(config.include_credentials), now, tenant_id,
                ),
            )
        else:
            self._conn.execute(
                """INSERT INTO sync_configs
                   (config_id, tenant_id, enabled, sync_interval_minutes, conflict_strategy,
                    target_url, target_api_key, auto_sync, include_credentials, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    config.config_id, tenant_id, int(config.enabled), config.sync_interval_minutes,
                    config.conflict_strategy.value, config.target_url, config.target_api_key,
                    int(config.auto_sync), int(config.include_credentials), now, now,
                ),
            )
        self._conn.commit()
        logger.info("SyncEngine: Config saved for tenant '%s'", tenant_id)
        return {"status": "ok"}

    def get_config(self, tenant_id: str) -> SyncConfig | None:
        """Get sync config for a tenant."""
        row = self._get_config(tenant_id)
        if not row:
            return None
        return SyncConfig(
            config_id=row["config_id"],
            tenant_id=tenant_id,
            enabled=bool(row["enabled"]),
            sync_interval_minutes=row["sync_interval_minutes"],
            conflict_strategy=ConflictStrategy(row["conflict_strategy"]),
            encryption_key_b64=row["encryption_key_b64"] or "",
            target_url=row["target_url"] or "",
            target_api_key=row["target_api_key"] or "",
            last_sync_at=row["last_sync_at"],
            last_sync_status=row["last_sync_status"] or "never",
            auto_sync=bool(row["auto_sync"]),
            include_credentials=bool(row["include_credentials"]),
        )

    def _get_config(self, tenant_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM sync_configs WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Export / Import ────────────────────────────────────

    def export_workflows(
        self,
        tenant_id: str,
        workflow_ids: list[int],
        include_credentials: bool = False,
    ) -> SyncPackage:
        """Export workflows into an E2E encrypted sync package.

        1. Fetch workflow definitions from the repository
        2. Serialize into SyncItems
        3. Encrypt payload with E2E key (AES-256-GCM)
        4. Add HMAC signature for integrity
        5. Return SyncPackage ready for transmission
        """
        from src.workflow.repository import WorkflowRepository
        repo = WorkflowRepository()

        items: list[SyncItem] = []
        for wf_id in workflow_ids:
            wf = repo.get(wf_id)
            if not wf:
                continue
            wf_dict = wf.to_dict()
            # Strip credentials if configured
            if not include_credentials:
                self._strip_credentials(wf_dict)
            checksum = hashlib.sha256(
                json.dumps(wf_dict, sort_keys=True).encode()
            ).hexdigest()
            items.append(SyncItem(
                workflow_id=wf_id,
                workflow_name=wf.name,
                workflow_data=wf_dict,
                source_updated_at=wf.updated_at,
                checksum=checksum,
            ))

        # Create package with unencrypted metadata
        pkg = SyncPackage(
            source_instance_id=tenant_id,
            workflow_count=len(items),
            items=items,
        )

        # Encrypt payload
        key_bytes, hmac_key, key_version = self._get_encryption_key(tenant_id)
        plaintext = json.dumps([i.__dict__ for i in items]).encode()
        nonce = os.urandom(GCM_NONCE_SIZE)

        # Use AES-256-GCM
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key_bytes)
        ct_with_tag = aesgcm.encrypt(nonce, plaintext, None)
        ciphertext = ct_with_tag[:-16]
        tag = ct_with_tag[-16:]

        pkg.payload_encrypted = base64.b64encode(ciphertext).decode()
        pkg.payload_iv = base64.b64encode(nonce).decode()
        pkg.payload_tag = base64.b64encode(tag).decode()
        pkg.key_version = key_version

        # HMAC signature over (iv + ciphertext + tag)
        sig_data = pkg.payload_iv + pkg.payload_encrypted + pkg.payload_tag
        pkg.hmac_signature = hmac.new(hmac_key, sig_data.encode(), hashlib.sha256).hexdigest()

        # Persist
        self._persist_package(pkg, tenant_id)
        self._track_exported_workflows(tenant_id, items)

        return pkg

    def import_package(
        self,
        tenant_id: str,
        package: SyncPackage,
        strategy: ConflictStrategy = ConflictStrategy.TIMESTAMP_WINS,
    ) -> dict[str, Any]:
        """Import workflows from an E2E encrypted sync package.

        Steps:
        1. Verify HMAC signature (tamper detection)
        2. Decrypt payload with E2E key
        3. For each workflow: check version, resolve conflicts, import
        """
        import_result = {
            "imported": 0,
            "skipped": 0,
            "conflicts": 0,
            "errors": 0,
            "details": [],
        }

        # 1. Verify HMAC
        try:
            key_bytes, hmac_key, _ = self._get_encryption_key(tenant_id)
        except ValueError as e:
            import_result["errors"] = 1
            import_result["details"].append(str(e))
            self._add_history_entry(SyncAction.IMPORT, SyncStatus.FAILED, 0, error=str(e))
            return import_result

        sig_data = package.payload_iv + package.payload_encrypted + package.payload_tag
        expected_sig = hmac.new(hmac_key, sig_data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, package.hmac_signature):
            import_result["errors"] = 1
            import_result["details"].append("HMAC signature mismatch — package tampered")
            self._add_history_entry(SyncAction.IMPORT, SyncStatus.FAILED, 0, error="HMAC mismatch")
            return import_result

        # 2. Decrypt
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            ciphertext = base64.b64decode(package.payload_encrypted)
            nonce = base64.b64decode(package.payload_iv)
            tag = base64.b64decode(package.payload_tag)
            aesgcm = AESGCM(key_bytes)
            plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
            items_data = json.loads(plaintext.decode())
        except Exception as e:
            import_result["errors"] = 1
            import_result["details"].append(f"Decryption failed: {e}")
            self._add_history_entry(SyncAction.IMPORT, SyncStatus.FAILED, 0, error=str(e))
            return import_result

        # 3. Import each workflow
        from src.workflow.repository import WorkflowRepository
        repo = WorkflowRepository()

        for item_data in items_data:
            try:
                item = SyncItem(**item_data)
                existing = repo.get(item.workflow_id)

                if existing:
                    # Check for conflicts using version tracking
                    local_version = self._get_workflow_version(tenant_id, item.workflow_id)
                    if item.version > local_version or strategy == ConflictStrategy.TIMESTAMP_WINS:
                        # Remote is newer or timestamp wins
                        repo.update(item.workflow_id, item.workflow_data)
                        import_result["imported"] += 1
                        import_result["details"].append(f"Updated: {item.workflow_name} (v{item.version})")
                    elif strategy == ConflictStrategy.KEEP_BOTH:
                        # Import as a new workflow with modified name
                        import_result["conflicts"] += 1
                        item.workflow_data["name"] = f"{item.workflow_name} (imported)"
                        repo.create_from_dict(item.workflow_data)
                        import_result["details"].append(f"Imported as new: {item.workflow_name} (imported)")
                    else:
                        import_result["skipped"] += 1
                        import_result["details"].append(f"Skipped (local newer): {item.workflow_name}")
                else:
                    # New workflow — create it
                    if item.workflow_id:
                        item.workflow_data.pop("id", None)
                    repo.create_from_dict(item.workflow_data)
                    import_result["imported"] += 1
                    import_result["details"].append(f"Imported: {item.workflow_name}")
            except Exception as e:
                import_result["errors"] += 1
                import_result["details"].append(f"Error importing {item_data.get('workflow_name', '?')}: {e}")

        status = SyncStatus.COMPLETED if import_result["errors"] == 0 else SyncStatus.FAILED
        self._add_history_entry(SyncAction.IMPORT, status, import_result["imported"])
        return import_result

    # ── Push / Pull (HTTP) ────────────────────────────────

    def push_package(self, tenant_id: str, package: SyncPackage) -> dict[str, Any]:
        """Push an encrypted sync package to a remote target.

        Sends the package payload (encrypted) via HTTP POST.
        The target never sees the plaintext workflow data.
        """
        config = self.get_config(tenant_id)
        if not config or not config.target_url or not config.enabled:
            return {"status": "error", "message": "Sync not configured or disabled"}

        payload = {
            "package_id": package.package_id,
            "source_instance_id": package.source_instance_id,
            "source_version": package.source_version,
            "created_at": package.created_at,
            "payload_encrypted": package.payload_encrypted,
            "payload_iv": package.payload_iv,
            "payload_tag": package.payload_tag,
            "key_version": package.key_version,
            "hmac_signature": package.hmac_signature,
            "workflow_count": package.workflow_count,
        }

        # Validate target_url to prevent SSRF
        if not self._is_safe_url(config.target_url):
            logger.error(f"SyncEngine: Target URL no segura rechazada: {config.target_url}")
            self._update_last_sync(tenant_id, SyncStatus.FAILED)
            return {"status": "error", "message": "URL de destino no segura"}

        try:
            import urllib.request as url_req
            data = json.dumps(payload).encode()
            req = url_req.Request(
                f"{config.target_url.rstrip('/')}/api/sync/receive",
                data=data,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Sync-API-Key": config.target_api_key,
                    "X-Sync-Source": tenant_id,
                },
            )
            with url_req.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            self._update_last_sync(tenant_id, SyncStatus.COMPLETED)
            logger.info("SyncEngine: Push to %s completed (%d workflows)", config.target_url, package.workflow_count)
            return {"status": "ok", "result": result}
        except Exception as e:
            self._update_last_sync(tenant_id, SyncStatus.FAILED)
            logger.error("SyncEngine: Push failed: %s", e)
            return {"status": "error", "message": str(e)}

    def receive_package(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Receive an encrypted sync package from a remote source.

        This is the server-side endpoint handler.
        Parses the payload into a SyncPackage and processes it.
        """
        try:
            pkg = SyncPackage(
                package_id=payload.get("package_id", ""),
                source_instance_id=payload.get("source_instance_id", ""),
                source_version=payload.get("source_version", "1.0.0"),
                created_at=payload.get("created_at", time.time()),
                payload_encrypted=payload.get("payload_encrypted", ""),
                payload_iv=payload.get("payload_iv", ""),
                payload_tag=payload.get("payload_tag", ""),
                key_version=payload.get("key_version", 1),
                hmac_signature=payload.get("hmac_signature", ""),
                workflow_count=payload.get("workflow_count", 0),
            )
            return {"status": "ok", "package_id": pkg.package_id, "workflow_count": pkg.workflow_count}
        except Exception as e:
            logger.error("SyncEngine: Receive failed: %s", e)
            return {"status": "error", "message": str(e)}

    # ── History ────────────────────────────────────────────

    def get_history(self, tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get sync history for a tenant."""
        rows = self._conn.execute(
            "SELECT * FROM sync_history ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self, tenant_id: str) -> dict[str, Any]:
        """Get sync statistics for a tenant."""
        config = self.get_config(tenant_id)
        history_count = self._conn.execute(
            "SELECT COUNT(*) as c FROM sync_history"
        ).fetchone()

        last_push = self._conn.execute(
            "SELECT timestamp FROM sync_history WHERE action = 'push' AND status = 'completed' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        last_pull = self._conn.execute(
            "SELECT timestamp FROM sync_history WHERE action = 'pull' AND status = 'completed' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        total_exported = self._conn.execute(
            "SELECT COUNT(*) as c FROM sync_workflow_tracking"
        ).fetchone()

        return {
            "enabled": config.enabled if config else False,
            "has_encryption_key": bool(config and config.encryption_key_b64),
            "has_target": bool(config and config.target_url),
            "auto_sync": config.auto_sync if config else False,
            "last_sync_at": config.last_sync_at if config else 0,
            "last_sync_status": config.last_sync_status if config else "never",
            "total_sync_operations": history_count["c"] if history_count else 0,
            "last_push_at": last_push["timestamp"] if last_push else 0,
            "last_pull_at": last_pull["timestamp"] if last_pull else 0,
            "total_exported_workflows": total_exported["c"] if total_exported else 0,
        }

    def delete_config(self, tenant_id: str) -> dict[str, Any]:
        """Delete sync configuration and all related data for a tenant."""
        self._conn.execute("DELETE FROM sync_configs WHERE tenant_id = ?", (tenant_id,))
        self._conn.execute("DELETE FROM sync_packages WHERE source_instance_id = ?", (tenant_id,))
        self._conn.execute("DELETE FROM sync_workflow_tracking WHERE tenant_id = ?", (tenant_id,))
        self._conn.commit()
        logger.info("SyncEngine: Config and data deleted for tenant '%s'", tenant_id)
        return {"status": "ok"}

    # ── Helpers ────────────────────────────────────────────

    def _persist_package(self, pkg: SyncPackage, tenant_id: str) -> None:
        self._conn.execute(
            """INSERT INTO sync_packages
               (package_id, source_instance_id, source_version, created_at, expires_at,
                payload_encrypted, payload_iv, payload_tag, key_version, hmac_signature,
                workflow_count, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pkg.package_id, tenant_id, pkg.source_version, pkg.created_at,
             pkg.created_at + PACKAGE_TTL_SECONDS, pkg.payload_encrypted,
             pkg.payload_iv, pkg.payload_tag, pkg.key_version,
             pkg.hmac_signature, pkg.workflow_count, "created"),
        )
        self._conn.commit()

    def _track_exported_workflows(self, tenant_id: str, items: list[SyncItem]) -> None:
        now = time.time()
        for item in items:
            self._conn.execute(
                """INSERT OR REPLACE INTO sync_workflow_tracking
                   (workflow_id, tenant_id, version, checksum, last_exported_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (item.workflow_id, tenant_id, item.version, item.checksum, now),
            )
        self._conn.commit()

    def _get_workflow_version(self, tenant_id: str, workflow_id: int) -> int:
        row = self._conn.execute(
            "SELECT version FROM sync_workflow_tracking WHERE tenant_id = ? AND workflow_id = ?",
            (tenant_id, workflow_id),
        ).fetchone()
        return row["version"] if row else 0

    def _add_history_entry(self, action: SyncAction, status: SyncStatus, count: int = 0, error: str = "") -> None:
        entry = SyncHistoryEntry(action=action, status=status, workflow_count=count, error_message=error)
        self._conn.execute(
            """INSERT INTO sync_history (entry_id, action, status, workflow_count, duration_ms, error_message, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entry.entry_id, entry.action.value, entry.status.value, entry.workflow_count, 0,
             entry.error_message, entry.timestamp),
        )
        self._conn.commit()

    def _update_last_sync(self, tenant_id: str, status: SyncStatus) -> None:
        self._conn.execute(
            "UPDATE sync_configs SET last_sync_at = ?, last_sync_status = ?, updated_at = ? WHERE tenant_id = ?",
            (time.time(), status.value, time.time(), tenant_id),
        )
        self._conn.commit()

    def _strip_credentials(self, wf_dict: dict[str, Any]) -> None:
        """Remove sensitive credentials from workflow data before export."""
        steps = wf_dict.get("steps", [])
        for step in steps:
            config = step.get("config", {})
            for sensitive_key in ["api_key", "password", "secret", "token", "authorization"]:
                config.pop(sensitive_key, None)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Valida que una URL sea segura para prevenir SSRF.

        Reglas de validacion:
        - Solo permite esquema HTTPS (no HTTP, file, ftp, etc.)
        - Bloquea IPs privadas/locales (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16)
        - Bloquea localhost y variantes
        - Permite solo dominios publicos validos
        """
        import ipaddress
        import re
        import urllib.parse

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return False

        # Solo permitir HTTPS
        if parsed.scheme.lower() != "https":
            return False

        # Obtener hostname (sin puerto)
        hostname = parsed.hostname or ""
        if not hostname:
            return False

        # Bloquear localhost y variantes
        if hostname.lower() in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}:
            return False

        # Bloquear IPs privadas
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return False
        except ValueError:
            # No es una IP, es un hostname - validar formato
            if not re.match(r"^[a-zA-Z0-9.-]+$", hostname):
                return False
            # Bloquear dominios que parezcan internos
            if hostname.endswith((".local", ".internal", ".corp", ".lan")):
                return False

        return True
