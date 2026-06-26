"""
WorkerManager — Gestor de workers para ejecución asíncrona
===============================================================

Sprint 7-8 del Roadmap Competitivo.

Gestiona N workers que procesan items de la WorkQueue.
Cada worker:
1. Toma un item de la cola (dequeue)
2. Ejecuta el workflow vía WorkflowEngine
3. Marca como completado (ack) o fallido (nack)
4. Reporta métricas

El WorkerManager:
- Inicia/detiene N workers
- Health check periódico
- Reinicio automático de workers caídos
- Graceful shutdown
- Métricas en tiempo real
"""

from __future__ import annotations

import threading
import time

from src.events.work_queue import WorkQueue
from src.core.logging import setup_logging
from src.workflow.engine import WorkflowEngine

logger = setup_logging(__name__)

# ── Configuración ──────────────────────────────────────────
DEFAULT_NUM_WORKERS = 4
WORKER_HEALTH_INTERVAL = 30  # segundos entre health checks
WORKER_MAX_CONSECUTIVE_FAILURES = 5


class Worker:
    """
    Worker individual que procesa items de la WorkQueue.

    Corre en su propio thread. Procesa un item a la vez.
    Reporta su estado al WorkerManager.
    """

    def __init__(self, worker_id: int, queue: WorkQueue):
        self.worker_id = worker_id
        self._queue = queue
        self._thread: threading.Thread | None = None
        self._running = False
        self._engine = WorkflowEngine()

        # Estado
        self.status = "idle"  # idle, processing, healthy, unhealthy, stopped
        self.current_item_id: int | None = None
        self.items_processed = 0
        self.items_failed = 0
        self.consecutive_failures = 0
        self.total_processing_time_ms = 0
        self.last_heartbeat = time.time()
        self.started_at: float | None = None

    def start(self) -> None:
        """Inicia el worker en un thread daemon."""
        if self._running:
            return
        self._running = True
        self.status = "idle"
        self.started_at = time.time()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"worker-{self.worker_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Worker #{self.worker_id} iniciado")

    def stop(self) -> None:
        """Solicita detención graceful."""
        self._running = False
        self.status = "stopped"
        logger.info(f"Worker #{self.worker_id}: detención solicitada")

    def is_alive(self) -> bool:
        """Verifica si el thread del worker está vivo."""
        return self._thread is not None and self._thread.is_alive()

    def get_health(self) -> dict:
        """Retorna estado de salud del worker."""
        return {
            "worker_id": self.worker_id,
            "status": self.status,
            "alive": self.is_alive(),
            "current_item_id": self.current_item_id,
            "items_processed": self.items_processed,
            "items_failed": self.items_failed,
            "consecutive_failures": self.consecutive_failures,
            "uptime_seconds": int(time.time() - (self.started_at or time.time())),
            "last_heartbeat_ago": int(time.time() - self.last_heartbeat),
        }

    def _run_loop(self) -> None:
        """Loop principal del worker."""
        while self._running:
            try:
                self.status = "idle"
                self.last_heartbeat = time.time()

                # Tomar item de la cola (con timeout)
                item = self._queue.dequeue(timeout=300)
                if item is None:
                    time.sleep(0.5)
                    continue

                # Procesar
                self.status = "processing"
                self.current_item_id = item.id
                self.last_heartbeat = time.time()

                start_time = time.time()
                try:
                    result = self._engine.execute(
                        item.workflow_id,
                        item.trigger_data,
                    )

                    if result.status == "completed":
                        self._queue.ack(item.id)
                        self.items_processed += 1
                        self.consecutive_failures = 0
                    else:
                        self._queue.nack(
                            item.id,
                            error_message=result.error_message or "Workflow failed",
                        )
                        self.items_failed += 1
                        self.consecutive_failures += 1

                    elapsed = int((time.time() - start_time) * 1000)
                    self.total_processing_time_ms += elapsed

                except Exception as e:
                    self._queue.nack(item.id, error_message=str(e))
                    self.items_failed += 1
                    self.consecutive_failures += 1
                    logger.error(f"Worker #{self.worker_id}: error ejecutando #{item.id}: {e}")

                self.current_item_id = None
                self.status = "idle"

            except Exception as e:
                logger.error(f"Worker #{self.worker_id}: error en loop: {e}")
                self.consecutive_failures += 1
                time.sleep(1)

        self.status = "stopped"


