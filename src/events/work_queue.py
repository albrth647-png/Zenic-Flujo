"""
WorkQueue — Cola de ejecución asíncrona de workflows
========================================================

Sprint 7-8 del Roadmap Competitivo.

Backend principal: SQLite (siempre disponible, sin dependencias).
Backend opcional: Redis (redis-py) cuando está disponible y configurado.

La cola soporta:
- Enqueue: agregar workflow a la cola
- Dequeue: tomar un workflow para procesar (con timeout)
- Ack: marcar como completado
- Nack: marcar como fallido (re-encolar si retry_count < max)
- Peek: ver el siguiente sin desencolar
- Metrics: queue depth, processing time, error rate
- Retry: re-encolar con backoff
"""

from __future__ import annotations

import json
import time
import threading
from datetime import datetime

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Configuración ──────────────────────────────────────────
DEFAULT_MAX_RETRIES = 3
DEFAULT_CLAIM_TIMEOUT = 300  # 5 minutos para procesar
MAX_QUEUE_SIZE = 10000


class WorkQueueItem:
    """Un item en la cola de trabajo."""

    def __init__(self, id: int | None = None,
                 workflow_id: int = 0,
                 trigger_data: dict | None = None,
                 priority: int = 0,
                 status: str = "queued",
                 retry_count: int = 0,
                 max_retries: int = DEFAULT_MAX_RETRIES,
                 claimed_at: float | None = None,
                 created_at: str | None = None,
                 scheduled_at: str | None = None,
                 error_message: str | None = None):
        self.id = id
        self.workflow_id = workflow_id
        self.trigger_data = trigger_data or {}
        self.priority = priority
        self.status = status  # queued, processing, completed, failed
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.claimed_at = claimed_at
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.scheduled_at = scheduled_at
        self.error_message = error_message

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "trigger_data": self.trigger_data,
            "priority": self.priority,
            "status": self.status,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "claimed_at": self.claimed_at,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "error_message": self.error_message,
        }


