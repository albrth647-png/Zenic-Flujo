"""
Zenic-Flijo — SettingsRepository
==================================

Repositorio dedicado para la gestión de settings (clave-valor).

Extraído de DatabaseManager (src/core/db/sqlite_manager.py) para separar
responsabilidades y romper la clase dios.
"""

from __future__ import annotations

import json

from src.core.db.interfaces import DatabaseInterface
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class SettingsRepository:
    """
    Repositorio de settings (clave-valor).

    Gestiona la tabla settings:
    - get_setting: obtener valor por clave con parseo JSON automático
    - set_setting: guardar valor por clave (INSERT OR REPLACE)
    - get_all: obtener todos los settings
    - delete_setting: eliminar un setting

    No debe contener lógica de negocio ni de configuración específica.
    Solo operaciones CRUD sobre la tabla settings.
    """

    def __init__(self, db: DatabaseInterface | None = None):
        """
        Args:
            db: Instancia de DatabaseInterface. Si es None, usa el singleton DatabaseManager.
        """
        if db is not None:
            self._db = db
        else:
            from src.core.db.sqlite_manager import DatabaseManager
            self._db = DatabaseManager()

    # ── CRUD ─────────────────────────────────────────────────

    def get_setting(self, key: str, default=None):
        """
        Obtiene un valor de settings con parseo JSON automático.

        Args:
            key: Clave del setting
            default: Valor por defecto si no existe

        Returns:
            Valor parseado (str, int, float, bool, list, dict) o default
        """
        row = self._db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if not row:
            return default
        raw = row["value"]
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def set_setting(self, key: str, value: str) -> None:
        """
        Guarda un valor en settings (INSERT OR REPLACE).

        Args:
            key: Clave del setting
            value: Valor a guardar (se guarda como string)
        """
        self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._db.commit()

    def get_all(self) -> dict:
        """
        Obtiene todos los settings.

        Returns:
            Dict con todas las claves y valores
        """
        rows = self._db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    def delete_setting(self, key: str) -> bool:
        """
        Elimina un setting.

        Args:
            key: Clave del setting a eliminar

        Returns:
            True si se eliminó, False si no existía
        """
        cursor = self._db.execute("DELETE FROM settings WHERE key = ?", (key,))
        self._db.commit()
        return cursor.rowcount > 0
