"""
Tests para ledger/ovc_bridge.py (F0-D4).

Cobertura:
- __init__ con dependencias inyectadas y defaults
- load_session: Facts, Hypotheses, Plan, Agent Cards + idempotencia + aislamiento por sesión
- persist_session: snapshot OVC → Facts/Hypotheses
- Helpers: _make_session_prefix sanitization, _deterministic_theta
- Edge cases: sesión vacía, sesión sin plan,Agent Cards globales
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.hat.level1_orchestrator.ledger.ovc_bridge import (
    FACT_GROUP,
    FACT_THETA,
    FACT_VELOCITY,
    HYPOTHESIS_GROUP,
    HYPOTHESIS_THETA,
    HYPOTHESIS_VELOCITY,
    OVCLedgerBridge,
    SESSION_VAR_PREFIX,
)
from src.orbital.context import OrbitalContext


@pytest.fixture
def repo():
    """LedgerRepository fresco para cada test."""
    return LedgerRepository()


@pytest.fixture
def ctx():
    """OrbitalContext singleton — se resetea entre tests para aislamiento."""
    OrbitalContext._reset()
    return OrbitalContext()


@pytest.fixture
def bridge(repo, ctx):
    """OVCLedgerBridge con dependencias inyectadas."""
    return OVCLedgerBridge(repo=repo, ctx=ctx)


@pytest.fixture
def session():
    """Session IDs únicos por test."""
    ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
    return {
        "user_id": f"bridge_user_{ts}",
        "session_id": f"bridge_sess_{ts}",
    }


@pytest.fixture(autouse=True)
def cleanup_orbital_context():
    """Limpia el singleton OrbitalContext después de cada test."""
    yield
    OrbitalContext._reset()


# ─────────────────────────────────────────────────────────
# __init__ y construcción
# ─────────────────────────────────────────────────────────


class TestOVCLedgerBridgeInit:
    def test_init_with_explicit_dependencies(self, repo, ctx):
        bridge = OVCLedgerBridge(repo=repo, ctx=ctx)
        assert bridge._repo is repo
        assert bridge._ctx is ctx

    def test_init_with_defaults_uses_singletons(self):
        """Si no se pasan deps, se usan los singletons (LedgerRepository y OrbitalContext)."""
        OrbitalContext._reset()
        bridge = OVCLedgerBridge()
        assert isinstance(bridge._repo, LedgerRepository)
        # OrbitalContext debe ser el singleton.
        assert bridge._ctx is OrbitalContext()


# ─────────────────────────────────────────────────────────
# load_session — Facts
# ─────────────────────────────────────────────────────────


class TestLoadSessionFacts:
    def test_load_session_returns_counts_dict(self, bridge, session):
        counts = bridge.load_session(session["user_id"], session["session_id"])
        assert isinstance(counts, dict)
        assert "facts" in counts
        assert "hypotheses" in counts
        assert "plan_steps" in counts
        assert "cards" in counts

    def test_load_session_with_no_data_returns_zeros(self, bridge, session):
        """Session sin Facts/Hypotheses/Plan: solo carga cards globales existentes."""
        counts = bridge.load_session(session["user_id"], session["session_id"])
        # Facts/Hypotheses/Plan son por sesión → 0 si no hay datos.
        # Cards son globales (definidas a nivel sistema) → pueden existir de tests previos.
        assert counts["facts"] == 0
        assert counts["hypotheses"] == 0
        assert counts["plan_steps"] == 0
        assert counts["cards"] >= 0  # tolerar cards globales preexistentes

    def test_load_session_loads_facts_as_ovc_variables(self, bridge, session):
        # Usar nombre único de fact por sesión para evitar colisiones en DB persistente.
        fact_key = f"user_lang_{session['session_id']}"
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, "es",
            confidence=1.0,
        )
        counts = bridge.load_session(session["user_id"], session["session_id"])
        assert counts["facts"] == 1

        # Verificar que la variable existe en el OVC con el prefijo correcto
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var = bridge._ctx.ovc.get_variable(f"{prefix}fact_{fact_key}")
        assert var is not None
        assert var.theta == FACT_THETA
        assert var.velocity == FACT_VELOCITY
        assert var.orbit_group == FACT_GROUP
        assert var.metadata["type"] == "fact"
        assert var.metadata["key"] == fact_key
        assert var.metadata["value"] == "es"

    def test_load_session_facts_use_stored_orbital_metadata(self, bridge, session):
        """Si el Fact tiene orbital_theta/amplitude guardados, se usan."""
        fact_key = f"with_theta_{session['session_id']}"
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, "v",
            confidence=0.85, orbital_theta=1.5, orbital_amplitude=2.5,
        )
        bridge.load_session(session["user_id"], session["session_id"])
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var = bridge._ctx.ovc.get_variable(f"{prefix}fact_{fact_key}")
        assert var.theta == 1.5
        assert var.amplitude == 2.5


# ─────────────────────────────────────────────────────────
# load_session — Hypotheses
# ─────────────────────────────────────────────────────────


class TestLoadSessionHypotheses:
    def test_load_session_loads_unverified_hypotheses_only(self, bridge, session):
        # Nombres únicos por sesión para evitar colisiones en DB persistente.
        h1_key = f"h1_{session['session_id']}"
        h2_key = f"h2_{session['session_id']}"
        bridge._repo.upsert_hypothesis(
            session["user_id"], session["session_id"], h1_key, "v1",
        )
        bridge._repo.upsert_hypothesis(
            session["user_id"], session["session_id"], h2_key, "v2",
        )
        # Verificar h1 — ya no se carga
        bridge._repo.verify_hypothesis(
            session["user_id"], session["session_id"], h1_key,
        )
        counts = bridge.load_session(session["user_id"], session["session_id"])
        assert counts["hypotheses"] == 1

        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        # h1 verificada no debe cargarse
        assert bridge._ctx.ovc.get_variable(f"{prefix}hyp_{h1_key}") is None
        # h2 no verificada sí debe cargarse
        var_h2 = bridge._ctx.ovc.get_variable(f"{prefix}hyp_{h2_key}")
        assert var_h2 is not None
        assert var_h2.orbit_group == HYPOTHESIS_GROUP

    def test_hypothesis_default_theta_is_pi_over_4(self, bridge, session):
        hyp_key = f"default_theta_{session['session_id']}"
        bridge._repo.upsert_hypothesis(
            session["user_id"], session["session_id"], hyp_key, "v",
        )
        bridge.load_session(session["user_id"], session["session_id"])
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var = bridge._ctx.ovc.get_variable(f"{prefix}hyp_{hyp_key}")
        assert abs(var.theta - HYPOTHESIS_THETA) < 1e-6
        assert abs(var.theta - math.pi / 4.0) < 1e-6
        assert var.velocity == HYPOTHESIS_VELOCITY


# ─────────────────────────────────────────────────────────
# load_session — Plan
# ─────────────────────────────────────────────────────────


class TestLoadSessionPlan:
    def test_load_session_creates_plan_cycle_with_3_steps(self, bridge, session):
        for i in range(3):
            bridge._repo.add_plan_step(
                session["user_id"], session["session_id"],
                step_index=i, step_description=f"step{i}",
                assigned_domain="research",
            )
        counts = bridge.load_session(session["user_id"], session["session_id"])
        assert counts["plan_steps"] == 3

        # Verificar que las variables se crearon con θ distribuida uniformemente
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        for i in range(3):
            var = bridge._ctx.ovc.get_variable(f"{prefix}plan_step_{i}")
            assert var is not None
            expected_theta = (i * 2 * math.pi) / 3
            assert abs(var.theta - expected_theta) < 1e-6

    def test_load_session_plan_with_1_step_no_cycle(self, bridge, session):
        """Plan con <2 pasos no forma ciclo RCC."""
        bridge._repo.add_plan_step(
            session["user_id"], session["session_id"],
            step_index=0, step_description="only step",
        )
        counts = bridge.load_session(session["user_id"], session["session_id"])
        assert counts["plan_steps"] == 1
        # No debe haber ciclo con el nombre esperado
        cycles = bridge._ctx.rcc.get_cycles()
        cycle_names = [c.name for c in cycles.values()]
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        assert f"{prefix}plan_cycle" not in cycle_names


# ─────────────────────────────────────────────────────────
# load_session — Agent Cards (globales, no por sesión)
# ─────────────────────────────────────────────────────────


class TestLoadSessionAgentCards:
    def test_load_session_loads_all_agent_cards(self, bridge, session):
        """Cards globales: el count incluye cards preexistentes + las nuevas."""
        cards_before = len(bridge._repo.get_agent_cards())
        bridge._repo.upsert_agent_card(
            f"agent1_{session['session_id']}", "Agent 1", "research", "specialist",
            ["search"], ["buscar", "info"],
        )
        bridge._repo.upsert_agent_card(
            f"agent2_{session['session_id']}", "Agent 2", "build", "worker",
            ["compile"], ["código", "build"],
        )
        counts = bridge.load_session(session["user_id"], session["session_id"])
        # Debe haber cargado las 2 nuevas + las preexistentes.
        assert counts["cards"] == cards_before + 2

        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var1 = bridge._ctx.ovc.get_variable(f"{prefix}card_agent1_{session['session_id']}")
        var2 = bridge._ctx.ovc.get_variable(f"{prefix}card_agent2_{session['session_id']}")
        assert var1 is not None
        assert var2 is not None
        assert var1.orbit_group == "hat_cards_research"
        assert var2.orbit_group == "hat_cards_build"

    def test_agent_card_theta_is_deterministic(self, bridge, session):
        """La θ de una card se deriva deterministamente de sus keywords."""
        agent_id = f"agent_x_{session['session_id']}"
        bridge._repo.upsert_agent_card(
            agent_id, "Agent X", "research", "specialist",
            ["search"], ["buscar", "info"],
        )
        bridge.load_session(session["user_id"], session["session_id"])
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var = bridge._ctx.ovc.get_variable(f"{prefix}card_{agent_id}")

        # Calcular θ esperada con el mismo algoritmo
        import hashlib
        joined = "|".join(["buscar", "info"])
        expected_hash = int(hashlib.md5(joined.encode(), usedforsecurity=False).hexdigest()[:8], 16)
        expected_theta = (expected_hash % 10000) / 10000.0 * 2 * math.pi
        assert abs(var.theta - expected_theta) < 1e-9


# ─────────────────────────────────────────────────────────
# load_session — Idempotencia y aislamiento
# ─────────────────────────────────────────────────────────


class TestLoadSessionIdempotency:
    def test_load_session_is_idempotent(self, bridge, session):
        """Cargar la misma sesión 2 veces no duplica variables."""
        fact_key = f"idem_{session['session_id']}"
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, "v",
        )
        bridge.load_session(session["user_id"], session["session_id"])
        bridge.load_session(user_id=session["user_id"], session_id=session["session_id"])
        # Debe haber exactamente 1 variable fact (no 2)
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        fact_vars = [
            n for n in bridge._ctx.ovc.get_variable_names()
            if n.startswith(f"{prefix}fact_{fact_key}")
        ]
        assert len(fact_vars) == 1

    def test_load_session_isolates_by_session(self, bridge):
        """Dos sesiones diferentes no contaminan sus variables OVC."""
        ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
        sess_a = {"user_id": "u1", "session_id": f"sess_a_{ts}"}
        sess_b = {"user_id": "u1", "session_id": f"sess_b_{ts}"}

        # Usar el mismo fact_key pero en sesiones distintas → no deben colisionar.
        bridge._repo.upsert_fact(sess_a["user_id"], sess_a["session_id"], "k", "value_a")
        bridge._repo.upsert_fact(sess_b["user_id"], sess_b["session_id"], "k", "value_b")

        bridge.load_session(sess_a["user_id"], sess_a["session_id"])
        bridge.load_session(sess_b["user_id"], sess_b["session_id"])

        prefix_a = OVCLedgerBridge._make_session_prefix(sess_a["session_id"])
        prefix_b = OVCLedgerBridge._make_session_prefix(sess_b["session_id"])
        var_a = bridge._ctx.ovc.get_variable(f"{prefix_a}fact_k")
        var_b = bridge._ctx.ovc.get_variable(f"{prefix_b}fact_k")
        assert var_a.metadata["value"] == "value_a"
        assert var_b.metadata["value"] == "value_b"

    def test_load_session_cleans_previous_session_vars(self, bridge, session):
        """Si la sesión ya tenía variables OVC, se limpian antes de recargar."""
        fact_key = f"clean_{session['session_id']}"
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, "v1",
        )
        bridge.load_session(session["user_id"], session["session_id"])
        # Eliminar el fact del repo y recargar — la variable vieja debe desaparecer.
        bridge._repo.delete_fact(session["user_id"], session["session_id"], fact_key)
        bridge.load_session(session["user_id"], session["session_id"])

        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        assert bridge._ctx.ovc.get_variable(f"{prefix}fact_{fact_key}") is None


# ─────────────────────────────────────────────────────────
# persist_session
# ─────────────────────────────────────────────────────────


class TestPersistSession:
    def test_persist_session_returns_counts_dict(self, bridge, session):
        counts = bridge.persist_session(session["user_id"], session["session_id"])
        assert counts == {"facts_persisted": 0, "hypotheses_persisted": 0}

    def test_persist_session_round_trip(self, bridge, session):
        """load → mutate θ → persist → load debe conservar la θ mutada."""
        fact_key = f"rt_{session['session_id']}"
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, "v",
            orbital_theta=0.0, orbital_amplitude=1.0,
        )
        bridge.load_session(session["user_id"], session["session_id"])

        # Mutar la θ del fact en el OVC
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var = bridge._ctx.ovc.get_variable(f"{prefix}fact_{fact_key}")
        var.theta = 1.234  # type: ignore[misc]  # mutar para test

        # Persistir
        counts = bridge.persist_session(session["user_id"], session["session_id"])
        assert counts["facts_persisted"] == 1

        # Verificar que el Ledger tiene la θ mutada
        fact = bridge._repo.get_fact(session["user_id"], session["session_id"], fact_key)
        assert abs(fact["orbital_theta"] - 1.234) < 1e-6

    def test_persist_session_only_touches_session_vars(self, bridge):
        """persist_session no debe tocar variables de otras sesiones."""
        ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
        sess_a = {"user_id": "u1", "session_id": f"sess_a_{ts}"}
        sess_b = {"user_id": "u1", "session_id": f"sess_b_{ts}"}

        bridge._repo.upsert_fact(sess_a["user_id"], sess_a["session_id"], f"k_a_{ts}", "v_a")
        bridge._repo.upsert_fact(sess_b["user_id"], sess_b["session_id"], f"k_b_{ts}", "v_b")

        bridge.load_session(sess_a["user_id"], sess_a["session_id"])
        bridge.load_session(sess_b["user_id"], sess_b["session_id"])

        # Persistir solo sess_a
        counts = bridge.persist_session(sess_a["user_id"], sess_a["session_id"])
        assert counts["facts_persisted"] == 1

    def test_persist_session_skips_non_fact_hypothesis_vars(self, bridge, session):
        """Variables OVC que no son fact/hypothesis (ej: plan_step) no se persisten."""
        for i in range(3):
            bridge._repo.add_plan_step(
                session["user_id"], session["session_id"],
                step_index=i, step_description=f"step{i}",
            )
        bridge.load_session(session["user_id"], session["session_id"])

        counts = bridge.persist_session(session["user_id"], session["session_id"])
        # 3 plan_steps cargados pero 0 facts/hypotheses → 0 persistidos
        assert counts == {"facts_persisted": 0, "hypotheses_persisted": 0}

    def test_persist_session_writes_facts_and_hypotheses(self, bridge, session):
        """Round-trip completo: load → persist debe reflejar Facts + Hypotheses."""
        fact_key = f"f1_{session['session_id']}"
        hyp_key = f"h1_{session['session_id']}"
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, "fact_value",
        )
        bridge._repo.upsert_hypothesis(
            session["user_id"], session["session_id"], hyp_key, "hyp_value",
        )
        bridge.load_session(session["user_id"], session["session_id"])
        counts = bridge.persist_session(session["user_id"], session["session_id"])
        assert counts["facts_persisted"] == 1
        assert counts["hypotheses_persisted"] == 1


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────


class TestHelpers:
    def test_make_session_prefix_format(self):
        prefix = OVCLedgerBridge._make_session_prefix("abc123")
        assert prefix == "hat_abc123__"
        assert prefix.startswith(SESSION_VAR_PREFIX)
        assert prefix.endswith("__")

    def test_make_session_prefix_sanitizes_non_alnum(self):
        prefix = OVCLedgerBridge._make_session_prefix("sess-123.with/special")
        # Todo no-alfanumérico se reemplaza por _
        assert prefix == "hat_sess_123_with_special__"
        # No debe tener caracteres que rompan nombres de variable OVC
        assert "-" not in prefix
        assert "." not in prefix
        assert "/" not in prefix

    def test_make_session_prefix_handles_none(self):
        """None session_id debe manejarse defensivamente (str(None) = 'None')."""
        prefix = OVCLedgerBridge._make_session_prefix(None)  # type: ignore[arg-type]
        assert prefix == "hat_None__"

    def test_deterministic_theta_is_deterministic(self):
        """La misma lista de keywords siempre produce la misma θ."""
        theta1 = OVCLedgerBridge._deterministic_theta(["buscar", "info"])
        theta2 = OVCLedgerBridge._deterministic_theta(["buscar", "info"])
        assert theta1 == theta2

    def test_deterministic_theta_different_keywords_different_theta(self):
        theta1 = OVCLedgerBridge._deterministic_theta(["buscar"])
        theta2 = OVCLedgerBridge._deterministic_theta(["código"])
        assert theta1 != theta2

    def test_deterministic_theta_in_range_0_to_2pi(self):
        theta = OVCLedgerBridge._deterministic_theta(["test"])
        assert 0.0 <= theta < 2 * math.pi

    def test_deterministic_theta_empty_keywords(self):
        """Lista vacía de keywords debe dar una θ válida (no crash)."""
        theta = OVCLedgerBridge._deterministic_theta([])
        assert 0.0 <= theta < 2 * math.pi


# ─────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_load_session_empty_string_session_id(self, bridge):
        """session_id vacío debe funcionar (prefijo será 'hat___')."""
        counts = bridge.load_session("u", "")
        # Facts/Hypotheses/Plan por sesión = 0. Cards globales pueden existir.
        assert counts["facts"] == 0
        assert counts["hypotheses"] == 0
        assert counts["plan_steps"] == 0
        assert counts["cards"] >= 0

    def test_load_session_with_complex_fact_value(self, bridge, session):
        """Facts con valores JSON complejos se cargan correctamente."""
        fact_key = f"complex_{session['session_id']}"
        complex_value = {"nested": {"list": [1, 2, 3]}, "flag": True}
        bridge._repo.upsert_fact(
            session["user_id"], session["session_id"], fact_key, complex_value,
        )
        bridge.load_session(session["user_id"], session["session_id"])
        prefix = OVCLedgerBridge._make_session_prefix(session["session_id"])
        var = bridge._ctx.ovc.get_variable(f"{prefix}fact_{fact_key}")
        assert var.metadata["value"] == complex_value

    def test_load_session_does_not_touch_other_users_vars(self, bridge):
        """Variables de workflow ZF (prefijo 'wf_') no se tocan."""
        # Crear variable con prefijo 'wf_' (simulando workflow ZF)
        bridge._ctx.ovc.create_variable(
            name="wf_other_session__some_var",
            theta=0.5, amplitude=1.0, velocity=0.1,
        )
        bridge.load_session("any_user", "any_session")
        # La variable wf_ debe seguir existiendo
        assert bridge._ctx.ovc.get_variable("wf_other_session__some_var") is not None