class WorkQueue:
    """
    Cola de ejecución de workflows.

    Backend primario: SQLite (tabla work_queue).
    Backend secundario: Redis (cuando redis-py está disponible).

    Thread-safe mediante RLock para operaciones críticas.
    """

    def __init__(self, use_redis: bool = False,
                 redis_host: str = "localhost",
                 redis_port: int = 6379,
                 redis_db: int = 0):
        self._db = DatabaseManager()
        self._use_redis = use_redis
        self._redis = None
        self._lock = threading.RLock()

        # Inicializar Redis si está disponible
        if use_redis:
            self._init_redis(redis_host, redis_port, redis_db)

        # Asegurar que la tabla existe
        self._ensure_table()

        # Métricas
        self._metrics = {
            "total_enqueued": 0,
            "total_processed": 0,
            "total_failed": 0,
            "total_retried": 0,
            "total_processing_time_ms": 0,
            "started_at": time.time(),
            "peak_depth": 0,
        }

    def _init_redis(self, host: str, port: int, db: int) -> None:
        """Intenta inicializar Redis."""
        try:
            import redis as redis_module
            self._redis = redis_module.Redis(
                host=host, port=port, db=db,
                socket_timeout=5,
                decode_responses=True,
            )
            self._redis.ping()
            logger.info("WorkQueue: Redis conectado")
        except ImportError:
            logger.warning("WorkQueue: redis-py no instalado, usando SQLite")
            self._use_redis = False
        except Exception as e:
            logger.warning(f"WorkQueue: Redis no disponible ({e}), usando SQLite")
            self._use_redis = False

    def _ensure_table(self) -> None:
        """Crea la tabla work_queue si no existe."""
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS work_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id     INTEGER NOT NULL,
                trigger_data    TEXT NOT NULL DEFAULT '{}',
                priority        INTEGER DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'queued',
                retry_count     INTEGER DEFAULT 0,
                max_retries     INTEGER DEFAULT 3,
                claimed_at      REAL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scheduled_at    TIMESTAMP,
                error_message   TEXT
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_wq_status ON work_queue(status)
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_wq_priority ON work_queue(priority, created_at)
        """)
        self._db.commit()

    # ── Enqueue ────────────────────────────────────────────

    def enqueue(self, workflow_id: int,
                trigger_data: dict | None = None,
                priority: int = 0,
                max_retries: int = DEFAULT_MAX_RETRIES,
                scheduled_at: str | None = None) -> WorkQueueItem:
        """
        Agrega un workflow a la cola de ejecución.

        Args:
            workflow_id: ID del workflow a ejecutar
            trigger_data: Datos de entrada
            priority: Prioridad (mayor = más prioritario)
            max_retries: Máximo de reintentos en caso de fallo
            scheduled_at: Fecha ISO para ejecución programada

        Returns:
            WorkQueueItem con los datos encolados

        Raises:
            ValueError: Si la cola está llena
        """
        with self._lock:
            # Verificar límite
            current_depth = self._count_by_status("queued")
            if current_depth >= MAX_QUEUE_SIZE:
                raise ValueError(
                    f"Cola llena ({MAX_QUEUE_SIZE} items). "
                    "Espera a que los workers procesen."
                )

            if self._use_redis and self._redis:
                return self._redis_enqueue(workflow_id, trigger_data,
                                           priority, max_retries, scheduled_at)
            return self._sqlite_enqueue(workflow_id, trigger_data,
                                        priority, max_retries, scheduled_at)

    def _sqlite_enqueue(self, workflow_id: int,
                         trigger_data: dict | None,
                         priority: int, max_retries: int,
                         scheduled_at: str | None) -> WorkQueueItem:
        """Enqueue usando SQLite."""
        cursor = self._db.execute(
            """INSERT INTO work_queue
               (workflow_id, trigger_data, priority, status, max_retries, scheduled_at)
               VALUES (?, ?, ?, 'queued', ?, ?)""",
            (workflow_id, json.dumps(trigger_data or {}),
             priority, max_retries, scheduled_at),
        )
        self._db.commit()
        item_id = cursor.lastrowid

        with self._lock:
            self._metrics["total_enqueued"] += 1
            depth = self._count_by_status("queued")
            self._metrics["peak_depth"] = max(self._metrics["peak_depth"], depth)

        logger.info(f"WorkQueue: encolado workflow {workflow_id} (#{item_id})")
        return WorkQueueItem(
            id=item_id, workflow_id=workflow_id,
            trigger_data=trigger_data, priority=priority,
            max_retries=max_retries, status="queued",
            scheduled_at=scheduled_at,
        )

    def _redis_enqueue(self, workflow_id: int,
                        trigger_data: dict | None,
                        priority: int, max_retries: int,
                        scheduled_at: str | None) -> WorkQueueItem:
        """Enqueue usando Redis."""
        item = {
            "workflow_id": workflow_id,
            "trigger_data": trigger_data or {},
            "priority": priority,
            "max_retries": max_retries,
            "scheduled_at": scheduled_at,
            "enqueued_at": time.time(),
        }
        # Usar sorted set con priority como score
        import secrets
        item_id = secrets.token_hex(8)
        self._redis.zadd("work_queue", {json.dumps(item): -priority})
        self._redis.lpush("work_queue:pending", item_id)
        self._metrics["total_enqueued"] += 1
        logger.info(f"WorkQueue (Redis): encolado workflow {workflow_id}")
        return WorkQueueItem(
            id=hash(item_id) % 1000000, workflow_id=workflow_id,
            trigger_data=trigger_data, priority=priority,
            max_retries=max_retries, status="queued",
            scheduled_at=scheduled_at,
        )

    # ── Dequeue ────────────────────────────────────────────

    def dequeue(self, timeout: int = DEFAULT_CLAIM_TIMEOUT) -> WorkQueueItem | None:
        """
        Toma el siguiente item de la cola para procesar.

        Args:
            timeout: Tiempo máximo para procesar (claim timeout)

        Returns:
            WorkQueueItem o None si no hay items
        """
        with self._lock:
            if self._use_redis and self._redis:
                return self._redis_dequeue(timeout)
            return self._sqlite_dequeue(timeout)

    def _sqlite_dequeue(self, timeout: int) -> WorkQueueItem | None:
        """Dequeue usando SQLite con claim timeout."""
        now = time.time()

        # Buscar item no reclamado, ordenado por prioridad descendente
        row = self._db.fetchone(
            """SELECT * FROM work_queue
               WHERE status = 'queued'
               AND (scheduled_at IS NULL OR scheduled_at <= datetime('now'))
               ORDER BY priority DESC, created_at ASC
               LIMIT 1"""
        )

        if not row:
            return None

        # Reclamar el item
        item_id = row["id"]
        self._db.execute(
            "UPDATE work_queue SET status = 'processing', claimed_at = ? WHERE id = ?",
            (now, item_id),
        )
        self._db.commit()

        logger.info(f"WorkQueue: item #{item_id} reclamado para procesar")
        # Retornar item con status actualizado para reflejar la DB
        item = self._row_to_item(row)
        item.status = "processing"
        return item

    def _redis_dequeue(self, timeout: int) -> WorkQueueItem | None:
        """Dequeue usando Redis."""
        import json as json_module

        # Pop de la lista de pendientes con bloqueo
        result = self._redis.brpop("work_queue:processing", timeout=1)
        if not result:
            return None

        # Obtener el item más prioritario
        items = self._redis.zpopmin("work_queue", count=1)
        if not items:
            return None

        item_json, score = items[0]
        data = json_module.loads(item_json)
        return WorkQueueItem(
            id=hash(item_json) % 1000000,
            workflow_id=data["workflow_id"],
            trigger_data=data.get("trigger_data", {}),
            priority=-score,
            max_retries=data.get("max_retries", DEFAULT_MAX_RETRIES),
            status="processing",
        )

    # ── Ack / Nack ────────────────────────────────────────

    def ack(self, item_id: int) -> bool:
        """
        Marca un item como completado exitosamente.

        Args:
            item_id: ID del item

        Returns:
            True si se marcó, False si no existe
        """
        with self._lock:
            row = self._db.fetchone(
                "SELECT * FROM work_queue WHERE id = ?", (item_id,)
            )
            if not row:
                return False

            processing_time = None
            if row.get("claimed_at"):
                processing_time = int((time.time() - row["claimed_at"]) * 1000)

            self._db.execute(
                "UPDATE work_queue SET status = 'completed', error_message = NULL WHERE id = ?",
                (item_id,),
            )
            self._db.commit()

            self._metrics["total_processed"] += 1
            if processing_time:
                self._metrics["total_processing_time_ms"] += processing_time

            logger.info(f"WorkQueue: item #{item_id} completado")
            return True

    def nack(self, item_id: int, error_message: str = "",
             requeue: bool = True) -> bool:
        """
        Marca un item como fallido.

        Args:
            item_id: ID del item
            error_message: Mensaje de error
            requeue: Si True, re-encola si retry_count < max_retries

        Returns:
            True si se procesó, False si no existe
        """
        with self._lock:
            row = self._db.fetchone(
                "SELECT * FROM work_queue WHERE id = ?", (item_id,)
            )
            if not row:
                return False

            retry_count = row.get("retry_count", 0) + 1
            max_retries = row.get("max_retries", DEFAULT_MAX_RETRIES)

            if requeue and retry_count < max_retries:
                # Re-encolar con backoff: cada reintento espera más
                backoff_seconds = min(60 * (2 ** (retry_count - 1)), 3600)
                from datetime import datetime, timedelta
                scheduled = (datetime.utcnow() + timedelta(seconds=backoff_seconds)).isoformat()

                self._db.execute(
                    """UPDATE work_queue
                       SET status = 'queued', retry_count = ?,
                           error_message = ?, claimed_at = NULL,
                           scheduled_at = ?
                       WHERE id = ?""",
                    (retry_count, error_message, scheduled, item_id),
                )
                self._metrics["total_retried"] += 1
                logger.info(
                    f"WorkQueue: item #{item_id} re-encolado "
                    f"(intento {retry_count}/{max_retries}, "
                    f"backoff {backoff_seconds}s)"
                )
            else:
                self._db.execute(
                    """UPDATE work_queue
                       SET status = 'failed', retry_count = ?,
                           error_message = ?
                       WHERE id = ?""",
                    (retry_count, error_message, item_id),
                )
                self._metrics["total_failed"] += 1
                logger.warning(
                    f"WorkQueue: item #{item_id} falló definitivamente "
                    f"después de {retry_count} intentos"
                )

            self._db.commit()
            return True

    # ── Peek ──────────────────────────────────────────────

    def peek(self, limit: int = 10) -> list[WorkQueueItem]:
        """
        Mira los próximos items sin desencolarlos.

        Args:
            limit: Máximo de items

        Returns:
            Lista de WorkQueueItem
        """
        rows = self._db.fetchall(
            """SELECT * FROM work_queue
               WHERE status = 'queued'
               ORDER BY priority DESC, created_at ASC
               LIMIT ?""",
            (limit,),
        )
        return [self._row_to_item(r) for r in rows]

    # ── Métricas ──────────────────────────────────────────

    def get_metrics(self) -> dict:
        """
        Retorna métricas de la cola.

        Returns:
            dict con métricas
        """
        with self._lock:
            queued = self._count_by_status("queued")
            processing = self._count_by_status("processing")
            completed = self._count_by_status("completed")
            failed = self._count_by_status("failed")

            avg_processing_time = 0
            if self._metrics["total_processed"] > 0:
                avg_processing_time = (
                    self._metrics["total_processing_time_ms"] //
                    self._metrics["total_processed"]
                )

            return {
                "depth": {
                    "queued": queued,
                    "processing": processing,
                    "completed": completed,
                    "failed": failed,
                    "total": queued + processing + completed + failed,
                },
                "throughput": {
                    "total_enqueued": self._metrics["total_enqueued"],
                    "total_processed": self._metrics["total_processed"],
                    "total_failed": self._metrics["total_failed"],
                    "total_retried": self._metrics["total_retried"],
                },
                "performance": {
                    "avg_processing_time_ms": avg_processing_time,
                    "peak_depth": self._metrics["peak_depth"],
                    "uptime_seconds": int(time.time() - self._metrics["started_at"]),
                },
                "backend": "redis" if self._use_redis else "sqlite",
            }

    # ── Limpieza ──────────────────────────────────────────

    def cleanup(self, max_age_hours: int = 24) -> int:
        """
        Limpia items completados/failed viejos.

        Args:
            max_age_hours: Edad máxima en horas

        Returns:
            Número de items eliminados
        """
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()

        self._db.execute(
            """DELETE FROM work_queue
               WHERE status IN ('completed', 'failed')
               AND created_at < ?""",
            (cutoff,),
        )
        self._db.commit()
        deleted = self._db.fetchone("SELECT changes() as c")
        count = deleted["c"] if deleted else 0
        if count > 0:
            logger.info(f"WorkQueue: cleanup eliminó {count} items viejos")
        return count

    def retry_failed(self, max_items: int = 10) -> int:
        """
        Re-intenta items fallidos.

        Args:
            max_items: Máximo a reintentar

        Returns:
            Número de items re-encolados
        """
        rows = self._db.fetchall(
            """SELECT * FROM work_queue
               WHERE status = 'failed'
               ORDER BY created_at DESC
               LIMIT ?""",
            (max_items,),
        )
        count = 0
        for row in rows:
            self._db.execute(
                """UPDATE work_queue
                   SET status = 'queued', retry_count = 0,
                       error_message = NULL, claimed_at = NULL,
                       scheduled_at = NULL
                   WHERE id = ?""",
                (row["id"],),
            )
            count += 1
        if count > 0:
            self._db.commit()
            logger.info(f"WorkQueue: {count} items fallidos re-encolados")
        return count

    # ── Helpers ───────────────────────────────────────────

    def _count_by_status(self, status: str) -> int:
        """Cuenta items por estado."""
        row = self._db.fetchone(
            "SELECT COUNT(*) as c FROM work_queue WHERE status = ?",
            (status,),
        )
        return row["c"] if row else 0

    @staticmethod
    def _row_to_item(row: dict) -> WorkQueueItem:
        """Convierte una fila SQL a WorkQueueItem."""
        return WorkQueueItem(
            id=row["id"],
            workflow_id=row["workflow_id"],
            trigger_data=json.loads(row.get("trigger_data", "{}")),
            priority=row.get("priority", 0),
            status=row.get("status", "queued"),
            retry_count=row.get("retry_count", 0),
            max_retries=row.get("max_retries", DEFAULT_MAX_RETRIES),
            claimed_at=row.get("claimed_at"),
            created_at=row.get("created_at"),
            scheduled_at=row.get("scheduled_at"),
            error_message=row.get("error_message"),
        )
