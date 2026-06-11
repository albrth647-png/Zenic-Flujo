"""
ORBITAL — Pilar Puente: OrbitalRepository
===========================================

Repositorio orbital que convierte definiciones de workflow lineales
en definiciones orbitales con fases theta, amplitudes y ciclos.

En el sistema LINEAL:
    WorkflowDefinition {steps: [step1, step2, step3]} → ejecucion secuencial

En el sistema ORBITAL:
    WorkflowOrbitalDef {variables: [var1(θ,A,ω), var2(θ,A,ω), ...], cycles: [...]}
    → ejecucion orbital con retroalimentacion

El OrbitalRepository:
1. Lee definiciones lineales de la DB existente
2. Las convierte a definiciones orbitales
3. Guarda las definiciones orbitales en las tablas orbitales
4. Permite consultar ambas representaciones

Esto permite la coexistencia durante la migracion:
- Los workflows existentes siguen funcionando (lineal)
- Los nuevos workflows se crean en modo orbital
- La conversion es automatica y reversible
"""

from __future__ import annotations

import hashlib
import json

from src.orbital.db import OrbitalDB
from src.orbital.models import (
    TWO_PI,
)
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OrbitalWorkflowDef:
    """
    Definicion de workflow orbital.

    Extiende WorkflowDefinition con propiedades orbitales:
    - Cada variable del workflow tiene fase theta, amplitud A, velocidad omega
    - Los ciclos cerrados entre variables se definen explicitamente
    - El workflow se ejecuta orbitalmente, no secuencialmente
    """

    def __init__(
        self,
        id: str = "",
        name: str = "",
        linear_workflow_id: int | None = None,
        variables: list[dict] | None = None,
        cycles: list[dict] | None = None,
        trigger_type: str = "",
        trigger_config: dict | None = None,
        retrofeed_damping: float = 0.3,
        status: str = "active",
    ):
        self.id = id
        self.name = name
        self.linear_workflow_id = linear_workflow_id
        self.variables = variables or []
        self.cycles = cycles or []
        self.trigger_type = trigger_type
        self.trigger_config = trigger_config or {}
        self.retrofeed_damping = retrofeed_damping
        self.status = status

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "linear_workflow_id": self.linear_workflow_id,
            "variables": self.variables,
            "cycles": self.cycles,
            "trigger_type": self.trigger_type,
            "trigger_config": self.trigger_config,
            "retrofeed_damping": self.retrofeed_damping,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OrbitalWorkflowDef:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            linear_workflow_id=data.get("linear_workflow_id"),
            variables=data.get("variables", []),
            cycles=data.get("cycles", []),
            trigger_type=data.get("trigger_type", ""),
            trigger_config=data.get("trigger_config", {}),
            retrofeed_damping=data.get("retrofeed_damping", 0.3),
            status=data.get("status", "active"),
        )


