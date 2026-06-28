"""Tests para intent/normalizer — normalización de texto para hashing.

Cubre:
- lowercase + strip.
- Reemplazo de acentos (á→a, é→e, í→i, ó→o, ú→u, ñ→n, ü→u).
- Eliminación de puntuación (solo alfanum + espacio).
- Colapso de espacios múltiples.
- Casos edge: None, no-string, vacío, solo espacios.
"""
from __future__ import annotations

from src.hat.level1_orchestrator.intent.normalizer import normalize_intent

# ── Tests de transformaciones básicas ──────────────────────────────────


class TestBasicTransformations:
    """Transformaciones básicas de normalización."""

    def test_lowercase(self) -> None:
        """Convierte a minúsculas."""
        assert normalize_intent("LISTAR LEADS") == "listar leads"

    def test_strip_whitespace(self) -> None:
        """Elimina espacios al inicio y final."""
        assert normalize_intent("  listar leads  ") == "listar leads"

    def test_collapses_multiple_spaces(self) -> None:
        """Colapsa espacios múltiples en uno solo."""
        assert normalize_intent("listar    leads") == "listar leads"

    def test_combined_basic(self) -> None:
        """Combinación de lowercase + strip + collapse."""
        assert normalize_intent("  LISTAR    LEADS  ") == "listar leads"


# ── Tests de acentos ───────────────────────────────────────────────────


class TestAccents:
    """Reemplazo de caracteres acentuados."""

    def test_acute_a(self) -> None:
        """á → a."""
        assert normalize_intent("lístár") == "listar"

    def test_acute_e(self) -> None:
        """é → e."""
        assert normalize_intent("léads") == "leads"

    def test_acute_i(self) -> None:
        """í → i."""
        assert normalize_intent("díás") == "dias"

    def test_acute_o(self) -> None:
        """ó → o."""
        assert normalize_intent("cómó") == "como"

    def test_acute_u(self) -> None:
        """ú → u."""
        assert normalize_intent("últimó") == "ultimo"

    def test_tilde_n(self) -> None:
        """ñ → n."""
        assert normalize_intent("español") == "espanol"

    def test_umlaut_u(self) -> None:
        """ü → u."""
        assert normalize_intent("bilingüe") == "bilingue"

    def test_all_accents_combined(self) -> None:
        """Todos los acentos en un solo string."""
        assert normalize_intent("Díás Márítímós") == "dias maritimos"


# ── Tests de puntuación ────────────────────────────────────────────────


class TestPunctuation:
    """Eliminación de puntuación."""

    def test_removes_commas(self) -> None:
        """Elimina comas."""
        assert normalize_intent("listar, leads") == "listar leads"

    def test_removes_periods(self) -> None:
        """Elimina puntos."""
        assert normalize_intent("listar. leads.") == "listar leads"

    def test_removes_exclamation(self) -> None:
        """Elimina signos de exclamación."""
        assert normalize_intent("¡hola!") == "hola"

    def test_removes_question_marks(self) -> None:
        """Elimina signos de interrogación (acentos también se normalizan)."""
        # ¿ y ? se eliminan; é → e
        assert normalize_intent("¿qué?") == "que"

    def test_removes_colons_semicolons(self) -> None:
        """Elimina dos puntos y punto y coma."""
        assert normalize_intent("lead: juan; perez") == "lead juan perez"

    def test_removes_parentheses(self) -> None:
        """Elimina paréntesis."""
        assert normalize_intent("(lead) juan") == "lead juan"

    def test_removes_hyphens_underscores(self) -> None:
        """Guiones y underscores se reemplazan por espacios."""
        assert normalize_intent("lead-juan_perez") == "lead juan perez"

    def test_removes_at_symbol(self) -> None:
        """Elimina @."""
        assert normalize_intent("user@domain") == "user domain"


# ── Tests de casos edge ────────────────────────────────────────────────


class TestEdgeCases:
    """Casos edge y robustez."""

    def test_none_returns_empty(self) -> None:
        """None → string vacío (no raise)."""
        assert normalize_intent(None) == ""  # type: ignore[arg-type]

    def test_non_string_returns_empty(self) -> None:
        """Input no-string → string vacío (no raise)."""
        assert normalize_intent(123) == ""  # type: ignore[arg-type]
        assert normalize_intent([]) == ""  # type: ignore[arg-type]
        assert normalize_intent(None) == ""  # type: ignore[arg-type]

    def test_empty_string_returns_empty(self) -> None:
        """String vacío → string vacío."""
        assert normalize_intent("") == ""

    def test_only_whitespace_returns_empty(self) -> None:
        """Solo espacios → string vacío."""
        assert normalize_intent("   ") == ""

    def test_only_punctuation_returns_empty(self) -> None:
        """Solo puntuación → string vacío."""
        assert normalize_intent("...!!!???") == ""

    def test_numbers_preserved(self) -> None:
        """Los números se preservan."""
        assert normalize_intent("lead 123") == "lead 123"

    def test_mixed_alphanumeric(self) -> None:
        """Strings alfanuméricos mixtos se preservan."""
        assert normalize_intent("Lead123 XYZ") == "lead123 xyz"

    def test_idempotent(self) -> None:
        """Normalizar dos veces da el mismo resultado."""
        text = "  Lístár, LEADS!  "
        once = normalize_intent(text)
        twice = normalize_intent(once)
        assert once == twice
