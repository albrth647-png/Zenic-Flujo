"""
HAT NIVEL 4 — WorkerRegistry
=============================

Lookup de workers por (tool_name, action_name).
Almacena instancias de ToolWorker (no clases).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.hat.level4_workers.base.tool_worker import ToolWorker


class WorkerRegistry:
    """Registro central de workers activos.

    Almacena instancias de ToolWorker creadas por WorkerFactory.
    """

    def __init__(self) -> None:
        self._workers: dict[tuple[str, str], ToolWorker] = {}

    def register(self, tool_name: str, action_name: str, worker_instance: ToolWorker) -> None:
        """Registra una instancia de worker."""
        self._workers[(tool_name, action_name)] = worker_instance

    def get(self, tool_name: str, action_name: str) -> ToolWorker | None:
        """Obtiene un worker por tool+action. None si no existe."""
        return self._workers.get((tool_name, action_name))

    def list_actions(self, tool_name: str) -> list[str]:
        """Lista las actions disponibles para una tool."""
        return sorted([
            action for (tool, action) in self._workers
            if tool == tool_name
        ])

    def list_tools(self) -> list[str]:
        """Lista las tools con workers registrados."""
        return sorted({tool for (tool, _) in self._workers})

    def list_all(self) -> dict[tuple[str, str], ToolWorker]:
        """Retorna todos los workers registrados."""
        return dict(self._workers)

    def __len__(self) -> int:
        """Total de workers registrados."""
        return len(self._workers)

    def total_count(self) -> int:
        """Alias de __len__."""
        return len(self._workers)
