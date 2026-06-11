"""
PostgreSQL Connector — Query, insert, update
================================================

Sprint 6 del Roadmap Competitivo.
Conector para bases de datos PostgreSQL usando psycopg2.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class PostgreSQLService:
    """
    Conector PostgreSQL.

    Proporciona:
    - query: Consultas SELECT arbitrarias
    - insert: Insertar registros
    - update: Actualizar registros
    - execute: SQL arbitrario
    - list_tables: Listar tablas
    - get_schema: Obtener schema de una tabla

    Uso en workflow:
    {
        "tool": "postgresql",
        "action": "query",
        "params": {
            "connection_string": "$settings.pg_connection_string",
            "sql": "SELECT * FROM users WHERE email = $input.email"
        }
    }

    La conexión se configura en Settings del sistema:
    - pg_connection_string: postgresql://user:pass@host:5432/dbname
    """

    def __init__(self):
        self._psycopg2 = None

    def _get_connection(self, connection_string: str):
        """Obtiene una conexión PostgreSQL."""
        try:
            import psycopg2

            self._psycopg2 = psycopg2
        except ImportError:
            raise ImportError("psycopg2 no está instalado. Instálalo con: pip install psycopg2-binary") from None

        try:
            conn = self._psycopg2.connect(connection_string, connect_timeout=10)
            return conn
        except self._psycopg2.OperationalError as e:
            raise ConnectionError(f"Error conectando a PostgreSQL: {e}") from e

    def query(self, sql: str, params: list | None = None, connection_string: str = "", limit: int = 100) -> dict:
        """
        Ejecuta una consulta SELECT.

        Args:
            sql: Consulta SQL
            params: Parámetros posicionales para la consulta
            connection_string: String de conexión PostgreSQL
            limit: Límite de filas

        Returns:
            dict con {columns, rows, row_count, duration_ms}
        """
        if not connection_string:
            return self._error("connection_string requerida")

        start_time = time.time()

        try:
            conn = self._get_connection(connection_string)
            cursor = conn.cursor()

            # Agregar límite si no existe
            final_sql = sql.strip()
            if not final_sql.upper().startswith("SELECT"):
                return self._error("Solo se permiten consultas SELECT en query()")
            if "LIMIT" not in final_sql.upper():
                final_sql += f" LIMIT {limit}"

            cursor.execute(final_sql, params or [])
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()

            # Convertir a lista de dicts
            result_rows = []
            for row in rows:
                result_rows.append(dict(zip(columns, [self._serialize(v) for v in row], strict=False)))

            cursor.close()
            conn.close()

            return {
                "columns": columns,
                "rows": result_rows,
                "row_count": len(result_rows),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError as e:
            return self._error(str(e))
        except ConnectionError as e:
            return self._error(str(e))
        except Exception as e:
            logger.error(f"PostgreSQL query error: {e}")
            return self._error(f"Error en consulta: {e}")

    def insert(self, table: str, data: dict, connection_string: str = "") -> dict:
        """
        Inserta un registro en una tabla.

        Args:
            table: Nombre de la tabla
            data: Dict con {columna: valor}
            connection_string: String de conexión

        Returns:
            dict con {inserted_id, row_count, duration_ms}
        """
        if not connection_string:
            return self._error("connection_string requerida")
        if not data:
            return self._error("data requerido")

        start_time = time.time()

        columns = list(data.keys())
        values = [data[c] for c in columns]
        placeholders = ", ".join(["%s"] * len(columns))
        columns_str = ", ".join(columns)

        sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) RETURNING *"

        try:
            conn = self._get_connection(connection_string)
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()

            # Obtener fila insertada
            columns_desc = [desc[0] for desc in cursor.description] if cursor.description else []
            row = cursor.fetchone()
            inserted = dict(zip(columns_desc, [self._serialize(v) for v in row], strict=False)) if row else {}

            cursor.close()
            conn.close()

            return {
                "inserted": inserted,
                "row_count": 1,
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError as e:
            return self._error(str(e))
        except Exception as e:
            logger.error(f"PostgreSQL insert error: {e}")
            return self._error(f"Error insertando: {e}")

    def update(
        self, table: str, data: dict, where: str, where_params: list | None = None, connection_string: str = ""
    ) -> dict:
        """
        Actualiza registros en una tabla.

        Args:
            table: Nombre de la tabla
            data: Dict con {columna: valor}
            where: Condición WHERE (ej: "id = %s")
            where_params: Parámetros para WHERE
            connection_string: String de conexión

        Returns:
            dict con {updated_count, duration_ms}
        """
        if not connection_string:
            return self._error("connection_string requerida")
        if not data:
            return self._error("data requerido")

        start_time = time.time()

        set_clauses = [f"{col} = %s" for col in data]
        values = [data[col] for col in data]
        if where_params:
            values.extend(where_params)

        sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {where}"

        try:
            conn = self._get_connection(connection_string)
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()

            updated = cursor.rowcount
            cursor.close()
            conn.close()

            return {
                "updated_count": updated,
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError as e:
            return self._error(str(e))
        except Exception as e:
            logger.error(f"PostgreSQL update error: {e}")
            return self._error(f"Error actualizando: {e}")

    def execute(self, sql: str, params: list | None = None, connection_string: str = "") -> dict:
        """
        Ejecuta SQL arbitrario (INSERT, UPDATE, DELETE, CREATE, etc.).

        Args:
            sql: Comando SQL
            params: Parámetros
            connection_string: String de conexión

        Returns:
            dict con {row_count, duration_ms}
        """
        if not connection_string:
            return self._error("connection_string requerida")

        start_time = time.time()

        try:
            conn = self._get_connection(connection_string)
            cursor = conn.cursor()
            cursor.execute(sql, params or [])
            conn.commit()

            affected = cursor.rowcount
            cursor.close()
            conn.close()

            return {
                "row_count": affected,
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError as e:
            return self._error(str(e))
        except Exception as e:
            logger.error(f"PostgreSQL execute error: {e}")
            return self._error(f"Error ejecutando SQL: {e}")

    def list_tables(self, connection_string: str = "", schema: str = "public") -> dict:
        """
        Lista tablas en un schema.

        Args:
            connection_string: String de conexión
            schema: Schema (default: public)

        Returns:
            dict con {tables: [{name, type}], count}
        """
        return self.query(
            "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
            [schema],
            connection_string,
            limit=500,
        )

    def get_schema(self, table: str, connection_string: str = "", schema: str = "public") -> dict:
        """
        Obtiene schema de una tabla.

        Args:
            table: Nombre de la tabla
            connection_string: String de conexión
            schema: Schema

        Returns:
            dict con {columns: [{name, type, nullable, default}], count}
        """
        return self.query(
            "SELECT column_name, data_type, is_nullable, "
            "column_default, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            [schema, table],
            connection_string,
            limit=500,
        )

    @staticmethod
    def _serialize(value: Any) -> Any:
        """Serializa valores no-JSON-serializables."""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, (Decimal,)):
            return float(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, set):
            return list(value)
        return value

    @staticmethod
    def _error(message: str) -> dict:
        return {"error": message, "status": "failed"}

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    @staticmethod
    def get_tool_definition() -> dict:
        return {
            "tool": "postgresql",
            "name": "PostgreSQL",
            "description": "Conexión a bases de datos PostgreSQL",
            "actions": {
                "query": {
                    "name": "Consulta SQL",
                    "description": "Ejecuta SELECT",
                    "params": [
                        {"name": "sql", "type": "string", "required": True, "label": "SQL"},
                        {"name": "connection_string", "type": "string", "required": True, "label": "Connection String"},
                    ],
                },
                "insert": {
                    "name": "Insertar",
                    "description": "Inserta un registro",
                    "params": [
                        {"name": "table", "type": "string", "required": True, "label": "Tabla"},
                        {"name": "data", "type": "dict", "required": True, "label": "Datos"},
                        {"name": "connection_string", "type": "string", "required": True, "label": "Connection String"},
                    ],
                },
                "update": {
                    "name": "Actualizar",
                    "description": "Actualiza registros",
                    "params": [
                        {"name": "table", "type": "string", "required": True, "label": "Tabla"},
                        {"name": "data", "type": "dict", "required": True, "label": "Datos"},
                        {"name": "where", "type": "string", "required": True, "label": "WHERE"},
                    ],
                },
            },
        }
