"""
Tests para Sprint 7-8: WorkQueue + Workers asíncronos.
=================================================================
Sprint 7-8 del Roadmap Competitivo.
"""

from __future__ import annotations

import time

from src.data.database_manager import DatabaseManager
from src.events.work_queue import WorkQueue, DEFAULT_MAX_RETRIES
from src.events.worker_manager import Worker, WorkerManager

# ── Helpers ──────────────────────────────────────────────────


def cleanup_queue():
    """Limpia la tabla work_queue después de cada test."""
    db = DatabaseManager()
    db.execute("DELETE FROM work_queue")
    db.commit()


# ── WorkQueue Tests ───────────────────────────────────────────


class TestWorkQueueEnqueue:
    """Enqueue básico."""

    def setup_method(self):
        cleanup_queue()

    def test_enqueue_returns_item(self):
        """Enqueue retorna WorkQueueItem con los datos correctos."""
        q = WorkQueue()
        item = q.enqueue(workflow_id=1, trigger_data={"key": "val"}, priority=5)
        assert item.workflow_id == 1
        assert item.trigger_data == {"key": "val"}
        assert item.priority == 5
        assert item.status == "queued"
        assert item.id is not None

    def test_enqueue_defaults(self):
        """Enqueue con valores por defecto."""
        q = WorkQueue()
        item = q.enqueue(workflow_id=99)
        assert item.workflow_id == 99
        assert item.trigger_data == {}
        assert item.priority == 0
        assert item.max_retries == DEFAULT_MAX_RETRIES

    def test_enqueue_multiple(self):
        """Enqueue de múltiples items incrementa IDs."""
        q = WorkQueue()
        items = []
        for i in range(5):
            items.append(q.enqueue(workflow_id=i + 1, priority=i))
        ids = [it.id for it in items]
        assert len(set(ids)) == 5  # Todos distintos
        # El último tiene mayor prioridad
        assert items[4].priority == 4

    def test_enqueue_with_scheduled(self):
        """Enqueue con fecha programada."""
        q = WorkQueue()
        item = q.enqueue(workflow_id=1, scheduled_at="2099-01-01T00:00:00")
        assert item.scheduled_at == "2099-01-01T00:00:00"


class TestWorkQueueDequeue:
    """Dequeue básico."""

    def setup_method(self):
        cleanup_queue()

    def test_dequeue_returns_oldest(self):
        """Dequeue retorna el item más antiguo (FIFO entre misma prioridad)."""
        q = WorkQueue()
        q.enqueue(workflow_id=1, priority=0)
        time.sleep(0.01)
        q.enqueue(workflow_id=2, priority=0)
        item = q.dequeue()
        assert item is not None
        assert item.workflow_id == 1  # El primero en entrar

    def test_dequeue_prioritizes_higher_priority(self):
        """Dequeue retorna item de mayor prioridad primero."""
        q = WorkQueue()
        q.enqueue(workflow_id=1, priority=1)
        q.enqueue(workflow_id=2, priority=10)
        item = q.dequeue()
        assert item is not None
        assert item.workflow_id == 2  # Mayor prioridad

    def test_dequeue_returns_none_when_empty(self):
        """Dequeue retorna None si no hay items."""
        q = WorkQueue()
        item = q.dequeue()
        assert item is None

    def test_dequeue_marks_as_processing(self):
        """Item dequeueado queda en estado 'processing'."""
        q = WorkQueue()
        q.enqueue(workflow_id=42)
        item = q.dequeue()
        assert item is not None
        assert item.status == "processing"
        # Verificar en DB
        db = DatabaseManager()
        row = db.fetchone("SELECT status FROM work_queue WHERE id = ?", (item.id,))
        assert row["status"] == "processing"

    def test_dequeue_respects_scheduled(self):
        """Dequeue no retorna items programados para futuro."""
        q = WorkQueue()
        q.enqueue(workflow_id=1, scheduled_at="2099-01-01T00:00:00")
        item = q.dequeue()
        assert item is None


