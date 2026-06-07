"""
Workflow Determinista — Database Manager (Singleton SQLite)
Gestión de UNA sola base de datos: workflow_determinista.db
"""
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.config import DB_PATH, DB_WAL_MODE
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class DatabaseManager:
    """Singleton que gestiona la conexión a SQLite unificada."""

    _instance: "DatabaseManager | None" = None
    _lock = threading.Lock()

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
        self._initialized = True
        self._db_path: Path = DB_PATH
        self._local = threading.local()
        self._init_database()

    # ── Conexión ─────────────────────────────────────────────

    def get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión SQLite (una por hilo)."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.connection = conn
        return self._local.connection

    def close_connection(self) -> None:
        """Cierra la conexión del hilo actual."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    # ── Inicialización ───────────────────────────────────────

    def _init_database(self) -> None:
        """Crea las tablas si no existen."""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.executescript(self._get_schema())
        conn.commit()
        logger.info(f"Base de datos inicializada: {self._db_path}")

    def _get_schema(self) -> str:
        """Retorna el schema completo de la base de datos unificada."""
        return """
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
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            notes           TEXT
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
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Índices
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
        """

    # ── Operaciones generales ────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Ejecuta una consulta SQL."""
        conn = self.get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Ejecuta una consulta SQL con múltiples parámetros."""
        conn = self.get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        """Ejecuta una consulta y retorna una fila como dict."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        """Ejecuta una consulta y retorna todas las filas como lista de dicts."""
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def commit(self) -> None:
        """Confirma la transacción actual."""
        self.get_connection().commit()

    def rollback(self) -> None:
        """Revierte la transacción actual."""
        self.get_connection().rollback()

    # ── Backup ───────────────────────────────────────────────

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

    # ── Settings helpers ─────────────────────────────────────

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor de settings con parseo JSON automático."""
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if not row:
            return default
        raw = row["value"]
        # Intentar parsear como JSON para tipos booleanos, numéricos, listas
        import json as _json
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            return raw

    def set_setting(self, key: str, value: str) -> None:
        """Guarda un valor en settings."""
        self.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.commit()

    # ── Audit helpers ────────────────────────────────────────

    def audit(self, event: str, details: str | None = None, ip_address: str | None = None) -> None:
        """Registra un evento de auditoría."""
        self.execute(
            "INSERT INTO audit_log (event, details, ip_address) VALUES (?, ?, ?)",
            (event, details, ip_address),
        )
        self.commit()

    # ── Cleanup ──────────────────────────────────────────────

    def close_all(self) -> None:
        """Cierra todas las conexiones."""
        self.close_connection()
