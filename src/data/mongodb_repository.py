"""
Workflow Determinista — MongoDB Repository (Base Class)
=======================================================

Clase base generica para repositorios MongoDB.
Sigue el patron Repository utilizado en CRM, Inventory, DataKeeper, etc.

Uso:
    class MiRepositorio(MongoRepository):
        def __init__(self):
            super().__init__("mi_coleccion")

    repo = MiRepositorio()
    doc_id = await repo.create({"nombre": "ejemplo", "valor": 42})
    doc = await repo.get_by_id(doc_id)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.data.mongodb_service import MongoDBService
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class MongoRepository:
    """
    Repositorio base generico para colecciones MongoDB.

    Provee operaciones CRUD estandar: create, get_by_id, get_by_filter,
    update, delete, list, count. Las subclases pueden extender o
    sobreescribir estos metodos.

    Args:
        collection_name: Nombre de la coleccion MongoDB
    """

    def __init__(self, collection_name: str) -> None:
        self._collection_name = collection_name
        self._service = MongoDBService()

    # ── Create ───────────────────────────────────────────────

    async def create(self, document: dict[str, Any]) -> str:
        """
        Crea un nuevo documento en la coleccion.

        Agrega automaticamente _created_at y _updated_at si no estan presentes.

        Args:
            document: Documento a insertar

        Returns:
            ID del documento creado como string
        """
        if "_created_at" not in document:
            document["_created_at"] = datetime.utcnow()
        if "_updated_at" not in document:
            document["_updated_at"] = datetime.utcnow()

        doc_id = await self._service.insert_one(self._collection_name, document)
        logger.info(f"Documento creado en {self._collection_name}: {doc_id}")
        return doc_id

    # ── Read ─────────────────────────────────────────────────

    async def get_by_id(self, doc_id: str) -> dict[str, Any] | None:
        """
        Obtiene un documento por su _id.

        Args:
            doc_id: ID del documento como string

        Returns:
            Documento encontrado o None
        """
        try:
            from bson import ObjectId

            query = {"_id": ObjectId(doc_id)}
        except (ImportError, ValueError):
            query = {"_id": doc_id}

        return await self._service.find_one(self._collection_name, query)

    async def get_by_filter(self, query: dict[str, Any]) -> dict[str, Any] | None:
        """
        Obtiene un unico documento por filtro.

        Args:
            query: Filtro de busqueda

        Returns:
            Primer documento que coincide o None
        """
        return await self._service.find_one(self._collection_name, query)

    # ── Update ───────────────────────────────────────────────

    async def update(self, doc_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """
        Actualiza un documento por su _id.

        Usa $set para actualizar solo los campos proporcionados.
        Agrega _updated_at automaticamente.

        Args:
            doc_id: ID del documento
            updates: Campos a actualizar

        Returns:
            Documento actualizado o None si no se encontro
        """
        try:
            from bson import ObjectId

            query = {"_id": ObjectId(doc_id)}
        except (ImportError, ValueError):
            query = {"_id": doc_id}

        if "_updated_at" not in updates:
            updates["_updated_at"] = datetime.utcnow()

        await self._service.update_one(
            self._collection_name,
            query,
            {"$set": updates},
        )
        return await self.get_by_id(doc_id)

    # ── Delete ───────────────────────────────────────────────

    async def delete(self, doc_id: str) -> bool:
        """
        Elimina un documento por su _id.

        Args:
            doc_id: ID del documento

        Returns:
            True si se elimino, False si no se encontro
        """
        try:
            from bson import ObjectId

            query = {"_id": ObjectId(doc_id)}
        except (ImportError, ValueError):
            query = {"_id": doc_id}

        deleted = await self._service.delete_one(self._collection_name, query)
        if deleted > 0:
            logger.info(f"Documento eliminado de {self._collection_name}: {doc_id}")
        return deleted > 0

    # ── List ─────────────────────────────────────────────────

    async def list(
        self,
        query: dict[str, Any] | None = None,
        skip: int = 0,
        limit: int = 100,
        sort: list[tuple[str, int]] | None = None,
    ) -> list[dict]:
        """
        Lista documentos con paginacion y ordenamiento opcionales.

        Args:
            query: Filtro de busqueda (default: todos los documentos)
            skip: Numero de documentos a saltar
            limit: Maximo de documentos a retornar
            sort: Lista de tuplas (campo, direccion), ej: [("name", 1)]

        Returns:
            Lista de documentos
        """
        default_sort = sort or [("_created_at", -1)]
        return await self._service.find_many(
            self._collection_name,
            query or {},
            skip=skip,
            limit=limit,
            sort=default_sort,
        )

    # ── Count ────────────────────────────────────────────────

    async def count(self, query: dict[str, Any] | None = None) -> int:
        """
        Cuenta documentos en la coleccion.

        Args:
            query: Filtro opcional (default: contar todos)

        Returns:
            Numero de documentos
        """
        return await self._service.count_documents(self._collection_name, query)

    # ── Utilidades ───────────────────────────────────────────

    async def exists(self, query: dict[str, Any]) -> bool:
        """
        Verifica si existe al menos un documento que coincida con el filtro.

        Args:
            query: Filtro de busqueda

        Returns:
            True si existe al menos un documento
        """
        count = await self._service.count_documents(self._collection_name, query)
        return count > 0

    # legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
    async def ensure_index(self, keys: Any, **kwargs: Any) -> str:
        """
        Crea un indice en la coleccion si no existe.

        Args:
            keys: Campo o lista de tuplas para el indice
            **kwargs: Parametros adicionales (unique, sparse, etc.)

        Returns:
            Nombre del indice creado
        """
        return await self._service.create_index(self._collection_name, keys, **kwargs)
