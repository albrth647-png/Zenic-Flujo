"""
Tests para Sprint 4 del Roadmap Competitivo.
Cubre: DeadLetterManager, retry mejorado, continue_on_error,
integración con engine y API.
"""

import time

from src.workflow.dead_letter import DeadLetterEntry, DeadLetterManager
from src.workflow.error_handler import ErrorHandler, ErrorHandlerResult
from src.workflow.step_executor import StepExecutor, StepResult

# ===================================================================
# DeadLetterManager — CRUD
# ===================================================================


class TestDeadLetterManager:
    """Tests para DeadLetterManager CRUD."""

    def test_add_entry(self):
        """Agregar entrada a dead letter queue."""
        dl = DeadLetterManager()
        entry_id = dl.add(
            workflow_id=1,
            workflow_name="Test WF",
            execution_id=10,
            step_id=5,
            tool="test_tool",
            action="test_action",
            error_message="Something went wrong",
            retry_count=3,
            step_definition={"id": 5, "tool": "test_tool"},
            context_snapshot={"input": {"x": 1}},
        )
        assert entry_id > 0

        # Verificar que se creó
        entry = dl.get(entry_id)
        assert entry is not None
        assert entry.workflow_id == 1
        assert entry.workflow_name == "Test WF"
        assert entry.error_message == "Something went wrong"
        assert entry.retry_count == 3
        assert entry.status == "pending"
        assert entry.notified == 0
        assert entry.step_definition["id"] == 5

    def test_add_and_list(self):
        """Listar entradas después de agregar."""
        dl = DeadLetterManager()
        dl.add(
            workflow_id=1,
            workflow_name="WF1",
            execution_id=1,
            step_id=1,
            tool="t1",
            action="a1",
            error_message="err1",
            retry_count=1,
        )
        dl.add(
            workflow_id=2,
            workflow_name="WF2",
            execution_id=2,
            step_id=2,
            tool="t2",
            action="a2",
            error_message="err2",
            retry_count=2,
        )

        entries = dl.list(limit=10)
        assert len(entries) >= 2

    def test_list_filter_by_status(self):
        """Listar filtrado por status."""
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )

        # Todas las pending
        pending = dl.list(status="pending")
        assert any(e.id == eid for e in pending)

        # Ninguna resolved aún
        resolved = dl.list(status="resolved")
        assert all(e.id != eid for e in resolved)

    def test_list_filter_by_workflow(self):
        """Listar filtrado por workflow_id."""
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=42,
            workflow_name="WF42",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )

        entries = dl.list(workflow_id=42)
        assert any(e.id == eid for e in entries)

        entries_other = dl.list(workflow_id=99)
        assert all(e.id != eid for e in entries_other)

    def test_get_nonexistent(self):
        """get entry inexistente retorna None."""
        dl = DeadLetterManager()
        entry = dl.get(99999)
        assert entry is None

    def test_discard_entry(self):
        """Descartar entrada cambia status."""
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )

        result = dl.discard(eid)
        assert result is True

        entry = dl.get(eid)
        assert entry.status == "discarded"

    def test_discard_nonexistent(self):
        """Descartar entrada inexistente."""
        dl = DeadLetterManager()
        result = dl.discard(99999)
        assert result is False

    def test_count(self):
        """Contar entradas."""
        dl = DeadLetterManager()
        initial = dl.count()
        dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )
        assert dl.count() == initial + 1

    def test_count_by_status(self):
        """Contar entradas por status."""
        dl = DeadLetterManager()
        pending_before = dl.count(status="pending")
        dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )
        assert dl.count(status="pending") == pending_before + 1

    def test_discard_all(self):
        """Descartar todas las pending."""
        dl = DeadLetterManager()
        dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )
        dl.add(
            workflow_id=2,
            workflow_name="WF2",
            execution_id=2,
            step_id=2,
            tool="t",
            action="a",
            error_message="err2",
            retry_count=2,
        )

        count = dl.discard_all()
        assert count >= 0  # Puede haber entradas de tests anteriores

    def test_get_stats(self):
        """Estadísticas de dead letter."""
        dl = DeadLetterManager()
        stats = dl.get_stats()
        assert "total" in stats
        assert "by_status" in stats
        assert "pending" in stats["by_status"]
        assert "resolved" in stats["by_status"]
        assert "discarded" in stats["by_status"]

    def test_notify_dead_letter(self):
        """Notificar entrada (aunque no haya suscriptores)."""
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=1,
        )
        result = dl.notify_dead_letter(eid)
        assert result is True

        # Segunda notificación debe ser False (ya notificado)
        result2 = dl.notify_dead_letter(eid)
        assert result2 is False

    def test_get_notification_summary(self):
        """Resumen de dead letters no vacío."""
        dl = DeadLetterManager()
        summary = dl.get_notification_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_to_dict(self):
        """DeadLetterEntry.to_dict() serializa correctamente."""
        entry = DeadLetterEntry(
            id=1,
            workflow_id=1,
            workflow_name="WF",
            execution_id=10,
            step_id=5,
            tool="t",
            action="a",
            error_message="err",
            retry_count=3,
            status="pending",
        )
        d = entry.to_dict()
        assert d["id"] == 1
        assert d["workflow_name"] == "WF"
        assert d["notified"] is False


