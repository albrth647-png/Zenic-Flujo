"""
Workflow Determinista — DataKeeperService
Tablas dinámicas que el usuario puede crear, leer, actualizar y eliminar.

Permite a los usuarios crear sus propias estructuras de datos sin modificar
el código fuente, ideales para almacenar información que no encaja en las
tablas predefinidas del sistema.
"""

from src.core.logging import setup_logging
from src.hat.level5_tools.data.data_keeper.repository import DataKeeperRepository
from typing import Any

logger = setup_logging(__name__)


class DataKeeperService:
    """
    Servicio de tablas dinámicas.

    Uso en workflow:
    {
        "tool": "data_keeper",
        "action": "insert",
        "params": {
            "collection": "clientes",
            "data": {
                "nombre": "$input.nombre",
                "email": "$input.email",
                "edad": 30
            }
        }
    }
    """

    def __init__(self):
        self._repo = DataKeeperRepository()

    def create_collection(self, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Crea una nueva colección con su schema de tipos.

        Args:
            name: Nombre único de la colección
            schema: Diccionario {campo: tipo}
                     Tipos válidos: string, number, boolean, text, date

        Returns:
            dict con: id, name, schema, created_at
        """
        return self._repo.create_collection(name, schema)

    def list_collections(self) -> list[dict]:
        """Lista todas las colecciones disponibles."""
        return self._repo.list_collections()

    def get_collection_info(self, name: str) -> dict[str, Any] | None:
        """Obtiene información de una colección incluyendo conteo de registros."""
        collection = self._repo.get_collection(name)
        if not collection:
            return None

        # Contar registros
        all_records = self._repo.query(name)
        collection["record_count"] = len(all_records)
        return collection

    def insert(self, collection: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Inserta un registro en una colección.

        Args:
            collection: Nombre de la colección
            data: Diccionario con los datos {campo: valor}

        Returns:
            El registro creado incluyendo id, created_at
        """
        return self._repo.insert(collection, data)

    def query(self, collection: str, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Consulta registros con filtros opcionales.

        Args:
            collection: Nombre de la colección
            filters: Diccionario {campo: valor} para filtrar
            limit: Máximo de resultados
            offset: Desplazamiento para paginación

        Returns:
            Lista de registros
        """
        return self._repo.query(collection, filters, limit, offset)

    def update(self, collection: str, record_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """
        Actualiza un registro existente.

        Args:
            collection: Nombre de la colección
            record_id: ID del registro a actualizar
            data: Diccionario con los campos a actualizar

        Returns:
            El registro actualizado
        """
        return self._repo.update(collection, record_id, data)

    def delete(self, collection: str, record_id: int) -> bool:
        """
        Elimina un registro.

        Args:
            collection: Nombre de la colección
            record_id: ID del registro a eliminar

        Returns:
            True si se eliminó, False si no existía
        """
        return self._repo.delete(collection, record_id)

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "data_keeper",
            "name": "Data Keeper",
            "description": "Tablas dinámicas para almacenar datos personalizados",
            "actions": {
                "insert": {
                    "name": "Insertar registro",
                    "description": "Inserta un nuevo registro en una colección",
                    "params": [
                        {
                            "name": "collection",
                            "type": "string",
                            "required": True,
                            "label": "Colección",
                            "placeholder": "nombre_de_la_coleccion",
                        },
                        {
                            "name": "data",
                            "type": "dict",
                            "required": True,
                            "label": "Datos",
                            "placeholder": '{"campo1": "valor1", "campo2": 123}',
                        },
                    ],
                },
                "query": {
                    "name": "Consultar registros",
                    "description": "Consulta registros de una colección",
                    "params": [
                        {"name": "collection", "type": "string", "required": True, "label": "Colección"},
                        {
                            "name": "filters",
                            "type": "dict",
                            "required": False,
                            "default": {},
                            "label": "Filtros",
                            "placeholder": '{"campo": "valor"}',
                        },
                        {"name": "limit", "type": "number", "required": False, "default": 100, "label": "Límite"},
                    ],
                },
                "update": {
                    "name": "Actualizar registro",
                    "description": "Actualiza un registro existente",
                    "params": [
                        {"name": "collection", "type": "string", "required": True, "label": "Colección"},
                        {"name": "record_id", "type": "number", "required": True, "label": "ID del registro"},
                        {
                            "name": "data",
                            "type": "dict",
                            "required": True,
                            "label": "Datos a actualizar",
                            "placeholder": '{"campo": "nuevo_valor"}',
                        },
                    ],
                },
                "delete": {
                    "name": "Eliminar registro",
                    "description": "Elimina un registro de una colección",
                    "params": [
                        {"name": "collection", "type": "string", "required": True, "label": "Colección"},
                        {"name": "record_id", "type": "number", "required": True, "label": "ID del registro"},
                    ],
                },
                "create_collection": {
                    "name": "Crear colección",
                    "description": "Crea una nueva colección con schema",
                    "params": [
                        {"name": "name", "type": "string", "required": True, "label": "Nombre de la colección"},
                        {
                            "name": "schema",
                            "type": "dict",
                            "required": True,
                            "label": "Schema",
                            "placeholder": '{"campo1": "string", "campo2": "number"}',
                        },
                    ],
                },
                "list_collections": {
                    "name": "Listar colecciones",
                    "description": "Lista todas las colecciones disponibles",
                    "params": [],
                },
            },
        }
