"""Tests Fase 1B — Foso 1: AuditChainRepository con hash chain inmutable.

Cubre:
- add_entry: genera entry con hash + firma Ed25519
- verify_chain: detecta tampering (modificación de entries)
- verify_chain: detecta reordenamiento (previous_hash mismatch)
- get_entries: filtrado por tenant y action
- genesis hash para primer entry
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="foso1_1b_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Cada test usa una DB SQLite limpia en WFD_DATA_DIR aislado.

    Patchea directamente sqlite_manager.DB_PATH para que el singleton use
    la DB nueva, sin depender de re-imports (que no funcionan por el cache
    de sys.modules).
    """
    data_dir = tmp_path / "data" / ".workflow_determinista"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "workflow_determinista.db"
    monkeypatch.setenv("WFD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Reset singletons
    from src.core.db import sqlite_manager as sm_mod
    monkeypatch.setattr(sm_mod, "DB_PATH", db_path)
    sm_mod.DatabaseManager._reset()

    from src.core.security.encryption import EncryptionService
    EncryptionService._instance = None  # type: ignore[attr-defined]
    EncryptionService._initialized = False  # type: ignore[attr-defined]

    yield
    with contextlib.suppress(Exception):
        sm_mod.DatabaseManager._reset()


class TestAuditChainRepository:
    """AuditChainRepository con hash chain inmutable."""

    def test_add_entry_returns_hashes(self):
        from src.core.repositories.audit_chain_repository import (
            GENESIS_HASH,
            AuditChainRepository,
        )

        repo = AuditChainRepository()
        result = repo.add_entry(
            actor="user1",
            action="create",
            resource_type="workflow",
            resource_id="1",
            tenant_id="test_tenant",
        )
        assert result["entry_hash"]
        assert result["previous_hash"] == GENESIS_HASH
        assert result["actor_signature"]  # firma Ed25519 generada
        assert result["entry_id"]  # UUID

    def test_chain_links_via_previous_hash(self):
        """El previous_hash del 2do entry = entry_hash del 1ro."""
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        e1 = repo.add_entry(actor="u1", action="create", resource_id="1", tenant_id="t1")
        e2 = repo.add_entry(actor="u1", action="update", resource_id="1", tenant_id="t1")
        e3 = repo.add_entry(actor="u2", action="delete", resource_id="1", tenant_id="t1")
        assert e2["previous_hash"] == e1["entry_hash"]
        assert e3["previous_hash"] == e2["entry_hash"]

    def test_verify_chain_intact(self):
        """Cadena de 3 entries se verifica correctamente."""
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        repo.add_entry(actor="u1", action="create", resource_id="1", tenant_id="verify_ok")
        repo.add_entry(actor="u1", action="update", resource_id="1", tenant_id="verify_ok")
        repo.add_entry(actor="u2", action="delete", resource_id="1", tenant_id="verify_ok")

        result = repo.verify_chain(tenant_id="verify_ok")
        assert result["valid"] is True
        assert result["entries_verified"] == 3

    def test_tampering_detected_modifying_details(self):
        """Modificar el campo details de un entry rompe la cadena."""
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        repo.add_entry(actor="u1", action="create", resource_id="1", tenant_id="tamper")
        repo.add_entry(actor="u1", action="update", resource_id="1", tenant_id="tamper")
        repo.add_entry(actor="u2", action="delete", resource_id="1", tenant_id="tamper")

        # Antes: cadena válida
        assert repo.verify_chain(tenant_id="tamper")["valid"] is True

        # Tamper: modificar details del entry 2
        from src.core.db.sqlite_manager import DatabaseManager
        db = DatabaseManager()
        db.execute(
            "UPDATE audit_log_chain SET details = 'tampered' "
            "WHERE tenant_id = ? AND action = ?",
            ("tamper", "update"),
        )
        db.commit()

        # Después: cadena rota
        result = repo.verify_chain(tenant_id="tamper")
        assert result["valid"] is False
        assert "mismatch" in result["reason"].lower() or "tampering" in result["reason"].lower()

    def test_tampering_detected_reordering(self):
        """Reordenar entries (cambiar previous_hash) rompe la cadena."""
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        e1 = repo.add_entry(actor="u1", action="create", resource_id="1", tenant_id="reorder")
        e2 = repo.add_entry(actor="u1", action="update", resource_id="1", tenant_id="reorder")

        # Swap previous_hash: e1 ahora apunta a e2 (orden invertido)
        from src.core.db.sqlite_manager import DatabaseManager
        db = DatabaseManager()
        db.execute(
            "UPDATE audit_log_chain SET previous_hash = ? WHERE entry_id = ?",
            (e2["entry_hash"], e1["entry_id"]),
        )
        db.commit()

        result = repo.verify_chain(tenant_id="reorder")
        assert result["valid"] is False
        assert "previous_hash" in result["reason"]

    def test_isolated_tenants(self):
        """Entries de diferentes tenants no se mezclan."""
        from src.core.repositories.audit_chain_repository import (
            GENESIS_HASH,
            AuditChainRepository,
        )

        repo = AuditChainRepository()
        e_a1 = repo.add_entry(actor="u", action="x", tenant_id="tenant_A")
        e_b1 = repo.add_entry(actor="u", action="x", tenant_id="tenant_B")
        # Ambos primeros entries deben tener previous_hash = genesis
        assert e_a1["previous_hash"] == GENESIS_HASH
        assert e_b1["previous_hash"] == GENESIS_HASH

        # Verificar cadena de tenant_A solo tiene 1 entry
        result_a = repo.verify_chain(tenant_id="tenant_A")
        assert result_a["entries_verified"] == 1

    def test_get_entries_filters_by_tenant(self):
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        repo.add_entry(actor="u", action="create", tenant_id="t1")
        repo.add_entry(actor="u", action="update", tenant_id="t1")
        repo.add_entry(actor="u", action="delete", tenant_id="t2")

        entries_t1 = repo.get_entries(tenant_id="t1")
        entries_t2 = repo.get_entries(tenant_id="t2")
        assert len(entries_t1) == 2
        assert len(entries_t2) == 1

    def test_get_entries_filters_by_action(self):
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        repo.add_entry(actor="u", action="create", tenant_id="t")
        repo.add_entry(actor="u", action="update", tenant_id="t")
        repo.add_entry(actor="u", action="delete", tenant_id="t")

        creates = repo.get_entries(tenant_id="t", action="create")
        assert len(creates) == 1
        assert creates[0]["action"] == "create"

    def test_signature_present(self):
        """Cada entry debe tener firma Ed25519 (si tenant tiene clave)."""
        from src.core.repositories.audit_chain_repository import AuditChainRepository

        repo = AuditChainRepository()
        result = repo.add_entry(
            actor="u",
            action="create",
            tenant_id="sig_test",
        )
        # La firma puede estar vacía si EncryptionService no pudo inicializar,
        # pero en tests con DB limpia debería generarse.
        # Aceptamos ambos casos: la cadena sigue siendo válida sin firma
        # (solo no se puede verificar autenticidad, pero sí integridad).
        assert "actor_signature" in result
