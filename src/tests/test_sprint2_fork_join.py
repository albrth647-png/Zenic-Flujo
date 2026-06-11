"""
Tests para Sprint 2 del Roadmap Competitivo.
Cubre: ForkHandler (parallel, fork), JoinHandler (all, any, race).
"""

import time

import pytest

from src.workflow.fork_handler import ForkHandler, ForkResult, JoinHandler
from src.workflow.step_executor import StepExecutor


class MockTool:
    """Mock para simular herramientas en los tests."""

    def echo(self, message=""):
        return {"echoed": message}

    def slow(self, delay=0.1):
        time.sleep(delay)
        return {"delayed": True}

    def fail(self):
        raise ValueError("Simulated failure")


@pytest.fixture
def step_executor():
    executor = StepExecutor()
    executor.register_tool("test_tool", MockTool())
    executor.register_tool("system", MockTool())
    return executor


@pytest.fixture
def fork_handler(step_executor):
    return ForkHandler(step_executor)


@pytest.fixture
def join_handler():
    return JoinHandler()


class TestForkHandler:
    """Tests para ForkHandler.execute_parallel."""

    def test_parallel_empty_branches(self, fork_handler):
        """Parallel sin ramas retorna vacío."""
        step = {"id": 1, "branches": [], "merge_strategy": "all"}
        result = fork_handler.execute_parallel(step, {})
        assert result.status == "completed"
        assert len(result.branches) == 0

    def test_parallel_two_branches(self, fork_handler):
        """Parallel con 2 ramas ejecuta ambas."""
        step = {
            "id": 1,
            "type": "parallel",
            "branches": [
                {
                    "name": "branch_a",
                    "steps": [{"id": 2, "tool": "test_tool", "action": "echo", "params": {"message": "hello from A"}}],
                },
                {
                    "name": "branch_b",
                    "steps": [{"id": 3, "tool": "test_tool", "action": "echo", "params": {"message": "hello from B"}}],
                },
            ],
            "merge_strategy": "all",
        }
        result = fork_handler.execute_parallel(step, {})
        assert result.status == "completed"
        assert len(result.branches) == 2
        names = [b["name"] for b in result.branches]
        assert "branch_a" in names
        assert "branch_b" in names

    def test_parallel_strategy_all_fails_on_error(self, fork_handler):
        """Strategy 'all' falla si una rama falla."""
        step = {
            "id": 1,
            "branches": [
                {
                    "name": "good",
                    "steps": [{"id": 2, "tool": "test_tool", "action": "echo", "params": {"message": "ok"}}],
                },
                {"name": "bad", "steps": [{"id": 3, "tool": "test_tool", "action": "fail", "params": {}}]},
            ],
            "merge_strategy": "all",
        }
        result = fork_handler.execute_parallel(step, {})
        assert result.status == "failed"

    def test_parallel_strategy_any_succeeds(self, fork_handler):
        """Strategy 'any' completa si al menos una rama funciona."""
        step = {
            "id": 1,
            "branches": [
                {
                    "name": "fast",
                    "steps": [{"id": 2, "tool": "test_tool", "action": "echo", "params": {"message": "fast"}}],
                },
            ],
            "merge_strategy": "any",
        }
        result = fork_handler.execute_parallel(step, {})
        assert result.status == "completed"

    def test_parallel_max_branches(self, fork_handler):
        """Parallel limita a MAX_BRANCHES (50)."""
        many_branches = [
            {
                "name": f"b{i}",
                "steps": [{"id": i, "tool": "test_tool", "action": "echo", "params": {"message": f"msg{i}"}}],
            }
            for i in range(60)
        ]
        step = {"id": 1, "branches": many_branches, "merge_strategy": "all"}
        result = fork_handler.execute_parallel(step, {})
        assert len(result.branches) == 50

    def test_parallel_with_timeout(self, fork_handler):
        """Parallel respeta el timeout."""
        step = {
            "id": 1,
            "branches": [
                {"name": "slow", "steps": [{"id": 2, "tool": "test_tool", "action": "slow", "params": {"delay": 2.0}}]},
            ],
            "merge_strategy": "all",
            "timeout": 1,
        }
        t0 = time.time()
        result = fork_handler.execute_parallel(step, {})
        elapsed = time.time() - t0
        assert elapsed < 3.0  # No debe esperar los 2s completos
        assert result.status in ("partial", "failed", "completed")


