"""Tests para OrbitalRouter — routing por resonancia ORBITAL.

Cubre:
- Namespacing por session_id (cross-session pollution).
- Filtrado de Agent Cards por metadata.type='agent_card'.
- Cálculo de resonancia promedio normalizada en [0, 1].
- Top-3 dominios ordenados desc.
- Casos edge: sin cards, sin user_intent, cards con dominio 'unknown'.
- Idempotencia: route() dos veces no acumula variables.
"""
from __future__ import annotations

import math
from typing import Any

import pytest

from src.hat.level1_orchestrator.routing.orbital_router import (
    INTENT_AMPLITUDE,
    INTENT_THETA,
    INTENT_VELOCITY,
    ROUTING_ORBIT_GROUP,
    TOP_N_DOMAINS,
    OrbitalRouter,
)
from src.orbital.context import OrbitalContext

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_orbital_context() -> Any:
    """Reset del singleton OrbitalContext antes de cada test.

    Sin esto, las variables OVC de un test contaminan al siguiente.
    """
    OrbitalContext._reset()
    yield
    OrbitalContext._reset()


@pytest.fixture
def ctx() -> OrbitalContext:
    """OrbitalContext fresco para cada test."""
    return OrbitalContext()


@pytest.fixture
def router(ctx: OrbitalContext) -> OrbitalRouter:
    """OrbitalRouter con ctx inyectado y session_id='s1'."""
    return OrbitalRouter(ctx=ctx, session_id="s1")


def _publish_card(
    ctx: OrbitalContext,
    agent_id: str,
    domain: str,
    amplitude: float = 1.0,
    velocity: float = 0.05,
    keywords: list[str] | None = None,
) -> str:
    """Helper: publica una Agent Card en el OVC y retorna el nombre de la variable.

    Replica la lógica de CardPublisherMixin._inject_card_to_ovc pero sin
    requerir un specialist instanciado — útil para tests unitarios del router.
    """
    import hashlib

    # θ determinista desde keywords (igual que CardPublisherMixin)
    kw = keywords or [agent_id]
    joined = "|".join(kw)
    hash_val = int(hashlib.md5(joined.encode(), usedforsecurity=False).hexdigest()[:8], 16)
    theta = (hash_val % 10000) / 10000.0 * (2 * math.pi)

    var_name = f"card_{agent_id}"
    ctx.ovc.create_variable(
        name=var_name,
        theta=theta,
        amplitude=amplitude,
        velocity=velocity,
        orbit_group=f"hat_cards_{domain}",
        metadata={
            "type": "agent_card",
            "agent_id": agent_id,
            "domain": domain,
            "tier": "specialist",
            "capabilities": [],
        },
    )
    return var_name


# ── Tests de namespacing ───────────────────────────────────────────────


class TestNamespacing:
    """Namespacing por session_id para evitar cross-session pollution."""

    def test_get_intent_var_name_uses_session_id(
        self, router: OrbitalRouter,
    ) -> None:
        """El nombre de la variable incluye el session_id sanitizado."""
        name = router.get_intent_var_name()
        assert "s1" in name
        assert name.startswith("hat_")
        assert name.endswith("__user_intent_current")

    def test_get_intent_var_name_sanitizes_special_chars(
        self, ctx: OrbitalContext,
    ) -> None:
        """Caracteres no alfanuméricos en session_id se reemplazan por '_'."""
        router = OrbitalRouter(ctx=ctx, session_id="s-1/test!@#")
        name = router.get_intent_var_name()
        # Solo debe contener alfanum y _
        suffix = name[len("hat_"):]
        assert all(c.isalnum() or c == "_" for c in suffix)

    def test_two_sessions_have_different_intent_vars(
        self, ctx: OrbitalContext,
    ) -> None:
        """Dos sesiones distintas tienen variables user_intent distintas."""
        r1 = OrbitalRouter(ctx=ctx, session_id="s1")
        r2 = OrbitalRouter(ctx=ctx, session_id="s2")
        assert r1.get_intent_var_name() != r2.get_intent_var_name()

    def test_set_session_updates_var_name(
        self, router: OrbitalRouter,
    ) -> None:
        """set_session actualiza el session_id y por ende el var name."""
        name_before = router.get_intent_var_name()
        router.set_session("other_session")
        name_after = router.get_intent_var_name()
        assert name_before != name_after
        assert "other_session" in name_after


