"""
Workflow Determinista — Database Manager (Singleton SQLite)
Gestion de UNA sola base de datos: workflow_determinista.db
"""

import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.core.config import DB_PATH
from src.core.db.interfaces import DatabaseInterface
from src.core.logging import setup_logging

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

    M10.3 (SRE hardening): Los imports de AuditRepository, SettingsRepository
    y UserRepository son LAZY (dentro de __init__) para romper una circular
    import: ``sqlite_manager`` ↔ ``user_repository``. Los repos importan
    ``DatabaseInterface`` desde ``src.core.db.interfaces`` a nivel de modulo,
    y si ``sqlite_manager`` tambien los importa a nivel de modulo, el orden
    de carga se vuelve no determinista y falla con ImportError en algunos
    entrypoints (p.ej. ``import src.web.app``).
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
            # Repositorios delegados (backward compat).
            # Lazy imports para romper circular: sqlite_manager ↔ user_repository.
            from src.core.repositories.audit_repository import AuditRepository
            from src.core.repositories.settings_repository import SettingsRepository
            from src.core.repositories.user_repository import UserRepository

            self._users = UserRepository(self)
            self._settings = SettingsRepository(self)
            self._audit = AuditRepository(self)

    # ── Conexion ─────────────────────────────────────────────

    def get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexion SQLite (una por hilo, WAL mode + busy_timeout)."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(str(self._db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.connection = conn
            if self._initialized:
                logger.debug("Nueva conexion SQLite WAL creada (busy_timeout=30s)")
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

        -- Foso 3: Clients (clientes maestros, no confundir con leads)
        CREATE TABLE IF NOT EXISTS clients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            fiscal_type     TEXT,
            fiscal_id       TEXT,
            email           TEXT,
            phone           TEXT,
            address         TEXT,
            city            TEXT,
            country_code    TEXT DEFAULT 'MX',
            currency        TEXT DEFAULT 'MXN',
            lead_id         INTEGER,
            user_id         INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );
        -- Foso 3: UNIQUE parcial — solo aplica cuando fiscal_id no está vacío
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_fiscal ON clients(fiscal_id, country_code) WHERE fiscal_id != '';

        -- Foso 3: Deals (oportunidades con monto)
        CREATE TABLE IF NOT EXISTS deals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id         INTEGER NOT NULL,
            client_id       INTEGER,
            title           TEXT NOT NULL,
            amount          REAL NOT NULL,
            currency        TEXT DEFAULT 'MXN',
            probability     REAL DEFAULT 0.5,
            expected_close_date DATE,
            stage           TEXT DEFAULT 'proposal',
            items           TEXT DEFAULT '[]',
            notes           TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id),
            FOREIGN KEY (client_id) REFERENCES clients(id)
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

        -- ─── Sprint 9: Multi-entorno + Versioning ──────────────
        -- Cada UPDATE de un workflow crea una nueva versión (snapshot completo).
        -- Retención: 20 versiones más recientes por workflow (configurable).
        CREATE TABLE IF NOT EXISTS workflow_versions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id     INTEGER NOT NULL,
            version_number  INTEGER NOT NULL,
            name            TEXT NOT NULL,
            description     TEXT,
            trigger_type    TEXT NOT NULL,
            trigger_config  TEXT NOT NULL,
            steps           TEXT NOT NULL,
            change_summary  TEXT DEFAULT '',
            created_by      INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE,
            UNIQUE(workflow_id, version_number)
        );

        CREATE INDEX IF NOT EXISTS idx_workflow_versions_workflow ON workflow_versions(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_versions_created ON workflow_versions(created_at);

        -- Tabla que asocia workflows a entornos (dev/staging/prod).
        -- Un mismo workflow lógico puede tener N filas, una por entorno.
        -- El environment_id es un identificador lógico (no FK) que permite
        -- separar entornos en la misma DB (free/smb) o en DBs dedicadas (enterprise).
        CREATE TABLE IF NOT EXISTS workflow_environments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id     INTEGER NOT NULL,
            environment     TEXT NOT NULL CHECK(environment IN ('dev','staging','prod')),
            promoted_from   TEXT,
            promoted_at     TIMESTAMP,
            promoted_by     INTEGER DEFAULT 1,
            is_current      INTEGER DEFAULT 0,
            notes           TEXT DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE,
            UNIQUE(workflow_id, environment)
        );

        CREATE INDEX IF NOT EXISTS idx_workflow_environments_env ON workflow_environments(environment);
        CREATE INDEX IF NOT EXISTS idx_workflow_environments_current ON workflow_environments(is_current);

        -- Tabla de promociones entre entornos (auditoría).
        CREATE TABLE IF NOT EXISTS workflow_promotions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id     INTEGER NOT NULL,
            source_env      TEXT NOT NULL,
            target_env      TEXT NOT NULL,
            source_version  INTEGER,
            target_version  INTEGER,
            diff_summary    TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'completed',
            promoted_by     INTEGER DEFAULT 1,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workflow_id) REFERENCES workflow_definitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_workflow_promotions_workflow ON workflow_promotions(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_promotions_status ON workflow_promotions(status);
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

        # Foso 3: Migración invoices — añadir columnas nuevas
        for col, ddl in [
            ("client_id",  "INTEGER REFERENCES clients(id)"),
            ("deal_id",    "INTEGER REFERENCES deals(id)"),
            ("lead_id",    "INTEGER REFERENCES leads(id)"),
            ("currency",   "TEXT DEFAULT 'MXN'"),
            ("fiscal_type", "TEXT"),
            ("fiscal_id",  "TEXT"),
            ("pdf_path",   "TEXT"),
            ("mp_preference_id", "TEXT"),
            ("mp_payment_id",    "TEXT"),
        ]:
            try:
                cursor.execute(f"SELECT {col} FROM invoices LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute(f"ALTER TABLE invoices ADD COLUMN {col} {ddl}")
                conn.commit()
                logger.info(f"Migración: invoices.{col} agregada")

        # ── Foso 1 — Compliance Reproducible ────────────────────────────
        # Tabla: audit_log_chain (reemplaza audit_log para compliance crítico)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log_chain (
                entry_id         TEXT PRIMARY KEY,
                previous_hash    TEXT NOT NULL,
                entry_hash       TEXT NOT NULL,
                actor            TEXT NOT NULL,
                actor_signature  TEXT,
                action           TEXT NOT NULL,
                resource_type    TEXT,
                resource_id      TEXT,
                details          TEXT,
                timestamp        REAL NOT NULL,
                tenant_id        TEXT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_chain_ts ON audit_log_chain(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_chain_tenant ON audit_log_chain(tenant_id, timestamp)"
        )

        # Tabla: orbital_step_snapshots (replay step-by-step)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orbital_step_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id    INTEGER NOT NULL REFERENCES workflow_executions(id),
                step_id         INTEGER NOT NULL,
                orbital_theta   REAL,
                orbital_tension REAL,
                input_hash      TEXT,
                output_hash     TEXT,
                step_signature  TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_step_snap_exec ON orbital_step_snapshots(execution_id)"
        )

        # Tabla: tenant_ed25519_keys (claves Ed25519 para firma de compliance)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tenant_ed25519_keys (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT NOT NULL,
                version         INTEGER NOT NULL,
                private_key_enc TEXT NOT NULL,
                public_key_pem  TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, version)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ed25519_tenant ON tenant_ed25519_keys(tenant_id)"
        )

        # ── Bug TENANT-03 (X-Tenant-ID bypass) ──────────────────────────
        # Tabla user_tenants: asocia usuarios a tenants con un rol por tenant.
        # Es la fuente de verdad para verify_tenant_ownership() que se usa en
        # la dependencia require_tenant_access() de la API v2.
        # Sin esta verificación, cualquier usuario autenticado puede enviar
        # X-Tenant-ID: <otro_tenant> y acceder a datos ajenos.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_tenants (
                user_id     INTEGER NOT NULL,
                tenant_id   TEXT    NOT NULL,
                role        TEXT    NOT NULL DEFAULT 'member',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, tenant_id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_tenants_user ON user_tenants(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_tenants_tenant ON user_tenants(tenant_id)"
        )

        # Tabla: orbital_executions (persiste OrbitalResult con hashes)
        # Si la tabla ya existe (creada por orbital/db.py legacy), añadir columnas nuevas.
        # Si no existe, crearla completa.
        try:
            cursor.execute("SELECT id FROM orbital_executions LIMIT 1")
            orbital_executions_exists = True
        except sqlite3.OperationalError:
            orbital_executions_exists = False

        if not orbital_executions_exists:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orbital_executions (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick                    INTEGER NOT NULL,
                    total_variables         INTEGER DEFAULT 0,
                    total_cycles            INTEGER DEFAULT 0,
                    total_tor_pairs         INTEGER DEFAULT 0,
                    resonant_cycles         INTEGER DEFAULT 0,
                    converged_cycles        INTEGER DEFAULT 0,
                    final_state             TEXT,
                    duration_ms             INTEGER DEFAULT 0,
                    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    -- Foso 1 campos (workflow_execution_id sin FK estricta:
                    -- permite persistir OrbitalResults standalone sin workflow real):
                    workflow_execution_id   INTEGER,
                    input_fingerprint       TEXT NOT NULL DEFAULT '',
                    result_hash             TEXT NOT NULL DEFAULT '',
                    result_signature        TEXT NOT NULL DEFAULT '',
                    previous_hash           TEXT NOT NULL DEFAULT '',
                    cod_payload             TEXT DEFAULT '{}',
                    rcc_payload             TEXT DEFAULT '[]',
                    tor_payload             TEXT DEFAULT '[]',
                    trace_id                TEXT,
                    span_id                 TEXT,
                    tenant_id               TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_orb_exec_workflow ON orbital_executions(workflow_execution_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_orb_exec_hash ON orbital_executions(result_hash)"
            )
        else:
            # Migración: añadir columnas Foso 1 a orbital_executions existente
            for col, ddl in [
                ("workflow_execution_id", "INTEGER"),
                ("input_fingerprint", "TEXT NOT NULL DEFAULT ''"),
                ("result_hash", "TEXT NOT NULL DEFAULT ''"),
                ("result_signature", "TEXT NOT NULL DEFAULT ''"),
                ("previous_hash", "TEXT NOT NULL DEFAULT ''"),
                ("cod_payload", "TEXT DEFAULT '{}'"),
                ("rcc_payload", "TEXT DEFAULT '[]'"),
                ("tor_payload", "TEXT DEFAULT '[]'"),
                ("trace_id", "TEXT"),
                ("span_id", "TEXT"),
                ("tenant_id", "TEXT"),
            ]:
                try:
                    cursor.execute(f"SELECT {col} FROM orbital_executions LIMIT 1")
                except sqlite3.OperationalError:
                    cursor.execute(f"ALTER TABLE orbital_executions ADD COLUMN {col} {ddl}")
                    conn.commit()
                    logger.info(f"Migración Foso 1: orbital_executions.{col} agregada")

        conn.commit()
        logger.info("Migración Foso 1: tablas audit_log_chain, orbital_step_snapshots, tenant_ed25519_keys verificadas")

        # ── Bug MISC-02 — Marketplace publish_connector api_key solo longitud ──
        # Tabla marketplace_publisher_keys: registra las API keys validas para
        # publicar conectores en el marketplace. La columna api_key_hash guarda
        # el SHA-256 hex de la api_key (nunca la clave en claro). Esto permite
        # que publish_connector valide la api_key contra la tabla en vez de
        # aceptar cualquier string >= 10 chars.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS marketplace_publisher_keys (
                api_key_hash  TEXT PRIMARY KEY,
                partner_name  TEXT NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_mkt_pub_keys_partner ON marketplace_publisher_keys(partner_name)"
        )
        conn.commit()
        logger.info("Migración MISC-02: tabla marketplace_publisher_keys verificada")

    # ── Operaciones generales ────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Ejecuta una consulta SQL."""
        conn = self.get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Ejecuta una consulta SQL con multiples parametros."""
        conn = self.get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Ejecuta una consulta y retorna una fila como dict[str, Any]."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict[str, Any](row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Ejecuta una consulta y retorna todas las filas como lista de dicts."""
        cursor = self.execute(sql, params)
        return [dict[str, Any](row) for row in cursor.fetchall()]

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

    def list_users(self) -> list[dict[str, Any]]:
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
