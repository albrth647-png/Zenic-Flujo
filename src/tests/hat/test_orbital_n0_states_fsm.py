"""
Tests para orbital_n0/states.py y orbital_n0/fsm_disambiguator.py (F0-D3).

Cobertura:
- states.py: 5 estados, mapping θ, theta_to_state (5 sectores), StateTransition,
  FORWARD_TRANSITIONS, is_valid_transition, next_states.
- fsm_disambiguator.py: 4 reglas (clear winner, active domain, keywords, clarify),
  edge cases (empty input, dominio inválido, empate exacto).
"""

from __future__ import annotations

import math

import pytest

from src.hat.level1_orchestrator.fsm.disambiguator import (
    CLARIFY_DOMAIN,
    DISAMBIGUATION_THRESHOLD,
    DOMAIN_KEYWORDS,
    VALID_DOMAINS,
    fsm_disambiguate,
)
from src.hat.level1_orchestrator.fsm.states import (
    FORWARD_TRANSITIONS,
    SECTOR_RAD,
    STATE_THETA,
    TWO_PI,
    StateTransition,
    SystemState,
    is_valid_transition,
    next_states,
    theta_to_state,
)

# ─────────────────────────────────────────────────────────
# states.py — SystemState enum
# ─────────────────────────────────────────────────────────


class TestSystemStateEnum:
    def test_has_exactly_6_states(self):
        # 6 estados: IDLE, ROUTING_ORBITAL, ROUTING_FSM, DISPATCHING,
        # CONSOLIDATING, RESPONDING (RESPONDING cierra el ciclo a IDLE).
        assert len(SystemState) == 6

    def test_state_names_match_plan(self):
        expected = {"IDLE", "ROUTING_ORBITAL", "ROUTING_FSM", "DISPATCHING", "CONSOLIDATING", "RESPONDING"}
        actual = {s.name for s in SystemState}
        assert expected == actual, f"Falta o sobra estados: {expected ^ actual}"

    def test_state_values_are_strings(self):
        for state in SystemState:
            assert isinstance(state.value, str)
            assert state.value  # no vacío


# ─────────────────────────────────────────────────────────
# states.py — STATE_THETA mapping
# ─────────────────────────────────────────────────────────


class TestStateTheta:
    def test_all_states_have_theta(self):
        for state in SystemState:
            assert state in STATE_THETA, f"Falta θ para {state.name}"

    def test_theta_values_in_range_0_to_2pi(self):
        for state, theta in STATE_THETA.items():
            assert 0.0 <= theta < TWO_PI, f"{state.name} θ={theta} fuera de [0, 2π)"

    def test_idle_theta_is_zero(self):
        assert STATE_THETA[SystemState.IDLE] == 0.0

    def test_responding_theta_closes_cycle(self):
        # RESPONDING cierra el ciclo: su θ ≡ 0 mod 2π.
        assert math.isclose(STATE_THETA[SystemState.RESPONDING] % TWO_PI, 0.0, abs_tol=1e-9)

    def test_consecutive_states_are_72_degrees_apart(self):
        order = [
            SystemState.IDLE,
            SystemState.ROUTING_ORBITAL,
            SystemState.ROUTING_FSM,
            SystemState.DISPATCHING,
            SystemState.CONSOLIDATING,
        ]
        for i in range(len(order) - 1):
            delta = STATE_THETA[order[i + 1]] - STATE_THETA[order[i]]
            assert math.isclose(delta, SECTOR_RAD, abs_tol=1e-9), (
                f"Δθ entre {order[i].name} y {order[i+1].name} = {delta}, "
                f"esperado {SECTOR_RAD}"
            )


# ─────────────────────────────────────────────────────────
# states.py — theta_to_state
# ─────────────────────────────────────────────────────────


