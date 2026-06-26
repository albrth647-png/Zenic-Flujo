"""
Workflow Determinista -- RBAC Granular
Sistema de control de acceso basado en roles y permisos granulares.
Compatibilidad retroactiva con el sistema de 3 roles (admin/editor/viewer).
"""

import contextlib
import json
import threading
from typing import ClassVar

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# ── Definiciones de recursos y acciones ──────────────────

RESOURCES = [
    "workflow",
    "connector",
    "tool",
    "settings",
    "user",
    "license",
    "report",
    "audit_log",
]

ACTIONS = [
    "create",
    "read",
    "update",
    "delete",
    "execute",
    "share",
    "export",
    "import",
]

# ── Roles por defecto ────────────────────────────────────

DEFAULT_ROLE_PERMISSIONS: ClassVar[dict[str, dict[str, list[str]]]] = {
    "admin": {
        "workflow": ["create", "read", "update", "delete", "execute", "share", "export", "import"],
        "connector": ["create", "read", "update", "delete", "execute"],
        "tool": ["create", "read", "update", "delete", "execute"],
        "settings": ["create", "read", "update", "delete"],
        "user": ["create", "read", "update", "delete"],
        "license": ["create", "read", "update", "delete"],
        "report": ["create", "read", "export"],
        "audit_log": ["create", "read", "delete", "export"],
    },
    "editor": {
        "workflow": ["create", "read", "update", "delete", "execute", "share", "export", "import"],
        "connector": ["read", "execute"],
        "tool": ["read", "execute"],
        "settings": ["read", "update"],
        "user": ["read"],
        "license": ["read"],
        "report": ["create", "read", "export"],
        "audit_log": ["read"],
    },
    "viewer": {
        "workflow": ["read", "execute", "export"],
        "connector": ["read"],
        "tool": ["read"],
        "settings": ["read"],
        "user": ["read"],
        "license": ["read"],
        "report": ["read", "export"],
        "audit_log": ["read"],
    },
}


