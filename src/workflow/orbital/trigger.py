"""Orbital trigger injection — convierte datos de trigger en variables orbitales.

Extraído de WorkflowEngine._inject_trigger_as_orbital().
"""

from __future__ import annotations

from src.orbital.models import TWO_PI
from src.core.logging import setup_logging

logger = setup_logging(__name__)


def inject_trigger_as_orbital(trigger_data: dict, ovc, var_prefix: str = "") -> None:
    """Convierte los datos del trigger en variables orbitales (OVC compartido).

    Args:
        trigger_data: Datos del trigger del workflow.
        ovc: Instancia de OVC donde crear las variables.
        var_prefix: Prefijo para namespacing por execution_id (fix Sprint 1 bug #1).
    """
    for key, value in trigger_data.items():
        if isinstance(value, (int, float)):
            var_name = f"{var_prefix}input_{key}"
            try:
                ovc.create_variable(
                    name=var_name,
                    theta=abs(value) % TWO_PI if value != 0 else 0.0,
                    amplitude=abs(value) if value != 0 else 1.0,
                    velocity=0.05,
                    orbit_group="trigger_data",
                    metadata={"source": "trigger", "original_key": key},
                )
            except ValueError:
                var = ovc.get_variable(var_name)
                if var:
                    var.amplitude = abs(value) if value != 0 else 1.0
