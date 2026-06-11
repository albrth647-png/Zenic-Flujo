"""
ORBITAL — EventBus Orbital (OVC Compartido)
=============================================

Bus de eventos orbital con retroalimentacion circular usando OVC compartido
via OrbitalContext.

MEJORA vs version anterior:
- Ahora usa OrbitalContext → OVC compartido con todos los demas componentes
- Los eventos retroalimentan al mismo OVC que los pasos y condiciones
- Lo que un workflow modifica, el bus lo ve, y viceversa

Compatibilidad: mantiene la misma API que el EventBus original.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from src.data.database_manager import DatabaseManager
from src.orbital.context import OrbitalContext
from src.orbital.models import TWO_PI
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OrbitalEvent:
    """
    Evento orbital: un evento del bus enriquecido con fase y amplitud.
    """

    def __init__(self, event_type: str, data: dict, theta: float = 0.0, amplitude: float = 1.0):
        self.event_type = event_type
        self.data = data
        self.theta = theta % TWO_PI
        self.amplitude = amplitude
        self.timestamp = time.time()

    @property
    def value(self) -> float:
        return self.amplitude * math.cos(self.theta)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "data": self.data,
            "theta": self.theta,
            "amplitude": self.amplitude,
            "value": self.value,
            "timestamp": self.timestamp,
        }


class EventBus:
    """
    Bus de eventos orbital — Motor unico con OVC compartido via OrbitalContext.

    Usa OrbitalContext para compartir el OVC con WorkflowEngine, StepExecutor,
    ConditionEvaluator, etc. Lo que un componente retroalimenta, el bus lo ve.

    Singleton como el original.
    """

    _instance: EventBus | None = None
    _lock = threading.RLock()

    def __new__(cls) -> EventBus:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        with self._lock:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._handlers: dict[str, list[Callable]] = {}
            self._local_events: list[dict] = []

            # ── ORBITAL COMPARTIDO ──────────────────────────
            self._ctx = OrbitalContext()
            self._event_history: list[OrbitalEvent] = []
            self._retrofeed_damping = 0.3

    # ── Suscripciones ───────────────────────────────────────

    def subscribe(self, event_type: str, workflow_id: int) -> None:
        """Registra que workflow_id debe ejecutarse cuando ocurra event_type."""
        self._db.execute(
            "INSERT OR IGNORE INTO event_subscriptions (event_type, workflow_id) VALUES (?, ?)",
            (event_type, workflow_id),
        )
        self._db.commit()
        self._ensure_orbital_variable(event_type)
        logger.debug(f"Workflow {workflow_id} suscrito a evento '{event_type}'")

    def unsubscribe(self, event_type: str, workflow_id: int) -> None:
        self._db.execute(
            "DELETE FROM event_subscriptions WHERE event_type = ? AND workflow_id = ?",
            (event_type, workflow_id),
        )
        self._db.commit()
        logger.debug(f"Workflow {workflow_id} desuscrito de evento '{event_type}'")

    def unsubscribe_all(self, workflow_id: int) -> None:
        self._db.execute(
            "DELETE FROM event_subscriptions WHERE workflow_id = ?",
            (workflow_id,),
        )
        self._db.commit()
        logger.debug(f"Todas las suscripciones del workflow {workflow_id} eliminadas")

    def add_handler(self, event_type: str, handler: Callable) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        self._ensure_orbital_variable(event_type)

    def remove_handler(self, event_type: str, handler: Callable) -> None:
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    # ── Publicacion ORBITAL (OVC compartido) ────────────────

    def publish(self, event_type: str, data: dict) -> list[dict]:
        """
        Publica un evento en el bus orbital (OVC compartido).

        Las variables orbitales que se crean/modifican aqui son las mismas
        que ven WorkflowEngine, StepExecutor, etc.
        """
        results = []

        # 1. Actualizar variable orbital del evento (en OVC compartido)
        self._ensure_orbital_variable(event_type)
        var = self._ctx.ovc.get_variable(event_type)
        if var:
            var.advance(dt=1.0)
            importance = min(len(json.dumps(data)) / 1000.0, 3.0)
            var.amplitude = max(1.0, importance)

        # 2. Crear evento orbital
        orbital_event = OrbitalEvent(
            event_type=event_type,
            data=data,
            theta=var.theta if var else 0.0,
            amplitude=var.amplitude if var else 1.0,
        )
        self._event_history.append(orbital_event)

        # 3. Calcular tensiones TOR (en OVC compartido)
        tor_results = self._ctx.tor.calculate_matrix() if self._ctx.ovc.variable_count >= 2 else []
        resonance_level = 0.0
        if tor_results:
            avg_tension = sum(abs(r.tor_value) for r in tor_results) / len(tor_results)
            resonance_level = min(avg_tension / 100.0, 1.0)

        logger.info(
            f"OrbitalBus: Evento '{event_type}' publicado — "
            f"theta={orbital_event.theta:.2f} A={orbital_event.amplitude:.2f} "
            f"resonancia={resonance_level:.4f}"
        )

        # 4. Guardar en cola persistente
        event_id = self._save_to_queue(event_type, data)

        # 5. Ejecutar handlers en memoria
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    handler(data)
                except (KeyError, ValueError, TypeError) as e:
                    logger.error(f"Error en handler para evento '{event_type}': {e}")

        # 6. Buscar workflows suscritos y priorizar por TOR
        subscribers = self._db.fetchall(
            """SELECT wf.id, wf.status, wf.name
               FROM event_subscriptions es
               JOIN workflow_definitions wf ON es.workflow_id = wf.id
               WHERE es.event_type = ?""",
            (event_type,),
        )

        prioritized = self._prioritize_subscribers(subscribers, event_type)

        for sub in prioritized:
            if sub["status"] != "active":
                logger.debug(f"Workflow {sub['id']} ({sub['name']}) no activo, saltando")
                continue

            result = self._execute_workflow(sub["id"], data)
            results.append(result)
            self._update_queue_status(event_id, "completed" if result.get("status") == "completed" else "failed")

        if not subscribers:
            logger.debug(f"Evento '{event_type}' publicado sin suscriptores activos")
            self._update_queue_status(event_id, "pending")

        # 7. Retroalimentar: resultados modifican variables orbitales compartidas
        self._retrofeed_from_results(event_type, results, resonance_level)

        # 8. Agregar metadatos orbitales a los resultados
        for result in results:
            result["orbital"] = {
                "theta": orbital_event.theta,
                "amplitude": orbital_event.amplitude,
                "resonance_level": resonance_level,
            }

        # 9. Auditoria
        self._db.audit("eventbus.published", f"Evento '{event_type}' publicado con {len(subscribers)} suscriptores")

        return results

    # ── Priorizacion orbital (OVC compartido) ───────────────

    def _prioritize_subscribers(self, subscribers: list[dict], event_type: str) -> list[dict]:
        if not subscribers or len(subscribers) <= 1:
            return subscribers

        event_var = self._ctx.ovc.get_variable(event_type)
        if not event_var:
            return subscribers

        scored = []
        for sub in subscribers:
            wf_var_name = f"wf_{sub['id']}"
            wf_var = self._ctx.ovc.get_variable(wf_var_name)
            if wf_var:
                alignment = event_var.phase_alignment(wf_var)
                scored.append((sub, alignment))
            else:
                scored.append((sub, 0.0))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [sub for sub, _ in scored]

    # ── Retroalimentacion (OVC compartido) ──────────────────

    def _retrofeed_from_results(self, event_type: str, results: list[dict], resonance_level: float) -> None:
        var = self._ctx.ovc.get_variable(event_type)
        if not var:
            return

        for result in results:
            if result.get("status") == "completed":
                var.retrofeed(0.1 * resonance_level, self._retrofeed_damping)
            else:
                var.retrofeed(-0.05 * resonance_level, self._retrofeed_damping)

    # ── Helpers orbitales (OVC compartido) ──────────────────

    def _ensure_orbital_variable(self, event_type: str) -> None:
        if self._ctx.ovc.get_variable(event_type) is None:
            hash_val = int(hashlib.md5(event_type.encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=event_type,
                theta=theta,
                amplitude=1.0,
                velocity=0.05,
                orbit_group="event_bus",
                metadata={"source": "orbital_bus", "event_type": event_type},
            )

    def _ensure_workflow_variable(self, workflow_id: int) -> None:
        var_name = f"wf_{workflow_id}"
        if self._ctx.ovc.get_variable(var_name) is None:
            hash_val = int(hashlib.md5(var_name.encode()).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            self._ctx.ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=1.0,
                velocity=0.08,
                orbit_group="subscribed_workflows",
                metadata={"source": "orbital_bus", "workflow_id": workflow_id},
            )

    # ── Persistencia ────────────────────────────────────────

    @staticmethod
    def _json_default(obj: object) -> str:
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def _save_to_queue(self, event_type: str, data: dict) -> int:
        cursor = self._db.execute(
            "INSERT INTO event_queue (event_type, event_data, status) VALUES (?, ?, 'pending')",
            (event_type, json.dumps(data, default=self._json_default)),
        )
        self._db.commit()
        return cursor.lastrowid

    def _update_queue_status(self, event_id: int, status: str) -> None:
        self._db.execute(
            "UPDATE event_queue SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, event_id),
        )
        self._db.commit()

    def _execute_workflow(self, workflow_id: int, data: dict) -> dict:
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
            {"event": "email.received", "description": "Correo electronico recibido (IMAP)"},
        ]

    # ── Recuperacion ────────────────────────────────────────

    def get_pending_events(self) -> list[dict]:
        return self._db.fetchall("SELECT * FROM event_queue WHERE status = 'pending' ORDER BY created_at")

    def reprocess_pending(self) -> int:
        pending = self.get_pending_events()
        count = 0
        for event in pending:
            try:
                event_data = json.loads(event["event_data"])
                self._update_queue_status(event["id"], "processing")
                self.publish(event["event_type"], event_data)
                count += 1
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Error reprocesando evento {event['id']}: {e}")
                self._update_queue_status(event["id"], "failed")
        return count

    def reprocess_failed(self) -> int:
        failed = self._db.fetchall("SELECT * FROM event_queue WHERE status = 'failed' ORDER BY created_at")
        count = 0
        for event in failed:
            try:
                event_data = json.loads(event["event_data"])
                self._update_queue_status(event["id"], "processing")
                self.publish(event["event_type"], event_data)
                count += 1
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Error reprocesando evento fallido {event['id']}: {e}")
        return count

    # ── Consultas orbitales (OVC compartido) ────────────────

    def get_event_phase(self, event_type: str) -> float | None:
        var = self._ctx.ovc.get_variable(event_type)
        return var.theta if var else None

    def get_event_resonance(self, event_type_a: str, event_type_b: str) -> float | None:
        var_a = self._ctx.ovc.get_variable(event_type_a)
        var_b = self._ctx.ovc.get_variable(event_type_b)
        if var_a and var_b:
            return var_a.phase_alignment(var_b)
        return None

    def get_orbital_snapshot(self) -> dict[str, Any]:
        return {
            "variables": self._ctx.ovc.get_value_snapshot(),
            "phases": self._ctx.ovc.get_phase_snapshot(),
            "tor_matrix": [r.to_dict() for r in self._ctx.tor.calculate_matrix()],
            "event_count": len(self._event_history),
            "orbital_mode": True,
            "shared_context": True,
        }

    def orbital_summary(self) -> str:
        lines = ["OrbitalBus — Estado Orbital del Bus de Eventos (OVC Compartido)"]
        lines.append("  Modo: ORBITAL (compartido)")
        lines.append(f"  Variables orbitales: {self._ctx.ovc.variable_count}")
        lines.append(f"  Eventos procesados: {len(self._event_history)}")
        if self._ctx.ovc.variable_count > 0:
            lines.append(self._ctx.ovc.status_summary())
        return "\n".join(lines)

    # ── Reset para testing ──────────────────────────────────

    @classmethod
    def _reset(cls) -> None:
        """Reinicia el singleton (para tests)."""
        cls._instance = None

    def __repr__(self) -> str:
        return f"EventBus(ORBITAL-shared, events={self._ctx.ovc.variable_count})"
