"""
Workflow Determinista — Database Manager (Singleton SQLite)
Gestion de UNA sola base de datos: workflow_determinista.db
"""

import sqlite3
import threading
from pathlib import Path

from src.config import DB_PATH
from src.data.audit_repository import AuditRepository
from src.data.interfaces import DatabaseInterface
from src.data.settings_repository import SettingsRepository
from src.data.user_repository import UserRepository
from src.utils.logger import setup_logging
from typing import Any

logger = setup_logging(__name__)


class DatabaseManager(DatabaseInterface):
    """Singleton que gestiona la conexion a SQLite unificada.

    NOTA: Los metodos de dominio (usuarios, settings, auditoria) se han
    extraido a repositorios dedicados:
    - UserRepository: create_user, get_user, etc.
    - SettingsRepository: get_setting, set_setting
    - AuditRepository: log/audit

    DatabaseManager mantiene wrappers de backward compatibility que
    delegan a los nuevos repos. Estos wrappers se eliminaran en Phase 4.5.
    """

    _instance: "DatabaseManager | None" = None
    _lock = threading.RLock()

    def __new__(cls) -> "DatabaseManager":
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
            self._db_path: Path = DB_PATH
            self._local = threading.local()
            self._init_database()
            # Repositorios delegados (backward compat)
            self._users = UserRepository(self)
            self._settings = SettingsRepository(self)
            self._audit = AuditRepository(self)

    # ── Conexion ─────────────────────────────────────────────

    def get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexion SQLite (una por hilo)."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.connection = conn
            if self._initialized:
                logger.debug("Nueva conexion SQLite creada con foreign_keys=ON")
        return self._local.connection

    def close_connection(self) -> None:
        """Cierra la conexion del hilo actual."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    # ── Inicializacion ───────────────────────────────────────

    def _init_database(self) -> None:
        """Crea las tablas si no existen."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.executescript(self._get_schema())
        conn.commit()
        self._migrate()
        logger.info(f"Base de datos inicializada: {self._db_path}")

    def _get_schema(self) -> str:
        """Retorna el schema completo de la base de datos unificada."""
        return """
        -- Users & Auth (Mejora #10)
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

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

        -- Workflow Engine
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
            user_id         INTEGER DEFAULT 1
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
            user_id         INTEGER DEFAULT 1,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id)
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
            retry_count     INTEGER DEFAULT 0,
            FOREIGN KEY (execution_id) REFERENCES workflow_executions(id)
        );

        -- Event Bus
        CREATE TABLE IF NOT EXISTS event_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type      TEXT NOT NULL,
            event_data      TEXT NOT NULL,
            workflow_id     INTEGER,
            status          TEXT DEFAULT 'pending',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at    TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS event_subscriptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type      TEXT NOT NULL,
            workflow_id     INTEGER NOT NULL,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id)
        );

        -- CRM
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
            user_id         INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS lead_activities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id         INTEGER NOT NULL,
            activity_type   TEXT NOT NULL,
            description     TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        -- Inventory
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
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id         INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS stock_movements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id      INTEGER NOT NULL,
            type            TEXT NOT NULL,
            quantity        INTEGER NOT NULL,
            reason          TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        -- Invoices
        CREATE TABLE IF NOT EXISTS invoices (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            number          TEXT UNIQUE,
            client_name     TEXT NOT NULL,
            client_email    TEXT,
            items           TEXT NOT NULL,
            subtotal        REAL,
            tax_rate        REAL DEFAULT 0.16,
            tax_amount      REAL,
            discount        REAL DEFAULT 0,
            total           REAL,
            status          TEXT DEFAULT 'pending',
            due_date        DATE,
            issued_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at         TIMESTAMP,
            notes           TEXT,
            user_id         INTEGER DEFAULT 1
        );

        -- Settings
        CREATE TABLE IF NOT EXISTS settings (
            key             TEXT PRIMARY KEY,
            value           TEXT NOT NULL
        );

        -- Licenses
        CREATE TABLE IF NOT EXISTS license (
            key             TEXT PRIMARY KEY,
            type            TEXT NOT NULL,
            client_name     TEXT,
            issued_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at      TIMESTAMP,
            is_trial        INTEGER DEFAULT 0,
            trial_started_at TIMESTAMP
        );

        -- Audit Log
        CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event           TEXT NOT NULL,
            details         TEXT,
            ip_address      TEXT,
            user_id         INTEGER,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Indices
        CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflow_definitions(status);
        CREATE INDEX IF NOT EXISTS idx_execution_workflow ON workflow_executions(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_execution_status ON workflow_executions(status);
        CREATE INDEX IF NOT EXISTS idx_step_log_execution ON workflow_step_logs(execution_id);
        CREATE INDEX IF NOT EXISTS idx_event_queue_status ON event_queue(status);
        CREATE INDEX IF NOT EXISTS idx_event_subscriptions ON event_subscriptions(event_type);
        CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
        CREATE INDEX IF NOT EXISTS idx_products_low_stock ON products(stock, min_stock);
        CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
        CREATE INDEX IF NOT EXISTS idx_audit_log_event ON audit_log(event);
        CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

        -- NLU (Sprint 4)
        CREATE TABLE IF NOT EXISTS nlp_synonyms (
            word            TEXT NOT NULL,
            synonym_of      TEXT NOT NULL,
            intent          TEXT NOT NULL,
            usage_count     INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (word, intent)
        );

        CREATE TABLE IF NOT EXISTS nlp_intent_vectors (
            intent          TEXT NOT NULL,
            keyword         TEXT NOT NULL,
            idf_weight      REAL NOT NULL,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (intent, keyword)
        );

        CREATE TABLE IF NOT EXISTS nlu_traces (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            text_hash       TEXT NOT NULL,
            lang            TEXT,
            intent_top      TEXT,
            confidence      REAL,
            trace_json      TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_nlu_traces_hash ON nlu_traces(text_hash);
        -- Dead Letter Queue (Sprint 4)
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id     INTEGER NOT NULL,
            workflow_name   TEXT NOT NULL DEFAULT '',
            execution_id    INTEGER NOT NULL,
            step_id         INTEGER NOT NULL,
            tool            TEXT NOT NULL DEFAULT '',
            action          TEXT NOT NULL DEFAULT '',
            error_message   TEXT NOT NULL DEFAULT '',
            retry_count     INTEGER DEFAULT 0,
            step_definition TEXT NOT NULL DEFAULT '{}',
            context_snapshot TEXT NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'pending',
            notified        INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_dead_letter_status ON dead_letter_queue(status);
        CREATE INDEX IF NOT EXISTS idx_dead_letter_workflow ON dead_letter_queue(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_dead_letter_created ON dead_letter_queue(created_at);

        CREATE INDEX IF NOT EXISTS idx_nlp_synonyms_intent ON nlp_synonyms(intent);
        """

    def _migrate(self) -> None:
        """Migraciones incrementales: agrega columnas faltantes sin perder datos."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Migración: audit_log.user_id
        try:
            cursor.execute("SELECT user_id FROM audit_log LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE audit_log ADD COLUMN user_id INTEGER")
            conn.commit()
            logger.info("Migración: audit_log.user_id agregada")

        # Migración: workflow_definitions.user_id
        try:
            cursor.execute("SELECT user_id FROM workflow_definitions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE workflow_definitions ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.commit()
            logger.info("Migración: workflow_definitions.user_id agregada")

        # Migración: workflow_executions.user_id
        try:
            cursor.execute("SELECT user_id FROM workflow_executions LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE workflow_executions ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.commit()
            logger.info("Migración: workflow_executions.user_id agregada")

        # Migración: leads.user_id
        try:
            cursor.execute("SELECT user_id FROM leads LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE leads ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.commit()
            logger.info("Migración: leads.user_id agregada")

        # Migración: products.user_id
        try:
            cursor.execute("SELECT user_id FROM products LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE products ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.commit()
            logger.info("Migración: products.user_id agregada")

        # Migración: invoices.user_id
        try:
            cursor.execute("SELECT user_id FROM invoices LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE invoices ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.commit()
            logger.info("Migración: invoices.user_id agregada")

        # Migración: license.signature_b64 (Ed25519 full signature storage)
        try:
            cursor.execute("SELECT signature_b64 FROM license LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE license ADD COLUMN signature_b64 TEXT DEFAULT ''")
            conn.commit()
            logger.info("Migración: license.signature_b64 agregada")

    # ── Operaciones generales ────────────────────────────────

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Ejecuta una consulta SQL."""
        conn = self.get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Ejecuta una consulta SQL con multiples parametros."""
        conn = self.get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Ejecuta una consulta y retorna una fila como dict."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
        """Ejecuta una consulta y retorna todas las filas como lista de dicts."""
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def commit(self) -> None:
        """Confirma la transaccion actual."""
        self.get_connection().commit()

    def rollback(self) -> None:
        """Rev介 la transaccion actual."""
        self.get_connection().rollback()

    # ── Backup ───────────────────────────────────────────────

    def close(self) -> None:
        """Cierra todas las conexiones (alias de close_all)."""
        self.close_all()

    def backup(self, dest_path: str | Path) -> str:
        """Crea un backup de la base de datos."""
        dest = Path(dest_path)
        if dest.is_dir():
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = dest / f"workflow_determinista_backup_{timestamp}.db"

        dest.parent.mkdir(parents=True, exist_ok=True)
        conn = self.get_connection()
        back_conn = sqlite3.connect(str(dest))
        conn.backup(back_conn)
        back_conn.close()
        logger.info(f"Backup creado: {dest}")
        return str(dest)

    # ── Backward Compatibility Wrappers ──────────────────────
    # Delegan a los nuevos repositorios. Se eliminaran en Phase 4.5
    # cuando todos los consumidores se hayan migrado.

    def get_setting(self, key: str, default=None):
        """Wrapper: delega a SettingsRepository."""
        return self._settings.get_setting(key, default)

    def set_setting(self, key: str, value: str) -> None:
        """Wrapper: delega a SettingsRepository."""
        self._settings.set_setting(key, value)

    def audit(self, event: str, details: str | None = None, ip_address: str | None = None, user_id: int | None = None) -> None:
        """Wrapper: delega a AuditRepository."""
        self._audit.log(event, details, ip_address, user_id)

    def create_user(self, username: str, password: str, role: str = "admin", display_name: str = "", email: str = "") -> dict[str, Any]:
        """Wrapper: delega a UserRepository."""
        return self._users.create_user(username, password, role, display_name, email)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Wrapper: delega a UserRepository."""
        return self._users.get_user(user_id)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        """Wrapper: delega a UserRepository."""
        return self._users.get_user_by_username(username)

    def list_users(self) -> list[dict]:
        """Wrapper: delega a UserRepository."""
        return self._users.list_users()

    def update_user(self, user_id: int, updates: dict[str, Any]) -> bool:
        """Wrapper: delega a UserRepository."""
        return self._users.update_user(user_id, updates)

    def delete_user(self, user_id: int) -> bool:
        """Wrapper: delega a UserRepository."""
        return self._users.delete_user(user_id)

    # ── Cleanup ──────────────────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None

    def close_all(self) -> None:
        """Cierra todas las conexiones."""
        self.close_connection()
