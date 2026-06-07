"""
Workflow Determinista — EventBus
Sistema de mensajería interno pub/sub persistente.
Los eventos se guardan en SQLite por si el sistema se apaga.
"""
import json
import threading
from typing import Any, Callable

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class EventBus:
    """
    Sistema de mensajería pub/sub con persistencia en SQLite.
    
    - subscribe(event_type, workflow_id): Registra workflow para evento
    - unsubscribe(event_type, workflow_id): Elimina suscripción
    - publish(event_type, data): Publica evento, ejecuta workflows suscritos
    """

    _instance: "EventBus | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self._db = DatabaseManager()
        self._handlers: dict[str, list[Callable]] = {}
        self._local_events: list[dict] = []

    # ── Suscripciones ───────────────────────────────────────

    def subscribe(self, event_type: str, workflow_id: int) -> None:
        """Registra que workflow_id debe ejecutarse cuando ocurra event_type."""
        self._db.execute(
            "INSERT OR IGNORE INTO event_subscriptions (event_type, workflow_id) VALUES (?, ?)",
            (event_type, workflow_id),
        )
        self._db.commit()
        logger.debug(f"Workflow {workflow_id} suscrito a evento '{event_type}'")

    def unsubscribe(self, event_type: str, workflow_id: int) -> None:
        """Elimina la suscripción de un workflow a un evento."""
        self._db.execute(
            "DELETE FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            (event_type, workflow_id),
        )
        self._db.commit()
        logger.debug(f"Workflow {workflow_id} desuscrito de evento '{event_type}'")

    def unsubscribe_all(self, workflow_id: int) -> None:
        """Elimina todas las suscripciones de un workflow."""
        self._db.execute(
            "DELETE FROM event_subscriptions WHERE workflow_id = ?",
            (workflow_id,),
        )
        self._db.commit()
        logger.debug(f"Todas las suscripciones del workflow {workflow_id} eliminadas")

    def add_handler(self, event_type: str, handler: Callable) -> None:
        """Registra un handler en memoria para un tipo de evento."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def remove_handler(self, event_type: str, handler: Callable) -> None:
        """Elimina un handler registrado."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    # ── Publicación ─────────────────────────────────────────

    def publish(self, event_type: str, data: dict) -> list[dict]:
        """
        Publica un evento en el bus.
        
        1. Guarda el evento en SQLite
        2. Busca workflows suscritos al tipo de evento
        3. Ejecuta handlers en memoria
        4. Ejecuta workflows suscritos vía WorkflowEngine
        
        Returns:
            Lista de resultados de ejecución
        """
        results = []

        # 1. Guardar en cola persistente
        event_id = self._save_to_queue(event_type, data)

        # 2. Ejecutar handlers en memoria
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(f"Error en handler para evento '{event_type}': {e}")

        # 3. Buscar workflows suscritos
        subscribers = self._db.fetchall(
            """SELECT wf.id, wf.status, wf.name 
               FROM event_subscriptions es
               JOIN workflow_definitions wf ON es.workflow_id = wf.id
               WHERE es.event_type = ?""",
            (event_type,),
        )

        for sub in subscribers:
            if sub["status"] != "active":
                logger.debug(f"Workflow {sub['id']} ({sub['name']}) no está activo, saltando")
                continue

            result = self._execute_workflow(sub["id"], data)
            results.append(result)

            # Actualizar estado del evento
            self._update_queue_status(event_id, "completed" if result.get("status") == "completed" else "failed")

        if not subscribers:
            # Marcar como pendiente para procesar después
            logger.debug(f"Evento '{event_type}' publicado sin suscriptores activos")
            self._update_queue_status(event_id, "pending")

        # 4. Registrar auditoría
        self._db.audit("eventbus.published", f"Evento '{event_type}' publicado con {len(subscribers)} suscriptores")

        return results

    def _save_to_queue(self, event_type: str, data: dict) -> int:
        """Guarda un evento en la cola persistente."""
        cursor = self._db.execute(
            "INSERT INTO event_queue (event_type, event_data, status) VALUES (?, ?, 'pending')",
            (event_type, json.dumps(data)),
        )
        self._db.commit()
        return cursor.lastrowid

    def _update_queue_status(self, event_id: int, status: str) -> None:
        """Actualiza el estado de un evento en la cola."""
        self._db.execute(
            "UPDATE event_queue SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, event_id),
        )
        self._db.commit()

    def _execute_workflow(self, workflow_id: int, data: dict) -> dict:
        """Ejecuta un workflow en respuesta a un evento."""
        try:
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
            logger.error(f"Error ejecutando workflow {workflow_id} para evento: {e}")
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "error": str(e),
            }

    # ── Eventos del sistema ─────────────────────────────────

    def get_system_events(self) -> list[dict]:
        """Retorna la lista de eventos del sistema predefinidos."""
        return [
            {"event": "system.started", "description": "Al iniciar el sistema"},
            {"event": "workflow.completed", "description": "Workflow termina OK"},
            {"event": "workflow.failed", "description": "Workflow falla"},
            {"event": "crm.lead.created", "description": "Nuevo lead en CRM"},
            {"event": "crm.lead.stage_changed", "description": "Lead cambia de etapa"},
            {"event": "invoice.created", "description": "Nueva factura"},
            {"event": "invoice.paid", "description": "Factura pagada"},
            {"event": "invoice.overdue", "description": "Factura vencida"},
            {"event": "inventory.stock_low", "description": "Stock bajo umbral"},
            {"event": "inventory.stock_out", "description": "Stock en cero"},
            {"event": "file.created", "description": "Nuevo archivo en carpeta"},
            {"event": "file.modified", "description": "Archivo modificado"},
            {"event": "schedule.triggered", "description": "Cron job ejecutado"},
            {"event": "webhook.received", "description": "Webhook HTTP recibido"},
            {"event": "email.received", "description": "Correo electrónico recibido (IMAP)"},
        ]

    # ── Recuperación ────────────────────────────────────────

    def get_pending_events(self) -> list[dict]:
        """Retorna eventos no procesados (útil al iniciar el sistema)."""
        return self._db.fetchall(
            "SELECT * FROM event_queue WHERE status = 'pending' ORDER BY created_at"
        )

    def reprocess_pending(self) -> int:
        """Reintenta procesar eventos pendientes. Retorna cantidad procesada."""
        pending = self.get_pending_events()
        count = 0
        for event in pending:
            try:
                event_data = json.loads(event["event_data"])
                # Mark original as processing to avoid duplicate on re-publish
                self._update_queue_status(event["id"], "processing")
                self.publish(event["event_type"], event_data)
                count += 1
            except Exception as e:
                logger.error(f"Error reprocesando evento {event['id']}: {e}")
                self._update_queue_status(event["id"], "failed")
        return count
