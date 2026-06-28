"""Tests para WorkerRegistry — lookup de workers por (tool_name, action_name).

Cubre:
- register: añade worker al registry.
- get: obtiene worker por tool+action.
- list_actions: lista actions de una tool.
- list_tools: lista tools con workers.
- list_all: retorna todos los workers.
- len() y total_count().
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level4_workers.base.registry import WorkerRegistry


@pytest.fixture
def registry() -> WorkerRegistry:
    """WorkerRegistry vacío."""
    return WorkerRegistry()


@pytest.fixture
def mock_worker() -> MagicMock:
    """Worker mockeado."""
    return MagicMock()


class TestRegister:
    """Registro de workers."""

    def test_register_adds_worker(
        self, registry: WorkerRegistry, mock_worker: MagicMock,
    ) -> None:
        """register() añade el worker al registry."""
        registry.register("crm", "create_lead", mock_worker)
        assert registry.get("crm", "create_lead") is mock_worker

    def test_register_multiple_workers_same_tool(
        self, registry: WorkerRegistry,
    ) -> None:
        """Múltiples workers de la misma tool se registran correctamente."""
        w1, w2 = MagicMock(), MagicMock()
        registry.register("crm", "create_lead", w1)
        registry.register("crm", "list_leads", w2)
        assert registry.get("crm", "create_lead") is w1
        assert registry.get("crm", "list_leads") is w2


class TestGet:
    """Obtención de workers."""

    def test_get_returns_none_if_not_found(self, registry: WorkerRegistry) -> None:
        """get() retorna None si el worker no existe."""
        assert registry.get("unknown", "action") is None

    def test_get_returns_worker(self, registry: WorkerRegistry, mock_worker: MagicMock) -> None:
        """get() retorna el worker registrado."""
        registry.register("crm", "create_lead", mock_worker)
        assert registry.get("crm", "create_lead") is mock_worker


class TestListActions:
    """Listado de actions por tool."""

    def test_list_actions_returns_sorted(self, registry: WorkerRegistry) -> None:
        """list_actions() retorna actions ordenadas alfabéticamente."""
        registry.register("crm", "create_lead", MagicMock())
        registry.register("crm", "list_leads", MagicMock())
        registry.register("crm", "advance_stage", MagicMock())
        actions = registry.list_actions("crm")
        assert actions == ["advance_stage", "create_lead", "list_leads"]

    def test_list_actions_empty_for_unknown_tool(self, registry: WorkerRegistry) -> None:
        """list_actions() retorna vacío para tool desconocida."""
        assert registry.list_actions("unknown") == []


class TestListTools:
    """Listado de tools."""

    def test_list_tools_returns_sorted(self, registry: WorkerRegistry) -> None:
        """list_tools() retorna tools ordenadas."""
        registry.register("crm", "a", MagicMock())
        registry.register("invoice", "b", MagicMock())
        registry.register("api", "c", MagicMock())
        tools = registry.list_tools()
        assert tools == ["api", "crm", "invoice"]

    def test_list_tools_empty_when_nothing_registered(self, registry: WorkerRegistry) -> None:
        """list_tools() retorna vacío si no hay workers."""
        assert registry.list_tools() == []


class TestListAll:
    """Listado completo de workers."""

    def test_list_all_returns_dict(self, registry: WorkerRegistry) -> None:
        """list_all() retorna dict con tuplas (tool, action) → worker."""
        w1, w2 = MagicMock(), MagicMock()
        registry.register("crm", "a", w1)
        registry.register("crm", "b", w2)
        all_workers = registry.list_all()
        assert len(all_workers) == 2
        assert all_workers[("crm", "a")] is w1
        assert all_workers[("crm", "b")] is w2

    def test_list_all_empty_when_nothing_registered(self, registry: WorkerRegistry) -> None:
        """list_all() retorna dict vacío."""
        assert registry.list_all() == {}


class TestLen:
    """len() y total_count()."""

    def test_len_returns_count(self, registry: WorkerRegistry) -> None:
        """len(registry) retorna número de workers."""
        registry.register("crm", "a", MagicMock())
        registry.register("crm", "b", MagicMock())
        registry.register("invoice", "c", MagicMock())
        assert len(registry) == 3

    def test_total_count_equals_len(self, registry: WorkerRegistry) -> None:
        """total_count() == len(registry)."""
        registry.register("crm", "a", MagicMock())
        assert registry.total_count() == len(registry)

    def test_len_zero_when_empty(self, registry: WorkerRegistry) -> None:
        """len(registry) == 0 cuando está vacío."""
        assert len(registry) == 0
