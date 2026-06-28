"""
Zenic-Flujo — Tenant Storage Provisioning
==========================================

Aprovisionamiento y desaprovisionamiento de almacenamiento de datos
por tenant. Soporta dos modos de aislamiento:

- schema: tablas con prefijo en BD compartida (SMB)
- database: archivo .db separado por tenant (Enterprise)
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path
from typing import Any

from src.core.config import DATA_DIR
from src.core.db import DatabaseManager, safe_drop_table_if_exists, validate_identifier
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# Planes disponibles con sus configuraciones
TENANT_PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "max_workflows": 3,
        "max_users": 2,
        "max_executions_per_day": 100,
        "features": ["basic_workflow", "crm"],
        "db_isolation": "schema",
    },
    "smb": {
        "max_workflows": 50,
        "max_users": 25,
        "max_executions_per_day": 5000,
        "features": ["basic_workflow", "crm", "inventory", "invoice", "sso"],
        "db_isolation": "schema",
    },
    "enterprise": {
        "max_workflows": -1,
        "max_users": -1,
        "max_executions_per_day": -1,
        "features": ["all"],
        "db_isolation": "database",
    },
}

TENANT_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS {prefix}workflow_definitions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        description     TEXT,
        trigger_type    TEXT NOT NULL,
        trigger_config  TEXT NOT NULL,
        steps           TEXT NOT NULL,
        status          TEXT DEFAULT 'active',
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id         INTEGER
    );

    CREATE TABLE IF NOT EXISTS {prefix}workflow_executions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_id     INTEGER NOT NULL,
        status          TEXT NOT NULL,
        trigger_data    TEXT,
        started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at    TIMESTAMP,
        duration_ms     INTEGER,
        error_message   TEXT,
        user_id         INTEGER
    );

    CREATE TABLE IF NOT EXISTS {prefix}users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT UNIQUE NOT NULL,
        password_hash   TEXT NOT NULL,
        role            TEXT DEFAULT 'admin',
        display_name    TEXT,
        email           TEXT,
        is_active       INTEGER DEFAULT 1,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at   TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS {prefix}settings (
        key             TEXT PRIMARY KEY,
        value           TEXT NOT NULL
    );
"""

TENANT_DATABASE_SQL = """
    CREATE TABLE IF NOT EXISTS workflow_definitions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        description     TEXT,
        trigger_type    TEXT NOT NULL,
        trigger_config  TEXT NOT NULL,
        steps           TEXT NOT NULL,
        status          TEXT DEFAULT 'active',
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id         INTEGER
    );

    CREATE TABLE IF NOT EXISTS workflow_executions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workflow_id     INTEGER NOT NULL,
        status          TEXT NOT NULL,
        trigger_data    TEXT,
        started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at    TIMESTAMP,
        duration_ms     INTEGER,
        error_message   TEXT,
        user_id         INTEGER
    );

    CREATE TABLE IF NOT EXISTS workflow_step_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        execution_id    INTEGER NOT NULL,
        step_id         INTEGER NOT NULL,
        tool            TEXT NOT NULL,
        action          TEXT NOT NULL,
        input_data      TEXT,
        output_data     TEXT,
        status          TEXT NOT NULL,
        started_at      TIMESTAMP,
        completed_at    TIMESTAMP,
        duration_ms     INTEGER,
        error_message   TEXT,
        retry_count     INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        username        TEXT UNIQUE NOT NULL,
        password_hash   TEXT NOT NULL,
        role            TEXT DEFAULT 'admin',
        display_name    TEXT,
        email           TEXT,
        is_active       INTEGER DEFAULT 1,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at   TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS settings (
        key             TEXT PRIMARY KEY,
        value           TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS leads (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        email           TEXT,
        phone           TEXT,
        company         TEXT,
        stage           TEXT DEFAULT 'new',
        source          TEXT,
        notes           TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id         INTEGER
    );

    CREATE TABLE IF NOT EXISTS products (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        sku             TEXT UNIQUE,
        name            TEXT NOT NULL,
        description     TEXT,
        category        TEXT,
        stock           INTEGER DEFAULT 0,
        min_stock       INTEGER DEFAULT 10,
        price           REAL,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
"""


