"""Tests para fsm_disambiguate — FSM de desambiguación de dominios.

Cubre las 4 reglas en orden de prioridad:
1. Clear winner: top1 - top2 > threshold → top1.
2. Active domain: si está en top2 → priorizarlo.
3. Keywords: si input menciona keyword de dominio en top2 → ese.
4. Clarify: si ninguna resuelve → 'clarify'.

Más validación de inputs (ValueError, TypeError) y casos edge.
"""
from __future__ import annotations

import pytest

from src.hat.level1_orchestrator.fsm.disambiguator import (
    CLARIFY_DOMAIN,
    DISAMBIGUATION_THRESHOLD,
    DOMAIN_KEYWORDS,
    VALID_DOMAINS,
    fsm_disambiguate,
)

# ── Tests de clear winner (regla 1) ────────────────────────────────────


class TestClearWinner:
    """Regla 1: si top1 - top2 > threshold, top1 gana sin más."""

    def test_clear_winner_returns_top1(self) -> None:
        """Diferencia grande → top1 sin invocar otras reglas."""
        top3 = [("operaciones", 0.9), ("comunicaciones", 0.3), ("datos_auto", 0.1)]
        assert fsm_disambiguate(top3, "xyz") == "operaciones"

    def test_clear_winner_with_single_element(self) -> None:
        """Con un solo elemento, diff = score - 0 = score → clear winner si > threshold."""
        top3 = [("operaciones", 0.5)]
        assert fsm_disambiguate(top3, "xyz") == "operaciones"

    def test_clear_winner_threshold_boundary(self) -> None:
        """En el boundary exacto (diff = threshold) NO es clear winner (strict >)."""
        # diff = 0.15 = threshold → NO es clear winner (usa >, no >=)
        top3 = [("operaciones", 0.30), ("comunicaciones", 0.15)]
        # Sin keywords ni active_domain → clarify
        assert fsm_disambiguate(top3, "xyz") == CLARIFY_DOMAIN

    def test_clear_winner_just_above_threshold(self) -> None:
        """Diff ligeramente mayor al threshold → clear winner."""
        top3 = [("operaciones", 0.31), ("comunicaciones", 0.15)]
        assert fsm_disambiguate(top3, "xyz") == "operaciones"


# ── Tests de active domain (regla 2) ───────────────────────────────────


class TestActiveDomain:
    """Regla 2: si active_domain está en top2 y es válido, gana."""

    def test_active_domain_in_top2_wins(self) -> None:
        """active_domain en top2 (no clear winner) → active_domain."""
        top3 = [
            ("comunicaciones", 0.5),
            ("operaciones", 0.45),  # active_domain aquí
            ("datos_auto", 0.3),
        ]
        result = fsm_disambiguate(top3, "xyz", active_domain="operaciones")
        assert result == "operaciones"

    def test_active_domain_not_in_top2_ignored(self) -> None:
        """Si active_domain no está en top2, se ignora."""
        top3 = [
            ("comunicaciones", 0.5),
            ("datos_auto", 0.45),
        ]
        # active_domain='operaciones' no está en top2 → se ignora
        # Sin keywords → clarify
        result = fsm_disambiguate(top3, "xyz", active_domain="operaciones")
        assert result == CLARIFY_DOMAIN

    def test_active_domain_none_skips_rule(self) -> None:
        """active_domain=None → regla 2 se skip, va a regla 3."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        # Sin active ni keywords → clarify
        assert fsm_disambiguate(top3, "xyz", active_domain=None) == CLARIFY_DOMAIN

    def test_active_domain_invalid_ignored(self) -> None:
        """active_domain no canónico → se ignora."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        result = fsm_disambiguate(top3, "xyz", active_domain="invalid_domain")
        assert result == CLARIFY_DOMAIN


# ── Tests de keywords (regla 3) ────────────────────────────────────────