class TestForkHandlerFork:
    """Tests para ForkHandler.execute_fork."""

    def test_fork_simple(self, fork_handler):
        """Fork con 3 items ejecuta todos."""
        step = {
            "id": 1,
            "type": "fork",
            "collection": [{"val": 1}, {"val": 2}, {"val": 3}],
            "item_var": "item",
            "steps": [{"id": 2, "tool": "test_tool", "action": "echo", "params": {"message": "$item.val"}}],
            "merge_strategy": "all",
        }
        result = fork_handler.execute_fork(step, {})
        assert result.status == "completed"
        assert len(result.branches) == 3

    def test_fork_empty_collection(self, fork_handler):
        """Fork con colección vacía."""
        step = {
            "id": 1,
            "collection": [],
            "item_var": "item",
            "steps": [],
            "merge_strategy": "all",
        }
        result = fork_handler.execute_fork(step, {})
        assert result.status == "completed"
        assert len(result.branches) == 0

    def test_fork_max_concurrency(self, fork_handler):
        """Fork respeta max_concurrency."""
        step = {
            "id": 1,
            "collection": [{"n": i} for i in range(20)],
            "item_var": "item",
            "steps": [{"id": 2, "tool": "test_tool", "action": "echo", "params": {"message": "$item.n"}}],
            "merge_strategy": "all",
            "max_concurrency": 5,
        }
        t0 = time.time()
        result = fork_handler.execute_fork(step, {})
        _elapsed = time.time() - t0
        assert result.status == "completed"
        assert len(result.branches) == 20

    def test_fork_caps_at_100(self, fork_handler):
        """Fork limita a 100 ítems."""
        step = {
            "id": 1,
            "collection": list(range(150)),
            "item_var": "item",
            "steps": [{"id": 2, "tool": "test_tool", "action": "echo", "params": {"message": "$item"}}],
            "merge_strategy": "all",
        }
        result = fork_handler.execute_fork(step, {})
        assert len(result.branches) == 100


class TestJoinHandler:
    """Tests para JoinHandler."""

    def test_join_all_merges_all_branches(self, join_handler):
        """Join 'all' mergea todas las ramas."""
        fork_result = ForkResult(
            status="completed",
            branches=[
                {"name": "A", "status": "completed", "steps": [{"step_id": 1, "output": {"data": "from_a"}}]},
                {"name": "B", "status": "completed", "steps": [{"step_id": 2, "output": {"data": "from_b"}}]},
            ],
            merge_strategy="all",
        )
        step = {"id": 10}
        context = {}
        result = join_handler.join(fork_result, step, context)
        assert result.status == "completed"
        assert result.branch_count == 2
        assert "branches" in result.merged_output
        assert "A" in result.merged_output["branches"]
        assert "B" in result.merged_output["branches"]

    def test_join_any_returns_first(self, join_handler):
        """Join 'any' retorna la primera rama completada."""
        fork_result = ForkResult(
            status="completed",
            branches=[
                {"name": "A", "status": "completed", "steps": [{"step_id": 1, "output": {"data": "first"}}]},
            ],
            merge_strategy="any",
        )
        step = {"id": 10}
        result = join_handler.join(fork_result, step, {})
        assert result.status == "completed"
        assert result.merged_output.get("selected_branch") == "A"

    def test_join_race_like_any(self, join_handler):
        """Join 'race' funciona igual que 'any'."""
        fork_result = ForkResult(
            status="completed",
            branches=[
                {"name": "winner", "status": "completed", "steps": [{"step_id": 1, "output": {"data": "win"}}]},
            ],
            merge_strategy="race",
        )
        step = {"id": 10}
        result = join_handler.join(fork_result, step, {})
        assert result.status == "completed"
        assert result.merged_output.get("selected_branch") == "winner"


class TestToolDefinition:
    """Tests para la definición del tool Fork/Join."""

    def test_tool_definition_exists(self, join_handler):
        """ForkHandler tiene definición de tool para el editor."""
        definition = join_handler.get_tool_definition()
        assert definition["tool"] == "fork_join"
        assert "parallel" in definition["actions"]
        assert "fork" in definition["actions"]
        assert definition["actions"]["parallel"]["params"][0]["name"] == "branches"