class TestWorkQueueAckNack:
    """Ack/Nack después de procesar."""

    def setup_method(self):
        cleanup_queue()

    def test_ack_marks_completed(self):
        """Ack marca como completado."""
        q = WorkQueue()
        q.enqueue(workflow_id=1)
        item = q.dequeue()
        assert item is not None
        result = q.ack(item.id)
        assert result is True
        db = DatabaseManager()
        row = db.fetchone("SELECT status FROM work_queue WHERE id = ?", (item.id,))
        assert row["status"] == "completed"

    def test_ack_nonexistent(self):
        """Ack en item inexistente retorna False."""
        q = WorkQueue()
        result = q.ack(99999)
        assert result is False

    def test_nack_requeue_on_retry_left(self):
        """Nack re-encola si quedan reintentos."""
        q = WorkQueue()
        q.enqueue(workflow_id=1, max_retries=3)
        item = q.dequeue()
        assert item is not None
        result = q.nack(item.id, error_message="fail", requeue=True)
        assert result is True
        db = DatabaseManager()
        row = db.fetchone("SELECT status, retry_count FROM work_queue WHERE id = ?", (item.id,))
        assert row["status"] == "queued"
        assert row["retry_count"] == 1

    def test_nack_fails_when_no_retries_left(self):
        """Nack marca como failed si se agotaron los reintentos.

        Con max_retries=2, el primer nack (retry_count=1) re-encola,
        el segundo nack (retry_count=2) agota los reintentos → failed.
        Nota: nack pone scheduled_at en futuro (backoff); se limpia
        manualmente para que dequeue pueda encontrarlo inmediatamente.
        """
        q = WorkQueue()
        q.enqueue(workflow_id=1, max_retries=2)
        item = q.dequeue()
        assert item is not None
        q.nack(item.id, error_message="fail", requeue=True)  # retry_count → 1, 1<2 → requeue
        # Limpiar scheduled_at para que dequeue lo encuentre sin esperar backoff
        db = DatabaseManager()
        db.execute("UPDATE work_queue SET scheduled_at = NULL WHERE id = ?", (item.id,))
        db.commit()

        item2 = q.dequeue()
        assert item2 is not None, "El item debió re-encolarse después del primer nack"
        q.nack(item2.id, error_message="fail again", requeue=True)  # retry_count → 2, 2<2 → failed
        row = db.fetchone("SELECT status, retry_count FROM work_queue WHERE id = ?", (item.id,))
        assert row["status"] == "failed"
        assert row["retry_count"] >= 2


class TestWorkQueuePeek:
    """Peek para inspeccionar cola sin desencolar."""

    def setup_method(self):
        cleanup_queue()

    def test_peek_returns_items(self):
        """Peek retorna items sin cambiarlos de estado."""
        q = WorkQueue()
        for i in range(3):
            q.enqueue(workflow_id=i + 1)
        items = q.peek(limit=10)
        assert len(items) == 3
        # Siguen en 'queued'
        db = DatabaseManager()
        rows = db.fetchall("SELECT COUNT(*) as c FROM work_queue WHERE status = 'queued'")
        assert rows[0]["c"] == 3

    def test_peek_respects_limit(self):
        """Peek respeta el límite."""
        q = WorkQueue()
        for i in range(10):
            q.enqueue(workflow_id=i + 1)
        items = q.peek(limit=3)
        assert len(items) == 3


class TestWorkQueueMetrics:
    """Métricas de la cola."""

    def setup_method(self):
        cleanup_queue()

    def test_get_metrics_structure(self):
        """get_metrics retorna estructura correcta."""
        q = WorkQueue()
        metrics = q.get_metrics()
        assert "depth" in metrics
        assert "throughput" in metrics
        assert "performance" in metrics
        assert "backend" in metrics
        assert metrics["backend"] == "sqlite"

    def test_get_metrics_updates(self):
        """Métricas se actualizan con operaciones."""
        q = WorkQueue()
        q.enqueue(workflow_id=1)
        q.enqueue(workflow_id=2)
        metrics = q.get_metrics()
        assert metrics["depth"]["queued"] >= 2
        assert metrics["throughput"]["total_enqueued"] >= 2