class TenantStorageProvisioner:
    """
    Aprovisiona y desaprovisiona almacenamiento de datos por tenant.

    Soporta dos modos:
    - schema: tablas con prefijo en BD compartida (free, SMB)
    - database: archivo SQLite separado por tenant (Enterprise)
    """

    def __init__(self) -> None:
        self._db = DatabaseManager()

    def provision(self, tenant_id: str, slug: str, db_type: str) -> dict[str, Any]:
        """
        Aprovisiona almacenamiento para un tenant.

        Args:
            tenant_id: ID del tenant
            slug: Slug del tenant
            db_type: Tipo de aislamiento ('schema' o 'database')

        Returns:
            dict con status, db_type y connection_string
        """
        if db_type == "schema":
            return self._provision_schema(tenant_id, slug)
        elif db_type == "database":
            return self._provision_database(tenant_id, slug)
        else:
            return {"status": "error", "message": f"Tipo de aislamiento invalido: {db_type}"}

    def deprovision(self, tenant_id: str, db_type: str, connection_string: str) -> None:
        """
        Elimina el almacenamiento de datos de un tenant.

        Args:
            tenant_id: ID del tenant
            db_type: Tipo de aislamiento
            connection_string: String de conexion
        """
        if db_type == "schema":
            self._deprovision_schema(connection_string)
        elif db_type == "database":
            self._deprovision_database(connection_string)

    def get_connection(self, tenant_id: str, db_type: str, connection_string: str) -> sqlite3.Connection | None:
        """
        Obtiene una conexion a la BD del tenant.

        Args:
            tenant_id: ID del tenant
            db_type: Tipo de aislamiento
            connection_string: String de conexion

        Returns:
            sqlite3.Connection o None
        """
        if db_type == "database":
            parts = connection_string.split(":", 1)
            if len(parts) >= 2 and parts[0] == "sqlite":
                db_path = Path(parts[1])
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys=ON")
                    return conn

        # Para schema, retornar la conexion compartida
        return self._db.get_connection()

    # ── Schema isolation ──────────────────────────────────

    def _provision_schema(self, tenant_id: str, slug: str) -> dict[str, Any]:
        """Aprovisiona un schema con prefijo en la BD compartida.

        Fix Sprint 3 bug #42: antes usaba .format(prefix=prefix) sin validar
        que el prefijo fuera un identificador SQL válido. Si slug provenía
        de user input malicioso, podía causar SQL injection en DDL.
        Ahora valida con regex estricta antes del .format().
        """
        import re
        # Validar slug: solo [a-z0-9-] y longitud razonable
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,63}$", slug):
            raise ValueError(
                f"slug inválido: {slug!r} — debe ser [a-z0-9][a-z0-9-]{{0,63}}"
            )

        conn = self._db.get_connection()
        cursor = conn.cursor()
        prefix = f"t_{slug.replace('-', '_')}_"

        # Validar prefix resultante: debe ser identificador SQL válido
        if not re.match(r"^[a-z][a-z0-9_]{1,67}$", prefix):
            raise ValueError(
                f"prefix resultante inválido: {prefix!r}"
            )

        cursor.executescript(TENANT_SCHEMA_SQL.format(prefix=prefix))  # nosec B608 — prefix validado
        conn.commit()

        connection_string = f"sqlite:shared:{prefix}"
        self._db.execute(
            "INSERT INTO tenant_databases (tenant_id, db_type, connection_string) VALUES (?, 'schema', ?)",
            (tenant_id, connection_string),
        )
        self._db.commit()

        logger.info(f"Tenant: Schema aprovisionado para {tenant_id} (prefix={prefix})")
        return {"status": "ok", "db_type": "schema", "connection_string": connection_string}

    def _deprovision_schema(self, connection_string: str) -> None:
        """Elimina tablas con prefijo de la BD compartida.

        SEGURIDAD: El nombre de cada tabla se valida con `validate_identifier`
        (regex `^[A-Za-z_][A-Za-z0-9_]{0,127}$`) y se dropea vía
        `safe_drop_table_if_exists`, que usa quote-style de SQLite. Esto mitiga
        Bandit B608 (SQL injection via string concatenation) y B607 (partial path).

        El prefijo del tenant se pasa como parámetro `?` al SELECT inicial —
        no se interpola. Los nombres de tabla retornados por sqlite_master
        vienen de la propia BD (no de input externo), pero el patrón de
        validación defende en profundidad contra compromisos de la BD.
        """
        parts = connection_string.split(":")
        if len(parts) >= 3:
            prefix = parts[2]
            conn = self._db.get_connection()
            cursor = conn.cursor()
            tables = self._db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                (f"{prefix}%",),
            )
            for table in tables:
                table_name = table["name"]
                try:
                    validate_identifier(table_name)
                except ValueError:
                    logger.warning(f"Tenant: Nombre de tabla invalido ignorado: {table_name}")
                    continue
                # Mitigación B608: usar helper con quote + validación estricta
                # en vez de concatenación manual de strings.
                safe_drop_table_if_exists(cursor, table_name)
            conn.commit()
            logger.info(f"Tenant: Tablas con prefijo '{prefix}' eliminadas")

    # ── Database isolation ────────────────────────────────

    def _provision_database(self, tenant_id: str, slug: str) -> dict[str, Any]:
        """Aprovisiona un archivo .db dedicado para un tenant."""
        db_path = DATA_DIR / "tenants" / f"{slug}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        tenant_conn = sqlite3.connect(str(db_path))
        tenant_conn.execute("PRAGMA journal_mode=WAL")
        tenant_conn.execute("PRAGMA foreign_keys=ON")
        tenant_conn.executescript(TENANT_DATABASE_SQL)
        tenant_conn.commit()
        tenant_conn.close()

        connection_string = f"sqlite:{db_path}"
        self._db.execute(
            "INSERT INTO tenant_databases (tenant_id, db_type, connection_string) VALUES (?, 'database', ?)",
            (tenant_id, connection_string),
        )
        self._db.commit()

        logger.info(f"Tenant: BD dedicada aprovisionada para {tenant_id} (path={db_path})")
        return {"status": "ok", "db_type": "database", "connection_string": connection_string}

    def _deprovision_database(self, connection_string: str) -> None:
        """Elimina el archivo .db de un tenant."""
        parts = connection_string.split(":", 1)
        if len(parts) >= 2 and parts[0] == "sqlite":
            db_path = Path(parts[1])
            if db_path.exists():
                db_path.unlink()
                logger.info(f"Tenant: BD eliminada: {db_path}")


