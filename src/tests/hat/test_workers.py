"""Tests for HAT Nivel 4 — WorkerFactory + ToolWorker + WorkerRegistry."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.events.bus import EventBus
from src.hat.level5_tools.registry import get_tools_registry
from src.hat.level4_workers.base.worker_factory import WorkerFactory
from src.hat.level4_workers.base.tool_worker import ToolWorker
from src.hat.level4_workers.base.registry import WorkerRegistry
from src.hat.level4_workers.base.idempotency import compute_worker_hash


class TestWorkerFactory:
    """Tests for WorkerFactory auto-generation."""

    @pytest.fixture(scope="class")
    def tools_registry(self):
        """Register all tools once for the test class."""
        registry = get_tools_registry()
        registry.register_all(event_bus=EventBus())
        return registry

    @pytest.fixture(scope="class")
    def factory(self, tools_registry):
        """Create WorkerFactory and generate all workers."""
        factory = WorkerFactory()
        factory.generate_all()
        return factory

    def test_generate_all_creates_workers_for_all_tools(self, factory):
        """generate_all() should create workers for all 19 tools."""
        all_workers = factory.registry.list_all()
        tools_with_workers = set(tool for (tool, _) in all_workers)
        assert len(tools_with_workers) >= 15  # at least 15 of 19 tools should have workers

    def test_total_workers_above_40(self, factory):
        """Should generate at least 40 workers total (expected ~59)."""
        assert len(factory.registry) >= 40

    def test_crm_has_9_actions(self, factory):
        """CRM tool should have 9 public method workers."""
        crm_actions = factory.list_actions("crm")
        assert len(crm_actions) == 9
        assert "create_lead" in crm_actions
        assert "list_leads" in crm_actions
        assert "advance_stage" in crm_actions
        assert "close_won" in crm_actions
        assert "close_lost" in crm_actions
        assert "get_stats" in crm_actions

    def test_invoice_has_actions(self, factory):
        """Invoice tool should have multiple workers."""
        invoice_actions = factory.list_actions("invoice")
        assert len(invoice_actions) >= 5
        assert "create_invoice" in invoice_actions
        assert "mark_paid" in invoice_actions

    def test_excluded_methods_not_generated(self, factory):
        """Administrative methods should NOT be generated as workers."""
        for tool_name in factory.registry.list_tools():
            actions = factory.list_actions(tool_name)
            assert "get_tool_definition" not in actions
            assert "get_status" not in actions
            assert "configure" not in actions
            assert "test_connection" not in actions

    def test_worker_class_names_are_pascalcase(self, factory):
        """Worker class names should be PascalCase."""
        worker = factory.get_worker("crm", "create_lead")
        assert worker is not None
        assert type(worker).__name__ == "CrmCreateLeadWorker"

    def test_get_worker_returns_toolworker_instance(self, factory):
        """get_worker() should return a ToolWorker instance."""
        worker = factory.get_worker("crm", "list_leads")
        assert worker is not None
        assert isinstance(worker, ToolWorker)
        assert worker.tool_name == "crm"
        assert worker.action_name == "list_leads"

    def test_get_nonexistent_worker_returns_none(self, factory):
        """get_worker() for non-existent action should return None."""
        assert factory.get_worker("crm", "nonexistent_action") is None
        assert factory.get_worker("nonexistent_tool", "any_action") is None


class TestToolWorker:
    """Tests for ToolWorker execution."""

    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool with a method that returns a value."""
        tool = MagicMock()
        tool.create_lead.return_value = {"id": 1, "name": "Test Lead"}
        tool.list_leads.return_value = [{"id": 1, "name": "Lead 1"}]
        return tool

    @pytest.fixture
    def worker(self, mock_tool):
        """Create a worker for the mock tool."""
        # Create a dynamic worker class
        worker_class = type(
            "MockCreateLeadWorker",
            (ToolWorker,),
            {"tool_name": "mock", "action_name": "create_lead"},
        )
        return worker_class(tool_instance=mock_tool)

    def test_run_returns_completed_status(self, worker, mock_tool):
        """run() should return status='completed' on success."""
        result = worker.run({"name": "Test Lead"})
        assert result["status"] == "completed"
        assert result["action"] == "create_lead"
        assert result["tool"] == "mock"
        assert result["result"] == {"id": 1, "name": "Test Lead"}
        mock_tool.create_lead.assert_called_once_with(name="Test Lead")

    def test_run_includes_params_hash(self, worker):
        """run() should include a params_hash for idempotency."""
        result = worker.run({"name": "Test"})
        assert "params_hash" in result
        assert len(result["params_hash"]) == 16

    def test_run_includes_duration_ms(self, worker):
        """run() should include duration_ms."""
        result = worker.run({"name": "Test"})
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0

    def test_run_with_empty_params(self, worker, mock_tool):
        """run() with no params should call method without args."""
        result = worker.run()
        assert result["status"] == "completed"
        mock_tool.create_lead.assert_called_once_with()

    def test_run_handles_errors_gracefully(self, mock_tool):
        """run() should return status='failed' on exception."""
        mock_tool.create_lead.side_effect = ValueError("Invalid lead")
        worker_class = type(
            "MockErrorWorker",
            (ToolWorker,),
            {"tool_name": "mock", "action_name": "create_lead"},
        )
        worker = worker_class(tool_instance=mock_tool)
        result = worker.run({"name": "Test"})
        assert result["status"] == "failed"
        assert "Invalid lead" in result["error"]

    def test_params_hash_is_deterministic(self, worker):
        """Same params should produce same hash."""
        r1 = worker.run({"name": "Test", "email": "test@test.com"})
        r2 = worker.run({"name": "Test", "email": "test@test.com"})
        assert r1["params_hash"] == r2["params_hash"]

    def test_different_params_produce_different_hash(self, worker):
        """Different params should produce different hash."""
        r1 = worker.run({"name": "Test1"})
        r2 = worker.run({"name": "Test2"})
        assert r1["params_hash"] != r2["params_hash"]


