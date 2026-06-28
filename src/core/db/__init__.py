"""src.core.db — SQLite + Redis + Mongo infrastructure.

M10.3 (SRE hardening): ``interfaces`` MUST be imported before
``sqlite_manager``. Otherwise, when ``sqlite_manager`` imports
``UserRepository`` from ``src.core.repositories``, which in turn imports
``DatabaseInterface`` from ``src.core.db.interfaces``, Python tries to
access ``interfaces`` on the partially-initialized ``src.core.db`` package
and fails with a circular import. Importing ``interfaces`` first ensures
the submodule is registered on the package before any downstream
repository import triggers it.
"""
from src.core.db.backup_engine import BackupEngine
from src.core.db.interfaces import DatabaseInterface
from src.core.db.marketplace_db import MarketplaceDBManager
from src.core.db.mongodb_service import MongoDBService
from src.core.db.redis_service import RedisService
from src.core.db.sql_builder import (
    build_in_clause,
    build_update_query,
    quote_identifier,
    safe_drop_table_if_exists,
    validate_identifier,
)
from src.core.db.sqlite_manager import DatabaseManager

__all__ = [
    "BackupEngine",
    "DatabaseInterface",
    "DatabaseManager",
    "MarketplaceDBManager",
    "MongoDBService",
    "RedisService",
    "build_in_clause",
    "build_update_query",
    "quote_identifier",
    "safe_drop_table_if_exists",
    "validate_identifier",
]
