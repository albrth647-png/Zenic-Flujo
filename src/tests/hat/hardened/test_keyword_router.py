"""Tests para KeywordRouter — keyword override + FSM desambiguación.

Cubre:
- Keyword override (M10.1): si el mensaje tiene keywords de un dominio en top3, gana.
- FSM delegada: clear winner, active domain, keywords, clarify.
- Casos edge: top3 vacío, message vacío, dominios inválidos.
- Helpers: get_keywords_for_domain, is_valid_domain.
"""
from __future__ import annotations

import pytest

from src.hat.level1_orchestrator.fsm.disambiguator import (
    CLARIFY_DOMAIN,
    DISAMBIGUATION_THRESHOLD,
    DOMAIN_KEYWORDS,
    VALID_DOMAINS,
)
from src.hat.level1_orchestrator.routing.keyword_router import KeywordRouter

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def router() -> KeywordRouter:
    """KeywordRouter sin dominio activo."""
    return KeywordRouter(active_domain=None)


@pytest.fixture
def router_with_active() -> KeywordRouter:
    """KeywordRouter con active_domain='operaciones'."""
    return KeywordRouter(active_domain="operaciones")


# ── Tests de disambiguate — casos base ─────────────────────────────────


class TestDisambiguateBase:
    """Comportamiento base de disambiguate()."""

    def test_disambiguate_returns_clarify_when_top3_empty(
        self, router: KeywordRouter,
    ) -> None:
        """top3 vacío → 'clarify'."""
        assert router.disambiguate([], "listar leads") == CLARIFY_DOMAIN

    def test_disambiguate_returns_clarify_when_no_keyword_and_no_clear(
        self, router: KeywordRouter,
    ) -> None:
        """Sin keywords, sin clear winner, sin active domain → 'clarify'."""
        # top3 con dos dominios muy cercanos (diff < 0.15)
        top3 = [
            ("operaciones", 0.5),
            ("comunicaciones", 0.45),
            ("datos_auto", 0.3),
        ]
        # Mensaje sin keywords de ningún dominio
        result = router.disambiguate(top3, "xyz abc qwerty")
        assert result == CLARIFY_DOMAIN

    def test_disambiguate_returns_clear_winner(
        self, router: KeywordRouter,
    ) -> None:
        """Si top1 - top2 > threshold, FSM retorna top1 (clear winner)."""
        top3 = [
            ("operaciones", 0.9),
            ("comunicaciones", 0.3),  # diff = 0.6 > 0.15
            ("datos_auto", 0.1),
        ]
        result = router.disambiguate(top3, "xyz qwerty")
        assert result == "operaciones"


# ── Tests de keyword override (M10.1) ──────────────────────────────────


class TestKeywordOverride:
    """M10.1: si el mensaje tiene keywords de un dominio en top3, gana."""

    def test_keyword_override_operaciones(
        self, router: KeywordRouter,
    ) -> None:
        """Mensaje con 'lead' → operaciones (aunque no sea clear winner)."""
        top3 = [
            ("comunicaciones", 0.5),
            ("operaciones", 0.45),  # diff < 0.15 → FSM intentaría
            ("datos_auto", 0.3),
        ]
        result = router.disambiguate(top3, "listar leads del CRM")
        assert result == "operaciones"

    def test_keyword_override_comunicaciones(
        self, router: KeywordRouter,
    ) -> None:
        """Mensaje con 'email' → comunicaciones (sin keywords de operaciones)."""
        top3 = [
            ("operaciones", 0.5),
            ("comunicaciones", 0.45),
            ("datos_auto", 0.3),
        ]
        # Mensaje solo con keyword de comunicaciones (sin 'cliente' que es de operaciones)
        result = router.disambiguate(top3, "enviar email al contacto")
        assert result == "comunicaciones"

    def test_keyword_override_datos_auto(
        self, router: KeywordRouter,
    ) -> None:
        """Mensaje con 'python' → datos_auto."""
        top3 = [
            ("operaciones", 0.5),
            ("comunicaciones", 0.45),
            ("datos_auto", 0.3),
        ]
        result = router.disambiguate(top3, "ejecutar código python")
        assert result == "datos_auto"

    def test_keyword_override_returns_first_match_in_top3_order(
        self, router: KeywordRouter,
    ) -> None:
        """Si múltiples dominios matchean, gana el de mayor resonancia (primero en top3)."""
        # Mensaje que contiene keywords de operaciones Y comunicaciones
        top3 = [
            ("operaciones", 0.6),  # gana porque aparece primero
            ("comunicaciones", 0.55),
        ]
        # "lead" es de operaciones, "email" es de comunicaciones
        result = router.disambiguate(top3, "crear lead y enviar email")
        assert result == "operaciones"

    def test_keyword_override_ignores_domain_not_in_top3(
        self, router: KeywordRouter,
    ) -> None:
        """Si el keyword es de un dominio NO en top3, no se considera."""
        top3 = [
            ("operaciones", 0.9),  # clear winner igual
            ("comunicaciones", 0.1),
        ]
        # 'python' es de datos_auto que no está en top3
        result = router.disambiguate(top3, "ejecutar python")
        # No hay override → FSM clear winner → operaciones
        assert result == "operaciones"


