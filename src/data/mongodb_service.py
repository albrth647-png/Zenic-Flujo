"""
Workflow Determinista — MongoDB Service (Async Singleton)
=========================================================

Servicio asincrono de MongoDB usando Motor (driver async de PyMongo).
Sigue el patron Singleton thread-safe de DatabaseManager.

Configuracion via variables de entorno:
- WFD_MONGODB_URI: URI de conexion (default: mongodb://localhost:27017)
- WFD_MONGODB_DB: Nombre de la base de datos (default: zenic_flijo)
- WFD_MONGODB_MAX_POOL_SIZE: Tamano del pool de conexiones (default: 100)
- WFD_MONGODB_MIN_POOL_SIZE: Tamano minimo del pool (default: 10)
- WFD_MONGODB_TIMEOUT_MS: Timeout de conexion en ms (default: 5000)

Caracteristicas:
- Singleton thread-safe con doble check locking
- CRUD completo: insert, find, update, delete, count
- Aggregation pipeline
- Gestion de indices
- Soporte de migraciones versionadas por coleccion
- Pool de conexiones configurable
- Cierre elegante de conexion
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any

from src.config import PRODUCTION
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class MongoDBService:
    """Singleton asincrono que gestiona la conexion a MongoDB via Motor."""

    _instance: MongoDBService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> MongoDBService:
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
            self._uri: str = os.environ.get("WFD_MONGODB_URI", "mongodb://localhost:27017")
            self._db_name: str = os.environ.get("WFD_MONGODB_DB", "zenic_flijo")
            self._max_pool_size: int = int(os.environ.get("WFD_MONGODB_MAX_POOL_SIZE", "100"))
            self._min_pool_size: int = int(os.environ.get("WFD_MONGODB_MIN_POOL_SIZE", "10"))
            self._timeout_ms: int = int(os.environ.get("WFD_MONGODB_TIMEOUT_MS", "5000"))
            self._client: Any | None = None  # AsyncIOMotorClient
            self._db: Any | None = None  # AsyncIOMotorDatabase
            self._migration_collection: str = "_schema_migrations"

    # ── Conexion ─────────────────────────────────────────────

    async def connect(self) -> None:
        """Establece la conexion asincrona a MongoDB."""
        if self._client is not None:
            return

        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            self._client = AsyncIOMotorClient(
                self._uri,
                maxPoolSize=self._max_pool_size,
                minPoolSize=self._min_pool_size,
                serverSelectionTimeoutMS=self._timeout_ms,
                connectTimeoutMS=self._timeout_ms,
                socketTimeoutMS=self._timeout_ms,
            )
            self._db = self._client[self._db_name]

            # Verificar conexion con ping
            await self._client.admin.command("ping")
            logger.info(f"MongoDB conectado: {self._uri} / db={self._db_name}")

        except ImportError:
            raise ImportError("Motor no esta instalado. Instalalo con: pip install motor>=3.6.0") from None
        except Exception as e:
            logger.error(f"Error conectando a MongoDB: {e}")
            if PRODUCTION:
                raise
            # En desarrollo, permitir que continue sin conexion
            logger.warning("Modo desarrollo: MongoDB no disponible, operaciones fallaran")

    async def _ensure_connection(self) -> None:
        """Asegura que la conexion este establecida."""
        if self._client is None:
            await self.connect()

    # ── Colecciones ──────────────────────────────────────────

    # legítimo: pymongo.collection.Collection, no tipado por compatibilidad
    async def get_collection(self, name: str) -> Any:
        """
        Obtiene una coleccion Motor por nombre.

        Args:
            name: Nombre de la coleccion

        Returns:
            AsyncIOMotorCollection
        """
        await self._ensure_connection()
        return self._db[name]

    async def list_collections(self) -> list[str]:
        """Lista los nombres de todas las colecciones en la base de datos."""
        await self._ensure_connection()
        collections = await self._db.list_collection_names()
        return sorted(collections)

    async def drop_collection(self, name: str) -> None:
        """
        Elimina una coleccion completa.

        Args:
            name: Nombre de la coleccion a eliminar
        """
        await self._ensure_connection()
        await self._db.drop_collection(name)
        logger.info(f"Coleccion eliminada: {name}")

    # ── CRUD — Insert ────────────────────────────────────────

    async def insert_one(self, collection: str, document: dict[str, Any]) -> str:
        """
        Inserta un documento en una coleccion.

        Args:
            collection: Nombre de la coleccion
            document: Documento a insertar

        Returns:
            ID del documento insertado como string
        """
        await self._ensure_connection()
        col = self._db[collection]

        # Agregar timestamps si no existen
        if "_created_at" not in document:
            document["_created_at"] = datetime.utcnow()
        if "_updated_at" not in document:
            document["_updated_at"] = datetime.utcnow()

        result = await col.insert_one(document)
        logger.debug(f"insert_one en {collection}: {result.inserted_id}")
        return str(result.inserted_id)

    async def insert_many(self, collection: str, documents: list[dict]) -> list[str]:
        """
        Inserta multiples documentos en una coleccion.

        Args:
            collection: Nombre de la coleccion
            documents: Lista de documentos a insertar

        Returns:
            Lista de IDs insertados como strings
        """
        await self._ensure_connection()
        col = self._db[collection]

        # Agregar timestamps a cada documento
        now = datetime.utcnow()
        for doc in documents:
            if "_created_at" not in doc:
                doc["_created_at"] = now
            if "_updated_at" not in doc:
                doc["_updated_at"] = now

        result = await col.insert_many(documents)
        ids = [str(oid) for oid in result.inserted_ids]
        logger.debug(f"insert_many en {collection}: {len(ids)} documentos")
        return ids

    # ── CRUD — Find ──────────────────────────────────────────

    async def find_one(self, collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
        """
        Busca un unico documento en una coleccion.

        Args:
            collection: Nombre de la coleccion
            query: Filtro de busqueda

        Returns:
            Documento encontrado o None
        """
        await self._ensure_connection()
        col = self._db[collection]
        doc = await col.find_one(query)
        return self._serialize_doc(doc) if doc else None

    async def find_many(
        self,
        collection: str,
        query: dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict]:
        """
        Busca multiples documentos en una coleccion.

        Args:
            collection: Nombre de la coleccion
            query: Filtro de busqueda
            skip: Numero de documentos a saltar
            limit: Maximo de documentos a retornar
            sort: Lista de tuplas (campo, direccion), ej: [("name", 1)]

        Returns:
            Lista de documentos encontrados
        """
        await self._ensure_connection()
        col = self._db[collection]
        cursor = col.find(query)

        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.skip(skip).limit(limit)

        docs = await cursor.to_list(length=limit)
        return [self._serialize_doc(doc) for doc in docs]

    # ── CRUD — Update ────────────────────────────────────────

    async def update_one(self, collection: str, query: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> dict[str, Any]:
        """
        Actualiza un unico documento.

        Args:
            collection: Nombre de la coleccion
            query: Filtro para encontrar el documento
            update: Operaciones de actualizacion (ej: {"$set": {...}})
            upsert: Crear documento si no existe

        Returns:
            dict con matched_count, modified_count, upserted_id
        """
        await self._ensure_connection()
        col = self._db[collection]

        # Agregar timestamp de actualizacion si es $set
        if "$set" in update and "_updated_at" not in update["$set"]:
            update["$set"]["_updated_at"] = datetime.utcnow()

        result = await col.update_one(query, update, upsert=upsert)
        response = {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
        }
        if result.upserted_id:
            response["upserted_id"] = str(result.upserted_id)
        logger.debug(f"update_one en {collection}: matched={result.matched_count}, modified={result.modified_count}")
        return response

    async def update_many(self, collection: str, query: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza multiples documentos.

        Args:
            collection: Nombre de la coleccion
            query: Filtro para encontrar documentos
            update: Operaciones de actualizacion

        Returns:
            dict con matched_count, modified_count
        """
        await self._ensure_connection()
        col = self._db[collection]

        if "$set" in update and "_updated_at" not in update["$set"]:
            update["$set"]["_updated_at"] = datetime.utcnow()

        result = await col.update_many(query, update)
        logger.debug(f"update_many en {collection}: matched={result.matched_count}, modified={result.modified_count}")
        return {
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
        }

    # ── CRUD — Delete ────────────────────────────────────────

    async def delete_one(self, collection: str, query: dict[str, Any]) -> int:
        """
        Elimina un unico documento.

        Args:
            collection: Nombre de la coleccion
            query: Filtro para encontrar el documento

        Returns:
            Numero de documentos eliminados (0 o 1)
        """
        await self._ensure_connection()
        col = self._db[collection]
        result = await col.delete_one(query)
        logger.debug(f"delete_one en {collection}: deleted={result.deleted_count}")
        return result.deleted_count

    async def delete_many(self, collection: str, query: dict[str, Any]) -> int:
        """
        Elimina multiples documentos.

        Args:
            collection: Nombre de la coleccion
            query: Filtro para encontrar documentos

        Returns:
            Numero de documentos eliminados
        """
        await self._ensure_connection()
        col = self._db[collection]
        result = await col.delete_many(query)
        logger.debug(f"delete_many en {collection}: deleted={result.deleted_count}")
        return result.deleted_count

    # ── CRUD — Count ─────────────────────────────────────────

    async def count_documents(self, collection: str, query: dict[str, Any] | None = None) -> int:
        """
        Cuenta documentos en una coleccion.

        Args:
            collection: Nombre de la coleccion
            query: Filtro opcional (default: contar todos)

        Returns:
            Numero de documentos
        """
        await self._ensure_connection()
        col = self._db[collection]
        count = await col.count_documents(query or {})
        return count

    # ── Aggregation ──────────────────────────────────────────

    async def aggregate(self, collection: str, pipeline: list[dict]) -> list[dict]:
        """
        Ejecuta un pipeline de agregacion.

        Args:
            collection: Nombre de la coleccion
            pipeline: Lista de etapas de agregacion

        Returns:
            Lista de documentos resultantes
        """
        await self._ensure_connection()
        col = self._db[collection]
        cursor = col.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return [self._serialize_doc(doc) for doc in results]

    # ── Indices ──────────────────────────────────────────────

    # legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
    async def create_index(self, collection: str, keys: str | list[tuple[str, int]], **kwargs: Any) -> str:
        """
        Crea un indice en una coleccion.

        Args:
            collection: Nombre de la coleccion
            keys: Campo o lista de tuplas (campo, direccion)
            **kwargs: Parametros adicionales (unique, sparse, etc.)

        Returns:
            Nombre del indice creado
        """
        await self._ensure_connection()
        col = self._db[collection]
        index_name = await col.create_index(keys, **kwargs)
        logger.info(f"Indice creado en {collection}: {index_name}")
        return index_name

    async def create_indexes(self, collection: str, indexes: list[list[tuple[str, int]]]) -> list[str]:
        """
        Crea multiples indices en una coleccion.

        Args:
            collection: Nombre de la coleccion
            indexes: Lista de definiciones de indices

        Returns:
            Lista de nombres de indices creados
        """
        await self._ensure_connection()
        col = self._db[collection]
        result = await col.create_indexes(indexes)
        logger.info(f"Indices creados en {collection}: {result}")
        return result

    async def list_indexes(self, collection: str) -> list[dict]:
        """
        Lista los indices de una coleccion.

        Args:
            collection: Nombre de la coleccion

        Returns:
            Lista de definiciones de indices
        """
        await self._ensure_connection()
        col = self._db[collection]
        indexes = []
        async for index in col.list_indexes():
            indexes.append(self._serialize_doc(index))
        return indexes

    async def drop_index(self, collection: str, index_name: str) -> None:
        """
        Elimina un indice de una coleccion.

        Args:
            collection: Nombre de la coleccion
            index_name: Nombre del indice a eliminar
        """
        await self._ensure_connection()
        col = self._db[collection]
        await col.drop_index(index_name)
        logger.info(f"Indice eliminado en {collection}: {index_name}")

    # ── Schema Migration ─────────────────────────────────────

    async def get_schema_version(self, collection: str) -> int:
        """
        Obtiene la version del schema de una coleccion.

        Args:
            collection: Nombre de la coleccion

        Returns:
            Version actual del schema (0 si no tiene migraciones)
        """
        await self._ensure_connection()
        col = self._db[self._migration_collection]
        doc = await col.find_one({"collection": collection})
        return doc["version"] if doc else 0

    async def set_schema_version(self, collection: str, version: int) -> None:
        """
        Establece la version del schema de una coleccion.

        Args:
            collection: Nombre de la coleccion
            version: Nueva version del schema
        """
        await self._ensure_connection()
        col = self._db[self._migration_collection]
        await col.update_one(
            {"collection": collection},
            {"$set": {"collection": collection, "version": version, "updated_at": datetime.utcnow()}},
            upsert=True,
        )
        logger.info(f"Schema version actualizada: {collection} -> v{version}")

    # ── Health Check ─────────────────────────────────────────

    async def ping(self) -> bool:
        """
        Verifica la conexion a MongoDB.

        Returns:
            True si la conexion esta activa
        """
        try:
            await self._ensure_connection()
            await self._client.admin.command("ping")
            return True
        except Exception as e:
            logger.error(f"MongoDB ping fallido: {e}")
            return False

    async def get_stats(self) -> dict[str, Any]:
        """
        Retorna estadisticas de la base de datos.

        Returns:
            dict con estadisticas de la base de datos
        """
        await self._ensure_connection()
        stats = await self._db.command("dbstats")
        collections = await self.list_collections()
        return {
            "db_name": self._db_name,
            "collections_count": len(collections),
            "collections": collections,
            "data_size": stats.get("dataSize", 0),
            "storage_size": stats.get("storageSize", 0),
            "indexes": stats.get("indexes", 0),
            "ok": stats.get("ok", 0) == 1,
        }

    # ── Cierre ───────────────────────────────────────────────

    async def close(self) -> None:
        """Cierra la conexion a MongoDB de forma elegante."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB conexion cerrada")

    # ── Utilidades internas ──────────────────────────────────

    @staticmethod
    def _serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
        """Serializa un documento MongoDB convirtiendo ObjectId y datetime a string."""
        if doc is None:
            return {}
        serialized = {}
        for key, value in doc.items():
            if hasattr(value, "__str__") and type(value).__name__ == "ObjectId":
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            else:
                serialized[key] = value
        return serialized
