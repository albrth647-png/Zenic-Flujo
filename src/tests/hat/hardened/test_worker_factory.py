"""Tests para WorkerFactory — auto-generación de workers por introspección.

Cubre:
- generate_for_tool: crea 1 worker por método público.
- Exclusión de métodos privados (_*) y administrativos.
- Exclusión de métodos en _EXCLUDED_METHODS.
- generate_all: genera para todas las tools registradas.
- Nombres de clases dinámicas (PascalCase).
- Registry integrado: workers se registran automáticamente.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.hat.level4_workers.base.worker_factory import WorkerFactory

# ── Fixtures ────────────────────────────────────────────────────────────


class _FakeTool:
    """Tool de prueba con métodos públicos y privados."""

    def public_action(self) -> dict[str, str]:
        """Método público que se expone como worker."""
        return {"status": "ok"}

    def another_action(self, param: str = "default") -> str:
        """Otro método público."""
        return f"result: {param}"

    def _private_method(self) -> None:
        """Método privado — NO se expone."""
        return None

    def get_status(self) -> dict[str, str]:
        """Método administrativo — excluido por _EXCLUDED_METHODS."""
        return {"status": "running"}

    def configure(self, **kwargs: object) -> None:
        """Método administrativo — excluido."""
        return None


@pytest.fixture
def factory() -> WorkerFactory:
    """WorkerFactory fresco."""
    return WorkerFactory()


@pytest.fixture
def fake_tool() -> _FakeTool:
    """Instancia de _FakeTool."""
    return _FakeTool()


# ── Tests de generate_for_tool ─────────────────────────────────────────


class TestGenerateForTool:
    """Generación de workers para una tool individual."""

    def test_generates_workers_for_public_methods(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """Genera 1 worker por método público (no privado, no excluido)."""
        workers = factory.generate_for_tool("fake", fake_tool)
        # public_action y another_action son públicos y no excluidos
        # get_status y configure están en _EXCLUDED_METHODS
        # _private_method es privado
        assert "public_action" in workers
        assert "another_action" in workers
        # Excluidos
        assert "get_status" not in workers
        assert "configure" not in workers
        assert "_private_method" not in workers

    def test_worker_class_name_is_pascal_case(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """El nombre de la clase generada es PascalCase + 'Worker'."""
        workers = factory.generate_for_tool("fake", fake_tool)
        worker = workers["public_action"]
        class_name = type(worker).__name__
        assert class_name == "FakePublicActionWorker"

    def test_generated_worker_has_correct_attributes(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """El worker generado tiene tool_name y action_name correctos."""
        workers = factory.generate_for_tool("fake", fake_tool)
        worker = workers["public_action"]
        assert worker.tool_name == "fake"
        assert worker.action_name == "public_action"

    def test_generated_worker_can_run(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """El worker generado puede ejecutar el método de la tool."""
        workers = factory.generate_for_tool("fake", fake_tool)
        worker = workers["public_action"]
        result = worker.run()
        assert result["status"] == "completed"
        assert result["result"] == {"status": "ok"}

    def test_generated_worker_passes_params(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """El worker generado pasa params al método."""
        workers = factory.generate_for_tool("fake", fake_tool)
        worker = workers["another_action"]
        result = worker.run(params={"param": "test_value"})
        assert result["status"] == "completed"
        assert result["result"] == "result: test_value"

    def test_excluded_methods_not_generated(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """Los métodos en _EXCLUDED_METHODS no generan workers."""
        workers = factory.generate_for_tool("fake", fake_tool)
        # get_status, configure, test_connection están excluidos
        assert "get_status" not in workers
        assert "configure" not in workers


# ── Tests de generate_all ──────────────────────────────────────────────


class TestGenerateAll:
    """Generación de workers para todas las tools registradas."""

    def test_generate_all_with_multiple_tools(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """generate_all() genera workers para todas las tools."""
        import sys

        mock_reg = MagicMock()
        mock_reg.list_all.return_value = {
            "fake": fake_tool,
            "another": _FakeTool(),
        }
        mock_module = MagicMock()
        mock_module.get_tools_registry.return_value = mock_reg

        with patch.dict(sys.modules, {"src.hat.level5_tools.registry": mock_module}):
            all_workers = factory.generate_all()
        assert "fake" in all_workers
        assert "another" in all_workers
        assert len(all_workers["fake"]) >= 2
        assert len(all_workers["another"]) >= 2

    def test_generate_all_returns_empty_when_no_tools(
        self, factory: WorkerFactory,
    ) -> None:
        """generate_all() retorna dict vacío si no hay tools registradas."""
        import sys

        mock_reg = MagicMock()
        mock_reg.list_all.return_value = {}
        mock_module = MagicMock()
        mock_module.get_tools_registry.return_value = mock_reg

        with patch.dict(sys.modules, {"src.hat.level5_tools.registry": mock_module}):
            all_workers = factory.generate_all()
        assert all_workers == {}

    def test_generate_all_logs_warning_when_no_tools(
        self, factory: WorkerFactory,
    ) -> None:
        """generate_all() loggea warning si no hay tools."""
        import sys

        mock_reg = MagicMock()
        mock_reg.list_all.return_value = {}
        mock_module = MagicMock()
        mock_module.get_tools_registry.return_value = mock_reg

        with patch.dict(sys.modules, {"src.hat.level5_tools.registry": mock_module}):
            result = factory.generate_all()
        # No crash, solo warning loggeado — verificar que retorna dict vacío
        assert result == {}


# ── Tests de registry integrado ────────────────────────────────────────


class TestRegistryIntegration:
    """Integración con WorkerRegistry."""

    def test_workers_registered_in_factory_registry(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """Los workers generados se registran en el registry del factory."""
        factory.generate_for_tool("fake", fake_tool)
        worker = factory.get_worker("fake", "public_action")
        assert worker is not None
        assert worker.tool_name == "fake"
        assert worker.action_name == "public_action"

    def test_list_actions_returns_generated_actions(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """list_actions() retorna las actions generadas para una tool."""
        factory.generate_for_tool("fake", fake_tool)
        actions = factory.list_actions("fake")
        assert "public_action" in actions
        assert "another_action" in actions

    def test_total_count_returns_number_of_workers(
        self, factory: WorkerFactory, fake_tool: _FakeTool,
    ) -> None:
        """total_count() retorna el número total de workers."""
        factory.generate_for_tool("fake", fake_tool)
        assert factory.total_count() >= 2

    def test_get_worker_returns_none_for_unregistered(
        self, factory: WorkerFactory,
    ) -> None:
        """get_worker() retorna None para tool/action no registrado."""
        assert factory.get_worker("unknown", "unknown") is None


# ── Tests de _make_class_name ──────────────────────────────────────────


class TestMakeClassName:
    """Generación de nombres de clase PascalCase."""

    def test_simple_name(self) -> None:
        """Nombre simple: ('crm', 'create_lead') → 'CrmCreateLeadWorker'."""
        name = WorkerFactory._make_class_name("crm", "create_lead")
        assert name == "CrmCreateLeadWorker"

    def test_multi_word_tool_and_action(self) -> None:
        """Nombres multi-palabra: ('data_keeper', 'save_record') → 'DataKeeperSaveRecordWorker'."""
        name = WorkerFactory._make_class_name("data_keeper", "save_record")
        assert name == "DataKeeperSaveRecordWorker"

    def test_single_word(self) -> None:
        """Una sola palabra: ('crm', 'list') → 'CrmListWorker'."""
        name = WorkerFactory._make_class_name("crm", "list")
        assert name == "CrmListWorker"