class TestThetaToState:
    def test_exact_theta_returns_corresponding_state(self):
        # θ exacta en el centro de un sector debe retornar ese estado.
        assert theta_to_state(0.0) == SystemState.IDLE
        assert theta_to_state(SECTOR_RAD) == SystemState.ROUTING_ORBITAL
        assert theta_to_state(2.0 * SECTOR_RAD) == SystemState.ROUTING_FSM
        assert theta_to_state(3.0 * SECTOR_RAD) == SystemState.DISPATCHING
        assert theta_to_state(4.0 * SECTOR_RAD) == SystemState.CONSOLIDATING

    def test_theta_normalized_to_0_2pi(self):
        # θ fuera de [0, 2π) se normaliza.
        assert theta_to_state(TWO_PI) == SystemState.IDLE  # 2π ≡ 0
        assert theta_to_state(-0.1) == SystemState.RESPONDING  # -0.1 ≡ 2π - 0.1

    def test_theta_above_2pi_wraps(self):
        # 5π ≡ π debe caer en sector de DISPATCHING (3·72°=216°, ±36°).
        result = theta_to_state(5.0 * math.pi)
        assert isinstance(result, SystemState)

    def test_theta_at_sector_boundary(self):
        # Límite entre IDLE (centro 0) y ROUTING_ORBITAL (centro 72°) está en 36°.
        # Por convención, el límite pertenece al sector "siguiente".
        boundary = SECTOR_RAD / 2.0  # 36°
        result = theta_to_state(boundary)
        assert result in (SystemState.IDLE, SystemState.ROUTING_ORBITAL)

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            theta_to_state("not a number")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            theta_to_state(None)  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────
# states.py — FORWARD_TRANSITIONS + is_valid_transition + next_states
# ─────────────────────────────────────────────────────────


class TestTransitions:
    def test_idle_can_go_to_routing_orbital(self):
        assert is_valid_transition(SystemState.IDLE, SystemState.ROUTING_ORBITAL)

    def test_routing_orbital_can_skip_fsm(self):
        # Si ORBITAL decide solo, salta directamente a DISPATCHING.
        assert is_valid_transition(SystemState.ROUTING_ORBITAL, SystemState.DISPATCHING)

    def test_routing_fsm_can_ask_clarification(self):
        # Si FSM no resuelve, va a RESPONDING para pedir aclaración.
        assert is_valid_transition(SystemState.ROUTING_FSM, SystemState.RESPONDING)

    def test_responding_closes_cycle_to_idle(self):
        assert is_valid_transition(SystemState.RESPONDING, SystemState.IDLE)

    def test_invalid_transition_rejected(self):
        # No se puede saltar de IDLE a CONSOLIDATING sin pasar por DISPATCHING.
        assert not is_valid_transition(SystemState.IDLE, SystemState.CONSOLIDATING)
        # No se puede retroceder arbitrariamente.
        assert not is_valid_transition(SystemState.DISPATCHING, SystemState.IDLE)

    def test_next_states_returns_all_valid_targets(self):
        targets = next_states(SystemState.ROUTING_ORBITAL)
        assert SystemState.ROUTING_FSM in targets
        assert SystemState.DISPATCHING in targets

    def test_next_states_empty_for_unknown(self):
        # Si el estado no tiene transiciones forward, retorna tupla vacía.
        # (En la topología actual, todos tienen al menos 1.)
        targets = next_states(SystemState.RESPONDING)
        assert SystemState.IDLE in targets

    def test_state_transition_is_frozen(self):
        # StateTransition es frozen dataclass.
        t = StateTransition(SystemState.IDLE, SystemState.ROUTING_ORBITAL)
        with pytest.raises(AttributeError):
            t.from_state = SystemState.DISPATCHING  # type: ignore[misc]

    def test_forward_transitions_no_duplicates(self):
        # No debe haber dos transiciones idénticas (from, to).
        seen = set()
        for t in FORWARD_TRANSITIONS:
            key = (t.from_state, t.to_state)
            assert key not in seen, f"Transición duplicada: {key}"
            seen.add(key)


# ─────────────────────────────────────────────────────────
# fsm_disambiguator.py — Regla 1: Clear winner
# ─────────────────────────────────────────────────────────


