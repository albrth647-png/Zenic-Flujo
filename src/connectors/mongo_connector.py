"""
Conector MongoDB — Operaciones de Base de Datos MongoDB
==========================================================

Permite ejecutar operaciones CRUD, agregaciones y gestion
de colecciones en bases de datos MongoDB usando el
MongoDB Atlas Data API (REST) o motor/pymongo driver,
con HttpClient para las operaciones REST.
"""

from __future__ import annotations

import contextlib
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class MongoConnectorConnector(BaseConnector):
    """Conector para MongoDB: CRUD, agregaciones y gestion de colecciones."""

    name = "mongo_connector"
    version = "1.0.0"
    description = "Ejecuta operaciones CRUD y agregaciones en bases de datos MongoDB"
    category = "databases"
    icon = "database"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._connection_uri: str = "mongodb://localhost:27017"
        self._database: str = ""
        self._http: HttpClient | None = None
        self._client: Any | None = None
        self._use_http: bool = False
        self._data_api_url: str = ""
        self._data_source: str = ""

    def connect(self) -> bool:
        """Establece conexion con MongoDB."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("MongoConnector: credenciales no configuradas")
            return False

        # Extract connection parameters
        self._connection_uri = getattr(self._auth_provider, "_connection_uri", "") or getattr(self._auth_provider, "connection_uri", "mongodb://localhost:27017")
        self._database = getattr(self._auth_provider, "_database", "") or getattr(self._auth_provider, "database", "")
        self._data_api_url = getattr(self._auth_provider, "_data_api_url", "") or getattr(self._auth_provider, "data_api_url", "")
        self._data_source = getattr(self._auth_provider, "_data_source", "") or getattr(self._auth_provider, "data_source", "Cluster0")

        # If Atlas Data API URL is provided, use HTTP
        if self._data_api_url:
            self._use_http = True
            api_key = getattr(self._auth_provider, "_api_key", "") or getattr(self._auth_provider, "api_key", "")
            self._http = HttpClient(
                base_url=self._data_api_url,
                connector_name=self.name,
            )
            if api_key:
                self._http.set_header("api-key", api_key)
        else:
            # Use pymongo/motor driver
            self._use_http = False
            try:
                from pymongo import MongoClient
                self._client = MongoClient(self._connection_uri, serverSelectionTimeoutMS=10000)
                # Test connection
                self._client.admin.command("ping")
            except ImportError:
                logger.warning("MongoConnector: pymongo no instalado, intentando con motor")
                try:
                    import importlib.util

                    if importlib.util.find_spec("motor"):
                        # motor requires async, fall back to REST
                        self._use_http = True
                        self._http = HttpClient(
                            base_url="https://data.mongodb-api.com/app/data-api/endpoint/data/v1",
                            connector_name=self.name,
                        )
                    else:
                        raise ImportError("motor no instalado")
                except ImportError:
                    logger.error("MongoConnector: ni pymongo ni motor estan instalados")
                    return False
            except Exception as e:
                logger.error(f"MongoConnector: error conectando a MongoDB: {e}")
                return False

        self._connected = True
        self._log_operation("connect", "Conexion MongoDB establecida")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector MongoDB.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "find": self._find,
            "insert_one": self._insert_one,
            "update_one": self._update_one,
            "delete_one": self._delete_one,
            "aggregate": self._aggregate,
            "list_collections": self._list_collections,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de MongoDB esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con MongoDB."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _build_base_body(self, params: dict[str, Any]) -> dict[str, Any]:
        """Build the base body for MongoDB Atlas Data API requests."""
        database = params.get("database", self._database)
        collection = params.get("collection", "")
        body: dict[str, Any] = {
            "dataSource": self._data_source,
            "database": database,
            "collection": collection,
        }
        return body

    def _find_http(self, params: dict[str, Any]) -> dict[str, Any]:
        """Find documents via MongoDB Atlas Data API."""
        try:
            body = self._build_base_body(params)
            if params.get("filter"):
                body["filter"] = params["filter"]
            if params.get("projection"):
                body["projection"] = params["projection"]
            if params.get("limit"):
                body["limit"] = params["limit"]
            if params.get("skip"):
                body["skip"] = params["skip"]
            if params.get("sort"):
                body["sort"] = params["sort"]

            response = self._http.post("/action/find", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            documents = data.get("documents", [])
            return {
                "success": True,
                "documents": documents,
                "count": len(documents),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _find_driver(self, params: dict[str, Any]) -> dict[str, Any]:
        """Find documents using pymongo driver."""
        try:
            database = params.get("database", self._database)
            collection = params.get("collection", "")
            filter_doc = params.get("filter", {})
            limit = params.get("limit", 0)
            skip = params.get("skip", 0)
            projection = params.get("projection")
            sort = params.get("sort")

            db = self._client[database]
            col = db[collection]

            cursor = col.find(filter_doc, projection)
            if sort:
                cursor = cursor.sort(list(sort.items()))
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)

            documents = list(cursor)
            # Convert ObjectId to string
            for doc in documents:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])

            return {
                "success": True,
                "documents": documents,
                "count": len(documents),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find(self, params: dict[str, Any]) -> dict[str, Any]:
        """Busca documentos en una coleccion de MongoDB.

        Args:
            params: Debe contener 'database', 'collection' y opcionalmente 'filter', 'limit', 'projection'
        """
        database = params.get("database", "")
        collection = params.get("collection", "")
        if not database and not self._database:
            return {"success": False, "error": "Parametros requeridos: database, collection"}
        if not collection:
            return {"success": False, "error": "Parametro requerido: collection"}
        self._log_operation("find", f"db={database or self._database}, col={collection}")

        if self._use_http:
            return self._find_http(params)
        return self._find_driver(params)

    def _insert_one_http(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert a document via MongoDB Atlas Data API."""
        try:
            body = self._build_base_body(params)
            body["document"] = params["document"]

            response = self._http.post("/action/insertOne", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "inserted_id": data.get("insertedId", ""),
                "acknowledged": True,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _insert_one_driver(self, params: dict[str, Any]) -> dict[str, Any]:
        """Insert a document using pymongo driver."""
        try:
            database = params.get("database", self._database)
            collection = params.get("collection", "")
            document = params.get("document", {})

            db = self._client[database]
            col = db[collection]
            result = col.insert_one(document)

            return {
                "success": True,
                "inserted_id": str(result.inserted_id),
                "acknowledged": result.acknowledged,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _insert_one(self, params: dict[str, Any]) -> dict[str, Any]:
        """Inserta un documento en una coleccion de MongoDB.

        Args:
            params: Debe contener 'database', 'collection' y 'document'
        """
        database = params.get("database", "")
        collection = params.get("collection", "")
        document = params.get("document", {})
        if not database and not self._database:
            return {"success": False, "error": "Parametros requeridos: database, collection, document"}
        if not collection or not document:
            return {"success": False, "error": "Parametros requeridos: collection, document"}
        self._log_operation("insert_one", f"db={database or self._database}, col={collection}")

        if self._use_http:
            return self._insert_one_http(params)
        return self._insert_one_driver(params)

    def _update_one_http(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update a document via MongoDB Atlas Data API."""
        try:
            body = self._build_base_body(params)
            body["filter"] = params["filter"]
            body["update"] = params["update"]
            if params.get("upsert"):
                body["upsert"] = params["upsert"]

            response = self._http.post("/action/updateOne", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "matched_count": data.get("matchedCount", 0),
                "modified_count": data.get("modifiedCount", 0),
                "acknowledged": True,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _update_one_driver(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update a document using pymongo driver."""
        try:
            database = params.get("database", self._database)
            collection = params.get("collection", "")
            filter_doc = params.get("filter", {})
            update_doc = params.get("update", {})
            upsert = params.get("upsert", False)

            db = self._client[database]
            col = db[collection]
            result = col.update_one(filter_doc, update_doc, upsert=upsert)

            return {
                "success": True,
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "acknowledged": result.acknowledged,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _update_one(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza un documento en una coleccion de MongoDB.

        Args:
            params: Debe contener 'database', 'collection', 'filter' y 'update'
        """
        database = params.get("database", "")
        collection = params.get("collection", "")
        filter_doc = params.get("filter", {})
        update_doc = params.get("update", {})
        if not database and not self._database:
            return {"success": False, "error": "Parametros requeridos: database, collection, filter, update"}
        if not collection or not filter_doc or not update_doc:
            return {"success": False, "error": "Parametros requeridos: collection, filter, update"}
        self._log_operation("update_one", f"db={database or self._database}, col={collection}")

        if self._use_http:
            return self._update_one_http(params)
        return self._update_one_driver(params)

    def _delete_one_http(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a document via MongoDB Atlas Data API."""
        try:
            body = self._build_base_body(params)
            body["filter"] = params["filter"]

            response = self._http.post("/action/deleteOne", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "deleted_count": data.get("deletedCount", 0),
                "acknowledged": True,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _delete_one_driver(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a document using pymongo driver."""
        try:
            database = params.get("database", self._database)
            collection = params.get("collection", "")
            filter_doc = params.get("filter", {})

            db = self._client[database]
            col = db[collection]
            result = col.delete_one(filter_doc)

            return {
                "success": True,
                "deleted_count": result.deleted_count,
                "acknowledged": result.acknowledged,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _delete_one(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un documento de una coleccion de MongoDB.

        Args:
            params: Debe contener 'database', 'collection' y 'filter'
        """
        database = params.get("database", "")
        collection = params.get("collection", "")
        filter_doc = params.get("filter", {})
        if not database and not self._database:
            return {"success": False, "error": "Parametros requeridos: database, collection, filter"}
        if not collection or not filter_doc:
            return {"success": False, "error": "Parametros requeridos: collection, filter"}
        self._log_operation("delete_one", f"db={database or self._database}, col={collection}")

        if self._use_http:
            return self._delete_one_http(params)
        return self._delete_one_driver(params)

    def _aggregate_http(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an aggregation pipeline via MongoDB Atlas Data API."""
        try:
            body = self._build_base_body(params)
            body["pipeline"] = params["pipeline"]

            response = self._http.post("/action/aggregate", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            documents = data.get("documents", [])
            return {
                "success": True,
                "results": documents,
                "ok": 1.0,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _aggregate_driver(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an aggregation pipeline using pymongo driver."""
        try:
            database = params.get("database", self._database)
            collection = params.get("collection", "")
            pipeline = params.get("pipeline", [])

            db = self._client[database]
            col = db[collection]
            results = list(col.aggregate(pipeline))

            # Convert ObjectId to string
            for doc in results:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])

            return {
                "success": True,
                "results": results,
                "ok": 1.0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _aggregate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta un pipeline de agregacion en MongoDB.

        Args:
            params: Debe contener 'database', 'collection' y 'pipeline'
        """
        database = params.get("database", "")
        collection = params.get("collection", "")
        pipeline = params.get("pipeline", [])
        if not database and not self._database:
            return {"success": False, "error": "Parametros requeridos: database, collection, pipeline"}
        if not collection or not pipeline:
            return {"success": False, "error": "Parametros requeridos: collection, pipeline"}
        self._log_operation("aggregate", f"db={database or self._database}, col={collection}")

        if self._use_http:
            return self._aggregate_http(params)
        return self._aggregate_driver(params)

    def _list_collections(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista las colecciones de una base de datos MongoDB.

        Args:
            params: Debe contener 'database'
        """
        database = params.get("database", "")
        if not database and not self._database:
            return {"success": False, "error": "Parametro requerido: database"}
        self._log_operation("list_collections", f"db={database or self._database}")

        db_name = database or self._database

        if self._use_http:
            # Atlas Data API doesn't have a list collections endpoint
            # We can try to use the listCollections command via runCommand
            try:
                body = {
                    "dataSource": self._data_source,
                    "database": db_name,
                    "command": {"listCollections": 1},
                }
                response = self._http.post("/action/runCommand", json=body)
                if not response.ok:
                    return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
                data = response.json()
                cursor = data.get("cursor", {})
                collections = [col.get("name", "") for col in cursor.get("firstBatch", [])]
                return {
                    "success": True,
                    "collections": collections,
                    "database": db_name,
                }
            except HTTPClientError as e:
                return {"success": False, "error": str(e)}
        else:
            try:
                db = self._client[db_name]
                collections = db.list_collection_names()
                return {
                    "success": True,
                    "collections": collections,
                    "database": db_name,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}


MONGO_SCHEMA = ConnectorSchema(
    name="mongo_connector",
    version="1.0.0",
    description="Ejecuta operaciones CRUD y agregaciones en bases de datos MongoDB",
    category="databases",
    icon="database",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="find", description="Busca documentos", category="read"),
        ActionDefinition(name="insert_one", description="Inserta un documento", category="write"),
        ActionDefinition(name="update_one", description="Actualiza un documento", category="write"),
        ActionDefinition(name="delete_one", description="Elimina un documento", category="delete"),
        ActionDefinition(name="aggregate", description="Ejecuta pipeline de agregacion", category="read"),
        ActionDefinition(name="list_collections", description="Lista colecciones", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["connection_uri"], description="MongoDB Connection URI")
    ],
)
