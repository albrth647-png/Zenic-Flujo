"""
Zenic-Flijo — EventQueueService
=================================

Servicio independiente para la persistencia y reprocesamiento de eventos
en la tabla event_queue.

Extraído de EventBus (src/events/bus.py) para separar responsabilidades.

Responsabilidades:
- Persistir eventos en la cola SQLite (event_queue)
- Actualizar estado de eventos
- Listar eventos pendientes y fallidos
- Reprocesar eventos pendientes/fallidos
- Limpieza de eventos viejos
"""

from __future__ import annotations

import json
from typing import Any

from src.core.db import DatabaseManager
from src.core.logging import setup_logging

logger = setup_logging(__name__)


def _json_default(obj: object) -> str:
    """Serializa objetos no estándar a JSON (ej. datetime)."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class EventQueueService:
    """
    Servicio de persistencia para la cola de eventos (event_queue).

    Gestiona el ciclo de vida de eventos en la tabla unificada event_queue:
    - save: inserta un nuevo evento en la cola
    - update_status: actualiza el estado de un evento existente
    - list_pending: recupera eventos pendientes
    - list_failed: recupera eventos fallidos
    - reprocess_pending: re-publica eventos pendientes
    - reprocess_failed: re-publica eventos fallidos
    - cleanup: elimina eventos completados/fallidos viejos
    - count_by_status: cuenta eventos por estado

    No debe contener lógica de negocio (workflows, handlers, orbital).
    Solo persistencia y estado de la cola.
    """

    def __init__(self, db: DatabaseManager | None = None):
        """
        Args:
            db: Instancia de DatabaseManager. Si es None, usa el singleton.
        """
        self._db = db or DatabaseManager()

    # ── Persistencia básica ─────────────────────────────────

    def save(self, event_type: str, data: dict[str, Any] | str) -> int:
        """
        Guarda un evento en la cola persistente.

        Args:
            event_type: Tipo de evento (ej. 'crm.lead.created')
            data: Datos del evento (dict o str JSON)

        Returns:
            ID del evento creado (lastrowid)
        """
        event_data = json.dumps(data, default=_json_default) if isinstance(data, dict) else data
        cursor = self._db.execute(
            "INSERT INTO event_queue (event_type, event_data, status) VALUES (?, ?, 'pending')",
            (event_type, event_data),
        )
        self._db.commit()
        return cursor.lastrowid

    def update_status(self, event_id: int, status: str) -> None:
        """
        Actualiza el estado de un evento en la cola.

        Args:
            event_id: ID del evento
            status: Nuevo estado ('pending', 'processing', 'completed', 'failed')
        """
        self._db.execute(
            "UPDATE event_queue SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, event_id),
        )
        self._db.commit()

    # ── Consultas ──────────────────────────────────────────

    def list_pending(self, limit: int = 100) -> list[dict]:
        """
        Retorna eventos pendientes ordenados por creación.

        Args:
            limit: Máximo de eventos a retornar

        Returns:
            Lista de dicts con los eventos
        """
        return self._db.fetchall(
            "SELECT * FROM event_queue WHERE status = 'pending' ORDER BY created_at LIMIT ?",
            (limit,),
        )

    def list_failed(self, limit: int = 100) -> list[dict]:
        """
        Retorna eventos fallidos ordenados por creación.

        Args:
            limit: Máximo de eventos a retornar

        Returns:
            Lista de dicts con los eventos
        """
        return self._db.fetchall(
            "SELECT * FROM event_queue WHERE status = 'failed' ORDER BY created_at LIMIT ?",
            (limit,),
        )

    def list_by_type(self, event_type: str, limit: int = 50) -> list[dict]:
        """
        Retorna eventos de un tipo específico.

        Args:
            event_type: Tipo de evento
            limit: Máximo de eventos

        Returns:
            Lista de dicts con los eventos
        """
        return self._db.fetchall(
            "SELECT * FROM event_queue WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
            (event_type, limit),
        )

    def get(self, event_id: int) -> dict[str, Any] | None:
        """
        Obtiene un evento por ID.

        Args:
            event_id: ID del evento

        Returns:
            Dict con el evento o None si no existe
        """
        return self._db.fetchone("SELECT * FROM event_queue WHERE id = ?", (event_id,))

    def count_by_status(self, status: str) -> int:
        """
        Cuenta eventos por estado.

        Args:
            status: Estado a contar

        Returns:
            Número de eventos con ese estado
        """
        row = self._db.fetchone(
            "SELECT COUNT(*) as c FROM event_queue WHERE status = ?",
            (status,),
        )
        return row["c"] if row else 0

    def get_stats(self) -> dict[str, Any]:
        """
        Retorna estadísticas de la cola de eventos.

        Returns:
            Dict con pending, processing, completed, failed, total
        """
        pending = self.count_by_status("pending")
        processing = self.count_by_status("processing")
        completed = self.count_by_status("completed")
        failed = self.count_by_status("failed")

        return {
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "total": pending + processing + completed + failed,
        }

    # ── Reprocesamiento ────────────────────────────────────

    # legítimo: callback de publish dinámico (skill §1.2)
    def reprocess_pending(self, publish_fn: Any = None) -> int:
        """
        Reprocesa eventos pendientes.

        Si se proporciona publish_fn, lo llama para cada evento.
        Si no, solo marca cada evento como 'processing' (para reprocesamiento externo).

        Args:
            publish_fn: Función opcional publish(event_type, data) para re-publicar

        Returns:
            Número de eventos reprocesados
        """
        pending = self.list_pending()
        count = 0

        for event in pending:
            event_id = event["id"]
            event_type = event["event_type"]

            try:
                event_data = json.loads(event["event_data"])
                self.update_status(event_id, "processing")

                if publish_fn:
                    publish_fn(event_type, event_data)

                self.update_status(event_id, "completed")
                count += 1

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"EventQueue: error reprocesando evento {event_id}: {e}")
                self.update_status(event_id, "failed")

        return count

    # legítimo: callback de publish dinámico (skill §1.2)
    def reprocess_failed(self, publish_fn: Any = None) -> int:
        """
        Reprocesa eventos fallidos.

        Args:
            publish_fn: Función opcional publish(event_type, data) para re-publicar

        Returns:
            Número de eventos reprocesados
        """
        failed = self.list_failed()
        count = 0

        for event in failed:
            event_id = event["id"]
            event_type = event["event_type"]

            try:
                event_data = json.loads(event["event_data"])
                self.update_status(event_id, "processing")

                if publish_fn:
                    publish_fn(event_type, event_data)

                self.update_status(event_id, "completed")
                count += 1

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"EventQueue: error reprocesando evento fallido {event_id}: {e}")

        return count

    # ── Limpieza ──────────────────────────────────────────

    def cleanup(self, max_age_hours: int = 24) -> int:
        """
        Elimina eventos completados/fallidos más viejos que max_age_hours.

        Args:
            max_age_hours: Edad máxima en horas (default: 24)

        Returns:
            Número de eventos eliminados
        """
        from datetime import datetime, timedelta

        cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()

        self._db.execute(
            """DELETE FROM event_queue
               WHERE status IN ('completed', 'failed')
               AND created_at < ?""",
            (cutoff,),
        )
        self._db.commit()

        deleted = self._db.fetchone("SELECT changes() as c")
        count = deleted["c"] if deleted else 0

        if count > 0:
            logger.info(f"EventQueue: cleanup eliminó {count} eventos viejos")

        return count
