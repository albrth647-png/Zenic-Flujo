"""
WorkflowOrbitalAdapter — Conversión de workflows a definiciones orbitales
==========================================================================

Extraído de workflow_repository.py — responsabilidad única: migrar
workflows lineales al motor ORBITAL.
"""

from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class WorkflowOrbitalAdapter:
    """Adaptador para convertir workflows lineales a definiciones orbitales."""

    def __init__(self, db=None):
        self._db = db

    def to_orbital(self, workflow_id: int, definition_getter=None) -> dict[str, Any] | None:
        """Convierte una definición de workflow lineal a orbital.

        Args:
            workflow_id: ID del workflow a convertir.
            definition_getter: Callable(workflow_id) → dict | None.
                               Si None, usa import lazy de WorkflowDefinitionRepository.

        Returns:
            Definición orbital o None si no se encuentra el workflow.
        """
        if definition_getter is None:
            definition_getter = self._get_definition

        definition = definition_getter(workflow_id)
        if not definition:
            return None

        from src.orbital.orbital_repository import OrbitalRepository

        orbital_repo = OrbitalRepository()
        orbital_def = orbital_repo.convert_linear_to_orbital(definition)
        orbital_repo.save_orbital_workflow(orbital_def)
        orbital_repo.close()

        return orbital_def.to_dict()

    def get_orbital_stats(self) -> dict[str, Any]:
        """Retorna estadísticas de las tablas orbitales."""
        from src.orbital.db import OrbitalDB

        orbital_db = OrbitalDB()
        stats = orbital_db.get_stats()
        orbital_db.close()
        return stats

    @staticmethod
    def _get_definition(workflow_id: int) -> dict[str, Any] | None:
        """Obtiene una definición usando WorkflowDefinitionRepository (lazy import)."""
        from src.hat.level5_tools.automation.autopilot._definitions_repo import WorkflowDefinitionRepository

        repo = WorkflowDefinitionRepository()
        wf = repo.get(workflow_id)
        return wf.to_dict() if wf else None
