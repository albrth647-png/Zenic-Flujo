"""
Workflow Determinista — Data Keeper Repository
Persistencia para colecciones dinámicas de datos.

Cada colección se almacena como una tabla SQLite separada creada dinámicamente.
La tabla data_keeper_collections guarda el catálogo de colecciones.
"""

import json
import sqlite3
from datetime import datetime

from src.core.db.sql_builder import quote_identifier
from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.hat.level5_tools.data.data_keeper.models import validate_name, validate_schema
from typing import Any

logger = setup_logging(__name__)


class DataKeeperRepository:
    """Repositorio para colecciones dinámicas."""

    def __init__(self):
        self._db = DatabaseManager()

    def _init_collections_catalog(self) -> None:
        """Crea la tabla catálogo de colecciones si no existe."""
        conn = self._db.get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_keeper_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                schema TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

    def create_collection(self, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Crea una nueva colección con su schema."""
        self._init_collections_catalog()

        # Validar nombre y schema
        validate_name(name)
        validate_schema(schema)

        # Verificar que no exista
        existing = self._db.fetchone(
            "SELECT id FROM data_keeper_collections WHERE name = ?",
            (name,),
        )
        if existing:
            raise ValueError(f"La colección '{name}' ya existe")

        # Insertar en catálogo
        cursor = self._db.execute(
            "INSERT INTO data_keeper_collections (name, schema) VALUES (?, ?)",
            (name, json.dumps(schema)),
        )
        self._db.commit()
        collection_id = cursor.lastrowid

        logger.info(f"Colección creada: {name} (ID: {collection_id})")
        return {
            "id": collection_id,
            "name": name,
            "schema": schema,
            "created_at": datetime.now().isoformat(),
        }

    def list_collections(self) -> list[dict]:
        """Lista todas las colecciones."""
        self._init_collections_catalog()
        rows = self._db.fetchall("SELECT id, name, schema, created_at FROM data_keeper_collections ORDER BY name")
        result = []
        for row in rows:
            collection = dict(row)
            collection["schema"] = json.loads(collection["schema"])
            result.append(collection)
        return result

    def get_collection(self, name: str) -> dict[str, Any] | None:
        """Obtiene una colección por nombre."""
        self._init_collections_catalog()
        row = self._db.fetchone(
            "SELECT id, name, schema, created_at FROM data_keeper_collections WHERE name = ?",
            (name,),
        )
        if not row:
            return None
        collection = dict(row)
        collection["schema"] = json.loads(collection["schema"])
        return collection

    def _ensure_data_table(self, collection_name: str, schema: dict[str, Any]) -> None:
        """
        Crea o asegura que existe la tabla de datos para una colección.
        Cada colección tiene su propia tabla: dk_{collection_name}
        """
        conn = self._db.get_connection()
        # collection_name is validated by validate_name() before use (only alphanumeric + underscore)
        table_name = f"dk_{collection_name}"

        # Mapeo de tipos
        type_map = {
            "string": "TEXT",
            "text": "TEXT",
            "number": "REAL",
            "boolean": "INTEGER",
            "date": "TEXT",
        }

        # Construir columnas
        columns = [
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        ]

        for field_name, field_type in schema.items():
            sql_type = type_map.get(field_type, "TEXT")
            columns.append(f'"{field_name}" {sql_type}')

        # Crear tabla — table_name y columns ya validados por validate_name() + quote_identifier.
        # B608 mitigado: identificadores pasan quote_identifier (regex estricto).
        create_sql = f"CREATE TABLE IF NOT EXISTS {quote_identifier(table_name)} ({', '.join(columns)})"
        conn.execute(create_sql)  # nosec B608 — identificadores validados
        conn.commit()

    def insert(self, collection_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Inserta un registro en una colección."""
        collection = self.get_collection(collection_name)
        if not collection:
            raise ValueError(f"Colección '{collection_name}' no encontrada")

        self._ensure_data_table(collection_name, collection["schema"])
        # collection_name is validated by validate_name() before use (only alphanumeric + underscore)
        table_name = f"dk_{collection_name}"

        # Filtrar solo campos del schema (quitar id, created_at, etc.)
        from src.hat.level5_tools.data.data_keeper.models import validate_record

        validate_record(data, collection["schema"])

        allowed_fields = [k for k in data if k in collection["schema"]]
        if not allowed_fields:
            raise ValueError("No hay campos válidos para insertar")

        values = [data[field] for field in allowed_fields]
        field_list = ", ".join(f'"{f}"' for f in allowed_fields)
        placeholders = ", ".join("?" for _ in allowed_fields)

        conn = self._db.get_connection()
        # table_name y field_list validados via quote_identifier (B608 mitigado).
        cursor = conn.execute(
            f"INSERT INTO {quote_identifier(table_name)} ({field_list}) VALUES ({placeholders})",  # nosec B608 — identificadores validados
            values,
        )
        conn.commit()
        record_id = cursor.lastrowid

        # Retornar el registro completo
        return self.get(collection_name, record_id)

    @staticmethod
    def _convert_types(record: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        """Convierte tipos de datos al recuperar de SQLite.
        SQLite no tiene booleanos nativos - los guarda como 0/1.
        """
        converted = dict(record)
        for field_name, field_type in schema.items():
            if field_name in converted and field_type == "boolean" and converted[field_name] is not None:
                converted[field_name] = bool(converted[field_name])
        return converted

    def get(self, collection_name: str, record_id: int) -> dict[str, Any] | None:
        """Obtiene un registro por ID."""
        collection = self.get_collection(collection_name)
        if not collection:
            return None

        # collection_name is validated by validate_name() before use (only alphanumeric + underscore)
        table_name = f"dk_{collection_name}"
        conn = self._db.get_connection()

        try:
            row = conn.execute(
                f"SELECT * FROM {quote_identifier(table_name)} WHERE id = ?",  # nosec B608 — table_name validado
                (record_id,),
            ).fetchone()

            if not row:
                return None

            # PRAGMA table_info retorna: cid, name, type, notnull, dflt_value, pk
            # desc[1] = name (nombre de columna)
            # table_name is safe: collection_name validated by validate_name() (only alphanumeric + underscore)
            columns = [desc[1] for desc in conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()]  # nosec B608 — table_name validado

            result = dict(zip(columns, row, strict=False))
            return self._convert_types(result, collection["schema"])

        except sqlite3.OperationalError:
            return None

    def query(self, collection_name: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        """Consulta registros con filtros opcionales."""
        collection = self.get_collection(collection_name)
        if not collection:
            return []

        self._ensure_data_table(collection_name, collection["schema"])
        # collection_name is validated by validate_name() before use (only alphanumeric + underscore)
        table_name = f"dk_{collection_name}"
        conn = self._db.get_connection()

        try:
            # Construir WHERE
            where_clauses = []
            values = []

            if filters:
                for field, value in filters.items():
                    if field in collection["schema"]:
                        where_clauses.append(f'"{field}" = ?')
                        values.append(value)

            where_sql = ""
            if where_clauses:
                where_sql = " WHERE " + " AND ".join(where_clauses)

            # table_name is safe: collection_name validated by validate_name() (only alphanumeric + underscore)
            sql = f"SELECT * FROM {quote_identifier(table_name)}{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"  # nosec B608 — table_name validado
            values.extend([limit, offset])

            rows = conn.execute(sql, values).fetchall()
            # table_name is safe: collection_name validated by validate_name() (only alphanumeric + underscore)
            columns = [desc[1] for desc in conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()]  # nosec B608 — table_name validado

            return [self._convert_types(dict(zip(columns, row, strict=False)), collection["schema"]) for row in rows]

        except sqlite3.OperationalError:
            return []

    def update(self, collection_name: str, record_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Actualiza un registro."""
        collection = self.get_collection(collection_name)
        if not collection:
            return None

        self._ensure_data_table(collection_name, collection["schema"])
        # collection_name is validated by validate_name() before use (only alphanumeric + underscore)
        table_name = f"dk_{collection_name}"
        conn = self._db.get_connection()

        # Filtrar solo campos del schema
        set_clauses = []
        values = []
        for field, value in data.items():
            if field in collection["schema"]:
                set_clauses.append(f'"{field}" = ?')
                values.append(value)

        if not set_clauses:
            return self.get(collection_name, record_id)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        set_sql = ", ".join(set_clauses)
        values.append(record_id)

        # table_name is safe: collection_name validated by validate_name() (only alphanumeric + underscore)
        conn.execute(
            f"UPDATE {quote_identifier(table_name)} SET {set_sql} WHERE id = ?",  # nosec B608 — table_name validado
            values,
        )
        conn.commit()

        return self.get(collection_name, record_id)

    def delete(self, collection_name: str, record_id: int) -> bool:
        """Elimina un registro."""
        collection = self.get_collection(collection_name)
        if not collection:
            return False

        self._ensure_data_table(collection_name, collection["schema"])
        # collection_name is validated by validate_name() before use (only alphanumeric + underscore)
        table_name = f"dk_{collection_name}"

        conn = self._db.get_connection()
        # table_name is safe: collection_name validated by validate_name() (only alphanumeric + underscore)
        cursor = conn.execute(
            f"DELETE FROM {quote_identifier(table_name)} WHERE id = ?",  # nosec B608 — table_name validado
            (record_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
