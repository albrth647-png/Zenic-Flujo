"""Orbital steps injection — convierte pasos de workflow en variables orbitales.

Extraído de WorkflowEngine._inject_steps_as_orbital().
"""

from __future__ import annotations

import hashlib

from src.core.logging import setup_logging
from src.orbital.models import TWO_PI

logger = setup_logging(__name__)


def inject_steps_as_orbital(steps: list[dict], ovc, var_prefix: str = "") -> None:
    """Convierte los pasos del workflow en variables orbitales (OVC compartido).

    Args:
        steps: Lista de pasos del workflow.
        ovc: Instancia de OVC donde crear las variables.
        var_prefix: Prefijo para namespacing por execution_id (fix Sprint 1 bug #1).
            Si se pasa, las variables se llamarán "<prefix>step_<id>_<tool>" en
            vez de "step_<id>_<tool>", evitando colisiones entre workflows
            concurrentes que compartan el singleton OVC.
    """
    for step in steps:
        step_id = step.get("id", 0)
        tool = step.get("tool", "")
        action = step.get("action", "")
        var_name = f"{var_prefix}step_{step_id}_{tool}"

        try:
            # Hash no criptográfico: deriva theta determinista del tool.action (B324 mitigado).
            hash_val = int(hashlib.md5(f"{tool}.{action}".encode(), usedforsecurity=False).hexdigest()[:8], 16)
            theta = (hash_val % 1000) / 1000.0 * TWO_PI
            amplitude = 1.0
            if step.get("condition"):
                amplitude += 0.5
            if step.get("type") in ("branch", "loop"):
                amplitude += 1.0

            ovc.create_variable(
                name=var_name,
                theta=theta,
                amplitude=min(amplitude, 5.0),
                velocity=0.1,
                orbit_group="workflow_steps",
                metadata={"step_id": step_id, "tool": tool, "action": action},
            )
        except ValueError:
            pass  # Variable ya existe