# ── Tests de FSM delegada ──────────────────────────────────────────────


class TestFSMDelegation:
    """Cuando no hay keyword override, delega a fsm_disambiguate."""

    def test_fsm_clear_winner(
        self, router: KeywordRouter,
    ) -> None:
        """Sin keywords, clear winner → top1."""
        top3 = [
            ("operaciones", 0.9),
            ("comunicaciones", 0.3),  # diff > threshold
        ]
        result = router.disambiguate(top3, "xyz qwerty")
        assert result == "operaciones"

    def test_fsm_active_domain_in_top2(
        self, router_with_active: KeywordRouter,
    ) -> None:
        """Sin keywords, no clear winner, active_domain en top2 → active_domain."""
        top3 = [
            ("comunicaciones", 0.5),
            ("operaciones", 0.45),  # active_domain='operaciones' está aquí
            ("datos_auto", 0.3),
        ]
        result = router_with_active.disambiguate(top3, "xyz qwerty")
        assert result == "operaciones"

    def test_fsm_clarify_when_no_rule_resolves(
        self, router: KeywordRouter,
    ) -> None:
        """Sin keywords, no clear winner, no active domain → clarify."""
        top3 = [
            ("operaciones", 0.5),
            ("comunicaciones", 0.45),
        ]
        result = router.disambiguate(top3, "xyz qwerty")
        assert result == CLARIFY_DOMAIN


# ── Tests de match_keyword_domain ──────────────────────────────────────


class TestMatchKeywordDomain:
    """Matching de keywords contra el mensaje."""

    def test_match_returns_none_for_empty_message(
        self, router: KeywordRouter,
    ) -> None:
        """Mensaje vacío → None."""
        top3 = [("operaciones", 0.9)]
        assert router.match_keyword_domain("", top3) is None

    def test_match_returns_none_for_non_string_message(
        self, router: KeywordRouter,
    ) -> None:
        """Mensaje no-string → None (defensivo)."""
        top3 = [("operaciones", 0.9)]
        assert router.match_keyword_domain(None, top3) is None  # type: ignore[arg-type]
        assert router.match_keyword_domain(123, top3) is None  # type: ignore[arg-type]

    def test_match_is_case_insensitive(
        self, router: KeywordRouter,
    ) -> None:
        """El matching es case-insensitive."""
        top3 = [("operaciones", 0.9)]
        assert router.match_keyword_domain("LISTAR LEADS", top3) == "operaciones"
        assert router.match_keyword_domain("Listar Leads", top3) == "operaciones"
        assert router.match_keyword_domain("listar leads", top3) == "operaciones"

    def test_match_returns_none_when_no_keyword_in_message(
        self, router: KeywordRouter,
    ) -> None:
        """Sin keyword en mensaje → None."""
        top3 = [("operaciones", 0.9)]
        assert router.match_keyword_domain("xyz abc qwerty", top3) is None

    def test_match_skips_invalid_domains_in_top3(
        self, router: KeywordRouter,
    ) -> None:
        """Dominios no canónicos en top3 se skipenan."""
        top3 = [
            ("invalid_domain", 0.9),
            ("operaciones", 0.5),
        ]
        # 'invalid_domain' no está en VALID_DOMAINS → se skip
        # 'operaciones' sí, y 'lead' está en su keywords
        result = router.match_keyword_domain("listar leads", top3)
        assert result == "operaciones"


# ── Tests de set_active_domain ─────────────────────────────────────────


