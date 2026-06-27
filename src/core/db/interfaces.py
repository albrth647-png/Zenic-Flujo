"""Database Interface — Abstract base class for database implementations.

Defines the contract for all database managers in the system.
Each domain module (compliance, partnership, marketplace, sync) uses
its own database file via this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class DatabaseInterface(ABC):
    """Abstract interface for database operations.

    All database managers must implement these methods to ensure
    consistent data access patterns across the system.
    """

    @abstractmethod
    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        """Execute a SQL query with parameters."""
        ...

    @abstractmethod
    def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> Any:
        """Execute a SQL query with multiple parameter sets."""
        ...

    @abstractmethod
    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute a query and return one row as dict[str, Any]."""
        ...

    @abstractmethod
    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a query and return all rows as list[Any] of dicts."""
        ...

    @abstractmethod
    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the current transaction."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        ...

    @abstractmethod
    def backup(self, dest_path: str | Path) -> str:
        """Create a backup of the database."""
        ...


__all__ = [
    "DatabaseInterface",
]
