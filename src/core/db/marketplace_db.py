"""Marketplace Database — Dedicated SQLite database for marketplace domain.

Uses its own marketplace.db file to ensure domain separation
from the main workflow_determinista.db.
"""

from __future__ import annotations

import json as _json
import sqlite3
from pathlib import Path
from typing import TypeVar

from src.core.db.interfaces import DatabaseInterface
from src.core.logging import setup_logging

T = TypeVar("T")

logger = setup_logging(__name__)

from src.core.config import MARKETPLACE_DB_PATH as _MK
MARKETPLACE_DB_PATH = _MK


class MarketplaceDBManager(DatabaseInterface):
    """Database manager for the marketplace domain.

    Uses a dedicated marketplace.db file to store connectors,
    categories, installations, and reviews — separate from
    the main workflow database.
    """

    def __init__(self, db_path: str | Path = MARKETPLACE_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the marketplace database and create tables."""
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_tables()
        logger.info(f"MarketplaceDB initialized: {self._db_path}")

    def _ensure_tables(self) -> None:
        """Create marketplace tables if they don't exist."""
        if self._conn is None:
            return
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS marketplace_connectors (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT DEFAULT '',
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'general',
                icon TEXT DEFAULT 'plug',
                author TEXT DEFAULT '',
                homepage TEXT DEFAULT '',
                docs_url TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                certification_status TEXT DEFAULT 'pending',
                current_version TEXT DEFAULT '1.0.0',
                versions TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                actions TEXT DEFAULT '[]',
                auth_types TEXT DEFAULT '[]',
                installs INTEGER DEFAULT 0,
                rating REAL DEFAULT 0.0,
                review_count INTEGER DEFAULT 0,
                featured INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_mkt_conn_name ON marketplace_connectors(name);
            CREATE INDEX IF NOT EXISTS idx_mkt_conn_category ON marketplace_connectors(category);
            CREATE INDEX IF NOT EXISTS idx_mkt_conn_status ON marketplace_connectors(status);
            CREATE INDEX IF NOT EXISTS idx_mkt_conn_cert ON marketplace_connectors(certification_status);

            CREATE TABLE IF NOT EXISTS marketplace_categories (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT DEFAULT '',
                description TEXT DEFAULT '',
                icon TEXT DEFAULT 'folder',
                parent_category TEXT,
                connector_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS marketplace_installations (
                id TEXT PRIMARY KEY,
                connector_name TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                version TEXT DEFAULT '1.0.0',
                status TEXT DEFAULT 'active',
                config TEXT DEFAULT '{}',
                installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                uninstalled_at TIMESTAMP,
                UNIQUE(connector_name, tenant_id)
            );
            CREATE INDEX IF NOT EXISTS idx_mkt_inst_connector ON marketplace_installations(connector_name);
            CREATE INDEX IF NOT EXISTS idx_mkt_inst_tenant ON marketplace_installations(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_mkt_inst_status ON marketplace_installations(status);

            CREATE TABLE IF NOT EXISTS marketplace_reviews (
                id TEXT PRIMARY KEY,
                connector_name TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                title TEXT DEFAULT '',
                comment TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_mkt_rev_connector ON marketplace_reviews(connector_name);
            CREATE INDEX IF NOT EXISTS idx_mkt_rev_tenant ON marketplace_reviews(tenant_id);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ── DatabaseInterface implementation ────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query with parameters."""
        if self._conn is None:
            raise RuntimeError("Database connection is closed")
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Execute a SQL query with multiple parameter sets."""
        if self._conn is None:
            raise RuntimeError("Database connection is closed")
        return self._conn.executemany(sql, params_list)

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        """Execute a query and return one row as dict."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a query and return all rows as list of dicts."""
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def commit(self) -> None:
        """Commit the current transaction."""
        if self._conn is not None:
            self._conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._conn is not None:
            self._conn.rollback()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def backup(self, dest_path: str | Path) -> str:
        """Create a backup of the marketplace database."""
        dest = Path(dest_path)
        if dest.is_dir():
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = dest / f"marketplace_backup_{timestamp}.db"

        dest.parent.mkdir(parents=True, exist_ok=True)
        if self._conn is None:
            raise RuntimeError("Database connection is closed")
        back_conn = sqlite3.connect(str(dest))
        self._conn.backup(back_conn)
        back_conn.close()
        logger.info(f"Marketplace backup created: {dest}")
        return str(dest)

    # ── Settings helpers (compat) ───────────────────────────

    def get_setting(self, key: str, default: T | None = None) -> str | int | float | bool | list | dict | None:
        """Get a setting value with automatic JSON parsing."""
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if not row:
            return default
        raw = row["value"]
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            return raw

    def set_setting(self, key: str, value: str) -> None:
        """Save a setting value."""
        self.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.commit()

    # ── Connection status ──────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Check if the database connection is active."""
        return self._conn is not None

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self._db_path


__all__ = [
    "MARKETPLACE_DB_PATH",
    "MarketplaceDBManager",
]
