"""
Zenic-Flijo — WorkflowSubscriber
==================================

Suscriptor de workflows que escucha eventos del EventBus y ejecuta
workflows suscritos.

Extraído de EventBus (src/events/bus.py) para separar responsabilidades.

Responsabilidades:
- Gestionar suscripciones DB (event_subscriptions)
- Ejecutar workflows cuando ocurre un evento
- Actualizar estado de eventos en EventQueueService
- Listar suscriptores por tipo de evento
"""

from __future__ import annotations

import threading

from src.core.db import DatabaseManager
from src.events.bus import EventBus
from src.events.queue_service import EventQueueService
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class WorkflowSubscriber:
    """
    Suscriptor de workflows para EventBus.

    Se registra como handler global en EventBus (via set_global_handler)
    y, cuando ocurre un evento, busca workflows suscritos a ese tipo
    de evento y los ejecuta.

    Responsabilidades:
    - Gestionar suscripciones DB (event_subscriptions)
    - Ejecutar workflows cuando ocurre un evento
    - Actualizar estado de eventos en EventQueueService
    - Listar suscriptores por tipo de evento
    """

    def __init__(
        self,
        event_bus: EventBus,
        event_queue: EventQueueService,
        workflow_engine: object | None = None,
    ):
        """
        Args:
            event_bus: Instancia de EventBus. Se registra como handler global.
            event_queue: Servicio de persistencia de eventos.
            workflow_engine: Instancia de WorkflowEngine (opcional, lazy import).
        """
        self._event_bus = event_bus
        # Usar misma DB que event_queue si está disponible, o crear nueva
        self._db = getattr(event_queue, '_db', DatabaseManager())
        self._queue = event_queue
        self._engine = workflow_engine
        self._lock = threading.RLock()

        # Últimos resultados (para tests y orquestación)
        self.last_results: list[dict] = []

        # Registrar como handler global de EventBus
        # _on_event recibe TODOS los eventos publicados
        self._event_bus.set_global_handler(self._on_event)

    # ── Gestión de suscripciones DB ──────────────────────────

    def subscribe(self, event_type: str, workflow_id: int) -> None:
        """
        Registra que workflow_id debe ejecutarse cuando ocurra event_type.
        Es idempotente: si ya existe la suscripción, no hace nada.

        Args:
            event_type: Tipo de evento (ej. 'crm.lead.created')
            workflow_id: ID del workflow a ejecutar
        """
        # Verificar si ya existe la suscripción (idempotente)
        existing = self._db.fetchone(
            "SELECT id FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            (event_type, workflow_id),
        )
        if existing:
            logger.debug(
                f"WorkflowSubscriber: workflow {workflow_id} ya está "
                f"suscrito a evento '{event_type}', omitiendo"
            )
            return

        self._db.execute(
            "INSERT INTO event_subscriptions (event_type, workflow_id) VALUES (?, ?)",
            (event_type, workflow_id),
        )
        self._db.commit()
        logger.debug(f"WorkflowSubscriber: workflow {workflow_id} suscrito a evento '{event_type}'")

    def unsubscribe(self, event_type: str, workflow_id: int) -> None:
        """
        Elimina la suscripción de un workflow a un evento.

        Args:
            event_type: Tipo de evento
            workflow_id: ID del workflow
        """
        self._db.execute(
            "DELETE FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            (event_type, workflow_id),
        )
        self._db.commit()
        logger.debug(f"WorkflowSubscriber: workflow {workflow_id} desuscrito de evento '{event_type}'")

    def unsubscribe_all(self, workflow_id: int) -> None:
        """
        Elimina todas las suscripciones de un workflow.

        Args:
            workflow_id: ID del workflow
        """
        self._db.execute(
            "DELETE FROM event_subscriptions WHERE workflow_id = ?",
            (workflow_id,),
        )
        self._db.commit()
        logger.debug(f"WorkflowSubscriber: todas las suscripciones del workflow {workflow_id} eliminadas")

    def list_subscribers(self, event_type: str) -> list[dict]:
        """
        Retorna los workflows suscritos a un tipo de evento.

        Args:
            event_type: Tipo de evento

        Returns:
            Lista de dicts con id, status, name de workflows activos
        """
        return self._db.fetchall(
            """SELECT wf.id, wf.status, wf.name
               FROM event_subscriptions es
               JOIN workflow_definitions wf ON es.workflow_id = wf.id
               WHERE es.event_type = ?""",
            (event_type,),
        )

    # ── Ejecución de workflows ──────────────────────────────

    def _execute_workflow(self, workflow_id: int, data: dict) -> dict:
        """
        Ejecuta un workflow por su ID.

        Args:
            workflow_id: ID del workflow a ejecutar
            data: Datos de entrada para el workflow

        Returns:
            Dict con resultado de la ejecución
        """
        try:
            if self._engine:
                engine = self._engine
            else:
                from src.workflow.engine import WorkflowEngine

                engine = WorkflowEngine()

            result = engine.execute(workflow_id, data)
            return {
                "workflow_id": workflow_id,
                "status": result.status,
                "execution_id": result.execution_id,
                "duration_ms": result.duration_ms,
            }
        except Exception as e:
            logger.error(f"WorkflowSubscriber: error ejecutando workflow {workflow_id}: {e}")
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
            }

    # ── Manejo de eventos ───────────────────────────────────

    def handle_event(self, event_type: str, data: dict, event_id: int | None = None) -> list[dict]:
        """
        Procesa un evento: busca suscriptores y ejecuta workflows.

        Llamado por EventBus.publish() después de guardar el evento
        y disparar handlers en memoria.

        Args:
            event_type: Tipo de evento publicado
            data: Datos del evento
            event_id: ID del evento en la cola (para actualizar estado)

        Returns:
            Lista de resultados de ejecución de workflows
        """
        with self._lock:
            results: list[dict] = []

            # Buscar workflows suscritos
            subscribers = self.list_subscribers(event_type)

            for sub in subscribers:
                if sub["status"] != "active":
                    logger.debug(
                        f"WorkflowSubscriber: workflow {sub['id']} ({sub['name']}) "
                        f"no activo (status={sub['status']}), saltando"
                    )
                    continue

                result = self._execute_workflow(sub["id"], data)
                results.append(result)

                # Actualizar estado del evento en la cola
                if event_id is not None:
                    new_status = "completed" if result.get("status") == "completed" else "failed"
                    self._queue.update_status(event_id, new_status)

            if not subscribers:
                logger.debug(
                    f"WorkflowSubscriber: evento '{event_type}' publicado "
                    f"sin suscriptores activos"
                )
                if event_id is not None:
                    self._queue.update_status(event_id, "pending")

            self.last_results = results
            return results

    # ── Handler registrado en EventBus ────────────────────

    def _on_event(self, event_type: str, data: dict) -> None:
        """
        Handler registrado como global en EventBus.
        Recibe TODOS los eventos publicados y los procesa.

        Args:
            event_type: Tipo de evento publicado
            data: Datos del evento
        """
        self.handle_event(event_type, data)

    # ── Registro de suscripciones DB en EventBus ────────────

    def register_all_db_subscriptions(self) -> int:
        """
        Lee todas las suscripciones de la DB y registra handlers
        específicos en EventBus para cada event_type único.

        Esto optimiza el dispatch: los eventos con suscriptores DB
        se manejan directamente en lugar de solo via global handler.

        Returns:
            Número de event_types únicos registrados
        """
        rows = self._db.fetchall(
            "SELECT DISTINCT event_type FROM event_subscriptions"
        )
        count = 0
        for row in rows:
            event_type = row["event_type"]
            # Registrar handler específico para este event_type
            # Usamos closure para capturar event_type
            def make_handler(et: str):
                return lambda data: self._on_event(et, data)
            self._event_bus.subscribe(event_type, make_handler(event_type))
            count += 1
            logger.debug(
                f"WorkflowSubscriber: handler registrado en EventBus "
                f"para evento '{event_type}'"
            )

        if count > 0:
            logger.info(f"WorkflowSubscriber: {count} handler(s) registrado(s) "
                        f"desde suscripciones DB")

        return count