class TenantConnectionPool:
    """
    Pool de conexiones a BD de tenants.

    Mantiene conexiones reutilizables para tenants con BD dedicada.
    """

    def __init__(self) -> None:
        self._connections: dict[str, sqlite3.Connection] = {}
        self._provisioner = TenantStorageProvisioner()

    def get_connection(self, tenant_id: str, db_type: str, connection_string: str) -> sqlite3.Connection | None:
        """
        Obtiene o crea una conexion para un tenant.

        Reutiliza conexiones existentes si estan activas.

        Args:
            tenant_id: ID del tenant
            db_type: Tipo de aislamiento
            connection_string: String de conexion

        Returns:
            sqlite3.Connection o None
        """
        if tenant_id in self._connections:
            try:
                conn = self._connections[tenant_id]
                conn.execute("SELECT 1")
                return conn
            except Exception:
                del self._connections[tenant_id]

        conn = self._provisioner.get_connection(tenant_id, db_type, connection_string)
        if conn and db_type == "database":
            self._connections[tenant_id] = conn
        return conn

    def close_all(self) -> None:
        """Cierra todas las conexiones del pool."""
        for _tenant_id, conn in self._connections.items():
            with contextlib.suppress(Exception):
                conn.close()
        self._connections.clear()
        logger.info("Tenant: Todas las conexiones de BD cerradas")

    def close(self, tenant_id: str) -> None:
        """Cierra la conexion de un tenant especifico."""
        conn = self._connections.pop(tenant_id, None)
        if conn:
            with contextlib.suppress(Exception):
                conn.close()