class RBACManager:
    """Gestor de RBAC granular con soporte para permisos por recurso."""

    _instance: "RBACManager | None" = None
    _lock = threading.RLock()

    def __new__(cls) -> "RBACManager":
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
            self._ensure_tables()

    # ── Inicializacion de tablas ──────────────────────────

    def _ensure_tables(self) -> None:
        """Crea las tablas RBAC si no existen."""
        conn = self._db.get_connection()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS rbac_permissions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                resource    TEXT NOT NULL,
                action      TEXT NOT NULL,
                description TEXT,
                UNIQUE(resource, action)
            );

            CREATE TABLE IF NOT EXISTS rbac_roles (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                description TEXT,
                is_default  INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS rbac_role_permissions (
                role_id       INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES rbac_roles(id),
                FOREIGN KEY (permission_id) REFERENCES rbac_permissions(id)
            );

            CREATE TABLE IF NOT EXISTS rbac_user_roles (
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (role_id) REFERENCES rbac_roles(id)
            );

            CREATE TABLE IF NOT EXISTS rbac_resource_permissions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                resource    TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                actions     TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_rbac_user_roles
                ON rbac_user_roles(user_id);
            CREATE INDEX IF NOT EXISTS idx_rbac_resource_perms
                ON rbac_resource_permissions(user_id, resource);
        """)
        conn.commit()
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Inicializa permisos y roles por defecto si no existen."""
        # Crear permisos si no existen
        existing = self._db.fetchone("SELECT COUNT(*) as c FROM rbac_permissions")
        if existing and existing["c"] > 0:
            return

        # Insertar todos los permisos
        for resource in RESOURCES:
            for action in ACTIONS:
                self._db.execute(
                    "INSERT OR IGNORE INTO rbac_permissions (resource, action, description) VALUES (?, ?, ?)",
                    (resource, action, f"{action} en {resource}"),
                )
        self._db.commit()

        # Crear roles por defecto
        for role_name, perms in DEFAULT_ROLE_PERMISSIONS.items():
            self._db.execute(
                "INSERT OR IGNORE INTO rbac_roles (name, description, is_default) VALUES (?, ?, ?)",
                (role_name, f"Rol por defecto: {role_name}", 1),
            )
            self._db.commit()

            role_row = self._db.fetchone("SELECT id FROM rbac_roles WHERE name = ?", (role_name,))
            if not role_row:
                continue
            role_id = role_row["id"]

            for resource, actions in perms.items():
                for action in actions:
                    perm_row = self._db.fetchone(
                        "SELECT id FROM rbac_permissions WHERE resource = ? AND action = ?",
                        (resource, action),
                    )
                    if perm_row:
                        self._db.execute(
                            "INSERT OR IGNORE INTO rbac_role_permissions (role_id, permission_id) VALUES (?, ?)",
                            (role_id, perm_row["id"]),
                        )
        self._db.commit()
        logger.info("RBAC: Permisos y roles por defecto inicializados")

    # ── Verificacion de permisos ──────────────────────────

    def check_permission(self, user_id: int, resource: str, action: str, resource_id: str | None = None) -> bool:
        """Verifica si un usuario tiene un permiso especifico.

        Primero verifica permisos de rol, luego permisos de recurso.
        Si el usuario tiene roles RBAC, usa esos. Si no, hace fallback
        al sistema legacy de 3 roles.
        """
        # 1. Verificar roles RBAC
        user_perms = self.get_user_permissions(user_id)
        perm_key = f"{resource}:{action}"
        if perm_key in user_perms:
            return True

        # 2. Verificar permisos a nivel de recurso
        if resource_id:
            resource_perms = self._get_resource_permissions(user_id, resource, resource_id)
            if action in resource_perms:
                return True

        # 3. Fallback al sistema legacy
        return self._check_legacy_permission(user_id, resource, action)

    def get_user_permissions(self, user_id: int) -> dict[str, bool]:
        """Obtiene todos los permisos de un usuario (desde sus roles)."""
        roles = self._get_user_roles(user_id)

        # Si no tiene roles RBAC, derivar permisos del rol legacy
        if not roles:
            return self._get_legacy_permissions(user_id)

        permissions: dict[str, bool] = {}
        for role_name in roles:
            role_perms = self._get_role_permissions(role_name)
            for perm in role_perms:
                key = f"{perm['resource']}:{perm['action']}"
                permissions[key] = True
        return permissions

    def _get_user_roles(self, user_id: int) -> list[str]:
        """Obtiene los nombres de los roles de un usuario."""
        rows = self._db.fetchall(
            """
            SELECT r.name FROM rbac_roles r
            JOIN rbac_user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = ?
            """,
            (user_id,),
        )
        return [row["name"] for row in rows]

    def _get_role_permissions(self, role_name: str) -> list[dict]:
        """Obtiene los permisos de un rol."""
        return self._db.fetchall(
            """
            SELECT p.resource, p.action FROM rbac_permissions p
            JOIN rbac_role_permissions rp ON p.id = rp.permission_id
            JOIN rbac_roles r ON rp.role_id = r.id
            WHERE r.name = ?
            """,
            (role_name,),
        )

    def _get_resource_permissions(self, user_id: int, resource: str, resource_id: str) -> list[str]:
        """Obtiene las acciones permitidas para un recurso especifico."""
        rows = self._db.fetchall(
            """
            SELECT actions FROM rbac_resource_permissions
            WHERE user_id = ? AND resource = ? AND resource_id = ?
            """,
            (user_id, resource, resource_id),
        )
        actions: list[str] = []
        for row in rows:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                actions.extend(json.loads(row["actions"]))
        return actions

    def _check_legacy_permission(self, user_id: int, resource: str, action: str) -> bool:
        """Fallback al sistema de 3 roles legacy."""
        user = self._db.get_user(user_id)
        if not user:
            return False
        role = user.get("role", "viewer")
        if role not in DEFAULT_ROLE_PERMISSIONS:
            role = "viewer"
        return action in DEFAULT_ROLE_PERMISSIONS[role].get(resource, [])

    def _get_legacy_permissions(self, user_id: int) -> dict[str, bool]:
        """Obtiene permisos derivados del rol legacy."""
        user = self._db.get_user(user_id)
        if not user:
            return {}
        role = user.get("role", "viewer")
        if role not in DEFAULT_ROLE_PERMISSIONS:
            role = "viewer"
        perms: dict[str, bool] = {}
        for res, actions in DEFAULT_ROLE_PERMISSIONS[role].items():
            for act in actions:
                perms[f"{res}:{act}"] = True
        return perms

    # ── Gestion de roles ──────────────────────────────────

    def create_role(self, name: str, description: str = "", permissions: list[str] | None = None) -> dict:
        """Crea un rol personalizado.

        Args:
            name: Nombre del rol (unico)
            description: Descripcion del rol
            permissions: Lista de permisos en formato "resource:action"
        """
        existing = self._db.fetchone("SELECT id FROM rbac_roles WHERE name = ?", (name,))
        if existing:
            return {"status": "error", "message": f"El rol '{name}' ya existe"}

        cursor = self._db.execute(
            "INSERT INTO rbac_roles (name, description, is_default) VALUES (?, ?, 0)",
            (name, description),
        )
        self._db.commit()
        role_id = cursor.lastrowid

        if permissions:
            for perm_str in permissions:
                parts = perm_str.split(":", 1)
                if len(parts) != 2:
                    continue
                resource, action = parts
                perm_row = self._db.fetchone(
                    "SELECT id FROM rbac_permissions WHERE resource = ? AND action = ?",
                    (resource, action),
                )
                if perm_row:
                    self._db.execute(
                        "INSERT OR IGNORE INTO rbac_role_permissions (role_id, permission_id) VALUES (?, ?)",
                        (role_id, perm_row["id"]),
                    )
            self._db.commit()

        logger.info(f"RBAC: Rol '{name}' creado con {len(permissions or [])} permisos")
        return {"status": "ok", "role_id": role_id, "name": name}

    def assign_role(self, user_id: int, role_name: str) -> dict:
        """Asigna un rol a un usuario."""
        role = self._db.fetchone("SELECT id FROM rbac_roles WHERE name = ?", (role_name,))
        if not role:
            return {"status": "error", "message": f"Rol '{role_name}' no encontrado"}

        self._db.execute(
            "INSERT OR IGNORE INTO rbac_user_roles (user_id, role_id) VALUES (?, ?)",
            (user_id, role["id"]),
        )
        self._db.commit()
        logger.info(f"RBAC: Rol '{role_name}' asignado a usuario {user_id}")
        return {"status": "ok", "user_id": user_id, "role": role_name}

    def revoke_role(self, user_id: int, role_name: str) -> dict:
        """Revoca un rol de un usuario."""
        role = self._db.fetchone("SELECT id FROM rbac_roles WHERE name = ?", (role_name,))
        if not role:
            return {"status": "error", "message": f"Rol '{role_name}' no encontrado"}

        self._db.execute(
            "DELETE FROM rbac_user_roles WHERE user_id = ? AND role_id = ?",
            (user_id, role["id"]),
        )
        self._db.commit()
        logger.info(f"RBAC: Rol '{role_name}' revocado de usuario {user_id}")
        return {"status": "ok"}

    def delete_role(self, role_name: str) -> dict:
        """Elimina un rol personalizado (no los por defecto)."""
        role = self._db.fetchone("SELECT id, is_default FROM rbac_roles WHERE name = ?", (role_name,))
        if not role:
            return {"status": "error", "message": f"Rol '{role_name}' no encontrado"}

        if role["is_default"]:
            return {"status": "error", "message": "No se pueden eliminar roles por defecto"}

        # Eliminar asignaciones y permisos del rol
        self._db.execute("DELETE FROM rbac_user_roles WHERE role_id = ?", (role["id"],))
        self._db.execute("DELETE FROM rbac_role_permissions WHERE role_id = ?", (role["id"],))
        self._db.execute("DELETE FROM rbac_roles WHERE id = ?", (role["id"],))
        self._db.commit()
        logger.info(f"RBAC: Rol '{role_name}' eliminado")
        return {"status": "ok"}

    # ── Permisos a nivel de recurso ───────────────────────

    def grant_resource_access(self, user_id: int, resource: str, resource_id: str, actions: list[str]) -> dict:
        """Otorga acceso a un recurso especifico para un usuario.

        Args:
            user_id: ID del usuario
            resource: Tipo de recurso (workflow, connector, etc.)
            resource_id: ID del recurso especifico
            actions: Lista de acciones permitidas
        """
        # Verificar si ya existe
        existing = self._db.fetchone(
            """
            SELECT id, actions FROM rbac_resource_permissions
            WHERE user_id = ? AND resource = ? AND resource_id = ?
            """,
            (user_id, resource, resource_id),
        )

        if existing:
            # Merge actions
            try:
                current_actions = json.loads(existing["actions"])
            except (json.JSONDecodeError, TypeError):
                current_actions = []
            merged = list(set(current_actions + actions))
            self._db.execute(
                "UPDATE rbac_resource_permissions SET actions = ? WHERE id = ?",
                (json.dumps(merged), existing["id"]),
            )
        else:
            self._db.execute(
                """
                INSERT INTO rbac_resource_permissions (user_id, resource, resource_id, actions)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, resource, resource_id, json.dumps(actions)),
            )
        self._db.commit()
        logger.info(f"RBAC: Acceso a {resource}:{resource_id} concedido para usuario {user_id}")
        return {"status": "ok", "resource": resource, "resource_id": resource_id, "actions": actions}

    def revoke_resource_access(
        self, user_id: int, resource: str, resource_id: str, actions: list[str] | None = None
    ) -> dict:
        """Revoca acceso a un recurso especifico.

        Si actions es None, revoca todo el acceso al recurso.
        """
        if actions is None:
            self._db.execute(
                """
                DELETE FROM rbac_resource_permissions
                WHERE user_id = ? AND resource = ? AND resource_id = ?
                """,
                (user_id, resource, resource_id),
            )
        else:
            existing = self._db.fetchone(
                """
                SELECT id, actions FROM rbac_resource_permissions
                WHERE user_id = ? AND resource = ? AND resource_id = ?
                """,
                (user_id, resource, resource_id),
            )
            if existing:
                try:
                    current = json.loads(existing["actions"])
                except (json.JSONDecodeError, TypeError):
                    current = []
                remaining = [a for a in current if a not in actions]
                if remaining:
                    self._db.execute(
                        "UPDATE rbac_resource_permissions SET actions = ? WHERE id = ?",
                        (json.dumps(remaining), existing["id"]),
                    )
                else:
                    self._db.execute("DELETE FROM rbac_resource_permissions WHERE id = ?", (existing["id"],))
        self._db.commit()
        return {"status": "ok"}

    # ── Integracion con sesiones Flask ────────────────────

    def load_user_permissions_to_session(self, user_id: int) -> dict[str, bool]:
        """Carga los permisos del usuario en la sesion Flask.

        Se debe llamar despues del login para cachear permisos.
        """
        perms = self.get_user_permissions(user_id)
        from flask import session

        session["permissions"] = list(perms.keys())
        session["rbac_loaded"] = True
        logger.debug(f"RBAC: Permisos cargados para usuario {user_id}: {len(perms)} permisos")
        return perms

    def list_roles(self) -> list[dict]:
        """Lista todos los roles disponibles."""
        return self._db.fetchall(
            "SELECT id, name, description, is_default FROM rbac_roles ORDER BY is_default DESC, name"
        )

    def list_role_permissions(self, role_name: str) -> list[dict]:
        """Lista los permisos de un rol."""
        return self._db.fetchall(
            """
            SELECT p.resource, p.action, p.description FROM rbac_permissions p
            JOIN rbac_role_permissions rp ON p.id = rp.permission_id
            JOIN rbac_roles r ON rp.role_id = r.id
            WHERE r.name = ?
            ORDER BY p.resource, p.action
            """,
            (role_name,),
        )

    def list_user_resource_permissions(self, user_id: int) -> list[dict]:
        """Lista los permisos de recurso para un usuario."""
        return self._db.fetchall(
            """
            SELECT resource, resource_id, actions, created_at
            FROM rbac_resource_permissions
            WHERE user_id = ?
            ORDER BY resource, resource_id
            """,
            (user_id,),
        )


# ── Decorador Flask para permisos ─────────────────────────


def require_permission(resource: str, action: str):
    """Decorador Flask: requiere un permiso especifico para acceder a la ruta.

    Verifica los permisos del usuario actual contra el RBAC granular.
    Si el usuario no tiene el permiso, retorna 403.

    Args:
        resource: Recurso a verificar (workflow, connector, tool, etc.)
        action: Accion a verificar (create, read, update, delete, etc.)

    Usage:
        @app.route("/api/workflows", methods=["POST"])
        @login_required
        @require_permission("workflow", "create")
        def api_create_workflow():
            ...
    """
    from functools import wraps

    from flask import jsonify, session

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user" not in session:
                return jsonify({"error": "No autenticado"}), 401

            # Verificar si los permisos estan en sesion
            permissions = session.get("permissions", [])
            perm_key = f"{resource}:{action}"

            if perm_key in permissions:
                return f(*args, **kwargs)

            # Si no estan en sesion, verificar contra RBAC
            user_id = session.get("user_id")
            if user_id:
                rbac = RBACManager()
                resource_id = kwargs.get("id") or kwargs.get("wf_id")
                if rbac.check_permission(user_id, resource, action, resource_id):
                    return f(*args, **kwargs)

            return jsonify({"error": f"Permiso denegado: {resource}:{action}"}), 403

        return decorated

    return decorator
