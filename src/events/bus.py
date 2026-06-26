"""
Zenic-Flijo — EventBus (Pub/Sub Puro)
=======================================

Bus de eventos simple en memoria.

Sin base de datos, sin lógica orbital, sin singletons.
Solo pub/sub: suscribir handlers y publicar eventos.

Responsabilidades:
- Mantener un registro de handlers por tipo de evento
- Disparar handlers cuando se publica un evento
- Manejar errores en handlers gracefulmente

Para persistencia de eventos, usar EventQueueService.
Para ejecución de workflows, usar WorkflowSubscriber.
Para tracking orbital, usar OrbitalContext directamente.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from src.core.logging import setup_logging

logger = setup_logging(__name__)


class EventBus:
    """
    Bus de eventos simple en memoria, THREAD-SAFE.

    API:
        subscribe(event_type, handler)  → None
        unsubscribe(event_type, handler) → None
        publish(event_type, data)       → None

    No es singleton. Cada instancia tiene su propio registro de handlers.
    Usa threading.RLock para proteger _handlers y _global_handler contra
    race conditions cuando múltiples workers daemon publican/suscriben
    concurrentemente (ver BUG-FE-06 fix en Sprint 1).
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._global_handler: Callable[[str, dict], None] | None = None
        self._lock = threading.RLock()

    # ── Suscripciones ───────────────────────────────────────

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """
        Registra un handler para un tipo de evento.

        Args:
            event_type: Tipo de evento (ej. 'crm.lead.created')
            handler: Callable que recibe (data: dict)
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """
        Elimina un handler previamente registrado.

        Args:
            event_type: Tipo de evento
            handler: Handler a eliminar
        """
        with self._lock:
            if event_type in self._handlers:
                self._handlers[event_type] = [
                    h for h in self._handlers[event_type] if h != handler
                ]
                # Limpiar listas vacías para evitar crecimiento indefinido
                if not self._handlers[event_type]:
                    del self._handlers[event_type]

    # ── Global handler ─────────────────────────────────────

    def set_global_handler(self, handler: Callable[[str, dict], None] | None) -> None:
        """
        Registra un handler global que recibe TODOS los eventos publicados.
        Útil para WorkflowSubscriber u otros suscriptores universales.

        Args:
            handler: Callable que recibe (event_type: str, data: dict) o None para limpiar
        """
        with self._lock:
            self._global_handler = handler

    # ── Publicación ─────────────────────────────────────────

    def publish(self, event_type: str, data: dict) -> None:
        """
        Publica un evento. Todos los handlers suscritos son llamados.
        Si hay un global_handler registrado, también se llama con (event_type, data).

        Thread-safe: copia la lista de handlers bajo lock, luego invoca fuera
        del lock para evitar deadlocks si un handler publica recursivamente.

        Args:
            event_type: Tipo de evento
            data: Datos del evento (dict)
        """
        # Snapshot de handlers bajo lock (copy-on-read)
        with self._lock:
            handlers_snapshot = list(self._handlers.get(event_type, []))
            global_handler = self._global_handler

        # 1. Handlers específicos del tipo de evento (fuera del lock)
        for handler in handlers_snapshot:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"EventBus: error en handler para evento '{event_type}': {e}")

        # 2. Global handler (para WorkflowSubscriber y otros suscriptores universales)
        if global_handler:
            try:
                global_handler(event_type, data)
            except Exception as e:
                logger.error(f"EventBus: error en global handler para evento '{event_type}': {e}")

    # ── Utilidades ──────────────────────────────────────────

    @staticmethod
    def get_system_events() -> list[dict]:
        """
        Retorna la lista de eventos del sistema predefinidos.

        Returns:
            Lista de dicts con event_type y descripción
        """
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

    def __repr__(self) -> str:
        return f"EventBus(handlers={sum(len(h) for h in self._handlers.values())})"