class OrbitalRepository:
    """
    Repositorio Orbital — Conversion y almacenamiento de workflows orbitales.

    Convierte definiciones lineales a orbitales y viceversa.
    Permite la coexistencia de ambos paradigmas durante la migracion.
    """

    def __init__(self, db_path: str | None = None):
        self._db = OrbitalDB(db_path)

    # ── Conversion Lineal → Orbital ────────────────────────

    def convert_linear_to_orbital(self, linear_workflow: dict) -> OrbitalWorkflowDef:
        """
        Convierte una definicion de workflow lineal a orbital.

        Proceso:
        1. Cada step del workflow → variable orbital (OVC)
        2. Cada $variable del contexto → variable orbital
        3. Los pasos consecutivos forman ciclos orbitales
        4. Las condiciones se convierten en umbrales RCC

        Args:
            linear_workflow: Diccionario con la definicion lineal
                (de WorkflowDefinition.to_dict())

        Returns:
            OrbitalWorkflowDef con la representacion orbital
        """
        steps = linear_workflow.get("steps", [])
        if isinstance(steps, str):
            steps = json.loads(steps)

        # 1. Convertir pasos a variables orbitales
        variables = []
        for step in steps:
            step_id = step.get("id", 0)
            tool = step.get("tool", "")
            action = step.get("action", "")

            var_name = f"step_{step_id}_{tool}"
            theta = self._deterministic_theta(f"{tool}.{action}")
            amplitude = self._step_amplitude(step)
            velocity = self._step_velocity(step)

            variables.append(
                {
                    "name": var_name,
                    "theta": theta,
                    "amplitude": amplitude,
                    "velocity": velocity,
                    "orbit_group": "workflow_steps",
                    "metadata": {
                        "step_id": step_id,
                        "tool": tool,
                        "action": action,
                        "params": step.get("params", {}),
                        "condition": step.get("condition"),
                    },
                }
            )

        # 2. Convertir variables del trigger a orbitales
        trigger_data = linear_workflow.get("trigger_config", {})
        if isinstance(trigger_data, str):
            trigger_data = json.loads(trigger_data)

        trigger_event = trigger_data.get("event", "")
        if trigger_event:
            variables.append(
                {
                    "name": f"trigger_{trigger_event}",
                    "theta": self._deterministic_theta(trigger_event),
                    "amplitude": 2.0,  # Triggers tienen amplitud mayor
                    "velocity": 0.05,
                    "orbit_group": "triggers",
                    "metadata": {"source": "trigger", "event": trigger_event},
                }
            )

        # 3. Crear ciclo orbital con todos los pasos + trigger
        var_names = [v["name"] for v in variables]
        cycles = []
        if len(var_names) >= 2:
            cycles.append(
                {
                    "name": f"cycle_{linear_workflow.get('name', 'workflow')}",
                    "variable_ids": var_names,
                    "threshold": 0.3,
                }
            )

        # 4. Crear definicion orbital
        orbital_def = OrbitalWorkflowDef(
            id=self._generate_orbital_id(linear_workflow),
            name=f"{linear_workflow.get('name', 'Workflow')} [ORBITAL]",
            linear_workflow_id=linear_workflow.get("id"),
            variables=variables,
            cycles=cycles,
            trigger_type=linear_workflow.get("trigger_type", "manual"),
            trigger_config=trigger_data,
            retrofeed_damping=0.3,
        )

        logger.info(f"OrbitalRepository: Workflow lineal → orbital — {len(variables)} variables, {len(cycles)} ciclos")

        return orbital_def

    # ── Almacenamiento ─────────────────────────────────────

    def save_orbital_workflow(self, orbital_def: OrbitalWorkflowDef) -> str:
        """
        Guarda una definicion orbital en la base de datos.

        Guarda las variables en orbital_variables y los ciclos en orbital_cycles.

        Args:
            orbital_def: Definicion orbital a guardar

        Returns:
            ID del workflow orbital guardado
        """
        # Guardar variables
        for var_data in orbital_def.variables:
            self._db.save_variable(var_data)

        # Guardar ciclos
        for cycle_data in orbital_def.cycles:
            self._db.save_cycle(cycle_data)

        logger.info(
            f"OrbitalRepository: Workflow orbital guardado '{orbital_def.name}' — "
            f"{len(orbital_def.variables)} variables, {len(orbital_def.cycles)} ciclos"
        )

        return orbital_def.id

    def load_orbital_workflow(self, name_prefix: str) -> OrbitalWorkflowDef | None:
        """
        Carga una definicion orbital desde la base de datos.

        Args:
            name_prefix: Prefijo del nombre del workflow orbital

        Returns:
            OrbitalWorkflowDef o None si no se encuentra
        """
        all_vars = self._db.load_all_variables()
        all_cycles = self._db.load_all_cycles()

        if not all_vars:
            return None

        # Filtrar variables del workflow
        workflow_vars = [v for v in all_vars if v.get("name", "").startswith(name_prefix)]
        if not workflow_vars:
            return None

        # Filtrar ciclos del workflow
        workflow_cycles = [c for c in all_cycles if c.get("name", "").startswith(name_prefix)]

        return OrbitalWorkflowDef(
            name=f"{name_prefix} [ORBITAL]",
            variables=workflow_vars,
            cycles=workflow_cycles,
        )

    # ── Estadisticas ───────────────────────────────────────

    def get_migration_stats(self) -> dict:
        """Retorna estadisticas de la migracion lineal → orbital."""
        stats = self._db.get_stats()
        return {
            "orbital_variables": stats.get("orbital_variables", 0),
            "orbital_cycles": stats.get("orbital_cycles", 0),
            "orbital_spectrum": stats.get("orbital_spectrum", 0),
            "orbital_executions": stats.get("orbital_executions", 0),
        }

    # ── Helpers ────────────────────────────────────────────

    def _deterministic_theta(self, text: str) -> float:
        """Genera una fase determinista a partir de un texto."""
        hash_val = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        return (hash_val % 10000) / 10000.0 * TWO_PI

    def _step_amplitude(self, step: dict) -> float:
        """
        Calcula la amplitud de un paso basado en su importancia.

        Pasos con mas parametros o condiciones tienen mayor amplitud.
        """
        base = 1.0
        params = step.get("params", {})
        if isinstance(params, dict):
            base += len(params) * 0.2
        if step.get("condition"):
            base += 0.5
        if step.get("type") in ("branch", "loop"):
            base += 1.0
        return min(base, 5.0)

    def _step_velocity(self, step: dict) -> float:
        """
        Calcula la velocidad orbital de un paso.

        Pasos criticos (notificacion, error) son mas rapidos.
        Pasos de procesamiento son mas lentos.
        """
        tool = step.get("tool", "")
        fast_tools = {"notification", "logic_gate"}
        slow_tools = {"code_runner", "api_connector"}

        if tool in fast_tools:
            return 0.2
        elif tool in slow_tools:
            return 0.05
        return 0.1

    def _generate_orbital_id(self, linear_workflow: dict) -> str:
        """Genera un ID orbital determinista a partir del workflow lineal."""
        raw = f"{linear_workflow.get('id', '')}_{linear_workflow.get('name', '')}"
        hash_val = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"orbital_{hash_val}"

    def close(self) -> None:
        """Cierra la conexion a la base de datos."""
        self._db.close()

    def __repr__(self) -> str:
        return f"OrbitalRepository(db={self._db})"