# ── Tests de route() sin cards ─────────────────────────────────────────


class TestRouteNoCards:
    """Comportamiento de route() cuando no hay Agent Cards registradas."""

    def test_route_returns_empty_when_no_cards(
        self, router: OrbitalRouter,
    ) -> None:
        """Sin Agent Cards, route() retorna lista vacía."""
        result = router.route("listar leads")
        assert result == []

    def test_route_creates_intent_variable_even_without_cards(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Aunque no haya cards, la variable user_intent se crea."""
        router.route("listar leads")
        intent_var = ctx.ovc.get_variable(router.get_intent_var_name())
        assert intent_var is not None
        assert intent_var.metadata["type"] == "user_intent"
        assert intent_var.metadata["text"] == "listar leads"

    def test_route_is_idempotent(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """route() dos veces no crea dos variables user_intent."""
        router.route("mensaje 1")
        router.route("mensaje 2")
        # Solo debe existir una variable user_intent
        intent_vars = [
            v for v in ctx.ovc.get_all_variables().values()
            if v.metadata.get("type") == "user_intent"
        ]
        assert len(intent_vars) == 1
        # Y debe tener el último mensaje
        assert intent_vars[0].metadata["text"] == "mensaje 2"


# ── Tests de route() con cards ─────────────────────────────────────────


class TestRouteWithCards:
    """Ruteo con Agent Cards registradas."""

    def test_route_returns_top3_when_3_domains(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Con 3 dominios distintos, route() retorna top-3."""
        _publish_card(ctx, "crm", "operaciones", amplitude=1.5)
        _publish_card(ctx, "notification", "comunicaciones", amplitude=1.0)
        _publish_card(ctx, "data", "datos_auto", amplitude=0.8)

        result = router.route("buscar leads")

        assert len(result) == 3
        domains = [d for d, _ in result]
        assert set(domains) == {"operaciones", "comunicaciones", "datos_auto"}

    def test_route_returns_at_most_top3(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Si hay más de 3 dominios, route() retorna solo 3."""
        for i, domain in enumerate(["d1", "d2", "d3", "d4", "d5"]):
            _publish_card(ctx, f"agent_{i}", domain, amplitude=1.0)

        result = router.route("test")

        assert len(result) == TOP_N_DOMAINS

    def test_route_results_are_sorted_desc(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Los resultados están ordenados por resonancia descendente."""
        _publish_card(ctx, "crm", "operaciones", amplitude=2.0)
        _publish_card(ctx, "notification", "comunicaciones", amplitude=0.5)

        result = router.route("listar leads")

        assert len(result) == 2
        assert result[0][1] >= result[1][1]

    def test_route_resonance_is_normalized(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Los valores de resonancia están en [0, 1]."""
        _publish_card(ctx, "crm", "operaciones", amplitude=1.5)
        _publish_card(ctx, "notification", "comunicaciones", amplitude=1.0)

        result = router.route("listar leads")

        for _, resonance in result:
            assert 0.0 <= resonance <= 1.0

    def test_route_filters_non_card_variables(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Solo las variables con metadata.type='agent_card' se consideran."""
        # Publicar una card real
        _publish_card(ctx, "crm", "operaciones")
        # Crear una variable que NO es agent_card (simula un fact)
        ctx.ovc.create_variable(
            name="hat_s1__fact_active_domain",
            theta=0.0, amplitude=1.0, velocity=0.0,
            orbit_group="hat_facts",
            metadata={"type": "fact", "key": "active_domain", "value": "operaciones"},
        )

        result = router.route("listar leads")

        # Solo debe retornar el dominio de la card, no del fact
        domains = [d for d, _ in result]
        assert "operaciones" in domains
        # No debe aparecer un dominio espurio por el fact
        assert len(domains) == 1


# ── Tests de collect_cards_by_domain ──────────────────────────────────


class TestCollectCards:
    """Recolección y agrupación de Agent Cards por dominio."""

    def test_collect_returns_empty_when_no_cards(
        self, router: OrbitalRouter,
    ) -> None:
        """Sin cards, collect_cards_by_domain retorna dict vacío."""
        assert router.collect_cards_by_domain() == {}

    def test_collect_groups_multiple_cards_per_domain(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Múltiples cards del mismo dominio se agrupan en una lista."""
        _publish_card(ctx, "crm", "operaciones")
        _publish_card(ctx, "invoice", "operaciones")
        _publish_card(ctx, "inventory", "operaciones")
        _publish_card(ctx, "notification", "comunicaciones")

        result = router.collect_cards_by_domain()

        assert "operaciones" in result
        assert "comunicaciones" in result
        assert len(result["operaciones"]) == 3
        assert len(result["comunicaciones"]) == 1

    def test_collect_assigns_unknown_domain_when_missing(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Cards sin metadata.domain se asignan a 'unknown'."""
        # Crear card sin domain en metadata
        ctx.ovc.create_variable(
            name="card_orphan",
            theta=0.0, amplitude=1.0, velocity=0.1,
            orbit_group="hat_cards_orphan",
            metadata={"type": "agent_card"},  # sin "domain" key
        )

        result = router.collect_cards_by_domain()

        assert "unknown" in result
        assert "card_orphan" in result["unknown"]


# ── Tests de compute_domain_resonance ──────────────────────────────────


class TestComputeResonance:
    """Cálculo de resonancia de un dominio."""

    def test_resonance_zero_when_no_cards(
        self, router: OrbitalRouter,
    ) -> None:
        """Sin cards, resonancia es 0.0."""
        assert router.compute_domain_resonance("operaciones", []) == 0.0

    def test_resonance_zero_when_no_intent(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Sin user_intent creado, resonancia es 0.0."""
        _publish_card(ctx, "crm", "operaciones")
        # No llamamos a route() — no hay user_intent
        assert router.compute_domain_resonance(
            "operaciones", ["card_crm"],
        ) == 0.0

    def test_resonance_in_range_when_intent_exists(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """Con user_intent y cards, resonancia está en [0, 1]."""
        _publish_card(ctx, "crm", "operaciones", amplitude=1.5)
        router.route("listar leads")  # crea user_intent

        resonance = router.compute_domain_resonance(
            "operaciones", ["card_crm"],
        )
        assert 0.0 <= resonance <= 1.0


# ── Tests de parámetros orbitales del intent ──────────────────────────


class TestIntentParameters:
    """Los parámetros orbitales del user_intent son los correctos."""

    def test_intent_has_correct_amplitude(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """El user_intent se crea con INTENT_AMPLITUDE=1.0."""
        router.route("test")
        intent_var = ctx.ovc.get_variable(router.get_intent_var_name())
        assert intent_var is not None
        assert intent_var.amplitude == INTENT_AMPLITUDE

    def test_intent_has_correct_theta(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """El user_intent se crea con INTENT_THETA=0.0."""
        router.route("test")
        intent_var = ctx.ovc.get_variable(router.get_intent_var_name())
        assert intent_var is not None
        assert intent_var.theta == INTENT_THETA

    def test_intent_has_correct_velocity(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """El user_intent se crea con INTENT_VELOCITY=0.1."""
        router.route("test")
        intent_var = ctx.ovc.get_variable(router.get_intent_var_name())
        assert intent_var is not None
        assert intent_var.velocity == INTENT_VELOCITY

    def test_intent_has_correct_orbit_group(
        self, router: OrbitalRouter, ctx: OrbitalContext,
    ) -> None:
        """El user_intent se crea con ROUTING_ORBIT_GROUP='hat_routing'."""
        router.route("test")
        intent_var = ctx.ovc.get_variable(router.get_intent_var_name())
        assert intent_var is not None
        assert intent_var.orbit_group == ROUTING_ORBIT_GROUP