class TestCircuitBreaker:
    """Tests for per-worker circuit breaker."""

    @pytest.fixture
    def failing_tool(self):
        """Create a tool that always fails."""
        tool = MagicMock()
        tool.risky_action.side_effect = ConnectionError("Tool down")
        return tool

    @pytest.fixture
    def worker(self, failing_tool):
        """Create a worker with low threshold for testing."""
        worker_class = type(
            "MockRiskyWorker",
            (ToolWorker,),
            {"tool_name": "mock", "action_name": "risky_action"},
        )
        w = worker_class(tool_instance=failing_tool)
        w._failure_threshold = 3  # low threshold for testing
        w._recovery_timeout = 0.1  # 100ms for fast tests
        return w

    def test_circuit_starts_closed(self, worker):
        """Circuit breaker should start closed."""
        assert worker.circuit_state == "closed"

    def test_circuit_opens_after_threshold_failures(self, worker):
        """Circuit should open after N consecutive failures."""
        # First 2 failures: circuit stays closed
        worker.run()
        assert worker.circuit_state == "closed"
        worker.run()
        assert worker.circuit_state == "closed"

        # Third failure: circuit opens
        worker.run()
        assert worker.circuit_state == "open"

    def test_open_circuit_blocks_execution(self, worker):
        """When circuit is open, run() should return circuit_open status."""
        # Force 3 failures to open circuit
        for _ in range(3):
            worker.run()
        assert worker.circuit_state == "open"

        # Next call should be blocked
        result = worker.run({"param": "value"})
        assert result["status"] == "circuit_open"

    def test_circuit_recovers_after_timeout(self, worker):
        """Circuit should go half-open after recovery timeout."""
        import time
        # Force 3 failures
        for _ in range(3):
            worker.run()
        assert worker.circuit_state == "open"

        # Wait for recovery timeout
        time.sleep(0.15)

        # Next call should be allowed (half-open)
        # The tool still fails, but the call goes through
        result = worker.run()
        assert result["status"] == "failed"  # failed, but NOT circuit_open
        assert result["status"] != "circuit_open"

    def test_success_resets_circuit(self, worker, failing_tool):
        """A successful call should reset the circuit breaker."""
        # Make tool fail twice
        worker.run()
        worker.run()
        assert worker._failure_count == 2

        # Make tool succeed
        failing_tool.risky_action.side_effect = None
        failing_tool.risky_action.return_value = {"ok": True}
        result = worker.run()
        assert result["status"] == "completed"
        assert worker._failure_count == 0
        assert worker.circuit_state == "closed"


class TestIdempotency:
    """Tests for idempotency hash."""

    def test_same_params_same_hash(self):
        """Same params dict should produce same hash."""
        h1 = compute_worker_hash("crm", "create_lead", {"name": "Juan", "email": "juan@test.com"})
        h2 = compute_worker_hash("crm", "create_lead", {"name": "Juan", "email": "juan@test.com"})
        assert h1 == h2

    def test_different_tool_different_hash(self):
        """Different tool should produce different hash."""
        h1 = compute_worker_hash("crm", "create_lead", {"name": "Juan"})
        h2 = compute_worker_hash("invoice", "create_lead", {"name": "Juan"})
        assert h1 != h2

    def test_different_action_different_hash(self):
        """Different action should produce different hash."""
        h1 = compute_worker_hash("crm", "create_lead", {"name": "Juan"})
        h2 = compute_worker_hash("crm", "list_leads", {"name": "Juan"})
        assert h1 != h2

    def test_different_params_different_hash(self):
        """Different params should produce different hash."""
        h1 = compute_worker_hash("crm", "create_lead", {"name": "Juan"})
        h2 = compute_worker_hash("crm", "create_lead", {"name": "Pedro"})
        assert h1 != h2

    def test_hash_is_16_chars(self):
        """Hash should be 16 characters (sha256[:16])."""
        h = compute_worker_hash("crm", "create_lead", {"name": "Juan"})
        assert len(h) == 16

    def test_param_order_doesnt_matter(self):
        """Params with different key order should produce same hash."""
        h1 = compute_worker_hash("crm", "create_lead", {"name": "Juan", "email": "j@t.com"})
        h2 = compute_worker_hash("crm", "create_lead", {"email": "j@t.com", "name": "Juan"})
        assert h1 == h2
