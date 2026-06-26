"""
HAT-ORBITAL Nivel 0 — Estados del sistema como variables orbitales.

Define los 6 estados del orquestador HAT como constantes. Hay 5 θ distintas
en [0, 2π) porque RESPONDING cierra el ciclo al volver a IDLE (θ ≡ 0).
Los 5 estados "activos" (IDLE, ROUTING_ORBITAL, ROUTING_FSM, DISPATCHING,
CONSOLIDATING) ocupan sectores de 72° (2π/5) cada uno. RESPONDING comparte
el sector 0 con IDLE: se distingue por la mitad del círculo (alta = RESPONDING,
baja = IDLE), ver `theta_to_state`.

Los estados NO son una FSM externa — son variables orbitales. Las transiciones
entre estados se validan vía resonancia RCC (si el sistema está resonando en el
ciclo de transición, se permite avanzar).

Implementado en F0-D3 siguiendo HAT_ORBITAL_PLAN.md §2.2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final

from src.core.logging import setup_logging

logger = setup_logging(__name__)

TWO_PI: Final[float] = 2.0 * math.pi
SECTOR_RAD: Final[float] = TWO_PI / 5.0  # 72° entre estados activos consecutivos


class SystemState(Enum):
    """Estados del orquestador HAT-ORBITAL.

    El orden del enum define el orden de transición forward:
    IDLE → ROUTING_ORBITAL → ROUTING_FSM → DISPATCHING → CONSOLIDATING → RESPONDING → IDLE.
    """

    IDLE = "idle"
    ROUTING_ORBITAL = "routing_orbital"
    ROUTING_FSM = "routing_fsm"
    DISPATCHING = "dispatching"
    CONSOLIDATING = "consolidating"
    RESPONDING = "responding"


# Mapping estado → θ en radianes [0, 2π).
# IDLE = 0, ROUTING_ORBITAL = 2π/5, ..., RESPONDING = 8π/5 (sigue el orden del enum).
STATE_THETA: Final[dict[SystemState, float]] = {
    SystemState.IDLE: 0.0,
    SystemState.ROUTING_ORBITAL: SECTOR_RAD,
    SystemState.ROUTING_FSM: 2.0 * SECTOR_RAD,
    SystemState.DISPATCHING: 3.0 * SECTOR_RAD,
    SystemState.CONSOLIDATING: 4.0 * SECTOR_RAD,
    SystemState.RESPONDING: 5.0 * SECTOR_RAD % TWO_PI,  # ≡ 0, cierra el ciclo
}

# Mapping inverso: θ (float) → estado más cercano por sector.
# Útil para inferir el estado actual a partir de la θ observada en el OVC.


def theta_to_state(theta: float) -> SystemState:
    """Convierte una fase θ en [0, 2π) al estado cuyo sector la contiene.

    Cada estado ocupa un sector de 72° centrado en su θ. Por ejemplo,
    IDLE cubre [-36°, +36°] ≡ [324°, 36°], con centro en 0°.

    Args:
        theta: Fase en radianes. Se normaliza a [0, 2π) automáticamente.

    Returns:
        SystemState cuyo sector contiene a theta.

    Raises:
        TypeError: Si theta no es float/int.
    """
    if not isinstance(theta, (int, float)):
        raise TypeError(f"theta debe ser numérico, no {type(theta).__name__}")
    normalized = float(theta) % TWO_PI
    # El sector i cubre [i·72° - 36°, i·72° + 36°].
    # Desplazamos +36° (SECTOR/2) para que el sector 0 empiece en -36° ≡ 324°.
    shifted = (normalized + SECTOR_RAD / 2.0) % TWO_PI
    sector_index = int(shifted // SECTOR_RAD) % 5
    states_in_order = [
        SystemState.IDLE,
        SystemState.ROUTING_ORBITAL,
        SystemState.ROUTING_FSM,
        SystemState.DISPATCHING,
        SystemState.CONSOLIDATING,
    ]
    # RESPONDING e IDLE comparten el sector 0 porque RESPONDING cierra el ciclo
    # volviendo a IDLE (θ ≡ 0 mod 2π). Distinguimos por la mitad del círculo:
    # RESPONDING = mitad alta [324°, 360°); IDLE = mitad baja [0°, 36°].
    if sector_index == 0:
        # responding_lower_bound = 2π - SECTOR_RAD/2 = 9π/5 = 324°
        responding_lower_bound = (TWO_PI - SECTOR_RAD / 2.0) % TWO_PI
        # normalized > math.pi descarta la mitad baja (donde está IDLE).
        if normalized >= responding_lower_bound and normalized > math.pi:
            return SystemState.RESPONDING
        return SystemState.IDLE
    return states_in_order[sector_index]


@dataclass(frozen=True)
class StateTransition:
    """Transición válida entre dos estados del orquestador.

    Attributes:
        from_state: Estado de origen.
        to_state: Estado de destino.
        requires_resonance: Si True, la transición solo se permite si RCC
            detecta resonancia en el ciclo `transition_<from>_<to>`.
    """

    from_state: SystemState
    to_state: SystemState
    requires_resonance: bool = True


# Transiciones forward permitidas (el ciclo ORBITAL es: IDLE → ROUTING_ORBITAL →
# ROUTING_FSM → DISPATCHING → CONSOLIDATING → RESPONDING → IDLE).
# Nota: ROUTING_FSM solo se visita si ORBITAL no decidió solo (ver fsm_disambiguator.py).
FORWARD_TRANSITIONS: Final[tuple[StateTransition, ...]] = (
    StateTransition(SystemState.IDLE, SystemState.ROUTING_ORBITAL),
    StateTransition(SystemState.ROUTING_ORBITAL, SystemState.ROUTING_FSM),
    StateTransition(SystemState.ROUTING_ORBITAL, SystemState.DISPATCHING),  # skip FSM si claro
    StateTransition(SystemState.ROUTING_FSM, SystemState.DISPATCHING),
    StateTransition(SystemState.ROUTING_FSM, SystemState.RESPONDING),  # pedir aclaración
    StateTransition(SystemState.DISPATCHING, SystemState.CONSOLIDATING),
    StateTransition(SystemState.CONSOLIDATING, SystemState.RESPONDING),
    StateTransition(SystemState.RESPONDING, SystemState.IDLE),
)


def is_valid_transition(from_state: SystemState, to_state: SystemState) -> bool:
    """Verifica si una transición entre dos estados está permitida.

    Args:
        from_state: Estado de origen. Debe ser SystemState.
        to_state: Estado de destino. Debe ser SystemState.

    Returns:
        True si la transición aparece en FORWARD_TRANSITIONS.

    Raises:
        TypeError: Si `from_state` o `to_state` no son SystemState.
    """
    if not isinstance(from_state, SystemState):
        raise TypeError(
            f"from_state debe ser SystemState, no {type(from_state).__name__}: {from_state!r}"
        )
    if not isinstance(to_state, SystemState):
        raise TypeError(
            f"to_state debe ser SystemState, no {type(to_state).__name__}: {to_state!r}"
        )
    for transition in FORWARD_TRANSITIONS:
        if transition.from_state == from_state and transition.to_state == to_state:
            return True
    logger.debug("is_valid_transition: %s -> %s is NOT valid", from_state.value, to_state.value)
    return False


def next_states(current: SystemState) -> tuple[SystemState, ...]:
    """Retorna los estados a los que se puede transicionar desde `current`.

    Args:
        current: Estado actual del sistema. Debe ser instancia de SystemState.

    Returns:
        Tupla de estados destino válidos. Vacía si `current` no tiene
        transiciones forward (no debería ocurrir con la topología actual).

    Raises:
        TypeError: Si `current` no es instancia de SystemState.
    """
    if not isinstance(current, SystemState):
        raise TypeError(
            f"current debe ser SystemState, no {type(current).__name__}: {current!r}"
        )
    return tuple(
        t.to_state for t in FORWARD_TRANSITIONS if t.from_state == current
    )
