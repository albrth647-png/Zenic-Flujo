"""Tests para SpecialistAgent — base abstracta para specialists del Nivel 3.

Cubre:
- ABC: no se puede instanciar directamente.
- Subclase concreta debe implementar get_card() y route_action().
- handle() flujo: publish_card → route_action → invoke tool → return result.
- Error handling: tool not available, action not found.
- available_tools property.
- Métricas best-effort (TelemetryService) no rompen flujo.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent

# ── Helper: specialist concreto para tests ─────────────────────────────


class _FakeSpecialist(SpecialistAgent):
    """Specialist concreto para tests — implementa get_card y route_action."""

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="fake",
            agent_name="Fake",
            domain="test",
            tier="specialist",
            capabilities=["action_a", "action_b"],
            orbital_keywords=["fake", "test"],
        )

    def route_action(self, subtask: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        desc = (subtask.get("description") or "").lower()
        if "action_a" in desc:
            return "fake_tool", "action_a", {}
        return "fake_tool", "action_b", {"key": "value"}


@pytest.fixture
def mock_tool() -> MagicMock:
    """Tool mockeada con action_a y action_b."""
    tool = MagicMock()
    tool.action_a.return_value = {"result": "a"}
    tool.action_b.return_value = {"result": "b"}
    return tool


@pytest.fixture
def specialist(mock_tool: MagicMock) -> _FakeSpecialist:
    """_FakeSpecialist con tool mockeada."""
    return _FakeSpecialist(
        specialist_name="fake",
        responsibility="testing",
        tools={"fake_tool": mock_tool},
    )


# ── Tests de ABC ───────────────────────────────────────────────────────


class TestABC:
    """SpecialistAgent es abstracto."""

    def test_cannot_instantiate_directly(self) -> None:
        """No se puede instanciar SpecialistAgent directamente."""
        with pytest.raises(TypeError, match="abstract"):
            SpecialistAgent(
                specialist_name="x",
                responsibility="y",
            )  # type: ignore[abstract]

    def test_subclass_without_get_card_fails(self) -> None:
        """Subclase sin get_card no se puede instanciar."""
        class Incomplete(SpecialistAgent):
            def route_action(self, subtask: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
                return "t", "a", {}

        with pytest.raises(TypeError):
            Incomplete(specialist_name="x", responsibility="y")  # type: ignore[abstract]

    def test_subclass_without_route_action_fails(self) -> None:
        """Subclase sin route_action no se puede instanciar."""
        class Incomplete(SpecialistAgent):
            def get_card(self) -> AgentCard:
                return AgentCard(
                    agent_id="x", agent_name="X",
                    domain="d", tier="t",
                )

        with pytest.raises(TypeError):
            Incomplete(specialist_name="x", responsibility="y")  # type: ignore[abstract]


# ── Tests de handle() flujo exitoso ────────────────────────────────────


class TestHandleSuccess:
    """Flujo exitoso de handle()."""

    def test_handle_returns_completed_status(
        self, specialist: _FakeSpecialist, mock_tool: MagicMock,
    ) -> None:
        """handle() retorna status='completed' cuando todo funciona."""
        result = specialist.handle({"description": "do action_a"})
        assert result["status"] == "completed"
        assert result["action"] == "action_a"
        assert result["result"] == {"result": "a"}
        assert result["specialist"] == "fake"

    def test_handle_calls_route_action(
        self, specialist: _FakeSpecialist,
    ) -> None:
        """handle() llama route_action para decidir la acción."""
        with patch.object(specialist, "route_action", wraps=specialist.route_action) as mock_route:
            specialist.handle({"description": "do action_a"})
            assert mock_route.call_count == 1

    def test_handle_invokes_tool_method(
        self, specialist: _FakeSpecialist, mock_tool: MagicMock,
    ) -> None:
        """handle() invoca el método correcto de la tool."""
        specialist.handle({"description": "do action_a"})
        assert mock_tool.action_a.call_count == 1
        assert mock_tool.action_b.call_count == 0

    def test_handle_passes_params_to_tool(
        self, specialist: _FakeSpecialist, mock_tool: MagicMock,
    ) -> None:
        """handle() pasa los params de route_action a la tool."""
        specialist.handle({"description": "do action_b"})
        assert mock_tool.action_b.call_count == 1
        # Verificar que se llamó con key="value"
        call_kwargs = mock_tool.action_b.call_args.kwargs
        assert call_kwargs == {"key": "value"}

    def test_handle_includes_duration_ms(
        self, specialist: _FakeSpecialist,
    ) -> None:
        """handle() incluye duration_ms en el resultado."""
        result = specialist.handle({"description": "do action_a"})
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0


# ── Tests de handle() errores ──────────────────────────────────────────


class TestHandleErrors:
    """Manejo de errores en handle()."""

    def test_handle_tool_not_available(
        self, mock_tool: MagicMock,
    ) -> None:
        """Si la tool no está en _tools, retorna failed."""
        spec = _FakeSpecialist(
            specialist_name="fake",
            responsibility="test",
            tools={},  # sin tools
        )
        result = spec.handle({"description": "do action_a"})
        assert result["status"] == "failed"
        assert "not available" in result["error"]
        assert result["specialist"] == "fake"

    def test_handle_action_not_found_in_tool(
        self, mock_tool: MagicMock,
    ) -> None:
        """Si la action no existe en la tool, retorna failed."""
        # Usar spec=[] para que el mock no tenga ningún atributo automático
        empty_tool = MagicMock(spec=[])
        spec = _FakeSpecialist(
            specialist_name="fake",
            responsibility="test",
            tools={"fake_tool": empty_tool},
        )
        result = spec.handle({"description": "do action_a"})
        assert result["status"] == "failed"
        assert "not found" in result["error"]

    def test_handle_tool_raises_exception(
        self, mock_tool: MagicMock,
    ) -> None:
        """Si la tool lanza excepción, handle() la captura y retorna failed."""
        mock_tool.action_a.side_effect = RuntimeError("tool crashed")
        spec = _FakeSpecialist(
            specialist_name="fake",
            responsibility="test",
            tools={"fake_tool": mock_tool},
        )
        result = spec.handle({"description": "do action_a"})
        assert result["status"] == "failed"
        assert "tool crashed" in result["error"]


# ── Tests de available_tools ───────────────────────────────────────────


class TestAvailableTools:
    """Property available_tools."""

    def test_available_tools_returns_list(
        self, specialist: _FakeSpecialist,
    ) -> None:
        """available_tools retorna lista de nombres de tools."""
        tools = specialist.available_tools
        assert isinstance(tools, list)
        assert "fake_tool" in tools

    def test_available_tools_empty_when_no_tools(self) -> None:
        """available_tools es vacío si no hay tools."""
        spec = _FakeSpecialist(
            specialist_name="x", responsibility="y", tools=None,
        )
        assert spec.available_tools == []


# ── Tests de __repr__ ─────────────────────────────────────────────────


class TestRepr:
    """Representación string."""

    def test_repr_includes_name_and_responsibility(
        self, specialist: _FakeSpecialist,
    ) -> None:
        """__repr__ incluye specialist_name y responsibility."""
        r = repr(specialist)
        assert "_FakeSpecialist" in r
        assert "fake" in r
        assert "testing" in r


# ── Tests de inicialización ────────────────────────────────────────────


class TestInit:
    """Inicialización del specialist."""

    def test_init_sets_attributes(self) -> None:
        """__init__ setea specialist_name, responsibility, _tools."""
        spec = _FakeSpecialist(
            specialist_name="my_spec",
            responsibility="my_resp",
            tools={"t1": MagicMock()},
        )
        assert spec.specialist_name == "my_spec"
        assert spec.responsibility == "my_resp"
        assert "t1" in spec._tools

    def test_init_with_none_tools(self) -> None:
        """tools=None se trata como dict vacío."""
        spec = _FakeSpecialist(
            specialist_name="x", responsibility="y", tools=None,
        )
        assert spec._tools == {}
