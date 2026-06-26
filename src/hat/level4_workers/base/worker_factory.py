"""
HAT NIVEL 4 — WorkerFactory
============================

Genera workers dinámicamente desde métodos públicos de cada tool (Nivel 5).
Un worker = 1 método público de 1 tool.

Para 19 tools con ~59 métodos públicos totales, se generan ~59 workers.

Los workers generados NO se commitean al repo — se crean en memoria al startup.
La carpeta level4_workers/generated/ existe solo como documentación de qué
workers se generarían, pero los archivos reales se crean dinámicamente.

Uso:
    factory = WorkerFactory()
    workers = factory.generate_for_tool("crm", crm_instance)
    # workers = {"create_lead": CrmCreateLeadWorker, "list_leads": ..., ...}

    all_workers = factory.generate_all()
    # all_workers = {"crm": {"create_lead": ..., ...}, "invoice": {...}, ...}
"""

from __future__ import annotations

import inspect
from typing import Any

from src.core.logging import get_logger
from src.hat.level4_workers.base.registry import WorkerRegistry
from src.hat.level4_workers.base.tool_worker import ToolWorker

logger = get_logger("hat.level4.worker_factory")

# Métodos que NO se exponen como workers (administrativos, no de workflow)
_EXCLUDED_METHODS = frozenset({
    "get_tool_definition",
    "get_status",
    "configure",
    "test_connection",
    "configure_smtp",
    "configure_whatsapp",
    "get_whatsapp_status",
    "get_collection_info",  # data_keeper helper, similar a get_status
})


class WorkerFactory:
    """Factory que genera workers por introspección de tools.

    Flujo:
    1. ToolsRegistry.register_all() instancia las 19 tools (Nivel 5)
    2. WorkerFactory.generate_all() crea ~59 workers (Nivel 4)
    3. Cada specialist (Nivel 3) obtiene sus workers del registry
    """

    def __init__(self) -> None:
        self._registry = WorkerRegistry()

    def generate_for_tool(
        self,
        tool_name: str,
        tool_instance: object,
    ) -> dict[str, ToolWorker]:
        """Genera 1 worker por método público de la tool.

        Args:
            tool_name: Nombre de la tool (ej: "crm")
            tool_instance: Instancia singleton de la tool

        Returns:
            Dict {action_name: ToolWorker instance}
        """
        workers: dict[str, ToolWorker] = {}

        for method_name, _method in inspect.getmembers(tool_instance, predicate=inspect.ismethod):
            # Skip private methods
            if method_name.startswith("_"):
                continue
            # Skip excluded administrative methods
            if method_name in _EXCLUDED_METHODS:
                continue

            # Create a dynamic ToolWorker subclass for this method
            class_name = self._make_class_name(tool_name, method_name)
            worker_class = type(
                class_name,
                (ToolWorker,),
                {
                    "tool_name": tool_name,
                    "action_name": method_name,
                },
            )

            try:
                worker_instance = worker_class(tool_instance=tool_instance)
                workers[method_name] = worker_instance
                self._registry.register(tool_name, method_name, worker_instance)
            except Exception as exc:
                logger.error(
                    "Error creando worker %s.%s: %s",
                    tool_name, method_name, exc,
                )

        logger.info(
            "WorkerFactory: %d workers generados para tool '%s'",
            len(workers), tool_name,
        )
        return workers

    def generate_all(self) -> dict[str, dict[str, ToolWorker]]:
        """Genera workers para todas las tools registradas en Nivel 5.

        Returns:
            Dict {tool_name: {action_name: ToolWorker instance}}
        """
        from src.hat.level5_tools.registry import get_tools_registry

        tools = get_tools_registry().list_all()

        if not tools:
            logger.warning(
            "WorkerFactory: no hay tools registradas — "
            "llama a ToolsRegistry.register_all() primero"
        )
            return {}

        all_workers: dict[str, dict[str, ToolWorker]] = {}
        total_count = 0

        for tool_name, tool_instance in tools.items():
            workers = self.generate_for_tool(tool_name, tool_instance)
            all_workers[tool_name] = workers
            total_count += len(workers)

        logger.info(
            "WorkerFactory: %d workers generados para %d tools",
            total_count, len(tools),
        )
        return all_workers

    @staticmethod
    def _make_class_name(tool_name: str, action_name: str) -> str:
        """Genera un nombre de clase PascalCase para el worker dinámico.

        Ej: ("crm", "create_lead") → "CrmCreateLeadWorker"
        """
        parts = tool_name.split("_") + action_name.split("_")
        return "".join(p.capitalize() for p in parts) + "Worker"

    @property
    def registry(self) -> WorkerRegistry:
        """Acceso al registry de workers."""
        return self._registry

    def get_worker(self, tool_name: str, action_name: str) -> ToolWorker | None:
        """Obtiene un worker por tool+action."""
        return self._registry.get(tool_name, action_name)

    def list_actions(self, tool_name: str) -> list[str]:
        """Lista las actions disponibles para una tool."""
        return self._registry.list_actions(tool_name)

    def total_count(self) -> int:
        """Total de workers registrados."""
        return len(self._registry)