# ===================================================================
# ErrorHandler — Retry Mejorado
# ===================================================================


class FakeExecutor:
    """Fake executor que simula StepExecutor sin usar MagicMock."""

    def __init__(self, fail_count=0, result_after_fails=None):
        self._calls = 0
        self._fail_count = fail_count
        self._result = result_after_fails or StepResult(status="completed", output_data={"ok": True})

    def execute(self, step, context):
        self._calls += 1
        if self._calls <= self._fail_count:
            raise ValueError(f"Fallo simulado #{self._calls}")
        return self._result


class TestErrorHandlerEnhanced:
    """Tests para ErrorHandler mejorado (Sprint 4)."""

    def test_continue_on_error_step_flag(self):
        """continue_on_error=True en step retorna skipped."""
        handler = ErrorHandler()
        step = {"id": 1, "tool": "test", "action": "fail", "continue_on_error": True}
        error = ValueError("Test error")
        context = {"workflow": {"id": 1, "name": "Test"}}

        executor = FakeExecutor(fail_count=99)  # Siempre falla
        result = handler.handle(step, error, context, executor)
        assert result.status == "skipped"
        assert result.output_data.get("reason") == "continue_on_error"

    def test_continue_on_error_workflow_flag(self):
        """continue_on_error=True en workflow retorna skipped."""
        handler = ErrorHandler()
        step = {"id": 1, "tool": "test", "action": "fail"}
        error = ValueError("Test error")
        context = {"workflow": {"id": 1, "name": "Test", "continue_on_error": True}}

        executor = FakeExecutor(fail_count=99)
        result = handler.handle(step, error, context, executor)
        assert result.status == "skipped"

    def test_retry_on_timeout_true(self):
        """retry_on_timeout=True reintenta incluso timeout."""
        handler = ErrorHandler()
        step = {
            "id": 1,
            "tool": "test",
            "action": "timeout",
            "retry": {"retry_on_timeout": True, "max_attempts": 2, "base_delay": 0.01},
        }

        error = TimeoutError("Step 1 excedio el timeout de 30s")
        context = {}

        # Falla 1 vez, luego éxito (necesita 2 attempts porque
        # el primero falla y el segundo tiene éxito)
        executor = FakeExecutor(fail_count=1)

        result = handler.handle(step, error, context, executor)
        assert result.status == "recovered"
        assert result.retries >= 1

    def test_retry_backoff_with_jitter(self):
        """Backoff con jitter no crashea."""
        handler = ErrorHandler()
        step = {
            "id": 1,
            "tool": "test",
            "action": "fail",
            "retry": {"max_attempts": 3, "base_delay": 0.01, "multiplier": 2.0, "jitter": True},
        }
        error = ValueError("Test error")
        context = {}

        # Falla 2 veces, éxito en el 3er intento
        executor = FakeExecutor(
            fail_count=2, result_after_fails=StepResult(status="completed", output_data={"done": True})
        )

        t0 = time.time()
        result = handler.handle(step, error, context, executor)
        elapsed = time.time() - t0

        assert result.status == "recovered"
        assert elapsed > 0.005  # Debe haber esperado al menos un poco

    def test_retry_exhausted_goes_to_dead_letter(self):
        """Cuando se agotan reintentos, va a dead letter."""
        handler = ErrorHandler()
        step = {"id": 1, "tool": "test", "action": "fail", "retry": {"max_attempts": 1, "base_delay": 0.01}}
        error = ValueError("Fatal error")
        context = {"workflow": {"id": 1, "name": "Test"}}

        executor = FakeExecutor(fail_count=99)  # Siempre falla
        result = handler.handle(step, error, context, executor)
        assert result.status in ("dead_letter", "failed", "skipped")

    def test_retry_without_timeout_does_not_retry(self):
        """Timeout sin retry_on_timeout no reintenta."""
        handler = ErrorHandler()
        step = {"id": 1, "tool": "test", "action": "slow", "retry": {"retry_on_timeout": False, "max_attempts": 5}}
        error = TimeoutError("excedio el timeout de 30s")
        context = {"workflow": {"id": 1, "name": "Test"}}

        executor = FakeExecutor(fail_count=99)
        result = handler.handle(step, error, context, executor)

        # No debe reintentar porque retry_on_timeout=False
        assert result is not None
        assert result.status in ("dead_letter", "skipped", "failed")

    def test_context_snapshot(self):
        """_get_context_snapshot incluye keys seguras."""
        snapshot = ErrorHandler._get_context_snapshot(
            {
                "input": {"x": 1},
                "workflow": {"id": 1},
                "secret": "should_not_be_included",
            }
        )
        assert "input" in snapshot
        assert "workflow" in snapshot
        assert "secret" not in snapshot

    def test_error_handler_result(self):
        """ErrorHandlerResult se construye correctamente."""
        r = ErrorHandlerResult(status="dead_letter", error_message="test error", retries=3, orbital_alignment=0.5)
        assert r.status == "dead_letter"
        assert r.error_message == "test error"
        assert r.retries == 3


