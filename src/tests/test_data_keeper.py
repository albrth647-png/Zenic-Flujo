"""Tests para el Data Keeper Service."""

import pytest


class TestDataKeeperService:
    """Tests para DataKeeperService."""

    def test_create_collection(self, db_manager):
        """Test: crear una colección nueva."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        collection = service.create_collection(
            name="clientes",
            schema={
                "nombre": "string",
                "edad": "number",
                "activo": "boolean",
                "email": "string",
            },
        )

        assert collection["name"] == "clientes"
        assert "id" in collection
        assert collection["schema"]["nombre"] == "string"
        assert collection["schema"]["edad"] == "number"

    def test_create_collection_duplicate(self, db_manager):
        """Test: crear colección duplicada lanza error."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection("test", {"campo": "string"})
        with pytest.raises(ValueError, match="ya existe"):
            service.create_collection("test", {"otro": "string"})

    def test_list_collections(self, db_manager):
        """Test: listar colecciones."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection("clientes", {"nombre": "string"})
        service.create_collection("productos", {"sku": "string", "precio": "number"})

        collections = service.list_collections()
        assert len(collections) == 2
        names = [c["name"] for c in collections]
        assert "clientes" in names
        assert "productos" in names

    def test_insert_record(self, db_manager):
        """Test: insertar un registro en una colección."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection(
            "clientes",
            {
                "nombre": "string",
                "edad": "number",
                "activo": "boolean",
            },
        )

        record = service.insert(
            "clientes",
            {
                "nombre": "Juan Pérez",
                "edad": 30,
                "activo": True,
            },
        )

        assert record["nombre"] == "Juan Pérez"
        assert record["edad"] == 30
        assert record["activo"] is True
        assert "id" in record
        assert "created_at" in record

    def test_insert_record_invalid_collection(self, db_manager):
        """Test: insertar en colección inexistente lanza error."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        with pytest.raises(ValueError, match="no encontrada"):
            service.insert("inexistente", {"dato": "test"})

    def test_insert_record_validation(self, db_manager):
        """Test: insertar registro con campo no definido en schema."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection("test", {"nombre": "string"})
        with pytest.raises(ValueError, match="no está en el schema"):
            service.insert("test", {"nombre": "Juan", "campo_extra": "invalido"})

    def test_query_records(self, db_manager):
        """Test: consultar registros con filtros."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection(
            "clientes",
            {
                "nombre": "string",
                "ciudad": "string",
                "edad": "number",
            },
        )

        service.insert("clientes", {"nombre": "Juan", "ciudad": "Madrid", "edad": 30})
        service.insert("clientes", {"nombre": "Ana", "ciudad": "Barcelona", "edad": 25})
        service.insert("clientes", {"nombre": "Luis", "ciudad": "Madrid", "edad": 35})

        # Filtrar por ciudad
        results = service.query("clientes", {"ciudad": "Madrid"})
        assert len(results) == 2
        assert results[0]["nombre"] in ("Juan", "Luis")

        # Sin filtros
        all_results = service.query("clientes")
        assert len(all_results) == 3

    def test_update_record(self, db_manager):
        """Test: actualizar un registro."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection("test", {"nombre": "string", "edad": "number"})
        record = service.insert("test", {"nombre": "Juan", "edad": 30})

        updated = service.update("test", record["id"], {"edad": 31})
        assert updated["edad"] == 31
        assert updated["nombre"] == "Juan"  # No cambió

    def test_delete_record(self, db_manager):
        """Test: eliminar un registro."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection("test", {"nombre": "string"})
        record = service.insert("test", {"nombre": "Juan"})

        result = service.delete("test", record["id"])
        assert result is True

        # Verificar que ya no existe
        records = service.query("test")
        assert len(records) == 0

    def test_delete_record_not_found(self, db_manager):
        """Test: eliminar registro inexistente retorna False."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection("test", {"nombre": "string"})
        result = service.delete("test", 999)
        assert result is False

    def test_get_collection_info(self, db_manager):
        """Test: obtener info de una colección."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        service.create_collection(
            "productos",
            {
                "sku": "string",
                "precio": "number",
                "stock": "number",
            },
        )
        service.insert("productos", {"sku": "ABC", "precio": 100, "stock": 10})
        service.insert("productos", {"sku": "XYZ", "precio": 200, "stock": 5})

        info = service.get_collection_info("productos")
        assert info["name"] == "productos"
        assert info["record_count"] == 2
        assert info["schema"]["sku"] == "string"

    def test_get_tool_definition(self, db_manager):
        """Test: definición de la tool para el editor."""
        from src.tools.data_keeper.service import DataKeeperService

        service = DataKeeperService()

        definition = service.get_tool_definition()
        assert definition["tool"] == "data_keeper"
        assert "insert" in definition["actions"]
        assert "query" in definition["actions"]
        assert "update" in definition["actions"]
        assert "delete" in definition["actions"]
