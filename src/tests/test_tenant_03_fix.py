"""Tests para el fix del bug TENANT-03 (X-Tenant-ID header bypass).

Verifica que ``verify_tenant_ownership`` y ``require_tenant_access``
validan correctamente la pertenencia de un usuario al tenant solicitado
contra la tabla ``user_tenants``. Antes del fix, cualquier usuario
autenticado podía enviar ``X-Tenant-ID: <otro_tenant>`` y acceder a
datos ajenos sin verificación.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="tenant03_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Cada test usa una DB SQLite limpia con la tabla user_tenants creada."""
    data_dir = tmp_path / "data" / ".workflow_determinista"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "workflow_determinista.db"
    monkeypatch.setenv("WFD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HOME", str(tmp_path))

    from src.core.db import sqlite_manager as sm_mod

    monkeypatch.setattr(sm_mod, "DB_PATH", db_path)
    sm_mod.DatabaseManager._reset()

    # Reset singletons dependientes
    from src.core.security.encryption import EncryptionService

    EncryptionService._instance = None  # type: ignore[attr-defined]
    EncryptionService._initialized = False  # type: ignore[attr-defined]

    # Crear tabla 'tenants' (la crea TenantService._ensure_tables lazily;
    # la invocamos aquí para que los tests puedan insertar filas directamente).
    from src.tenant.service import TenantService

    TenantService._instance = None  # type: ignore[attr-defined]
    TenantService()  # fuerza _ensure_tables

    yield

    with contextlib.suppress(Exception):
        sm_mod.DatabaseManager._reset()
    TenantService._instance = None  # type: ignore[attr-defined]


class _FakeRequest:
    """Mock mínimo de starlette.Request para tests de dependencias."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class TestTenant03Fix:
    """Verifica el fix del bypass de X-Tenant-ID."""

    def test_user_belongs_to_own_tenant(self):
        """Usuario con fila en user_tenants pertenece a su tenant."""
        from src.api_v2.dependencies import verify_tenant_ownership
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        # Crear usuario y tenant, y asignar user->tenant_A
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("alice", "hash"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_A", "Tenant A", "tenant-a"))
        db.execute("INSERT INTO user_tenants (user_id, tenant_id, role) VALUES (?, ?, ?)", (1, "tenant_A", "admin"))
        db.commit()

        user = {"user_id": 1, "username": "alice"}
        assert verify_tenant_ownership(user, "tenant_A") is True

    def test_user_cannot_access_other_tenant(self):
        """Usuario de tenant A NO puede acceder a tenant B (bug TENANT-03)."""
        from src.api_v2.dependencies import verify_tenant_ownership
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("alice", "hash"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_A", "Tenant A", "tenant-a"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_B", "Tenant B", "tenant-b"))
        # alice solo tiene acceso a tenant_A, NO a tenant_B
        db.execute("INSERT INTO user_tenants (user_id, tenant_id, role) VALUES (?, ?, ?)", (1, "tenant_A", "admin"))
        db.commit()

        user = {"user_id": 1, "username": "alice"}
        # Sin el fix, un atacante enviaría X-Tenant-ID: tenant_B y bypass.
        assert verify_tenant_ownership(user, "tenant_A") is True
        assert verify_tenant_ownership(user, "tenant_B") is False

    def test_verify_tenant_ownership_rejects_empty_tenant(self):
        """Tenant_id vacío o None debe retornar False (fail-closed)."""
        from src.api_v2.dependencies import verify_tenant_ownership

        user = {"user_id": 1}
        assert verify_tenant_ownership(user, "") is False
        assert verify_tenant_ownership(user, None) is False  # type: ignore[arg-type]

    def test_verify_tenant_ownership_rejects_missing_user_id(self):
        """Usuario sin user_id o inválido debe retornar False."""
        from src.api_v2.dependencies import verify_tenant_ownership

        assert verify_tenant_ownership({}, "tenant_A") is False
        assert verify_tenant_ownership(None, "tenant_A") is False  # type: ignore[arg-type]
        assert verify_tenant_ownership({"user_id": None}, "tenant_A") is False

    def test_require_tenant_access_forbids_cross_tenant(self):
        """require_tenant_access levanta 403 cuando el usuario no pertenece al tenant."""
        from fastapi import HTTPException

        from src.api_v2.dependencies import require_tenant_access
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("alice", "hash"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_A", "Tenant A", "tenant-a"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_B", "Tenant B", "tenant-b"))
        db.execute("INSERT INTO user_tenants (user_id, tenant_id, role) VALUES (?, ?, ?)", (1, "tenant_A", "admin"))
        db.commit()

        user = {"user_id": 1, "username": "alice"}
        # Atacante envía X-Tenant-ID: tenant_B (al que no pertenece)
        request = _FakeRequest({"X-Tenant-ID": "tenant_B"})

        with pytest.raises(HTTPException) as exc:
            # require_tenant_access es async; la invocamos directamente.
            import asyncio

            asyncio.get_event_loop().run_until_complete(require_tenant_access(request, user))
        assert exc.value.status_code == 403
        assert "No autorizado" in exc.value.detail

    def test_require_tenant_access_allows_own_tenant(self):
        """require_tenant_access retorna contexto válido cuando el usuario pertenece al tenant."""
        import asyncio

        from src.api_v2.dependencies import require_tenant_access
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("alice", "hash"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_A", "Tenant A", "tenant-a"))
        db.execute("INSERT INTO user_tenants (user_id, tenant_id, role) VALUES (?, ?, ?)", (1, "tenant_A", "admin"))
        db.commit()

        user = {"user_id": 1, "username": "alice"}
        request = _FakeRequest({"X-Tenant-ID": "tenant_A"})

        ctx = asyncio.get_event_loop().run_until_complete(require_tenant_access(request, user))
        assert ctx["tenant_id"] == "tenant_A"
        assert ctx["user"]["user_id"] == 1

    def test_require_tenant_access_requires_header(self):
        """Sin header X-Tenant-ID la dependencia retorna 400."""
        import asyncio

        from fastapi import HTTPException

        from src.api_v2.dependencies import require_tenant_access

        user = {"user_id": 1, "username": "alice"}
        request = _FakeRequest({})

        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(require_tenant_access(request, user))
        assert exc.value.status_code == 400

    def test_user_tenants_table_exists(self):
        """La tabla user_tenants existe tras inicializar la DB."""
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        # Si la tabla no existe, sqlite lanza OperationalError.
        row = db.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='user_tenants'")
        assert row is not None
        assert row["name"] == "user_tenants"

    def test_user_tenants_composite_primary_key(self):
        """La PK compuesta (user_id, tenant_id) impide duplicados."""
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ("alice", "hash"))
        db.execute("INSERT INTO tenants (id, name, slug) VALUES (?, ?, ?)", ("tenant_A", "Tenant A", "tenant-a"))
        db.execute("INSERT INTO user_tenants (user_id, tenant_id, role) VALUES (?, ?, ?)", (1, "tenant_A", "admin"))
        db.commit()

        # Insertar duplicado debe fallar por PK compuesta
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO user_tenants (user_id, tenant_id, role) VALUES (?, ?, ?)",
                (1, "tenant_A", "member"),
            )
            db.commit()