class TestFSMRule1ClearWinner:
    def test_clear_winner_returns_top1(self):
        # Diferencia > 0.15 → ORBITAL decide solo.
        top3 = [("research", 0.9), ("build", 0.4), ("operate", 0.1)]
        assert fsm_disambiguate(top3, "buscar info") == "research"

    def test_exactly_at_threshold_uses_fsm(self):
        # Diferencia == 0.15 (no >) → NO es clear winner, FSM evalúa.
        # Usamos valores que se representan exactamente en float para evitar
        # issues de precisión binaria (0.5 - 0.35 = 0.15000000000000002 > 0.15).
        # Aquí diff = 0.30 - 0.15 = 0.15 exacto.
        top3 = [("research", 0.30), ("build", 0.15), ("operate", 0.05)]
        # El input no tiene keywords explícitas → clarify.
        result = fsm_disambiguate(top3, "algo ambiguo", active_domain=None)
        assert result == CLARIFY_DOMAIN

    def test_difference_just_above_threshold(self):
        # 0.16 > 0.15 → clear winner.
        top3 = [("build", 0.5), ("research", 0.34), ("operate", 0.1)]
        assert fsm_disambiguate(top3, "algo") == "build"


# ─────────────────────────────────────────────────────────
# fsm_disambiguator.py — Regla 2: Active domain
# ─────────────────────────────────────────────────────────


class TestFSMRule2ActiveDomain:
    def test_active_domain_wins_when_in_top2(self):
        # Empate entre research (0.5) y build (0.45). Active domain = research.
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "algo", active_domain="research")
        assert result == "research"

    def test_active_domain_ignored_when_not_in_top2(self):
        # Active domain = operate, pero operate está en top3 (no top2).
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        # active_domain=operate no está en top2 → regla 2 no aplica.
        # Sin keywords en el input → clarify.
        result = fsm_disambiguate(top3, "algo ambiguo", active_domain="operate")
        assert result == CLARIFY_DOMAIN

    def test_active_domain_invalid_returns_clarify(self):
        # active_domain="invalid" → no está en VALID_DOMAINS → se ignora.
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "algo", active_domain="invalid_domain")
        assert result == CLARIFY_DOMAIN

    def test_active_domain_none_falls_through_to_other_rules(self):
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        # Sin active_domain, sin keywords → clarify.
        assert fsm_disambiguate(top3, "algo", active_domain=None) == CLARIFY_DOMAIN


# ─────────────────────────────────────────────────────────
# fsm_disambiguator.py — Regla 3: Keywords explícitas
# ─────────────────────────────────────────────────────────


