"""Tests para fsm/states — estados del sistema como variables orbitales.

Cubre:
- SystemState enum (6 estados).
- STATE_THETA mapping (θ en radianes para cada estado).
- theta_to_state() conversión inversa (sector de 72°).
- FORWARD_TRANSITIONS y validación de transiciones.
- next_states() para consulta de destinos válidos.
"""
from __future__ import annotations

import math

import pytest

from src.hat.level1_orchestrator.fsm.states import (
    FORWARD_TRANSITIONS,
    SECTOR_RAD,
    STATE_THETA,
    TWO_PI,
    SystemState,
    is_valid_transition,
    next_states,
    theta_to_state,
)

# ── Tests del enum SystemState ─────────────────────────────────────────


class TestSystemStateEnum:
    """El enum SystemState tiene los 6 estados esperados."""

    def test_enum_has_6_states(self) -> None:
        """SystemState tiene exactamente 6 miembros."""
        assert len(SystemState) == 6

    def test_enum_values_are_strings(self) -> None:
        """Los valores del enum son strings lowercase."""
        assert SystemState.IDLE.value == "idle"
        assert SystemState.ROUTING_ORBITAL.value == "routing_orbital"
        assert SystemState.ROUTING_FSM.value == "routing_fsm"
        assert SystemState.DISPATCHING.value == "dispatching"
        assert SystemState.CONSOLIDATING.value == "consolidating"
        assert SystemState.RESPONDING.value == "responding"

    def test_enum_order_matches_transition_order(self) -> None:
        """El orden del enum define el orden de transición forward."""
        states = list(SystemState)
        assert states[0] == SystemState.IDLE
        assert states[1] == SystemState.ROUTING_ORBITAL
        assert states[2] == SystemState.ROUTING_FSM
        assert states[3] == SystemState.DISPATCHING
        assert states[4] == SystemState.CONSOLIDATING
        assert states[5] == SystemState.RESPONDING


# ── Tests de STATE_THETA ───────────────────────────────────────────────


class TestStateTheta:
    """Mapping estado → θ en radianes."""

    def test_idle_theta_is_zero(self) -> None:
        """IDLE tiene θ = 0.0 (inicio del ciclo)."""
        assert STATE_THETA[SystemState.IDLE] == 0.0

    def test_routing_orbital_theta_is_2pi_over_5(self) -> None:
        """ROUTING_ORBITAL tiene θ = 2π/5 (72°)."""
        assert STATE_THETA[SystemState.ROUTING_ORBITAL] == pytest.approx(SECTOR_RAD)

    def test_responding_theta_wraps_to_zero(self) -> None:
        """RESPONDING tiene θ ≡ 0 (mod 2π) — cierra el ciclo."""
        theta = STATE_THETA[SystemState.RESPONDING]
        # Debe ser equivalente a 0 mod 2π
        assert math.isclose(theta % TWO_PI, 0.0, abs_tol=1e-9)

    def test_all_thetas_in_range_0_to_2pi(self) -> None:
        """Todas las θ están en [0, 2π)."""
        for state, theta in STATE_THETA.items():
            assert 0.0 <= theta < TWO_PI, f"{state} tiene θ fuera de rango: {theta}"

    def test_each_active_state_occupies_72_degrees(self) -> None:
        """Los 5 estados activos están a 72° (2π/5) entre sí."""
        active_states = [
            SystemState.IDLE,
            SystemState.ROUTING_ORBITAL,
            SystemState.ROUTING_FSM,
            SystemState.DISPATCHING,
            SystemState.CONSOLIDATING,
        ]
        for i, state in enumerate(active_states):
            expected_theta = i * SECTOR_RAD
            assert math.isclose(STATE_THETA[state], expected_theta, abs_tol=1e-9)


# ── Tests de theta_to_state ────────────────────────────────────────────


