"""
Workflow Determinista — Multi-Tenancy Service
==============================================

Servicio de multi-tenancy con modelo hibrido: DB-per-tenant (enterprise) y
schema-per-tenant (SMB). Permite aislamiento de datos, resolucion de tenant
por subdominio/dominio/header/sesion, y configuracion por tenant.

Funcionalidades:
- Resolucion de tenant: subdominio, dominio custom, header X-Tenant-ID, sesion
- Gestion de tenants: CRUD, suspender/activar, eliminar con cleanup
- Aislamiento de BD: schema-per-tenant (SQLite/PostgreSQL) o DB-per-tenant (PostgreSQL)
- Propagacion de contexto: thread-local tenant context + middleware Flask
- Feature flags por tenant
- Rate limits por tenant
- Branding custom por tenant (logo, colores, dominio)
- Data residency por tenant (region de almacenamiento)
- Migraciones de schema por tenant

Configuracion via variables de entorno:
- WFD_TENANT_DEFAULT_PLAN: Plan por defecto para nuevos tenants (default: free)
- WFD_TENANT_ADMIN_DB: Path a la BD de administracion (default: auto)
- WFD_TENANT_DOMAIN: Dominio base para resolucion por subdominio (default: zenic-flijo.com)
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, ClassVar

from src.data.database_manager import DatabaseManager
from src.data.redis_service import RedisService
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Constantes ────────────────────────────────────────────────

_DEFAULT_PLAN: str = os.environ.get("WFD_TENANT_DEFAULT_PLAN", "free")
_TENANT_DOMAIN: str = os.environ.get("WFD_TENANT_DOMAIN", "zenic-flijo.com")
_TENANT_CACHE_TTL: int = int(os.environ.get("WFD_TENANT_CACHE_TTL", "3600"))

# Planes disponibles con sus limits
TENANT_PLANS: ClassVar[dict[str, dict]] = {
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

# ── Thread-Local Tenant Context ───────────────────────────────

_tenant_context = threading.local()


def get_current_tenant_id() -> str | None:
    """Obtiene el tenant_id del contexto thread-local actual."""
    return getattr(_tenant_context, "tenant_id", None)


def set_current_tenant_id(tenant_id: str | None) -> None:
    """Establece el tenant_id en el contexto thread-local actual."""
    _tenant_context.tenant_id = tenant_id


def clear_tenant_context() -> None:
    """Limpia el contexto de tenant del thread actual."""
    _tenant_context.tenant_id = None


# ── Tenant Service ────────────────────────────────────────────


class TenantService:
    """Servicio de multi-tenancy con modelo hibrido de aislamiento."""

    _instance: TenantService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> TenantService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._redis = RedisService()
            self._tenant_connections: dict[str, sqlite3.Connection] = {}
            self._ensure_tables()
            logger.info("Tenant Service inicializado")

    # ── Inicializacion de tablas ──────────────────────────

    def _ensure_tables(self) -> None:
        """Crea las tablas de gestion de tenants en la BD de administracion."""
        conn = self._db.get_connection()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                slug        TEXT UNIQUE NOT NULL,
                domain      TEXT,
                plan        TEXT DEFAULT 'free',
                status      TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'deleted')),
                config      TEXT DEFAULT '{}',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tenant_features (
                tenant_id   TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                enabled     INTEGER DEFAULT 1,
                PRIMARY KEY (tenant_id, feature_name),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS tenant_settings (
                tenant_id   TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (tenant_id, key),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE TABLE IF NOT EXISTS tenant_databases (
                tenant_id       TEXT NOT NULL,
                db_type         TEXT NOT NULL CHECK(db_type IN ('schema', 'database')),
                connection_string TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);
            CREATE INDEX IF NOT EXISTS idx_tenants_domain ON tenants(domain);
            CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
            CREATE INDEX IF NOT EXISTS idx_tenant_features_tenant ON tenant_features(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_tenant_settings_tenant ON tenant_settings(tenant_id);
        """)
        conn.commit()

    # ── Gestion de tenants ────────────────────────────────

    def create_tenant(self, name: str, slug: str, plan: str = "free", config: dict | None = None) -> dict:
        """Crea un nuevo tenant y aprovisiona su almacenamiento de datos.

        Args:
            name: Nombre legible del tenant
            slug: Identificador unico URL-safe (ej: 'acme-corp')
            plan: Plan de suscripcion ('free', 'smb', 'enterprise')
            config: Configuracion adicional del tenant

        Returns:
            dict con status y tenant_id
        """
        if plan not in TENANT_PLANS:
            return {"status": "error", "message": f"Plan invalido. Validos: {', '.join(TENANT_PLANS)}"}

        # Verificar slug unico
        existing = self._db.fetchone("SELECT id FROM tenants WHERE slug = ?", (slug,))
        if existing:
            return {"status": "error", "message": f"Slug '{slug}' ya existe"}

        tenant_id = str(uuid.uuid4())
        config = config or {}
        plan_config = TENANT_PLANS[plan]
        config.setdefault("max_workflows", plan_config["max_workflows"])
        config.setdefault("max_users", plan_config["max_users"])
        config.setdefault("max_executions_per_day", plan_config["max_executions_per_day"])

        # Branding default
        config.setdefault(
            "branding",
            {
                "logo_url": "",
                "primary_color": "#4A90D9",
                "secondary_color": "#2C3E50",
            },
        )

        # Data residency
        config.setdefault("data_residency", "us-east-1")

        config_json = json.dumps(config, default=str, ensure_ascii=False)

        # Crear tenant en BD
        self._db.execute(
            "INSERT INTO tenants (id, name, slug, plan, status, config) VALUES (?, ?, ?, ?, 'active', ?)",
            (tenant_id, name, slug, plan, config_json),
        )
        self._db.commit()

        # Aprovisionar almacenamiento de datos
        db_type = plan_config["db_isolation"]
        provision_result = self._provision_tenant_storage(tenant_id, slug, db_type)

        if provision_result.get("status") != "ok":
            # Rollback: eliminar tenant si falla aprovisionamiento
            self._db.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
            self._db.commit()
            return provision_result

        # Habilitar features del plan
        for feature in plan_config["features"]:
            self._db.execute(
                "INSERT OR IGNORE INTO tenant_features (tenant_id, feature_name, enabled) VALUES (?, ?, 1)",
                (tenant_id, feature),
            )
        self._db.commit()

        # Cache en Redis
        self._cache_tenant(
            tenant_id,
            {
                "id": tenant_id,
                "name": name,
                "slug": slug,
                "plan": plan,
                "status": "active",
                "config": config,
            },
        )

        self._db.audit("tenant.created", f"Tenant '{name}' creado (plan={plan}, id={tenant_id})")
        logger.info(f"Tenant: '{name}' creado (plan={plan}, db_type={db_type}, id={tenant_id})")

        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "name": name,
            "slug": slug,
            "plan": plan,
            "db_type": db_type,
        }

    def get_tenant(self, tenant_id: str) -> dict | None:
        """Obtiene la informacion completa de un tenant.

        Verifica primero en cache Redis, luego en BD.

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con datos del tenant, o None si no existe
        """
        # Verificar cache Redis
        cached = self._redis.get_json(f"tenant:{tenant_id}")
        if cached:
            return cached

        # Consultar BD
        row = self._db.fetchone("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        if not row:
            return None

        tenant_data = self._tenant_row_to_dict(row)

        # Cargar features y settings
        tenant_data["features"] = self._get_tenant_features(tenant_id)
        tenant_data["settings"] = self._get_tenant_settings(tenant_id)

        # Cache en Redis
        self._cache_tenant(tenant_id, tenant_data)

        return tenant_data

    def get_tenant_by_slug(self, slug: str) -> dict | None:
        """Obtiene un tenant por su slug."""
        row = self._db.fetchone("SELECT * FROM tenants WHERE slug = ?", (slug,))
        if not row:
            return None
        return self._tenant_row_to_dict(row)

    def resolve_tenant(self, request: Any) -> dict | None:
        """Resuelve el tenant a partir de una request HTTP.

        Orden de resolucion:
        1. Header X-Tenant-ID (para API)
        2. Sesion Flask (si ya se resolvio antes)
        3. Subdominio (tenant.zenic-flijo.com)
        4. Dominio custom

        Args:
            request: Objeto request de Flask

        Returns:
            dict con tenant_id y datos del tenant, o None
        """
        # 1. Header X-Tenant-ID
        tenant_id = request.headers.get("X-Tenant-ID", "")
        if tenant_id:
            tenant = self.get_tenant(tenant_id)
            if tenant and tenant.get("status") == "active":
                return tenant

        # 2. Sesion Flask
        try:
            from flask import session

            session_tenant_id = session.get("tenant_id")
            if session_tenant_id:
                tenant = self.get_tenant(session_tenant_id)
                if tenant and tenant.get("status") == "active":
                    return tenant
        except RuntimeError:
            pass  # No hay contexto de solicitud Flask

        # 3. Subdominio (tenant.zenic-flijo.com)
        host = request.host.split(":")[0]  # Remover puerto
        if host.endswith(f".{_TENANT_DOMAIN}"):
            subdomain = host[: -len(f".{_TENANT_DOMAIN}")]
            if subdomain and subdomain != "www":
                # Buscar por slug = subdomain
                tenant = self.get_tenant_by_slug(subdomain)
                if tenant and tenant.get("status") == "active":
                    return tenant

        # 4. Dominio custom
        tenant_row = self._db.fetchone("SELECT * FROM tenants WHERE domain = ? AND status = 'active'", (host,))
        if tenant_row:
            return self._tenant_row_to_dict(tenant_row)

        return None

    def update_tenant(self, tenant_id: str, updates: dict) -> dict:
        """Actualiza los datos de un tenant.

        Args:
            tenant_id: ID del tenant
            updates: Campos a actualizar (name, domain, plan, config, status)

        Returns:
            dict con status
        """
        existing = self._db.fetchone("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        allowed_fields = {"name", "domain", "plan", "status", "config"}
        set_parts = []
        params = []

        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key == "config":
                value = json.dumps(value, default=str, ensure_ascii=False)
            if key == "plan" and value not in TENANT_PLANS:
                return {"status": "error", "message": f"Plan invalido: {value}"}
            set_parts.append(f"{key} = ?")
            params.append(value)

        if not set_parts:
            return {"status": "ok", "message": "Sin cambios"}

        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        params.append(tenant_id)

        self._db.execute(
            f"UPDATE tenants SET {', '.join(set_parts)} WHERE id = ?",
            tuple(params),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")
        self._redis.delete(f"tenant:slug:{existing.get('slug', '')}")

        self._db.audit("tenant.updated", f"Tenant {tenant_id} actualizado")
        logger.info(f"Tenant: {tenant_id} actualizado")

        return {"status": "ok"}

    def suspend_tenant(self, tenant_id: str) -> dict:
        """Suspende un tenant (no se puede acceder pero se conservan datos).

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con status
        """
        return self._set_tenant_status(tenant_id, "suspended")

    def activate_tenant(self, tenant_id: str) -> dict:
        """Reactiva un tenant suspendido.

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con status
        """
        return self._set_tenant_status(tenant_id, "active")

    def delete_tenant(self, tenant_id: str) -> dict:
        """Elimina un tenant y todos sus datos asociados.

        Advertencia: Esta operacion es irreversible. Elimina:
        - Datos del tenant en la BD de administracion
        - Features y settings del tenant
        - Schema o BD del tenant (segun tipo de aislamiento)
        - Cache Redis del tenant

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con status
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        # 1. Marcar como deleted (soft delete inicial)
        self._db.execute(
            "UPDATE tenants SET status = 'deleted', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (tenant_id,)
        )
        self._db.commit()

        # 2. Eliminar features y settings
        self._db.execute("DELETE FROM tenant_features WHERE tenant_id = ?", (tenant_id,))
        self._db.execute("DELETE FROM tenant_settings WHERE tenant_id = ?", (tenant_id,))

        # 3. Eliminar almacenamiento de datos del tenant
        db_info = self._db.fetchone(
            "SELECT db_type, connection_string FROM tenant_databases WHERE tenant_id = ?", (tenant_id,)
        )
        if db_info:
            try:
                self._deprovision_tenant_storage(tenant_id, db_info["db_type"], db_info["connection_string"])
            except Exception as e:
                logger.error(f"Tenant: Error eliminando almacenamiento de tenant {tenant_id}: {e}")

        self._db.execute("DELETE FROM tenant_databases WHERE tenant_id = ?", (tenant_id,))

        # 4. Eliminar registro del tenant
        self._db.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
        self._db.commit()

        # 5. Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")
        slug = tenant.get("slug", "")
        if slug:
            self._redis.delete(f"tenant:slug:{slug}")

        # 6. Cerrar conexion del tenant si existe
        if tenant_id in self._tenant_connections:
            with contextlib.suppress(Exception):
                self._tenant_connections[tenant_id].close()
            del self._tenant_connections[tenant_id]

        self._db.audit("tenant.deleted", f"Tenant '{tenant.get('name', tenant_id)}' eliminado")
        logger.info(f"Tenant: '{tenant.get('name', tenant_id)}' eliminado completamente")

        return {"status": "ok"}

    def list_tenants(self, status: str | None = None) -> list[dict]:
        """Lista todos los tenants, opcionalmente filtrados por estado.

        Args:
            status: Filtrar por estado ('active', 'suspended', 'deleted')

        Returns:
            Lista de dicts con datos de cada tenant
        """
        if status:
            rows = self._db.fetchall(
                "SELECT * FROM tenants WHERE status = ? ORDER BY name",
                (status,),
            )
        else:
            rows = self._db.fetchall("SELECT * FROM tenants ORDER BY name")

        return [self._tenant_row_to_dict(row) for row in rows]

    def _set_tenant_status(self, tenant_id: str, status: str) -> dict:
        """Establece el estado de un tenant."""
        existing = self._db.fetchone("SELECT id, status FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        self._db.execute(
            "UPDATE tenants SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, tenant_id),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")

        self._db.audit(f"tenant.{status}", f"Tenant {tenant_id} cambiado a estado '{status}'")
        logger.info(f"Tenant: {tenant_id} cambiado a estado '{status}'")

        return {"status": "ok", "tenant_id": tenant_id, "new_status": status}

    # ── Aislamiento de BD ─────────────────────────────────

    def _provision_tenant_storage(self, tenant_id: str, slug: str, db_type: str) -> dict:
        """Aprovisiona el almacenamiento de datos para un tenant.

        Args:
            tenant_id: ID del tenant
            slug: Slug del tenant (para nombres de schema/BD)
            db_type: Tipo de aislamiento ('schema' o 'database')

        Returns:
            dict con status y connection_string
        """
        if db_type == "schema":
            return self._provision_schema(tenant_id, slug)
        elif db_type == "database":
            return self._provision_database(tenant_id, slug)
        else:
            return {"status": "error", "message": f"Tipo de aislamiento invalido: {db_type}"}

    def _provision_schema(self, tenant_id: str, slug: str) -> dict:
        """Aprovisiona un schema separado en la BD compartida para un tenant."""
        # En SQLite no hay schemas, usamos prefijo en tablas
        # Para PostgreSQL, se crearia un schema real
        conn = self._db.get_connection()
        cursor = conn.cursor()

        # Crear tablas con prefijo del tenant
        prefix = f"t_{slug.replace('-', '_')}_"
        cursor.executescript(f"""
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
        """)
        conn.commit()

        # Registrar en tenant_databases
        connection_string = f"sqlite:shared:{prefix}"
        self._db.execute(
            "INSERT INTO tenant_databases (tenant_id, db_type, connection_string) VALUES (?, 'schema', ?)",
            (tenant_id, connection_string),
        )
        self._db.commit()

        logger.info(f"Tenant: Schema aprovisionado para {tenant_id} (prefix={prefix})")
        return {"status": "ok", "db_type": "schema", "connection_string": connection_string}

    def _provision_database(self, tenant_id: str, slug: str) -> dict:
        """Aprovisiona una BD dedicada para un tenant (enterprise).

        En SQLite, crea un archivo .db separado. En PostgreSQL,
        crearia una BD dedicada.
        """
        from src.config import DATA_DIR

        db_path = DATA_DIR / "tenants" / f"{slug}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Crear BD del tenant con esquema completo
        tenant_conn = sqlite3.connect(str(db_path))
        tenant_conn.execute("PRAGMA journal_mode=WAL")
        tenant_conn.execute("PRAGMA foreign_keys=ON")
        tenant_conn.executescript("""
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
        """)
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

    def _deprovision_tenant_storage(self, tenant_id: str, db_type: str, connection_string: str) -> None:
        """Elimina el almacenamiento de datos de un tenant."""
        if db_type == "schema":
            # En schema mode: eliminar tablas con prefijo
            # Parsear prefijo del connection_string
            parts = connection_string.split(":")
            if len(parts) >= 3:
                prefix = parts[2]
                conn = self._db.get_connection()
                cursor = conn.cursor()
                # Obtener todas las tablas con el prefijo
                tables = self._db.fetchall(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                    (f"{prefix}%",),
                )
                for table in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS [{table['name']}]")
                conn.commit()
                logger.info(f"Tenant: Tablas con prefijo '{prefix}' eliminadas")
        elif db_type == "database":
            # En database mode: eliminar archivo .db
            parts = connection_string.split(":", 1)
            if len(parts) >= 2 and parts[0] == "sqlite":
                db_path = Path(parts[1])
                if db_path.exists():
                    db_path.unlink()
                    logger.info(f"Tenant: BD eliminada: {db_path}")

    def get_tenant_db(self, tenant_id: str) -> sqlite3.Connection | None:
        """Obtiene la conexion a la BD del tenant.

        Para tenants con BD dedicada, retorna una conexion al archivo .db.
        Para tenants con schema, retorna la conexion compartida con prefijo.

        Args:
            tenant_id: ID del tenant

        Returns:
            sqlite3.Connection o None si el tenant no existe
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant or tenant.get("status") != "active":
            return None

        db_info = self._db.fetchone(
            "SELECT db_type, connection_string FROM tenant_databases WHERE tenant_id = ?",
            (tenant_id,),
        )
        if not db_info:
            return None

        # Reutilizar conexion existente si esta disponible
        if tenant_id in self._tenant_connections:
            try:
                conn = self._tenant_connections[tenant_id]
                conn.execute("SELECT 1")
                return conn
            except Exception:
                del self._tenant_connections[tenant_id]

        if db_info["db_type"] == "database":
            parts = db_info["connection_string"].split(":", 1)
            if len(parts) >= 2 and parts[0] == "sqlite":
                db_path = Path(parts[1])
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA foreign_keys=ON")
                    self._tenant_connections[tenant_id] = conn
                    return conn

        # Para schema, retornar la conexion compartida
        return self._db.get_connection()

    def migrate_tenant_schema(self, tenant_id: str, migration_sql: str) -> dict:
        """Ejecuta una migracion de schema en la BD del tenant.

        Args:
            tenant_id: ID del tenant
            migration_sql: SQL de migracion a ejecutar

        Returns:
            dict con status
        """
        conn = self.get_tenant_db(tenant_id)
        if not conn:
            return {"status": "error", "message": f"No se pudo obtener conexion para tenant {tenant_id}"}

        try:
            conn.executescript(migration_sql)
            conn.commit()
            logger.info(f"Tenant: Migracion ejecutada para tenant {tenant_id}")
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Tenant: Error en migracion para tenant {tenant_id}: {e}")
            return {"status": "error", "message": str(e)}

    # ── Feature flags ─────────────────────────────────────

    def set_feature(self, tenant_id: str, feature: str, enabled: bool) -> dict:
        """Habilita o deshabilita una feature para un tenant.

        Args:
            tenant_id: ID del tenant
            feature: Nombre de la feature
            enabled: True para habilitar, False para deshabilitar

        Returns:
            dict con status
        """
        existing = self._db.fetchone("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        self._db.execute(
            "INSERT OR REPLACE INTO tenant_features (tenant_id, feature_name, enabled) VALUES (?, ?, ?)",
            (tenant_id, feature, 1 if enabled else 0),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")

        logger.info(f"Tenant: Feature '{feature}' {'habilitada' if enabled else 'deshabilitada'} para {tenant_id}")
        return {"status": "ok", "feature": feature, "enabled": enabled}

    def check_feature(self, tenant_id: str, feature: str) -> bool:
        """Verifica si una feature esta habilitada para un tenant.

        Si el tenant tiene feature 'all' habilitada (plan enterprise),
        retorna True para cualquier feature.

        Args:
            tenant_id: ID del tenant
            feature: Nombre de la feature

        Returns:
            True si la feature esta habilitada
        """
        # Verificar si tiene 'all' (enterprise)
        all_row = self._db.fetchone(
            "SELECT enabled FROM tenant_features WHERE tenant_id = ? AND feature_name = 'all'",
            (tenant_id,),
        )
        if all_row and all_row["enabled"]:
            return True

        # Verificar feature especifica
        row = self._db.fetchone(
            "SELECT enabled FROM tenant_features WHERE tenant_id = ? AND feature_name = ?",
            (tenant_id, feature),
        )
        return bool(row and row["enabled"])

    def _get_tenant_features(self, tenant_id: str) -> dict[str, bool]:
        """Obtiene todas las features de un tenant como dict."""
        rows = self._db.fetchall(
            "SELECT feature_name, enabled FROM tenant_features WHERE tenant_id = ?",
            (tenant_id,),
        )
        return {row["feature_name"]: bool(row["enabled"]) for row in rows}

    # ── Settings por tenant ───────────────────────────────

    def get_setting(self, tenant_id: str, key: str) -> str | None:
        """Obtiene un setting de un tenant.

        Args:
            tenant_id: ID del tenant
            key: Clave del setting

        Returns:
            Valor del setting, o None si no existe
        """
        row = self._db.fetchone(
            "SELECT value FROM tenant_settings WHERE tenant_id = ? AND key = ?",
            (tenant_id, key),
        )
        return row["value"] if row else None

    def set_setting(self, tenant_id: str, key: str, value: str) -> dict:
        """Establece un setting para un tenant.

        Args:
            tenant_id: ID del tenant
            key: Clave del setting
            value: Valor del setting

        Returns:
            dict con status
        """
        existing = self._db.fetchone("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
        if not existing:
            return {"status": "error", "message": f"Tenant {tenant_id} no encontrado"}

        self._db.execute(
            "INSERT OR REPLACE INTO tenant_settings (tenant_id, key, value) VALUES (?, ?, ?)",
            (tenant_id, key, value),
        )
        self._db.commit()

        # Invalidar cache
        self._redis.delete(f"tenant:{tenant_id}")

        return {"status": "ok"}

    def _get_tenant_settings(self, tenant_id: str) -> dict[str, str]:
        """Obtiene todos los settings de un tenant como dict."""
        rows = self._db.fetchall(
            "SELECT key, value FROM tenant_settings WHERE tenant_id = ?",
            (tenant_id,),
        )
        return {row["key"]: row["value"] for row in rows}

    # ── Rate limiting por tenant ──────────────────────────

    def check_rate_limit(self, tenant_id: str, action: str = "api") -> dict:
        """Verifica el rate limit de un tenant para una accion.

        Usa Redis para contar requests en ventana deslizante.

        Args:
            tenant_id: ID del tenant
            action: Tipo de accion (api, execution, etc.)

        Returns:
            dict con allowed, remaining, reset_at
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "remaining": 0, "reset_at": 0, "reason": "Tenant no encontrado"}

        config = tenant.get("config", {})
        max_per_day = config.get("max_executions_per_day", 100)
        if max_per_day == -1:  # Sin limite
            return {"allowed": True, "remaining": -1, "reset_at": 0}

        return self._redis.check_rate_limit(
            f"tenant:{tenant_id}:{action}",
            max_requests=max_per_day,
            window_seconds=86400,  # 24 horas
        )

    # ── Helpers ───────────────────────────────────────────

    def _tenant_row_to_dict(self, row: dict) -> dict:
        """Convierte una fila de la tabla tenants a dict con config parseado."""
        result = dict(row)
        if "config" in result and isinstance(result["config"], str):
            try:
                result["config"] = json.loads(result["config"])
            except (json.JSONDecodeError, TypeError):
                result["config"] = {}
        return result

    def _cache_tenant(self, tenant_id: str, data: dict) -> None:
        """Almacena datos del tenant en cache Redis."""
        self._redis.set_json(f"tenant:{tenant_id}", data, ttl=_TENANT_CACHE_TTL)

    def invalidate_tenant_cache(self, tenant_id: str) -> None:
        """Invalida la cache Redis de un tenant."""
        self._redis.delete(f"tenant:{tenant_id}")
        tenant = self._db.fetchone("SELECT slug FROM tenants WHERE id = ?", (tenant_id,))
        if tenant and tenant.get("slug"):
            self._redis.delete(f"tenant:slug:{tenant['slug']}")

    def close_all_tenant_connections(self) -> None:
        """Cierra todas las conexiones de BD de tenants."""
        for _tenant_id, conn in self._tenant_connections.items():
            with contextlib.suppress(Exception):
                conn.close()
        self._tenant_connections.clear()
        logger.info("Tenant: Todas las conexiones de tenant cerradas")


# ── Flask Middleware ──────────────────────────────────────────


class TenantMiddleware:
    """Middleware Flask que resuelve el tenant antes de cada request.

    Inyecta g.tenant_id para uso downstream y retorna 404 para
    dominios de tenant desconocidos.
    """

    def __init__(self, app: Any = None) -> None:
        self._tenant_service = TenantService()
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Any) -> None:
        """Registra el middleware en la aplicacion Flask."""
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        logger.info("TenantMiddleware registrado en la aplicacion Flask")

    def _before_request(self) -> Any | None:
        """Resuelve el tenant antes de cada request."""
        from flask import g, request

        # Skip para rutas de admin o health check
        if request.path.startswith("/api/v1/admin/") or request.path == "/health":
            return None

        # Skip para rutas de login/auth (no requieren tenant)
        if request.path.startswith("/api/auth/") or request.path.startswith("/api/v1/auth/"):
            return None

        # Skip para rutas de login page
        if request.path in ("/login", "/static") or request.path.startswith("/static/"):
            return None

        tenant = self._tenant_service.resolve_tenant(request)

        if tenant:
            g.tenant_id = tenant["id"]
            g.tenant = tenant
            set_current_tenant_id(tenant["id"])

            # Almacenar en sesion para requests futuros
            try:
                from flask import session

                session["tenant_id"] = tenant["id"]
            except RuntimeError:
                pass
        else:
            # Si no se puede resolver el tenant y no es una ruta publica,
            # retornar 404 solo para rutas que requieren tenant
            if request.path.startswith("/api/"):
                from flask import jsonify

                return jsonify({"error": "Tenant no encontrado", "code": "TENANT_NOT_FOUND"}), 404
            # Para paginas web, continuar sin tenant (multi-tenant global)
            g.tenant_id = None
            g.tenant = None

        return None

    def _after_request(self, response: Any) -> Any:
        """Limpia el contexto de tenant despues de cada request."""
        clear_tenant_context()
        return response
