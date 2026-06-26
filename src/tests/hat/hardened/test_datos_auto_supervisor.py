"""Tests para DatosAutoSupervisor — routing real por keywords.

Cubre:
- Routing a DataSpecialist (data, sheets, drive, postgres, sql).
- Routing a ApiSpecialist (api, http, endpoint, webhook).
- Routing a CodeSpecialist (codigo, python, openai, ollama, funcion).
- Fallback al primer specialist cuando no hay keyword match.
- Case-insensitive matching.
- Respuestas de error cuando faltan specialists.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.hat.level2_supervisors.datos_auto.supervisor import DatosAutoSupervisor


@pytest.fixture
def mock_specialists() -> dict[str, MagicMock]:
    """3 specialists mockeados: data, api, code."""
    return {
        "data": MagicMock(),
        "api": MagicMock(),
        "code": MagicMock(),
    }


@pytest.fixture
def supervisor(mock_specialists: dict[str, MagicMock]) -> DatosAutoSupervisor:
    """DatosAutoSupervisor con 3 specialists."""
    return DatosAutoSupervisor(specialists=mock_specialists)


class TestRoutingToApi:
    """Mensajes con keywords de Api rutean a ApiSpecialist."""

    @pytest.mark.parametrize("message", [
        "consultar api externa",
        "hacer peticion http",
        "configurar endpoint",
        "registrar webhook",
        "consumir servicio rest",
    ])
    def test_api_keywords_route_to_api(
        self, supervisor: DatosAutoSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Api rutea al ApiSpecialist."""
        mock_specialists["api"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["api"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["api"]


class TestRoutingToCode:
    """Mensajes con keywords de Code rutean a CodeSpecialist."""

    @pytest.mark.parametrize("message", [
        "ejecutar codigo python",
        "run code snippet",
        "consultar a openai",
        "usar ollama local",
        "crear funcion nueva",
        "ejecutar script de automatizacion",
        "automatizar tarea repetitiva",
    ])
    def test_code_keywords_route_to_code(
        self, supervisor: DatosAutoSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Code rutea al CodeSpecialist."""
        mock_specialists["code"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["code"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["code"]


class TestRoutingToData:
    """Mensajes con keywords de Data rutean a DataSpecialist."""

    @pytest.mark.parametrize("message", [
        "guardar data en memoria",
        "exportar a google sheets",
        "subir archivo a drive",
        "consultar postgres",
        "conectar a postgresql",
        "ejecutar query sql",
        "procesar datos del cliente",
    ])
    def test_data_keywords_route_to_data(
        self, supervisor: DatosAutoSupervisor,
        mock_specialists: dict[str, MagicMock],
        message: str,
    ) -> None:
        """Cada keyword de Data rutea al DataSpecialist."""
        mock_specialists["data"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": message})
        mock_specialists["data"].handle.assert_called_once()
        assert result["status"] == "completed"
        assert result["specialists_used"] == ["data"]


class TestCaseInsensitive:
    """El matching de keywords es case-insensitive."""

    def test_uppercase_keywords_match(
        self, supervisor: DatosAutoSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Keywords en mayúsculas funcionan."""
        mock_specialists["api"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": "CONSULTAR API EXTERNA"})
        mock_specialists["api"].handle.assert_called_once()
        assert result is not None


class TestFallback:
    """Fallback cuando no hay keyword match."""

    def test_fallback_to_first_specialist(
        self, supervisor: DatosAutoSupervisor,
        mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Sin keyword match → primer specialist (data por inserción)."""
        mock_specialists["data"].handle.return_value = {"status": "completed"}
        result = supervisor.handle({"description": "xyz qwerty unknown"})
        mock_specialists["data"].handle.assert_called_once()
        assert result["specialists_used"] == ["data"]


class TestErrors:
    """Manejo de errores."""

    def test_no_specialists_returns_failed(self) -> None:
        """Sin specialists → respuesta failed."""
        sup = DatosAutoSupervisor(specialists=None)
        result = sup.handle({"description": "ejecutar codigo"})
        assert result["status"] == "failed"
        assert result["domain"] == "datos_auto"
        assert "no specialists" in result["error"]

    def test_partial_specialists_set(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si solo hay data y code, routing a api falla graceful."""
        partial = {
            "data": mock_specialists["data"],
            "code": mock_specialists["code"],
        }
        sup = DatosAutoSupervisor(specialists=partial)
        result = sup.handle({"description": "consultar api externa"})
        assert result["status"] == "failed"
        assert "api" in result["error"]


class TestDomainAttribute:
    """El atributo domain está correctamente definido."""

    def test_domain_is_datos_auto(
        self, supervisor: DatosAutoSupervisor,
    ) -> None:
        """domain = 'datos_auto'."""
        assert supervisor.domain == "datos_auto"

    def test_keyword_map_is_populated(
        self, supervisor: DatosAutoSupervisor,
    ) -> None:
        """_keyword_map tiene entradas para los 3 specialists."""
        assert len(supervisor._keyword_map) > 0
        specialists_in_map = set(supervisor._keyword_map.values())
        assert "data" in specialists_in_map
        assert "api" in specialists_in_map
        assert "code" in specialists_in_map


class TestRepr:
    """Representación string."""

    def test_repr_includes_domain(
        self, supervisor: DatosAutoSupervisor,
    ) -> None:
        """__repr__ incluye 'datos_auto' y los specialists."""
        r = repr(supervisor)
        assert "DatosAutoSupervisor" in r
        assert "datos_auto" in r
        assert "data" in r