class TestThetaToState:
    """Conversión inversa: θ → estado por sector."""

    def test_theta_zero_returns_idle(self) -> None:
        """θ = 0 → IDLE (mitad baja del sector 0)."""
        assert theta_to_state(0.0) == SystemState.IDLE

    def test_theta_just_below_2pi_returns_responding(self) -> None:
        """θ ligeramente menor a 2π → RESPONDING (mitad alta del sector 0)."""
        assert theta_to_state(TWO_PI - 0.01) == SystemState.RESPONDING

    def test_theta_2pi_over_5_returns_routing_orbital(self) -> None:
        """θ = 2π/5 → ROUTING_ORBITAL."""
        assert theta_to_state(SECTOR_RAD) == SystemState.ROUTING_ORBITAL

    def test_theta_4pi_over_5_returns_routing_fsm(self) -> None:
        """θ = 4π/5 → ROUTING_FSM."""
        assert theta_to_state(2 * SECTOR_RAD) == SystemState.ROUTING_FSM

    def test_theta_normalizes_above_2pi(self) -> None:
        """θ > 2π se normaliza a [0, 2π)."""
        # 2π + 0.1 ≡ 0.1 → IDLE
        assert theta_to_state(TWO_PI + 0.1) == SystemState.IDLE

    def test_theta_negative_normalizes(self) -> None:
        """θ negativo se normaliza a [0, 2π)."""
        # -0.1 ≡ 2π - 0.1 → RESPONDING
        assert theta_to_state(-0.1) == SystemState.RESPONDING

    def test_theta_non_numeric_raises_type_error(self) -> None:
        """θ no numérico → TypeError."""
        with pytest.raises(TypeError, match="theta debe ser numérico"):
            theta_to_state("0.5")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="theta debe ser numérico"):
            theta_to_state(None)  # type: ignore[arg-type]


# ── Tests de FORWARD_TRANSITIONS ───────────────────────────────────────


class TestForwardTransitions:
    """Transiciones forward permitidas."""

    def test_idle_to_routing_orbital_is_valid(self) -> None:
        """IDLE → ROUTING_ORBITAL es válida."""
        assert is_valid_transition(SystemState.IDLE, SystemState.ROUTING_ORBITAL)

    def test_routing_orbital_to_dispatching_skip_fsm(self) -> None:
        """ROUTING_ORBITAL → DISPATCHING es válida (skip FSM si clear winner)."""
        assert is_valid_transition(SystemState.ROUTING_ORBITAL, SystemState.DISPATCHING)

    def test_routing_fsm_to_responding_for_clarify(self) -> None:
        """ROUTING_FSM → RESPONDING es válida (pedir aclaración)."""
        assert is_valid_transition(SystemState.ROUTING_FSM, SystemState.RESPONDING)

    def test_responding_to_idle_closes_cycle(self) -> None:
        """RESPONDING → IDLE es válida (cierra el ciclo)."""
        assert is_valid_transition(SystemState.RESPONDING, SystemState.IDLE)

    def test_invalid_transition_returns_false(self) -> None:
        """IDLE → CONSOLIDATING NO es válida (salto inválido)."""
        assert not is_valid_transition(SystemState.IDLE, SystemState.CONSOLIDATING)

    def test_is_valid_transition_type_error_on_non_enum(self) -> None:
        """Argumentos no-SystemState → TypeError."""
        with pytest.raises(TypeError):
            is_valid_transition("idle", SystemState.IDLE)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            is_valid_transition(SystemState.IDLE, "idle")  # type: ignore[arg-type]


# ── Tests de next_states ───────────────────────────────────────────────


class TestNextStates:
    """Consulta de estados destino válidos desde un estado dado."""

    def test_idle_next_states(self) -> None:
        """IDLE puede ir a ROUTING_ORBITAL."""
        nexts = next_states(SystemState.IDLE)
        assert SystemState.ROUTING_ORBITAL in nexts

    def test_routing_fsm_next_states(self) -> None:
        """ROUTING_FSM puede ir a DISPATCHING o RESPONDING."""
        nexts = next_states(SystemState.ROUTING_FSM)
        assert SystemState.DISPATCHING in nexts
        assert SystemState.RESPONDING in nexts

    def test_responding_next_states_only_idle(self) -> None:
        """RESPONDING solo puede ir a IDLE (cierra ciclo)."""
        nexts = next_states(SystemState.RESPONDING)
        assert nexts == (SystemState.IDLE,)

    def test_next_states_type_error_on_non_enum(self) -> None:
        """Argumento no-SystemState → TypeError."""
        with pytest.raises(TypeError):
            next_states("idle")  # type: ignore[arg-type]

    def test_forward_transitions_not_empty(self) -> None:
        """FORWARD_TRANSITIONS no está vacía."""
        assert len(FORWARD_TRANSITIONS) > 0