class TestSetActiveDomain:
    """Actualización del dominio activo en runtime."""

    def test_set_active_domain_updates_state(
        self, router: KeywordRouter,
    ) -> None:
        """set_active_domain actualiza el dominio activo."""
        assert router._active_domain is None
        router.set_active_domain("operaciones")
        assert router._active_domain == "operaciones"

    def test_set_active_domain_to_none_resets(
        self, router_with_active: KeywordRouter,
    ) -> None:
        """set_active_domain(None) resetea el dominio activo."""
        assert router_with_active._active_domain == "operaciones"
        router_with_active.set_active_domain(None)
        assert router_with_active._active_domain is None


# ── Tests de helpers de inspección ─────────────────────────────────────


class TestInspectionHelpers:
    """Helpers estáticos para inspección de keywords y dominios."""

    def test_get_keywords_for_operaciones(
        self, router: KeywordRouter,
    ) -> None:
        """get_keywords_for_domain retorna las keywords de operaciones."""
        keywords = router.get_keywords_for_domain("operaciones")
        assert isinstance(keywords, tuple)
        assert len(keywords) > 0
        assert "lead" in keywords
        assert "cliente" in keywords

    def test_get_keywords_for_unknown_domain_returns_empty(
        self, router: KeywordRouter,
    ) -> None:
        """get_keywords_for_domain retorna () para dominio desconocido."""
        assert router.get_keywords_for_domain("unknown") == ()

    def test_is_valid_domain_returns_true_for_canonical(
        self, router: KeywordRouter,
    ) -> None:
        """is_valid_domain retorna True para dominios canónicos."""
        for domain in ("operaciones", "comunicaciones", "datos_auto"):
            assert router.is_valid_domain(domain) is True

    def test_is_valid_domain_returns_false_for_unknown(
        self, router: KeywordRouter,
    ) -> None:
        """is_valid_domain retorna False para dominios no canónicos."""
        assert router.is_valid_domain("unknown") is False
        assert router.is_valid_domain("") is False

    def test_valid_domains_includes_current_canonical(
        self, router: KeywordRouter,
    ) -> None:
        """VALID_DOMAINS incluye los 3 dominios canónicos M8."""
        for domain in ("operaciones", "comunicaciones", "datos_auto"):
            assert domain in VALID_DOMAINS

    def test_threshold_is_0_15(self) -> None:
        """DISAMBIGUATION_THRESHOLD es 0.15 (valor del plan maestro)."""
        assert DISAMBIGUATION_THRESHOLD == 0.15

    def test_domain_keywords_has_all_3_canonical(
        self, router: KeywordRouter,
    ) -> None:
        """DOMAIN_KEYWORDS tiene entradas para los 3 dominios canónicos."""
        for domain in ("operaciones", "comunicaciones", "datos_auto"):
            assert domain in DOMAIN_KEYWORDS
            assert len(DOMAIN_KEYWORDS[domain]) > 0


# ── Tests de edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    """Casos edge y robustez."""

    def test_disambiguate_with_single_domain_in_top3(
        self, router: KeywordRouter,
    ) -> None:
        """top3 con un solo elemento → ese dominio si hay keyword, sino FSM."""
        top3 = [("operaciones", 0.9)]
        # Con keyword
        assert router.disambiguate(top3, "listar leads") == "operaciones"
        # Sin keyword, pero con clear winner (no hay top2, diff = 0.9 > threshold)
        assert router.disambiguate(top3, "xyz") == "operaciones"

    def test_disambiguate_preserves_top3_order_for_tie(
        self, router: KeywordRouter,
    ) -> None:
        """Empate de keywords entre dos dominios: gana el primero en top3."""
        top3 = [
            ("comunicaciones", 0.5),  # 'email' en sus keywords
            ("operaciones", 0.5),     # 'lead' en sus keywords
        ]
        # Mensaje con ambos keywords
        result = router.disambiguate(top3, "enviar email sobre lead")
        # comunicaciones aparece primero en top3 → gana
        assert result == "comunicaciones"

    def test_repr_includes_active_domain(
        self, router_with_active: KeywordRouter,
    ) -> None:
        """__repr__ incluye el active_domain."""
        repr_str = repr(router_with_active)
        assert "operaciones" in repr_str
        assert "KeywordRouter" in repr_str
