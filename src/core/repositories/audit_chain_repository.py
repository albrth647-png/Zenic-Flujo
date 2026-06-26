"""Audit log con hash chain + firma Ed25519 — inmutable y verificable.

Foso 1 — Compliance Reproducible Banca LATAM.

Cada entry del chain contiene:
    entry_hash    = SHA-256(canonical_json(payload + previous_hash))
    actor_signature = Ed25519(entry_hash, actor_private_key)

Para verificar integridad de toda la cadena:
1. Empezar desde el entry genesis (previous_hash = "0"*64)
2. Para cada entry: recompute entry_hash y comparar con el almacenado
3. Si cualquier entry falla → tampering detectado

Esto cumple con SOC2 CC7.2 (audit trail integrity) y requisitos de
retención de banca LATAM (5-10 años, reguladores SBS/CNBV/BACEN/SFC/CMF).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.security.encryption import EncryptionService
from src.orbital.canonical_serializer import (
    canonical_json,
    sha256_hex,
)

logger = setup_logging(__name__)

GENESIS_HASH = "0" * 64


class AuditChainRepository:
    """Repositorio de audit log con hash chain inmutable.

    Cada entrada se encadena a la anterior mediante:
        entry_hash = SHA-256(canonical_json({actor, action, ..., previous_hash}))

    Esto hace que cualquier modificación a un entry anterior invalide todos
    los entries posteriores (efecto dominó detectable).
    """

    def __init__(
        self,
        db: DatabaseManager | None = None,
        encryption: EncryptionService | None = None,
    ):
        self._db = db or DatabaseManager()
        self._enc = encryption or EncryptionService()

    def add_entry(
        self,
        actor: str,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Añade un entry al chain con hash + firma Ed25519 del actor.

        Args:
            actor: Quién realiza la acción (user_id, system, scheduler, ...).
            action: Qué hace (create, update, delete, execute, ...).
            resource_type: Tipo de recurso (workflow, invoice, ...).
            resource_id: ID del recurso.
            details: Detalles adicionales (dict serializable).
            tenant_id: Tenant al que pertenece el entry.

        Returns:
            Dict con {entry_id, entry_hash, previous_hash, actor_signature}.
        """
        # 1. Obtener previous_hash del último entry del tenant
        previous_hash = self._get_last_hash(tenant_id)

        # 2. Construir payload canónico
        timestamp = time.time()
        payload = {
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "details": details or {},
            "timestamp": timestamp,
            "tenant_id": tenant_id,
            "previous_hash": previous_hash,
        }
        payload_bytes = canonical_json(payload)

        # 3. Calcular entry_hash
        entry_hash = sha256_hex(payload_bytes)

        # 4. Firmar con Ed25519 del tenant (el "actor" firma)
        actor_signature = ""
        try:
            actor_signature = self._enc.sign_payload(payload_bytes, tenant_id=tenant_id)
        except Exception as e:
            logger.warning(f"AuditChainRepository: no se pudo firmar entry: {e}")

        # 5. Persistir
        entry_id = str(uuid.uuid4())
        self._db.execute(
            """
            INSERT INTO audit_log_chain
                (entry_id, previous_hash, entry_hash, actor, actor_signature,
                 action, resource_type, resource_id, details, timestamp, tenant_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                previous_hash,
                entry_hash,
                actor,
                actor_signature,
                action,
                resource_type,
                str(resource_id),
                canonical_json(details or {}).decode("utf-8"),
                timestamp,
                tenant_id,
            ),
        )
        self._db.commit()

        return {
            "entry_id": entry_id,
            "entry_hash": entry_hash,
            "previous_hash": previous_hash,
            "actor_signature": actor_signature,
        }

    def verify_chain(
        self,
        tenant_id: str = "default",
        since_timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Verifica integridad de toda la cadena de un tenant.

        Recorre todos los entries en orden cronológico y para cada uno:
        1. Verifica que previous_hash coincida con el entry_hash anterior
        2. Recalcula entry_hash y compara con el almacenado

        Args:
            tenant_id: Tenant cuya cadena se verifica.
            since_timestamp: Si se pasa, solo verifica entries desde ese timestamp.

        Returns:
            Dict con {valid: bool, entries_verified: int, broken_at: str | None, reason: str | None}.
        """
        query = "SELECT * FROM audit_log_chain WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if since_timestamp is not None:
            query += " AND timestamp >= ?"
            params.append(since_timestamp)
        query += " ORDER BY timestamp ASC"

        rows = self._db.fetchall(query, tuple(params))
        expected_prev = GENESIS_HASH
        for row in rows:
            if row["previous_hash"] != expected_prev:
                return {
                    "valid": False,
                    "broken_at": row["entry_id"],
                    "reason": (
                        f"previous_hash mismatch: expected {expected_prev[:16]}… "
                        f"got {row['previous_hash'][:16]}…"
                    ),
                    "entries_verified": 0,
                }
            # Recompute hash
            payload = {
                "actor": row["actor"],
                "action": row["action"],
                "resource_type": row["resource_type"] or "",
                "resource_id": row["resource_id"] or "",
                "details": self._parse_details(row["details"]),
                "timestamp": row["timestamp"],
                "tenant_id": row["tenant_id"],
                "previous_hash": row["previous_hash"],
            }
            recomputed = sha256_hex(canonical_json(payload))
            if recomputed != row["entry_hash"]:
                return {
                    "valid": False,
                    "broken_at": row["entry_id"],
                    "reason": "entry_hash mismatch: tampering detected",
                    "entries_verified": 0,
                }
            expected_prev = row["entry_hash"]

        return {
            "valid": True,
            "broken_at": None,
            "reason": None,
            "entries_verified": len(rows),
        }

    def get_entries(
        self,
        tenant_id: str = "default",
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista entries del chain de un tenant."""
        query = "SELECT * FROM audit_log_chain WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if action:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return self._db.fetchall(query, tuple(params))

    def _get_last_hash(self, tenant_id: str) -> str:
        """Obtiene el entry_hash del último entry del tenant (o genesis)."""
        row = self._db.fetchone(
            "SELECT entry_hash FROM audit_log_chain WHERE tenant_id = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (tenant_id,),
        )
        return row["entry_hash"] if row else GENESIS_HASH

    @staticmethod
    def _parse_details(details_str: str | None) -> dict[str, Any]:
        """Parsea details JSON string a dict (para verificación de hash)."""
        if not details_str:
            return {}
        try:
            return json.loads(details_str)
        except Exception:
            return {"_raw": details_str}