class TestKeywords:
    """Regla 3: si input menciona keyword de dominio en top2, gana."""

    def test_keyword_in_top1_wins(self) -> None:
        """Keyword de top1 en input → top1."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        assert fsm_disambiguate(top3, "listar leads") == "operaciones"

    def test_keyword_in_top2_wins(self) -> None:
        """Keyword de top2 en input → top2 (override del ranking)."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        assert fsm_disambiguate(top3, "enviar email") == "comunicaciones"

    def test_no_keyword_match_falls_to_clarify(self) -> None:
        """Sin keyword match → clarify (si no hay active_domain)."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        assert fsm_disambiguate(top3, "xyz qwerty") == CLARIFY_DOMAIN

    def test_keyword_matching_is_case_insensitive(self) -> None:
        """El matching de keywords es case-insensitive."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        assert fsm_disambiguate(top3, "LISTAR LEADS") == "operaciones"

    def test_keyword_none_input_treated_as_empty(self) -> None:
        """user_input=None se trata como sin keywords."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        # None → sin keywords → clarify
        assert fsm_disambiguate(top3, None) == CLARIFY_DOMAIN  # type: ignore[arg-type]


# ── Tests de clarify (regla 4) ─────────────────────────────────────────


class TestClarify:
    """Regla 4: si ninguna regla resuelve, retorna 'clarify'."""

    def test_clarify_when_no_rules_match(self) -> None:
        """Sin clear winner, sin active, sin keywords → clarify."""
        top3 = [("operaciones", 0.5), ("comunicaciones", 0.45)]
        assert fsm_disambiguate(top3, "xyz") == CLARIFY_DOMAIN

    def test_clarify_returned_for_invalid_top1_domain(self) -> None:
        """Si top1 no es canónico, _sanitize_domain retorna 'clarify'."""
        top3 = [("invalid_domain", 0.9), ("operaciones", 0.1)]
        # Clear winner pero dominio inválido → _sanitize_domain → clarify
        assert fsm_disambiguate(top3, "xyz") == CLARIFY_DOMAIN


# ── Tests de validación de inputs ──────────────────────────────────────


class TestInputValidation:
    """Validación defensiva de inputs."""

    def test_empty_top3_raises_value_error(self) -> None:
        """top3 vacío → ValueError."""
        with pytest.raises(ValueError, match="no puede estar vacío"):
            fsm_disambiguate([], "xyz")

    def test_non_numeric_score_raises_type_error(self) -> None:
        """Score no numérico → TypeError."""
        top3 = [("operaciones", "high"), ("comunicaciones", 0.3)]  # type: ignore[list-item]
        with pytest.raises(TypeError, match="score debe ser numérico"):
            fsm_disambiguate(top3, "xyz")

    def test_bool_score_raises_type_error(self) -> None:
        """bool como score → TypeError (bool es subclase de int pero inválido)."""
        top3 = [("operaciones", True), ("comunicaciones", 0.3)]  # type: ignore[list-item]
        with pytest.raises(TypeError, match="score debe ser numérico"):
            fsm_disambiguate(top3, "xyz")

    def test_tuple_without_score_raises_type_error(self) -> None:
        """Tupla sin score (solo 1 elemento) → TypeError."""
        top3 = [("operaciones",)]  # type: ignore[list-item]
        with pytest.raises(TypeError, match="no tiene score"):
            fsm_disambiguate(top3, "xyz")


# ── Tests de constantes y configuración ────────────────────────────────


class TestConstants:
    """Constantes exportadas del módulo."""

    def test_threshold_is_0_15(self) -> None:
        """DISAMBIGUATION_THRESHOLD es 0.15 (plan maestro §2.3)."""
        assert DISAMBIGUATION_THRESHOLD == 0.15

    def test_clarify_domain_is_string(self) -> None:
        """CLARIFY_DOMAIN es el string 'clarify'."""
        assert CLARIFY_DOMAIN == "clarify"

    def test_valid_domains_includes_canonical_m8(self) -> None:
        """VALID_DOMAINS incluye los 3 dominios canónicos M8."""
        for d in ("operaciones", "comunicaciones", "datos_auto"):
            assert d in VALID_DOMAINS

    def test_valid_domains_includes_legacy(self) -> None:
        """VALID_DOMAINS también incluye dominios legacy por compatibilidad."""
        for d in ("research", "build", "operate"):
            assert d in VALID_DOMAINS

    def test_domain_keywords_has_all_canonical(self) -> None:
        """DOMAIN_KEYWORDS tiene entradas para los 3 dominios canónicos."""
        for d in ("operaciones", "comunicaciones", "datos_auto"):
            assert d in DOMAIN_KEYWORDS
            assert len(DOMAIN_KEYWORDS[d]) > 0
