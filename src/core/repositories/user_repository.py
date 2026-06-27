"""
Zenic-Flijo — UserRepository
==============================

Repositorio dedicado para operaciones CRUD de usuarios.

Extraído de DatabaseManager (src/core/db/sqlite_manager.py) para separar
responsabilidades y romper la clase dios.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from src.core.db.interfaces import DatabaseInterface
from src.core.db.sql_builder import build_update_query
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class UserRepository:
    """
    Repositorio de usuarios.

    Gestiona el ciclo de vida de usuarios en la tabla users:
    - create_user: crear nuevo usuario con contraseña hasheada (pbkdf2)
    - get_user: obtener usuario por ID
    - get_user_by_username: obtener usuario por nombre de usuario
    - list_users: listar todos los usuarios activos
    - update_user: actualizar campos de un usuario
    - delete_user: desactivar un usuario (borrado lógico)

    No debe contener lógica de autenticación, sesiones ni RBAC.
    Solo operaciones CRUD sobre la tabla users.
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

    def create_user(
        self,
        username: str,
        password: str,
        role: str = "admin",
        display_name: str = "",
        email: str = "",
    ) -> dict[str, Any]:
        """
        Crea un nuevo usuario con contraseña hasheada (pbkdf2).

        Args:
            username: Nombre de usuario único
            password: Contraseña en texto plano (se hashea internamente)
            role: Rol del usuario (admin, editor, viewer)
            display_name: Nombre para mostrar
            email: Correo electrónico

        Returns:
            Dict con datos del usuario creado
        """
        salt = secrets.token_hex(16)
        iterations = 600000
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
        stored_hash = f"pbkdf2:sha256:{iterations}:{salt}:{hashed}"
        cursor = self._db.execute(
            "INSERT INTO users (username, password_hash, role, display_name, email) VALUES (?, ?, ?, ?, ?)",
            (username, stored_hash, role, display_name, email),
        )
        self._db.commit()
        return self.get_user(cursor.lastrowid)

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        """
        Obtiene un usuario por ID.

        Args:
            user_id: ID del usuario

        Returns:
            Dict con datos del usuario o None si no existe
        """
        return self._db.fetchone(
            "SELECT id, username, role, display_name, "
            "email, is_active, created_at, last_login_at "
            "FROM users WHERE id = ?",
            (user_id,),
        )

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        """
        Obtiene un usuario por nombre de usuario.

        Args:
            username: Nombre de usuario

        Returns:
            Dict con datos del usuario (incluyendo password_hash) o None
        """
        return self._db.fetchone("SELECT * FROM users WHERE username = ?", (username,))

    def list_users(self) -> list[dict[str, Any]]:
        """
        Lista todos los usuarios activos.

        Returns:
            Lista de dicts con datos de usuarios
        """
        return self._db.fetchall(
            "SELECT id, username, role, display_name, "
            "email, is_active, created_at, last_login_at "
            "FROM users ORDER BY username"
        )

    def update_user(self, user_id: int, updates: dict[str, Any]) -> bool:
        """
        Actualiza campos de un usuario.

        Args:
            user_id: ID del usuario
            updates: Dict con campos a actualizar (role, display_name, email, is_active)

        Returns:
            True si se actualizó, False si no había campos válidos
        """
        allowed = {"role", "display_name", "email", "is_active"}
        result = build_update_query("users", allowed, updates)
        if result is None:
            return False
        sql, params = result
        self._db.execute(sql, (*params, user_id))
        self._db.commit()
        return True

    def delete_user(self, user_id: int) -> bool:
        """
        Desactiva un usuario (borrado lógico).

        Args:
            user_id: ID del usuario

        Returns:
            True siempre
        """
        self._db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        self._db.commit()
        return True
