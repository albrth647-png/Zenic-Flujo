"""
Conector MySQL — Operaciones de Base de Datos MySQL
=======================================================

Permite ejecutar consultas, gestionar tablas y operaciones
CRUD en bases de datos MySQL usando pymysql driver
con HttpClient para operaciones REST (Presto/Trino) cuando
este disponible, o pymysql como driver directo.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class MysqlConnectorConnector(BaseConnector):
    """Conector para MySQL: consultas, tablas y operaciones CRUD."""

    name = "mysql_connector"
    version = "1.0.0"
    description = "Ejecuta consultas y gestiona tablas en bases de datos MySQL"
    category = "databases"
    icon = "database"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._host: str = "localhost"
        self._port: int = 3306
        self._database: str = ""
        self._username: str = ""
        self._password: str = ""
        self._http: HttpClient | None = None
        self._connection: Any | None = None
        self._use_http: bool = False

    def connect(self) -> bool:
        """Establece conexion con la base de datos MySQL."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("MysqlConnector: credenciales no configuradas")
            return False

        # Extract connection parameters from auth provider
        self._host = getattr(self._auth_provider, "_host", "") or getattr(self._auth_provider, "host", "localhost")
        self._port = int(getattr(self._auth_provider, "_port", 3306) or 3306)
        self._database = getattr(self._auth_provider, "_database", "") or getattr(self._auth_provider, "database", "")
        self._username = getattr(self._auth_provider, "_username", "") or getattr(self._auth_provider, "username", "")
        self._password = getattr(self._auth_provider, "_password", "") or getattr(self._auth_provider, "password", "")

        # Check if using HTTP transport (Presto/Trino)
        http_url = getattr(self._auth_provider, "_http_url", "") or getattr(self._auth_provider, "http_url", "")
        if http_url:
            self._use_http = True
            self._http = HttpClient(
                base_url=http_url,
                connector_name=self.name,
            )
            self._http.set_auth("Basic", username=self._username, password=self._password)
        else:
            # Use pymysql driver directly
            self._use_http = False
            try:
                import pymysql
                self._connection = pymysql.connect(
                    host=self._host,
                    port=self._port,
                    user=self._username,
                    password=self._password,
                    database=self._database,
                    cursorclass=pymysql.cursors.DictCursor,
                    connect_timeout=10,
                )
            except ImportError:
                logger.warning("MysqlConnector: pymysql no instalado, intentando con mysql-connector-python")
                try:
                    import mysql.connector
                    self._connection = mysql.connector.connect(
                        host=self._host,
                        port=self._port,
                        user=self._username,
                        password=self._password,
                        database=self._database,
                    )
                except ImportError:
                    logger.error("MysqlConnector: ni pymysql ni mysql-connector-python estan instalados")
                    return False
            except Exception as e:
                logger.error(f"MysqlConnector: error conectando a MySQL: {e}")
                return False

        self._connected = True
        self._log_operation("connect", "Conexion MySQL establecida")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector MySQL.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "execute_query": self._execute_query,
            "execute_update": self._execute_update,
            "list_tables": self._list_tables,
            "describe_table": self._describe_table,
            "insert_row": self._insert_row,
            "create_table": self._create_table,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de MySQL esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con MySQL."""
        if self._connection is not None:
            with contextlib.suppress(Exception):
                self._connection.close()
            self._connection = None
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _ensure_connection(self) -> bool:
        """Ensure the MySQL connection is alive, reconnect if needed."""
        if self._use_http or self._connection is None:
            return True
        try:
            self._connection.ping(reconnect=True)
            return True
        except Exception:
            try:
                self.connect()
                return True
            except Exception:
                return False

    def _execute_query_http(self, query: str, query_params: list[Any] | None = None) -> dict[str, Any]:
        """Execute a query via HTTP (Presto/Trino)."""
        try:
            body: dict[str, Any] = {"query": query}
            if query_params:
                body["params"] = query_params

            response = self._http.post("/v1/statement", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            columns = [col.get("name", "") for col in data.get("columns", [])]
            rows = data.get("data", [])
            return {
                "success": True,
                "rows": rows,
                "rowcount": len(rows),
                "columns": columns,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _execute_query_driver(self, query: str, query_params: tuple | list | None = None) -> dict[str, Any]:
        """Execute a query using pymysql/mysql-connector driver."""
        try:
            if not self._ensure_connection():
                return {"success": False, "error": "No hay conexion activa a MySQL"}

            with self._connection.cursor() as cursor:
                if query_params:
                    cursor.execute(query, query_params)
                else:
                    cursor.execute(query)

                rows = cursor.fetchall()
                # Extract column names from cursor description
                columns = []
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]

                # Convert rows to list of dicts if they're not already
                result_rows = []
                for row in rows:
                    if isinstance(row, dict):
                        result_rows.append(row)
                    elif isinstance(row, (tuple, list)):
                        result_rows.append(dict(zip(columns, row, strict=False)))
                    else:
                        result_rows.append(row)

                return {
                    "success": True,
                    "rows": result_rows,
                    "rowcount": len(result_rows),
                    "columns": columns,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _execute_query(self, params: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta una consulta SELECT en MySQL.

        Args:
            params: Debe contener 'query' y opcionalmente 'params' (parametros preparados)
        """
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Parametro requerido: query"}
        self._log_operation("execute_query", f"query={query[:80]}...")

        query_params = params.get("params")
        if self._use_http:
            return self._execute_query_http(query, query_params)
        return self._execute_query_driver(query, query_params)

    def _execute_update(self, params: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta una consulta INSERT/UPDATE/DELETE en MySQL.

        Args:
            params: Debe contener 'query' y opcionalmente 'params'
        """
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Parametro requerido: query"}
        self._log_operation("execute_update", f"query={query[:80]}...")

        query_params = params.get("params")

        if self._use_http:
            return self._execute_query_http(query, query_params)

        # Using driver
        try:
            if not self._ensure_connection():
                return {"success": False, "error": "No hay conexion activa a MySQL"}

            with self._connection.cursor() as cursor:
                if query_params:
                    cursor.execute(query, query_params)
                else:
                    cursor.execute(query)
                self._connection.commit()
                return {
                    "success": True,
                    "rowcount": cursor.rowcount,
                    "lastrowid": cursor.lastrowid,
                }
        except Exception as e:
            with contextlib.suppress(Exception):
                self._connection.rollback()
            return {"success": False, "error": str(e)}

    def _list_tables(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista las tablas de la base de datos MySQL."""
        self._log_operation("list_tables")

        query = "SHOW TABLES"
        if self._use_http:
            return self._execute_query_http(query)

        result = self._execute_query_driver(query)
        if result["success"]:
            tables = [next(iter(row.values())) for row in result.get("rows", [])]
            return {"success": True, "tables": tables}
        return result

    def _describe_table(self, params: dict[str, Any]) -> dict[str, Any]:
        """Describe la estructura de una tabla MySQL.

        Args:
            params: Debe contener 'table_name'
        """
        table_name = params.get("table_name", "")
        if not table_name:
            return {"success": False, "error": "Parametro requerido: table_name"}
        self._log_operation("describe_table", f"table={table_name}")

        # Validar nombre de tabla para prevenir SQL injection
        if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
            return {"success": False, "error": f"Nombre de tabla invalido: {table_name}"}

        # Fix NEW-BUG-1 (verificación Sprint 4): antes era "DESCRIBE ?" con
        # placeholder, pero MySQL NO acepta placeholders para identificadores
        # en DDL → runtime failure. Como table_name está validado con regex
        # estricto arriba, es seguro interpolar directamente.
        query = f"DESCRIBE {table_name}"  # nosec B608 — table_name validado con regex ^[a-zA-Z0-9_]+$
        if self._use_http:
            return self._execute_query_http(query, [])

        result = self._execute_query_driver(query, [])
        if result["success"]:
            return {
                "success": True,
                "table_name": table_name,
                "columns": result.get("rows", []),
            }
        return result

    def _insert_row(self, params: dict[str, Any]) -> dict[str, Any]:
        """Inserta una fila en una tabla MySQL.

        Args:
            params: Debe contener 'table_name' y 'data' (dict columna: valor)
        """
        table_name = params.get("table_name", "")
        data = params.get("data", {})
        if not table_name or not data:
            return {"success": False, "error": "Parametros requeridos: table_name, data"}
        self._log_operation("insert_row", f"table={table_name}")

        # Validar nombre de tabla para prevenir SQL injection
        if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
            return {"success": False, "error": f"Nombre de tabla invalido: {table_name}"}

        # Validar nombres de columnas
        for col in data:
            if not re.match(r'^[a-zA-Z0-9_]+$', col):
                return {"success": False, "error": f"Nombre de columna invalido: {col}"}

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        values = list(data.values())
        # table_name y columns validados con regex ^[a-zA-Z0-9_]+$ arriba (B608 mitigado).
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"  # nosec B608 — identificadores validados con regex

        if self._use_http:
            return self._execute_query_http(query, values)

        try:
            if not self._ensure_connection():
                return {"success": False, "error": "No hay conexion activa a MySQL"}

            with self._connection.cursor() as cursor:
                cursor.execute(query, values)
                self._connection.commit()
                return {
                    "success": True,
                    "table_name": table_name,
                    "lastrowid": cursor.lastrowid,
                    "rowcount": cursor.rowcount,
                }
        except Exception as e:
            with contextlib.suppress(Exception):
                self._connection.rollback()
            return {"success": False, "error": str(e)}

    def _create_table(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una tabla en MySQL.

        Args:
            params: Debe contener 'table_name' y 'columns' (lista de definiciones)
        """
        table_name = params.get("table_name", "")
        columns = params.get("columns", [])
        if not table_name or not columns:
            return {"success": False, "error": "Parametros requeridos: table_name, columns"}
        self._log_operation("create_table", f"table={table_name}")

        # Validar nombre de tabla para prevenir SQL injection
        if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
            return {"success": False, "error": f"Nombre de tabla invalido: {table_name}"}

        # columns can be a list of column definition strings or dicts
        if isinstance(columns, list):
            col_defs = []
            for col in columns:
                if isinstance(col, str):
                    # Validar definiciones de columnas string
                    if not re.match(r'^[a-zA-Z0-9_\s,()]+$', col):
                        return {"success": False, "error": f"Definicion de columna invalida: {col}"}
                    col_defs.append(col)
                elif isinstance(col, dict):
                    name = col.get("name", "")
                    col_type = col.get("type", "TEXT")
                    constraints = col.get("constraints", "")
                    # Validar nombre de columna
                    if not re.match(r'^[a-zA-Z0-9_]+$', name):
                        return {"success": False, "error": f"Nombre de columna invalido: {name}"}
                    # Validar tipo de dato (lista blanca de tipos MySQL comunes)
                    allowed_types = {"INT", "VARCHAR", "TEXT", "DATETIME", "TIMESTAMP", "DECIMAL", "FLOAT", "DOUBLE", "BOOLEAN", "CHAR", "BLOB", "JSON"}
                    if col_type.upper() not in allowed_types:
                        return {"success": False, "error": f"Tipo de dato no permitido: {col_type}"}
                    definition = f"{name} {col_type}"
                    if constraints:
                        definition += f" {constraints}"
                    col_defs.append(definition)
            columns_str = ", ".join(col_defs)
        else:
            columns_str = str(columns)

        query = f"CREATE TABLE {table_name} ({columns_str})"

        if self._use_http:
            return self._execute_query_http(query)

        try:
            if not self._ensure_connection():
                return {"success": False, "error": "No hay conexion activa a MySQL"}

            with self._connection.cursor() as cursor:
                cursor.execute(query)
                self._connection.commit()
                return {
                    "success": True,
                    "table_name": table_name,
                    "created": True,
                }
        except Exception as e:
            with contextlib.suppress(Exception):
                self._connection.rollback()
            return {"success": False, "error": str(e)}


MYSQL_SCHEMA = ConnectorSchema(
    name="mysql_connector",
    version="1.0.0",
    description="Ejecuta consultas y gestiona tablas en bases de datos MySQL",
    category="databases",
    icon="database",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="execute_query", description="Ejecuta consulta SELECT", category="read"),
        ActionDefinition(name="execute_update", description="Ejecuta INSERT/UPDATE/DELETE", category="write"),
        ActionDefinition(name="list_tables", description="Lista tablas", category="read"),
        ActionDefinition(name="describe_table", description="Describe estructura de tabla", category="read"),
        ActionDefinition(name="insert_row", description="Inserta una fila", category="write"),
        ActionDefinition(name="create_table", description="Crea una tabla", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="basic", required_fields=["host", "username", "password", "database"], description="Credenciales MySQL")
    ],
)
