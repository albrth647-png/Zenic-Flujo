"""
Workflow Determinista — DatabaseTrigger
Detecta cambios en tablas SQLite y emite eventos correspondientes.
"""

from typing import ClassVar

from src.core.db import DatabaseManager
from src.events.bus import EventBus
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class DatabaseTrigger:
    """
    Detecta cambios en tablas SQLite y emite eventos.

    Los triggers SQL se instalan al inicializar la base de datos
    y emiten eventos cuando se insertan, actualizan o eliminan registros.
    """

    # Mapeo de tablas a eventos
    TABLE_EVENTS: ClassVar[dict[str, dict[str, str]]] = {
        "leads": {
            "insert": "crm.lead.created",
            "update": "crm.lead.updated",
            "delete": "crm.lead.deleted",
        },
        "invoices": {
            "insert": "invoice.created",
            "update": "invoice.updated",
            "delete": "invoice.deleted",
        },
        "products": {
            "insert": "inventory.product.created",
            "update": "inventory.product.updated",
            "delete": "inventory.product.deleted",
        },
        "workflow_executions": {
            "insert": "workflow.execution.created",
            "update": "workflow.execution.updated",
        },
    }

    def __init__(self, event_bus: EventBus | None = None):
        self._db = DatabaseManager()
        self._event_bus = event_bus or EventBus()
        self._snapshots: dict[str, dict[int, dict]] = {}

    def install_triggers(self) -> None:
        """Instala triggers SQL en la base de datos.

        Fix Sprint 3 bug #41: aunque event_name proviene de TABLE_EVENTS
        (ClassVar hardcoded), el patrón de interpolarlo como string literal
        en el SQL del trigger es frágil. SQLite CREATE TRIGGER no soporta
        parameter binding para los VALUES dentro de BEGIN/END, así que
        validamos estrictamente que event_name cumple el patrón esperado
        (solo letras, números, puntos, guiones bajos) antes de interpolar.
        """
        # Patrón estricto para event_name: namespace.event_name (ej: crm.lead.created)
        import re
        _EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

        conn = self._db.get_connection()
        cursor = conn.cursor()

        for table, events in self.TABLE_EVENTS.items():
            # Validar table name también (debe ser identificador simple)
            if not re.match(r"^[a-z][a-z0-9_]*$", table):
                logger.error(f"db_trigger: nombre de tabla inválido: {table!r}")
                continue

            for action, event_name in events.items():
                # Validar event_name antes de interpolar (defense in depth)
                if not _EVENT_NAME_PATTERN.match(event_name):
                    logger.error(
                        f"db_trigger: event_name inválido {event_name!r} — "
                        f"debe seguir patrón 'namespace.event_name'"
                    )
                    continue

                trigger_name = f"trg_{table}_{action}"

                # Verificar si el trigger ya existe
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
                    (trigger_name,),
                )
                if cursor.fetchone():
                    continue

                # Crear trigger — table y trigger_name son literals de TABLE_EVENTS (ClassVar hardcoded).
                # event_name también es literal. B608 es falso positivo.
                if action == "insert":
                    sql = f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    AFTER INSERT ON {table}
                    BEGIN
                        INSERT INTO event_queue (event_type, event_data, status)
                        VALUES ('{event_name}', json_object('id', NEW.id), 'pending');
                    END;
                    """  # nosec B608 — identificadores son literals hardcoded
                elif action == "update":
                    sql = f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    AFTER UPDATE ON {table}
                    BEGIN
                        INSERT INTO event_queue (event_type, event_data, status)
                        VALUES ('{event_name}', json_object('id', NEW.id), 'pending');
                    END;
                    """  # nosec B608 — identificadores son literals hardcoded
                elif action == "delete":
                    sql = f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    AFTER DELETE ON {table}
                    BEGIN
                        INSERT INTO event_queue (event_type, event_data, status)
                        VALUES ('{event_name}', json_object('id', OLD.id), 'pending');
                    END;
                    """  # nosec B608 — identificadores son literals hardcoded

                cursor.execute(sql)
                logger.debug(f"Trigger SQL instalado: {trigger_name}")

        conn.commit()
        logger.info("Triggers SQL instalados correctamente")

    def poll_changes(self) -> list[dict]:
        """
        Lee eventos pendientes generados por triggers SQL y los procesa.

        Nota: Los triggers SQL ya insertan directamente en event_queue.
        Este método marca los eventos como procesados sin re-publicarlos
        a través del EventBus (lo cual crearía duplicados).
        Para disparar workflows, usar EventBus.publish() directamente.
        """
        pending = self._db.fetchall("SELECT * FROM event_queue WHERE status = 'pending' ORDER BY created_at LIMIT 50")

        results = []
        for event in pending:
            try:
                # Just mark as completed — triggers already inserted the event
                # If a workflow needs to be triggered, EventBus.subscribe handles it
                self._db.execute(
                    "UPDATE event_queue SET status = 'completed', processed_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (event["id"],),
                )
                self._db.commit()
                results.append({"event_id": event["id"], "event_type": event["event_type"], "status": "processed"})

            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error procesando evento DB {event['id']}: {e}")
                self._db.execute(
                    "UPDATE event_queue SET status = 'failed' WHERE id = ?",
                    (event["id"],),
                )
                self._db.commit()
                results.append({"event_id": event["id"], "status": "failed"})

        return results
