"""Tests para ToolWorker — worker atómico con circuit breaker + idempotency.

Cubre:
- run() flujo exitoso: invoke tool method → return completed.
- run() con params: pasa params al método de la tool.
- Circuit breaker: failure threshold, open state, half-open recovery.
- Idempotency: params_hash determinista.
- Error handling: tool method raises exception.
- Properties: idempotency_key, circuit_state.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.hat.level4_workers.base.tool_worker import ToolWorker

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_tool() -> MagicMock:
    """Tool mockeada con método 'execute'."""
    tool = MagicMock()
    tool.execute.return_value = {"status": "ok", "data": "result"}
    return tool


@pytest.fixture
def worker(mock_tool: MagicMock) -> ToolWorker:
    """ToolWorker dinámico con tool mockeada."""
    # WorkerFactory crea subclases dinámicas; aquí creamos una manualmente
    worker_class = type(
        "TestWorker",
        (ToolWorker,),
        {"tool_name": "test_tool", "action_name": "execute"},
    )
    return worker_class(tool_instance=mock_tool)


# ── Tests de run() flujo exitoso ───────────────────────────────────────


class TestRunSuccess:
    """Flujo exitoso de run()."""

    def test_run_returns_completed(self, worker: ToolWorker, mock_tool: MagicMock) -> None:
        """run() retorna status='completed' cuando la tool funciona."""
        result = worker.run()
        assert result["status"] == "completed"
        assert result["action"] == "execute"
        assert result["tool"] == "test_tool"
        assert result["result"] == {"status": "ok", "data": "result"}

    def test_run_invokes_tool_method(self, worker: ToolWorker, mock_tool: MagicMock) -> None:
        """run() invoca el método correcto de la tool."""
        worker.run()
        assert mock_tool.execute.call_count == 1

    def test_run_with_params(self, worker: ToolWorker, mock_tool: MagicMock) -> None:
        """run() pasa params al método de la tool."""
        worker.run(params={"key": "value"})
        assert mock_tool.execute.call_count == 1
        assert mock_tool.execute.call_args.kwargs == {"key": "value"}

    def test_run_with_empty_params(self, worker: ToolWorker, mock_tool: MagicMock) -> None:
        """run() sin params invoca la tool sin argumentos."""
        worker.run()
        assert mock_tool.execute.call_count == 1
        assert mock_tool.execute.call_args.args == ()
        assert mock_tool.execute.call_args.kwargs == {}

    def test_run_includes_params_hash(self, worker: ToolWorker) -> None:
        """run() incluye params_hash en el resultado."""
        result = worker.run(params={"a": 1})
        assert "params_hash" in result
        assert len(result["params_hash"]) == 16

    def test_run_includes_duration_ms(self, worker: ToolWorker) -> None:
        """run() incluye duration_ms en el resultado."""
        result = worker.run()
        assert "duration_ms" in result
        assert isinstance(result["duration_ms"], int)
        assert result["duration_ms"] >= 0


# ── Tests de circuit breaker ───────────────────────────────────────────


class TestCircuitBreaker:
    """Circuit breaker per-worker."""

    def test_circuit_starts_closed(self, worker: ToolWorker) -> None:
        """El circuit breaker empieza cerrado."""
        assert worker.circuit_state == "closed"

    def test_circuit_opens_after_threshold_failures(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Tras 3 fallos consecutivos, el circuit abre."""
        mock_tool.execute.side_effect = RuntimeError("fail")
        for _ in range(3):
            worker.run()
        assert worker.circuit_state == "open"

    def test_circuit_open_rejects_calls(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Con circuit open, run() retorna status='circuit_open' sin invocar tool."""
        mock_tool.execute.side_effect = RuntimeError("fail")
        for _ in range(3):
            worker.run()
        # Ahora el circuit está open
        mock_tool.execute.reset_mock()
        result = worker.run()
        assert result["status"] == "circuit_open"
        mock_tool.execute.assert_not_called()

    def test_circuit_resets_on_success(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Un éxito resetea el failure count a 0."""
        # Provocar 2 fallos (no suficiente para abrir)
        mock_tool.execute.side_effect = RuntimeError("fail")
        worker.run()
        worker.run()
        assert worker.circuit_state == "closed"  # aún cerrado
        # Ahora un éxito
        mock_tool.execute.side_effect = None
        mock_tool.execute.return_value = {"status": "ok"}
        worker.run()
        assert worker.circuit_state == "closed"
        # Los próximos 2 fallos no deberían abrir (count fue reseteado)
        mock_tool.execute.side_effect = RuntimeError("fail")
        worker.run()
        worker.run()
        assert worker.circuit_state == "closed"

    def test_circuit_half_open_after_recovery_timeout(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Tras recovery_timeout, el circuit pasa a half-open."""
        mock_tool.execute.side_effect = RuntimeError("fail")
        for _ in range(3):
            worker.run()
        assert worker.circuit_state == "open"
        # Simular que pasó el recovery_timeout
        worker._last_failure_time = time.monotonic() - 61.0  # > 60s
        assert worker.circuit_state == "half_open"


# ── Tests de error handling ────────────────────────────────────────────


class TestErrorHandling:
    """Manejo de errores en run()."""

    def test_run_returns_failed_on_exception(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Si la tool lanza excepción, run() retorna failed."""
        mock_tool.execute.side_effect = ValueError("bad params")
        result = worker.run()
        assert result["status"] == "failed"
        assert "bad params" in result["error"]
        assert result["action"] == "execute"
        assert result["tool"] == "test_tool"

    def test_run_includes_params_hash_on_failure(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """params_hash se incluye incluso en fallos."""
        mock_tool.execute.side_effect = RuntimeError("boom")
        result = worker.run(params={"x": 1})
        assert "params_hash" in result


# ── Tests de idempotency ───────────────────────────────────────────────


class TestIdempotency:
    """Idempotency tracking via params_hash."""

    def test_same_params_produce_same_hash(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Los mismos params producen el mismo params_hash."""
        r1 = worker.run(params={"a": 1, "b": 2})
        r2 = worker.run(params={"a": 1, "b": 2})
        assert r1["params_hash"] == r2["params_hash"]

    def test_different_params_produce_different_hash(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Params distintos producen params_hash distinto."""
        r1 = worker.run(params={"a": 1})
        r2 = worker.run(params={"a": 2})
        assert r1["params_hash"] != r2["params_hash"]

    def test_params_order_does_not_affect_hash(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """El orden de params no afecta el hash (sorted keys)."""
        r1 = worker.run(params={"a": 1, "b": 2})
        r2 = worker.run(params={"b": 2, "a": 1})
        assert r1["params_hash"] == r2["params_hash"]

    def test_no_params_produces_consistent_hash(
        self, worker: ToolWorker, mock_tool: MagicMock,
    ) -> None:
        """Sin params, el hash es consistente."""
        r1 = worker.run()
        r2 = worker.run()
        assert r1["params_hash"] == r2["params_hash"]


# ── Tests de properties ────────────────────────────────────────────────


class TestProperties:
    """Properties del ToolWorker."""

    def test_idempotency_key_format(self, worker: ToolWorker) -> None:
        """idempotency_key tiene formato 'tool_name.action_name'."""
        key = worker.idempotency_key
        assert key == "test_tool.execute"

    def test_circuit_state_returns_string(self, worker: ToolWorker) -> None:
        """circuit_state retorna un string."""
        state = worker.circuit_state
        assert isinstance(state, str)
        assert state in ("closed", "open", "half_open")

    def test_repr_includes_tool_and_action(self, worker: ToolWorker) -> None:
        """__repr__ incluye tool_name y action_name."""
        r = repr(worker)
        assert "test_tool" in r
        assert "execute" in r
        assert "circuit=" in r


# ── Tests de init sin método ───────────────────────────────────────────


class TestInitWithoutMethod:
    """Inicialización cuando la tool no tiene el método esperado."""

    def test_init_raises_if_method_not_found(self) -> None:
        """Si la tool no tiene el método, __init__ raise AttributeError."""
        # Usar spec=[] para que el mock no tenga atributos automáticos
        empty_tool = MagicMock(spec=[])
        worker_class = type(
            "MissingMethodWorker",
            (ToolWorker,),
            {"tool_name": "test_tool", "action_name": "nonexistent_method"},
        )
        with pytest.raises(AttributeError, match="nonexistent_method"):
            worker_class(tool_instance=empty_tool)