class WorkerManager:
    """
    Gestor de workers.

    Administra N workers, monitorea su salud, reinicia workers
    caídos, y provee métricas agregadas.

    Uso:
        mgr = WorkerManager(num_workers=4)
        mgr.start()
        # ...
        stats = mgr.get_metrics()
        mgr.stop()
    """

    def __init__(self, num_workers: int = DEFAULT_NUM_WORKERS, queue: WorkQueue | None = None):
        self._num_workers = num_workers
        self._queue = queue or WorkQueue()
        self._workers: list[Worker] = []
        self._health_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()

    @property
    def queue(self) -> WorkQueue:
        return self._queue

    # ── Start / Stop ──────────────────────────────────────

    def start(self) -> None:
        """Inicia N workers + health checker."""
        if self._running:
            return
        self._running = True

        # Iniciar workers
        for i in range(self._num_workers):
            worker = Worker(worker_id=i + 1, queue=self._queue)
            worker.start()
            self._workers.append(worker)

        # Iniciar health checker
        self._health_thread = threading.Thread(
            target=self._health_loop,
            name="worker-health",
            daemon=True,
        )
        self._health_thread.start()

        logger.info(f"WorkerManager: {self._num_workers} workers iniciados")

    def stop(self) -> None:
        """Detiene todos los workers gracefulmente."""
        self._running = False

        for worker in self._workers:
            worker.stop()

        # Esperar que terminen
        for worker in self._workers:
            if worker._thread and worker._thread.is_alive():
                worker._thread.join(timeout=5)

        logger.info("WorkerManager: todos los workers detenidos")

    # ── Health Check ──────────────────────────────────────

    def _health_loop(self) -> None:
        """Loop de health check: monitorea y reinicia workers."""
        while self._running:
            time.sleep(WORKER_HEALTH_INTERVAL)
            try:
                self._check_workers()
            except Exception as e:
                logger.error(f"WorkerManager: error en health check: {e}")

    def _check_workers(self) -> None:
        """Revisa salud de workers y reinicia los caídos."""
        with self._lock:
            for i, worker in enumerate(self._workers):
                health = worker.get_health()
                needs_restart = False

                # Worker muerto (thread terminado)
                if not health["alive"] and worker.status != "stopped":
                    logger.warning(f"Worker #{worker.worker_id}: thread muerto, reiniciando")
                    needs_restart = True

                # Demasiados fallos consecutivos
                if health["consecutive_failures"] >= WORKER_MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        f"Worker #{worker.worker_id}: {health['consecutive_failures']} fallos consecutivos, reiniciando"
                    )
                    needs_restart = True

                # Heartbeat muy viejo (> 2x health interval)
                if health["last_heartbeat_ago"] > WORKER_HEALTH_INTERVAL * 3:
                    logger.warning(
                        f"Worker #{worker.worker_id}: heartbeat viejo ({health['last_heartbeat_ago']}s), reiniciando"
                    )
                    needs_restart = True

                if needs_restart:
                    self._restart_worker(i)

    def _restart_worker(self, index: int) -> None:
        """Reinicia un worker por índice."""
        old_worker = self._workers[index]
        old_worker.stop()
        if old_worker._thread and old_worker._thread.is_alive():
            old_worker._thread.join(timeout=3)

        new_worker = Worker(worker_id=old_worker.worker_id, queue=self._queue)
        new_worker.start()
        self._workers[index] = new_worker
        logger.info(f"Worker #{new_worker.worker_id} reiniciado")

    # ── Escalamiento dinámico ─────────────────────────────

    def scale(self, num_workers: int) -> int:
        """
        Escala el número de workers.

        Si num_workers > actual, inicia nuevos workers.
        Si num_workers < actual, detiene los extras.

        Args:
            num_workers: Nuevo número de workers

        Returns:
            Número actual de workers después del escalamiento
        """
        with self._lock:
            current = len(self._workers)

            if num_workers > current:
                # Agregar workers
                for i in range(current, num_workers):
                    worker = Worker(worker_id=i + 1, queue=self._queue)
                    worker.start()
                    self._workers.append(worker)
                logger.info(f"WorkerManager: escalado a {num_workers} workers")

            elif num_workers < current:
                # Detener workers extras
                for worker in self._workers[num_workers:]:
                    worker.stop()
                self._workers = self._workers[:num_workers]
                logger.info(f"WorkerManager: reducido a {num_workers} workers")

            return len(self._workers)

    # ── Métricas ──────────────────────────────────────────

    def get_metrics(self) -> dict:
        """
        Retorna métricas agregadas de todos los workers + cola.

        Returns:
            dict con métricas
        """
        queue_metrics = self._queue.get_metrics()

        workers_health = [w.get_health() for w in self._workers]
        total_processed = sum(w.items_processed for w in self._workers)
        total_failed = sum(w.items_failed for w in self._workers)
        alive_count = sum(1 for w in self._workers if w.is_alive())

        avg_processing_time = 0
        if total_processed > 0:
            total_time = sum(w.total_processing_time_ms for w in self._workers)
            avg_processing_time = total_time // total_processed

        return {
            "workers": {
                "total": len(self._workers),
                "alive": alive_count,
                "dead": len(self._workers) - alive_count,
                "processing": sum(1 for h in workers_health if h["status"] == "processing"),
                "idle": sum(1 for h in workers_health if h["status"] == "idle"),
                "total_processed": total_processed,
                "total_failed": total_failed,
                "avg_processing_time_ms": avg_processing_time,
                "details": workers_health,
            },
            "queue": queue_metrics,
        }

    def get_workers_status(self) -> list[dict]:
        """Retorna estado de cada worker."""
        return [w.get_health() for w in self._workers]