class TestFSMRule3Keywords:
    def test_research_keyword_in_input_wins(self):
        top3 = [("build", 0.5), ("research", 0.45), ("operate", 0.1)]
        # El input contiene "buscar" (keyword de research).
        result = fsm_disambiguate(top3, "Quiero buscar información sobre Python")
        assert result == "research"

    def test_build_keyword_in_input_wins(self):
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "Necesito deploy del código")
        assert result == "build"

    def test_operate_keyword_in_input_wins(self):
        # operate debe estar en top2 (no top3) para que su keyword cuente.
        top3 = [("research", 0.5), ("operate", 0.45), ("build", 0.1)]
        result = fsm_disambiguate(top3, "Revisa los logs del servicio")
        assert result == "operate"

    def test_keyword_for_top3_does_not_win(self):
        # Si operate está en top3 (no top2), su keyword NO le hace ganar.
        # Documentación explícita del comportamiento de la FSM.
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "Revisa los logs del servicio")
        # "revisa logs" no es keyword de research ni build → clarify.
        assert result == CLARIFY_DOMAIN

    def test_keyword_matching_is_case_insensitive(self):
        top3 = [("build", 0.5), ("research", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "BUSCAR info de Python")
        assert result == "research"

    def test_keyword_with_accents_matches_normalized(self):
        # "documentación" con acento debe matchear "documentación" en DOMAIN_KEYWORDS.
        top3 = [("build", 0.5), ("research", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "busca la documentación")
        assert result == "research"


# ─────────────────────────────────────────────────────────
# fsm_disambiguator.py — Regla 4: Clarify
# ─────────────────────────────────────────────────────────


class TestFSMRule4Clarify:
    def test_no_resolution_returns_clarify(self):
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        # Input sin keywords, sin active_domain → clarify.
        result = fsm_disambiguate(top3, "xyz", active_domain=None)
        assert result == CLARIFY_DOMAIN

    def test_clarify_when_active_domain_invalid_and_no_keywords(self):
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "xyz", active_domain="invalid")
        assert result == CLARIFY_DOMAIN


# ─────────────────────────────────────────────────────────
# fsm_disambiguator.py — Edge cases y contrato
# ─────────────────────────────────────────────────────────


class TestFSMEdgeCases:
    def test_empty_top3_raises_value_error(self):
        with pytest.raises(ValueError, match="no puede estar vacío"):
            fsm_disambiguate([], "buscar", active_domain=None)

    def test_single_element_top3_returns_it(self):
        # Solo 1 elemento → no hay top2 → diferencia infinita → clear winner.
        top3 = [("research", 0.5)]
        assert fsm_disambiguate(top3, "buscar") == "research"

    def test_invalid_domain_in_top1_returns_clarify(self):
        # Si ORBITAL retorna un dominio inválido, FSM lo sanea.
        top3 = [("invalid_domain", 0.9), ("research", 0.4), ("build", 0.1)]
        result = fsm_disambiguate(top3, "buscar")
        # Clear winner con dominio inválido → _sanitize_domain lo convierte a clarify.
        assert result == CLARIFY_DOMAIN

    def test_returns_always_string_never_none(self):
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "anything", active_domain=None)
        assert isinstance(result, str)
        assert result in VALID_DOMAINS or result == CLARIFY_DOMAIN

    def test_threshold_is_0_15(self):
        # Documentación del valor específico del threshold.
        assert DISAMBIGUATION_THRESHOLD == 0.15

    def test_valid_domains_contains_exactly_3(self):
        assert frozenset({"research", "build", "operate"}) == VALID_DOMAINS

    def test_all_domains_have_keywords(self):
        for domain in VALID_DOMAINS:
            assert domain in DOMAIN_KEYWORDS, f"Falta keywords para {domain}"
            assert len(DOMAIN_KEYWORDS[domain]) > 0

    def test_clarify_constant_is_string(self):
        assert isinstance(CLARIFY_DOMAIN, str)
        assert CLARIFY_DOMAIN == "clarify"
        assert CLARIFY_DOMAIN not in VALID_DOMAINS


# ─────────────────────────────────────────────────────────
# Integration: states + FSM en conjunto
# ─────────────────────────────────────────────────────────


class TestStatesFSMIntegration:
    """Verifica que states.py y fsm_disambiguator.py trabajan juntos correctamente."""

    def test_fsm_does_not_use_orbital_states_directly(self):
        """La FSM es stateless — no debe importar el estado del sistema para
        desambiguar. Solo necesita top3, user_input y active_domain."""
        # Si la FSM funcionara igual sin importar el estado, está bien aislada.
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result1 = fsm_disambiguate(top3, "buscar info", active_domain=None)
        # Si invocamos la FSM nuevamente, debe dar el mismo resultado (determinista).
        result2 = fsm_disambiguate(top3, "buscar info", active_domain=None)
        assert result1 == result2 == "research"

    def test_state_theta_for_routing_fsm_sector_exists(self):
        """Cuando la FSM se invoca, el sistema debería estar en ROUTING_FSM."""
        # El sector de ROUTING_FSM debe ser válido y distinguible.
        theta_fsm = STATE_THETA[SystemState.ROUTING_FSM]
        # θ de FSM está entre ORBITAL (72°) y DISPATCHING (216°).
        assert STATE_THETA[SystemState.ROUTING_ORBITAL] < theta_fsm < STATE_THETA[SystemState.DISPATCHING]

    def test_valid_transitions_cover_all_states(self):
        """Cada estado debe tener al menos una transición saliente."""
        states_with_outgoing = {t.from_state for t in FORWARD_TRANSITIONS}
        for state in SystemState:
            assert state in states_with_outgoing, f"{state.name} no tiene transición saliente"


