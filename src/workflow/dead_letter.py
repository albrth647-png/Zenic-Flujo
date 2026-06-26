"""
DeadLetterManager — Cola de mensajes fallidos (Dead Letter Queue)
====================================================================

Sprint 4 del Roadmap Competitivo.
Proporciona almacenamiento persistente en SQLite para pasos de workflow
que fallaron después de todos los reintentos, con capacidad de:
- Listar entradas con filtros
- Reintentar (re-ejecutar) entradas
- Descartar entradas
- Batch operations (reintentar/descartar múltiples)
- Notificación al entrar a dead letter
- Estadísticas
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.core.db import DatabaseManager
from src.events.bus import EventBus
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class DeadLetterEntry:
    """Representa una entrada en la Dead Letter Queue."""

    def __init__(
        self,
        id: int | None = None,
        workflow_id: int = 0,
        workflow_name: str = "",
        execution_id: int = 0,
        step_id: int = 0,
        tool: str = "",
        action: str = "",
        error_message: str = "",
        retry_count: int = 0,
        step_definition: dict | None = None,
        context_snapshot: dict | None = None,
        status: str = "pending",
        created_at: str | None = None,
        updated_at: str | None = None,
        notified: int = 0,
    ):
        self.id = id
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.execution_id = execution_id
        self.step_id = step_id
        self.tool = tool
        self.action = action
        self.error_message = error_message
        self.retry_count = retry_count
        self.step_definition = step_definition or {}
        self.context_snapshot = context_snapshot or {}
        self.status = status  # 'pending', 'retrying', 'resolved', 'discarded'
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.notified = notified  # 0 = no, 1 = yes

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "tool": self.tool,
            "action": self.action,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "step_definition": self.step_definition,
            "context_snapshot": self.context_snapshot,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "notified": bool(self.notified),
        }


class DeadLetterManager:
    """
    Gestor de Dead Letter Queue.

    Almacena y gestiona pasos de workflow que fallaron después de
    todos los reintentos. Proporciona operaciones para listar,
    reintentar, descartar y obtener estadísticas.

    La tabla `dead_letter_queue` se crea automáticamente en el schema
    de la base de datos.
    """

    def __init__(self, event_bus: EventBus | None = None):
        self._db = DatabaseManager()
        self._event_bus = event_bus or EventBus()

    # ── CRUD ────────────────────────────────────────────────

    def add(
        self,
        workflow_id: int,
        workflow_name: str,
        execution_id: int,
        step_id: int,
        tool: str,
        action: str,
        error_message: str,
        retry_count: int,
        step_definition: dict | None = None,
        context_snapshot: dict | None = None,
    ) -> int:
        """
        Agrega una entrada a la Dead Letter Queue.

        Returns:
            ID de la entrada creada
        """
        cursor = self._db.execute(
            """INSERT INTO dead_letter_queue
               (workflow_id, workflow_name, execution_id, step_id,
                tool, action, error_message, retry_count,
                step_definition, context_snapshot, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                workflow_id,
                workflow_name,
                execution_id,
                step_id,
                tool,
                action,
                error_message,
                retry_count,
                json.dumps(step_definition or {}),
                json.dumps(context_snapshot or {}),
            ),
        )
        self._db.commit()
        entry_id = cursor.lastrowid
        logger.warning(
            f"DeadLetter: entrada #{entry_id} creada para workflow "
            f"'{workflow_name}' paso {step_id}: {error_message[:100]}"
        )
        return entry_id

    def get(self, entry_id: int) -> DeadLetterEntry | None:
        """Obtiene una entrada por ID."""
        row = self._db.fetchone(
            "SELECT * FROM dead_letter_queue WHERE id = ?",
            (entry_id,),
        )
        return self._row_to_entry(row) if row else None

    def list(
        self, status: str | None = None, workflow_id: int | None = None, limit: int = 50, offset: int = 0
    ) -> list[DeadLetterEntry]:
        """
        Lista entradas con filtros opcionales.

        Args:
            status: 'pending', 'retrying', 'resolved', 'discarded'
            workflow_id: Filtrar por workflow
            limit: Máximo de resultados (default 50)
            offset: Desplazamiento para paginación

        Returns:
            Lista de DeadLetterEntry
        """
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if workflow_id:
            conditions.append("workflow_id = ?")
            params.append(workflow_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        # where se construye solo con strings hardcoded ("status = ?", "workflow_id = ?"). B608 falso positivo.
        sql = f"""SELECT * FROM dead_letter_queue {where}
                  ORDER BY created_at DESC LIMIT ? OFFSET ?"""  # nosec B608 — where construido con literals
        params.extend([limit, offset])

        rows = self._db.fetchall(sql, tuple(params))
        return [self._row_to_entry(r) for r in rows if r]

    def count(self, status: str | None = None, workflow_id: int | None = None) -> int:
        """Cuenta entradas con filtros opcionales."""
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if workflow_id:
            conditions.append("workflow_id = ?")
            params.append(workflow_id)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT COUNT(*) as count FROM dead_letter_queue {where}"  # nosec B608 — where construido con literals

        row = self._db.fetchone(sql, tuple(params))
        return row["count"] if row else 0

    def retry(self, entry_id: int) -> dict:
        """
        Reintenta una entrada de dead letter.

        Fix Sprint 1 bug #4 (fase 1): antes re-ejecutaba el workflow completo
        SIN pasar trigger_data, lo que causaba ejecuciones con trigger_data=None
        y resultados no reproducibles. Ahora:
        - Recupera trigger_data del context_snapshot guardado en la entrada
        - Pasa trigger_data original a engine.execute()
        - Si context_snapshot no tiene trigger_data, usa {} y loggea warning

        Fase 2 (futura, sprint 2-3): implementar retry a nivel de STEP usando
        step_definition + context_snapshot. Por ahora fase 1 ya cierra el bug
        más grave (ejecuciones sin trigger_data original).

        Returns:
            dict con {status, message, result} del reintento
        """
        entry = self.get(entry_id)
        if not entry:
            return {"status": "error", "message": "Entrada no encontrada"}

        if entry.status == "discarded":
            return {"status": "error", "message": "La entrada fue descartada"}

        # Marcar como retrying
        self._db.execute(
            "UPDATE dead_letter_queue SET status = 'retrying', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), entry_id),
        )
        self._db.commit()

        try:
            from src.workflow.engine import WorkflowEngine

            engine = WorkflowEngine()

            # Recuperar trigger_data original del context_snapshot (fix bug #4)
            trigger_data = None
            if entry.context_snapshot:
                # context_snapshot puede tener estructura {"input": {...}, "workflow": {...}, ...}
                # El trigger_data original está bajo "input"
                snapshot = (
                    entry.context_snapshot
                    if isinstance(entry.context_snapshot, dict)
                    else _safe_json_loads(entry.context_snapshot, {})
                )
                trigger_data = snapshot.get("input") if isinstance(snapshot, dict) else None
                if trigger_data is None:
                    logger.warning(
                        f"DeadLetter: entrada #{entry_id} no tiene 'input' en "
                        f"context_snapshot — re-ejecutando con trigger_data={{}}"
                    )
                    trigger_data = {}
            else:
                logger.warning(
                    f"DeadLetter: entrada #{entry_id} sin context_snapshot — "
                    f"re-ejecutando con trigger_data={{}}"
                )
                trigger_data = {}

            # Re-ejecutar el workflow completo CON trigger_data original
            result = engine.execute(entry.workflow_id, trigger_data=trigger_data)

            if result.status == "completed":
                # Marcar como resuelta
                self._db.execute(
                    "UPDATE dead_letter_queue SET status = 'resolved', updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), entry_id),
                )
                self._db.commit()
                logger.info(f"DeadLetter: entrada #{entry_id} resuelta en reintento")
                return {
                    "status": "resolved",
                    "message": "Workflow ejecutado exitosamente",
                    "execution_id": result.execution_id,
                }
            else:
                # Incrementar retry_count
                self._db.execute(
                    "UPDATE dead_letter_queue SET status = 'pending', "
                    "retry_count = retry_count + 1, error_message = ?, "
                    "updated_at = ? WHERE id = ?",
                    (result.error_message or "Error desconocido", datetime.now().isoformat(), entry_id),
                )
                self._db.commit()
                logger.warning(f"DeadLetter: entrada #{entry_id} reintento falló: {result.error_message}")
                return {
                    "status": "failed",
                    "message": "Workflow falló en reintento",
                    "error": result.error_message,
                }

        except Exception as e:
            # Error al reintentar — volver a pending
            self._db.execute(
                "UPDATE dead_letter_queue SET status = 'pending', "
                "retry_count = retry_count + 1, error_message = ?, "
                "updated_at = ? WHERE id = ?",
                (str(e), datetime.now().isoformat(), entry_id),
            )
            self._db.commit()
            logger.error(f"DeadLetter: error al reintentar #{entry_id}: {e}")
            return {
                "status": "error",
                "message": f"Error al reintentar: {e}",
            }

    def discard(self, entry_id: int) -> bool:
        """
        Descarta una entrada de dead letter.

        La entrada se marca como 'discarded' pero no se elimina
        de la base de datos (para auditoría).
        """
        entry = self.get(entry_id)
        if not entry:
            return False

        self._db.execute(
            "UPDATE dead_letter_queue SET status = 'discarded', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), entry_id),
        )
        self._db.commit()
        logger.info(f"DeadLetter: entrada #{entry_id} descartada")
        return True

    def retry_all(self, status: str = "pending") -> dict:
        """
        Reintenta todas las entradas con un estado dado.

        Args:
            status: Estado de las entradas a reintentar (default 'pending')

        Returns:
            dict con {total, resolved, failed, errors}
        """
        entries = self.list(status=status, limit=100)
        results = {"total": len(entries), "resolved": 0, "failed": 0, "errors": []}

        for entry in entries:
            result = self.retry(entry.id)
            if result.get("status") == "resolved":
                results["resolved"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "id": entry.id,
                        "error": result.get("message", "Unknown"),
                    }
                )

        logger.info(f"DeadLetter: retry_all completado — {results['resolved']}/{results['total']} resueltos")
        return results

    def discard_all(self, status: str = "pending") -> int:
        """
        Descarta todas las entradas con un estado dado.

        Returns:
            Número de entradas descartadas
        """
        entries = self.list(status=status, limit=500)
        count = 0
        for entry in entries:
            if self.discard(entry.id):
                count += 1
        logger.info(f"DeadLetter: {count} entradas descartadas")
        return count

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """
        Retorna estadísticas de la Dead Letter Queue.

        Returns:
            dict con total, por estado, por workflow, etc.
        """
        total = self.count()
        pending = self.count(status="pending")
        resolved = self.count(status="resolved")
        discarded = self.count(status="discarded")
        retrying = self.count(status="retrying")

        # Top workflows con más dead letters
        top_wf = self._db.fetchall(
            """SELECT workflow_id, workflow_name, COUNT(*) as count
               FROM dead_letter_queue
               WHERE status = 'pending'
               GROUP BY workflow_id
               ORDER BY count DESC LIMIT 5"""
        )

        return {
            "total": total,
            "by_status": {
                "pending": pending,
                "resolved": resolved,
                "discarded": discarded,
                "retrying": retrying,
            },
            "top_workflows": [
                {"workflow_id": r["workflow_id"], "workflow_name": r["workflow_name"], "count": r["count"]}
                for r in top_wf
            ],
        }

    # ── Notification ────────────────────────────────────────

    def notify_dead_letter(self, entry_id: int, entry: DeadLetterEntry | None = None) -> bool:
        """
        Dispara una notificación cuando un paso entra a dead letter.

        Publica un evento 'dead_letter.new' en el EventBus para que
        otros componentes (email, slack, telegram) puedan reaccionar.

        Args:
            entry_id: ID de la entrada
            entry: Objeto DeadLetterEntry (opcional, se busca si no se pasa)

        Returns:
            True si la notificación se disparó, False si ya estaba notificado
        """
        if entry is None:
            entry = self.get(entry_id)
        if not entry:
            return False

        if entry.notified:
            return False

        self._event_bus.publish(
            "dead_letter.new",
            {
                "entry_id": entry.id,
                "workflow_id": entry.workflow_id,
                "workflow_name": entry.workflow_name,
                "execution_id": entry.execution_id,
                "step_id": entry.step_id,
                "tool": entry.tool,
                "action": entry.action,
                "error_message": entry.error_message,
                "retry_count": entry.retry_count,
                "created_at": entry.created_at,
            },
        )

        # Marcar como notificado
        self._db.execute(
            "UPDATE dead_letter_queue SET notified = 1 WHERE id = ?",
            (entry_id,),
        )
        self._db.commit()
        logger.info(f"DeadLetter: notificación enviada para entrada #{entry_id}")
        return True

    def get_notification_summary(self) -> str:
        """
        Retorna un resumen legible de las dead letters pendientes.

        Útil para enviar por email/slack/telegram.
        """
        stats = self.get_stats()
        pending = stats["by_status"]["pending"]

        if pending == 0:
            return "✅ No hay entradas en Dead Letter Queue."

        lines = [
            f"⚠️ Dead Letter Queue — {pending} entrada(s) pendiente(s)\n",
        ]

        for wf in stats["top_workflows"]:
            lines.append(f"  • {wf['workflow_name']}: {wf['count']} error(es)")

        lines.append(
            f"\nTotal: {stats['total']} | "
            f"Resueltas: {stats['by_status']['resolved']} | "
            f"Descartadas: {stats['by_status']['discarded']}"
        )

        return "\n".join(lines)

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _row_to_entry(row: dict) -> DeadLetterEntry:
        """Convierte una fila SQL en DeadLetterEntry."""
        return DeadLetterEntry(
            id=row.get("id"),
            workflow_id=row.get("workflow_id", 0),
            workflow_name=row.get("workflow_name", ""),
            execution_id=row.get("execution_id", 0),
            step_id=row.get("step_id", 0),
            tool=row.get("tool", ""),
            action=row.get("action", ""),
            error_message=row.get("error_message", ""),
            retry_count=row.get("retry_count", 0),
            step_definition=_safe_json_loads(row.get("step_definition", "{}")),
            context_snapshot=_safe_json_loads(row.get("context_snapshot", "{}")),
            status=row.get("status", "pending"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            notified=row.get("notified", 0),
        )


def _safe_json_loads(value: str | dict | list, default: Any = None) -> Any:
    """Carga JSON de forma segura."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default or {}
    return default or {}
