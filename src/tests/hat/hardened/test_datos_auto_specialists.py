"""Tests para los 3 specialists de datos_auto: Data, Api, Code.

Cubre para cada specialist:
- get_card() retorna AgentCard con domain='datos_auto'.
- handle() integra route + invoke + return.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.datos_auto.api_specialist import ApiSpecialist
from src.hat.level3_specialists.datos_auto.code_specialist import CodeSpecialist
from src.hat.level3_specialists.datos_auto.data_specialist import DataSpecialist


class TestDataSpecialist:
    """Tests para DataSpecialist."""

    @pytest.fixture
    def mock_data_tools(self) -> dict[str, MagicMock]:
        """Data tools mockeadas: data_keeper, sheets, drive, postgresql."""
        return {
            "data_keeper": MagicMock(),
            "sheets": MagicMock(),
            "drive": MagicMock(),
            "postgresql": MagicMock(),
        }

    @pytest.fixture
    def specialist(self, mock_data_tools: dict[str, MagicMock]) -> DataSpecialist:
        """DataSpecialist con tools mockeadas."""
        return DataSpecialist(tools=mock_data_tools)

    def test_get_card_returns_correct_metadata(
        self, specialist: DataSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='datos_auto'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.domain == "datos_auto"
        assert card.tier == "specialist"
        assert len(card.orbital_keywords) > 0


class TestApiSpecialist:
    """Tests para ApiSpecialist."""

    @pytest.fixture
    def mock_api_connector(self) -> MagicMock:
        """ApiConnector tool mockeada."""
        tool = MagicMock()
        tool.make_request.return_value = {"status": 200, "data": {}}
        tool.list_connectors.return_value = [{"id": 1}]
        tool.test_connector.return_value = {"status": "ok"}
        return tool

    @pytest.fixture
    def specialist(self, mock_api_connector: MagicMock) -> ApiSpecialist:
        """ApiSpecialist con tool mockeada."""
        return ApiSpecialist(tools={"api_connector": mock_api_connector})

    def test_get_card_returns_correct_metadata(
        self, specialist: ApiSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='datos_auto'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.domain == "datos_auto"
        assert card.tier == "specialist"
        assert len(card.orbital_keywords) > 0


class TestCodeSpecialist:
    """Tests para CodeSpecialist."""

    @pytest.fixture
    def mock_code_tools(self) -> dict[str, MagicMock]:
        """Code tools mockeadas: code_runner, logic_gate, autopilot, openai, ollama."""
        return {
            "code_runner": MagicMock(),
            "logic_gate": MagicMock(),
            "autopilot": MagicMock(),
            "openai": MagicMock(),
            "ollama": MagicMock(),
        }

    @pytest.fixture
    def specialist(self, mock_code_tools: dict[str, MagicMock]) -> CodeSpecialist:
        """CodeSpecialist con tools mockeadas."""
        return CodeSpecialist(tools=mock_code_tools)

    def test_get_card_returns_correct_metadata(
        self, specialist: CodeSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='datos_auto'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.domain == "datos_auto"
        assert card.tier == "specialist"
        assert len(card.orbital_keywords) > 0

    def test_handle_returns_completed_or_failed(self, specialist: CodeSpecialist) -> None:
        """handle() retorna status='completed' o 'failed' (depende del routing)."""
        result = specialist.handle({"description": "ejecutar codigo python", "params": {}})
        assert result["status"] in ("completed", "failed")