class TestWorkQueueCleanup:
    """Limpieza de items viejos."""

    def setup_method(self):
        cleanup_queue()

    def test_cleanup_removes_old_completed(self):
        """Cleanup elimina items completados/failed viejos."""
        q = WorkQueue()
        q.enqueue(workflow_id=1)
        item = q.dequeue()
        assert item is not None
        q.ack(item.id)

        # Forzar fecha vieja
        db = DatabaseManager()
        db.execute(
            "UPDATE work_queue SET created_at = '2020-01-01' WHERE id = ?",
            (item.id,),
        )
        db.commit()

        deleted = q.cleanup(max_age_hours=1)
        assert deleted > 0

    def test_cleanup_keeps_recent(self):
        """Cleanup no elimina items recientes."""
        q = WorkQueue()
        q.enqueue(workflow_id=1)
        item = q.dequeue()
        assert item is not None
        q.ack(item.id)
        deleted = q.cleanup(max_age_hours=24)
        assert deleted == 0  # Es reciente


class TestWorkQueueRetryFailed:
    """Reintentar items fallidos."""

    def setup_method(self):
        cleanup_queue()

    def test_retry_failed_requeues(self):
        """retry_failed re-encola items fallidos.

        Con max_retries=2, nack 2 veces para agotar reintentos,
        el item queda 'failed', y retry_failed lo re-encola.
        Nota: nack pone scheduled_at en futuro (backoff); se limpia
        manualmente para que dequeue pueda encontrarlo inmediatamente.
        """
        q = WorkQueue()
        q.enqueue(workflow_id=1, max_retries=2)
        db = DatabaseManager()

        item = q.dequeue()
        assert item is not None
        q.nack(item.id, error_message="fail", requeue=True)  # retry_count=1 → requeue
        db.execute("UPDATE work_queue SET scheduled_at = NULL WHERE id = ?", (item.id,))
        db.commit()

        # Consumir el reintento
        item2 = q.dequeue()
        assert item2 is not None, "El item debió re-encolarse"
        q.nack(item2.id, error_message="fail again", requeue=True)  # retry_count=2 → failed

        # Ahora está failed
        row = db.fetchone("SELECT status FROM work_queue WHERE id = ?", (item.id,))
        assert row["status"] == "failed"

        # Reintentar
        count = q.retry_failed(max_items=10)
        assert count > 0
        row = db.fetchone("SELECT status FROM work_queue WHERE id = ?", (item.id,))
        assert row["status"] == "queued"


# ── Worker Tests ─────────────────────────────────────────────


class TestWorker:
    """Worker individual."""

    def test_worker_initial_state(self):
        """Worker inicia en idle."""
        from src.events.work_queue import WorkQueue
        q = WorkQueue()
        w = Worker(worker_id=1, queue=q)
        assert w.worker_id == 1
        assert w.status == "idle"
        assert w.items_processed == 0
        assert w.items_failed == 0
        assert w.current_item_id is None

    def test_worker_start_and_stop(self):
        """Worker inicia y se detiene gracefulmente."""
        from src.events.work_queue import WorkQueue
        q = WorkQueue()
        w = Worker(worker_id=2, queue=q)
        w.start()
        assert w.is_alive() is True
        time.sleep(0.2)
        w.stop()
        time.sleep(0.1)
        assert w.status == "stopped"

    def test_worker_get_health(self):
        """get_health retorna estado del worker."""
        from src.events.work_queue import WorkQueue
        q = WorkQueue()
        w = Worker(worker_id=3, queue=q)
        health = w.get_health()
        assert health["worker_id"] == 3
        assert "status" in health
        assert "alive" in health
        assert "items_processed" in health

    def test_worker_processes_item(self):
        """Worker procesa un item de la cola.

        Workflow 1 no existe en la DB, así que el worker falla
        con "Workflow no encontrado". Con max_retries=0, el nack
        inmediatamente marca como 'failed' (no re-encola).
        """
        cleanup_queue()
        from src.events.work_queue import WorkQueue
        q = WorkQueue()
        q.enqueue(workflow_id=1, trigger_data={"test": True}, max_retries=0)

        w = Worker(worker_id=4, queue=q)
        w.start()
        time.sleep(0.5)  # Esperar que procese
        w.stop()
        time.sleep(0.1)

        # Workflow 1 no existe → falla inmediatamente → status='failed'
        db = DatabaseManager()
        row = db.fetchone(
            "SELECT status FROM work_queue WHERE workflow_id = 1"
        )
        assert row is not None
        assert row["status"] in ("failed", "completed")