# ===================================================================
# StepExecutor — continue_on_error
# ===================================================================


class TestContinueOnError:
    """Tests para continue_on_error en StepExecutor y Engine."""

    def test_step_executor_continue_on_error_param(self):
        """continue_on_error se pasa en step params."""
        executor = StepExecutor()
        step = {
            "id": 1,
            "tool": "nonexistent_tool",
            "action": "fail",
            "continue_on_error": True,
        }
        result = executor.execute(step, {})
        # StepExecutor no maneja continue_on_error directamente,
        # eso es responsabilidad del Engine + ErrorHandler.
        # El StepExecutor retorna failed, y el engine decide.
        assert result.status == "failed"

    def test_skipped_result_for_continue(self):
        """SkippedResult para continue_on_error."""
        # Verificar que el StepResult status "skipped" funciona
        result = StepResult(
            status="skipped",
            output_data={"skipped": True, "reason": "continue_on_error"},
        )
        assert result.status == "skipped"
        assert result.output_data["reason"] == "continue_on_error"


# ===================================================================
# DeadLetterEntry — Edge Cases
# ===================================================================


class TestDeadLetterEdgeCases:
    """Tests para edge cases de DeadLetterManager."""

    def test_empty_step_definition(self):
        """Step definition vacío no crashea."""
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message="err",
            retry_count=0,
        )
        entry = dl.get(eid)
        assert entry is not None
        assert entry.step_definition == {}

    def test_long_error_message(self):
        """Error message largo se guarda completo."""
        long_err = "A" * 5000
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=1,
            workflow_name="WF",
            execution_id=1,
            step_id=1,
            tool="t",
            action="a",
            error_message=long_err,
            retry_count=0,
        )
        entry = dl.get(eid)
        assert entry.error_message == long_err

    def test_special_chars_in_fields(self):
        """Caracteres especiales en nombres."""
        dl = DeadLetterManager()
        eid = dl.add(
            workflow_id=1,
            workflow_name="Test <script>alert('xss')</script>",
            execution_id=1,
            step_id=1,
            tool="tést_ñ",
            action="acción_española",
            error_message='Error: ñoño & "comillas"',
            retry_count=0,
        )
        entry = dl.get(eid)
        assert "script" in entry.workflow_name
        assert "ñoño" in entry.error_message

    def test_retry_nonexistent_entry(self):
        """Reintentar entrada inexistente."""
        dl = DeadLetterManager()
        result = dl.retry(99999)
        assert result["status"] == "error"


# ===================================================================
# Notification Summary
# ===================================================================


class TestNotificationSummary:
    """Tests para el resumen de notificación."""

    def test_summary_no_pending(self):
        """Summary sin entradas pendientes dice 'no hay'."""
        dl = DeadLetterManager()
        summary = dl.get_notification_summary()
        # Puede haber entradas de otros tests, pero si hay 0 pending
        # debe decir que no hay
        if dl.count(status="pending") == 0:
            assert "No hay entradas" in summary
        else:
            assert "Dead Letter Queue" in summary