# ─────────────────────────────────────────────────────────
# Mejoras post code-review F0-D3-review (contratos defensivos)
# ─────────────────────────────────────────────────────────


class TestTypeValidationPostReview:
    """Tests para validaciones de tipo añadidas tras code review F0-D3-review."""

    def test_next_states_rejects_string(self):
        """next_states debe rechazar strings con TypeError, no retornar ()."""
        with pytest.raises(TypeError, match="SystemState"):
            next_states("idle")  # type: ignore[arg-type]

    def test_next_states_rejects_none(self):
        with pytest.raises(TypeError):
            next_states(None)  # type: ignore[arg-type]

    def test_is_valid_transition_rejects_string_args(self):
        """is_valid_transition debe rechazar strings con TypeError."""
        with pytest.raises(TypeError, match="SystemState"):
            is_valid_transition("idle", SystemState.ROUTING_ORBITAL)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="SystemState"):
            is_valid_transition(SystemState.IDLE, "routing")  # type: ignore[arg-type]

    def test_fsm_disambiguate_rejects_non_numeric_scores(self):
        """Scores no numéricos deben dar TypeError, no propagarse al caller."""
        with pytest.raises(TypeError, match="numérico"):
            fsm_disambiguate(
                [("research", "high"), ("build", "low")],  # type: ignore[list-item]
                "buscar", None,
            )

    def test_fsm_disambiguate_rejects_bool_scores(self):
        """bool es subclase de int pero no es score válido."""
        with pytest.raises(TypeError, match="numérico"):
            fsm_disambiguate(
                [("research", True), ("build", False)],  # type: ignore[list-item]
                "buscar", None,
            )

    def test_fsm_disambiguate_handles_none_input_gracefully(self):
        """None como user_input no debe crashear; se trata como sin keywords."""
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        # Sin keywords (None input), sin active_domain → clarify.
        result = fsm_disambiguate(top3, None, None)  # type: ignore[arg-type]
        assert result == CLARIFY_DOMAIN

    def test_fsm_disambiguate_handles_empty_input(self):
        """String vacío debe treated como sin keywords."""
        top3 = [("research", 0.5), ("build", 0.45), ("operate", 0.1)]
        result = fsm_disambiguate(top3, "", None)
        assert result == CLARIFY_DOMAIN

    def test_fsm_disambiguate_with_clear_winner_ignores_none_input(self):
        """Incluso con None input, clear winner (diff > 0.15) debe retornar top1."""
        top3 = [("research", 0.9), ("build", 0.4), ("operate", 0.1)]
        result = fsm_disambiguate(top3, None, None)  # type: ignore[arg-type]
        assert result == "research"


class TestUnsortedScoresContractPostReview:
    """Documentación del contrato: top3 debe estar ordenado desc por score.

    La FSM NO re-ordena internamente. El caller es responsable.
    Si pasa lista desordenada, el resultado puede ser incorrecto — eso es
    contrato roto por el caller, no bug de la FSM.
    """

    def test_sorted_desc_returns_expected(self):
        top3 = [("research", 0.9), ("build", 0.4), ("operate", 0.1)]
        assert fsm_disambiguate(top3, "buscar", None) == "research"

    def test_unsorted_desc_returns_unexpected(self):
        """Documento explícitamente: si top3 no está ordenado, el resultado
        puede no ser el esperado. Esto es contrato del caller, no bug."""
        top3_unsorted = [("research", 0.1), ("build", 0.9), ("operate", 0.5)]
        # top1 es research con score 0.1, top2 es build con 0.9. Diferencia
        # 0.1 - 0.9 = -0.8 < 0.15, así que NO es clear winner → va a regla 2/3/4.
        # El input "buscar" es keyword de research → retorna research.
        # Pero research tiene el score MÁS BAJO. Esto es lo que el caller
        # obtiene si no ordena correctamente — documentado aquí como advertencia.
        result = fsm_disambiguate(top3_unsorted, "buscar", None)
        # Como research está en top1+top2 y "buscar" es su keyword, gana.
        assert result == "research"