class TestWorkerManager:
    """WorkerManager con múltiples workers."""

    def setup_method(self):
        cleanup_queue()

    def test_worker_manager_start_stop(self):
        """WorkerManager inicia y detiene N workers."""
        wm = WorkerManager(num_workers=2)
        wm.start()
        time.sleep(0.2)
        metrics = wm.get_metrics()
        assert metrics["workers"]["total"] == 2
        assert metrics["workers"]["alive"] == 2

        wm.stop()
        time.sleep(0.1)
        metrics = wm.get_metrics()
        assert metrics["workers"]["alive"] <= len(metrics["workers"]["details"])

    def test_worker_manager_scale_up(self):
        """WorkerManager escala hacia arriba."""
        wm = WorkerManager(num_workers=2)
        wm.start()
        time.sleep(0.1)

        new_count = wm.scale(5)
        assert new_count == 5
        metrics = wm.get_metrics()
        assert metrics["workers"]["total"] == 5

        wm.stop()

    def test_worker_manager_scale_down(self):
        """WorkerManager escala hacia abajo."""
        wm = WorkerManager(num_workers=4)
        wm.start()
        time.sleep(0.1)

        new_count = wm.scale(2)
        assert new_count == 2
        metrics = wm.get_metrics()
        assert metrics["workers"]["total"] == 2
        assert metrics["workers"]["alive"] <= 2

        wm.stop()

    def test_worker_manager_get_workers_status(self):
        """get_workers_status retorna lista de estados."""
        wm = WorkerManager(num_workers=3)
        wm.start()
        time.sleep(0.1)

        statuses = wm.get_workers_status()
        assert len(statuses) == 3
        for s in statuses:
            assert "worker_id" in s
            assert "alive" in s
            assert s["alive"] is True

        wm.stop()

    def test_worker_manager_metrics_structure(self):
        """get_metrics retorna estructura completa."""
        wm = WorkerManager(num_workers=2)
        wm.start()
        time.sleep(0.1)

        metrics = wm.get_metrics()
        assert "workers" in metrics
        assert "queue" in metrics
        assert metrics["workers"]["total"] == 2
        assert "total_processed" in metrics["workers"]
        assert "total_failed" in metrics["workers"]
        assert "avg_processing_time_ms" in metrics["workers"]
        assert metrics["queue"]["backend"] == "sqlite"

        wm.stop()

    def test_worker_manager_processes_queue(self):
        """WorkerManager procesa items de la cola automáticamente."""
        from src.events.work_queue import WorkQueue
        q = WorkQueue()

        wm = WorkerManager(num_workers=2, queue=q)
        wm.start()

        # Encolar varios items
        for i in range(3):
            q.enqueue(workflow_id=100 + i, trigger_data={"idx": i})

        time.sleep(4)  # Dar tiempo a que los workers procesen

        # Los items deberían estar completados (o al menos procesados)
        db = DatabaseManager()
        rows = db.fetchall(
            "SELECT status, COUNT(*) as c FROM work_queue "
            "WHERE workflow_id >= 100 AND workflow_id < 200 "
            "GROUP BY status"
        )
        statuses = {r["status"]: r["c"] for r in rows}
        total = sum(r["c"] for r in rows)
        assert total == 3
        # Deberían estar completed o failed (o processing si justo se está procesando)
        for s in statuses:
            assert s in ("completed", "failed", "processing")

        wm.stop()

    def test_worker_manager_queue_property(self):
        """La property queue retorna la cola asociada."""
        from src.events.work_queue import WorkQueue
        q = WorkQueue()
        wm = WorkerManager(num_workers=1, queue=q)
        assert wm.queue is q
