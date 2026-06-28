"""Tests para SpecialistRouter — base class del Nivel 2.

Cubre:
- Routing por keywords (case-insensitive, primer match gana).
- Fallback al primer specialist cuando no hay keyword match.
- Manejo de subtasks vacíos / sin mensaje.
- Respuestas de error (no specialists, specialist not found).
- _enrich_result añade specialists_used.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level2_supervisors.base_router import SpecialistRouter

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_specialists() -> dict[str, MagicMock]:
    """3 specialists mockeados con nombres canónicos."""
    return {
        "alpha": MagicMock(),
        "beta": MagicMock(),
        "gamma": MagicMock(),
    }


@pytest.fixture
def router(mock_specialists: dict[str, MagicMock]) -> SpecialistRouter:
    """SpecialistRouter de prueba con 3 specialists y keyword_map."""
    r = SpecialistRouter(specialists=mock_specialists)
    r.domain = "test_domain"
    r._keyword_map = {
        "alpha_kw": "alpha",
        "beta_kw": "beta",
        "gamma_kw": "gamma",
    }
    return r


# ── Tests de routing por keywords ──────────────────────────────────────


class TestKeywordRouting:
    """Routing por keywords case-insensitive."""

    def test_route_to_alpha_on_alpha_keyword(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Mensaje con 'alpha_kw' → specialist alpha."""
        mock_specialists["alpha"].handle.return_value = {"status": "completed"}
        result = router.handle({"description": "process alpha_kw now"})
        mock_specialists["alpha"].handle.assert_called_once()
        assert result["specialists_used"] == ["alpha"]

    def test_route_to_beta_on_beta_keyword(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Mensaje con 'beta_kw' → specialist beta."""
        mock_specialists["beta"].handle.return_value = {"status": "completed"}
        result = router.handle({"description": "use beta_kw here"})
        mock_specialists["beta"].handle.assert_called_once()
        assert result["specialists_used"] == ["beta"]

    def test_keyword_matching_is_case_insensitive(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """El matching es case-insensitive."""
        mock_specialists["alpha"].handle.return_value = {"status": "completed"}
        router.handle({"description": "ALPHA_KW uppercase"})
        mock_specialists["alpha"].handle.assert_called_once()
        assert True

    def test_first_match_wins_when_multiple_keywords(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si múltiples keywords matchean, gana el primer match en orden de inserción."""
        mock_specialists["alpha"].handle.return_value = {"status": "completed"}
        # Mensaje con ambas keywords — alpha_kw aparece primero en el dict
        router.handle({"description": "alpha_kw and beta_kw both present"})
        mock_specialists["alpha"].handle.assert_called_once()
        assert True
        mock_specialists["beta"].handle.assert_not_called()

    def test_partial_match_works(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Keyword como substring del mensaje también matchea."""
        mock_specialists["gamma"].handle.return_value = {"status": "completed"}
        router.handle({"description": "this has gamma_kw embedded in text"})
        mock_specialists["gamma"].handle.assert_called_once()
        assert True


# ── Tests de fallback ──────────────────────────────────────────────────


class TestFallback:
    """Fallback al primer specialist cuando no hay keyword match."""

    def test_fallback_to_first_specialist_on_no_match(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Sin keyword match → primer specialist (alpha)."""
        mock_specialists["alpha"].handle.return_value = {"status": "completed"}
        result = router.handle({"description": "xyz qwerty no keyword here"})
        mock_specialists["alpha"].handle.assert_called_once()
        assert result["specialists_used"] == ["alpha"]

    def test_fallback_uses_first_in_insertion_order(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """El fallback es el primer specialist en orden de inserción."""
        # Reordenar: gamma primero
        reordered = {
            "gamma": mock_specialists["gamma"],
            "alpha": mock_specialists["alpha"],
        }
        r = SpecialistRouter(specialists=reordered)
        r._keyword_map = {"x": "alpha"}
        mock_specialists["gamma"].handle.return_value = {"status": "completed"}
        r.handle({"description": "no match"})
        mock_specialists["gamma"].handle.assert_called_once()
        assert True


# ── Tests de extracción de mensaje ─────────────────────────────────────


class TestMessageExtraction:
    """Extracción del mensaje del subtask."""

    def test_uses_description_field(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si subtask tiene 'description', se usa."""
        mock_specialists["alpha"].handle.return_value = {"status": "ok"}
        router.handle({"description": "alpha_kw"})
        mock_specialists["alpha"].handle.assert_called_once()
        assert True

    def test_uses_message_field_if_no_description(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si no hay 'description', usa 'message'."""
        mock_specialists["alpha"].handle.return_value = {"status": "ok"}
        router.handle({"message": "alpha_kw"})
        mock_specialists["alpha"].handle.assert_called_once()
        assert True

    def test_uses_params_query_if_no_description_nor_message(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si no hay description ni message, usa params.query."""
        mock_specialists["alpha"].handle.return_value = {"status": "ok"}
        router.handle({"params": {"query": "alpha_kw"}})
        mock_specialists["alpha"].handle.assert_called_once()
        assert True

    def test_empty_subtask_falls_to_fallback(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Subtask vacío → fallback al primer specialist."""
        mock_specialists["alpha"].handle.return_value = {"status": "ok"}
        router.handle({})
        mock_specialists["alpha"].handle.assert_called_once()
        assert True


# ── Tests de manejo de errores ─────────────────────────────────────────


class TestErrorHandling:
    """Respuestas de error estructuradas."""

    def test_no_specialists_returns_failed_response(self) -> None:
        """Sin specialists → respuesta failed con error."""
        r = SpecialistRouter(specialists=None)
        r.domain = "empty"
        result = r.handle({"description": "test"})
        assert result["status"] == "failed"
        assert "no specialists available" in result["error"]
        assert result["domain"] == "empty"
        assert result["specialists_used"] == []

    def test_specialist_not_in_dict_returns_failed(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si _select_specialist retorna nombre no en dict → failed."""
        r = SpecialistRouter(specialists=mock_specialists)
        r._keyword_map = {"kw": "nonexistent"}  # specialist no existe
        result = r.handle({"description": "kw match"})
        assert result["status"] == "failed"
        assert "nonexistent" in result["error"]


# ── Tests de _enrich_result ────────────────────────────────────────────


class TestEnrichResult:
    """_enrich_result añade specialists_used al resultado."""

    def test_enrich_adds_specialists_used(
        self, router: SpecialistRouter, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """El resultado se enriquece con specialists_used."""
        mock_specialists["alpha"].handle.return_value = {
            "status": "completed", "result": "ok",
        }
        result = router.handle({"description": "alpha_kw"})
        assert "specialists_used" in result
        assert result["specialists_used"] == ["alpha"]

    def test_enrich_preserves_existing_specialists_used(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si el specialist ya retornó specialists_used, se respeta."""
        mock_specialists["alpha"].handle.return_value = {
            "status": "completed",
            "specialists_used": ["alpha", "extra"],
        }
        r = SpecialistRouter(specialists=mock_specialists)
        r.domain = "test"
        r._keyword_map = {"alpha_kw": "alpha"}
        result = r.handle({"description": "alpha_kw"})
        assert isinstance(result, dict)
        assert result["specialists_used"] == ["alpha", "extra"]

    def test_enrich_handles_non_dict_result(
        self, mock_specialists: dict[str, MagicMock],
    ) -> None:
        """Si el specialist retorna non-dict, se pasa through."""
        mock_specialists["alpha"].handle.return_value = "string result"
        r = SpecialistRouter(specialists=mock_specialists)
        r._keyword_map = {"alpha_kw": "alpha"}
        result = r.handle({"description": "alpha_kw"})
        assert result == "string result"


# ── Tests de __repr__ ──────────────────────────────────────────────────


class TestRepr:
    """Representación string del router."""

    def test_repr_includes_domain_and_specialists(
        self, router: SpecialistRouter,
    ) -> None:
        """__repr__ incluye domain y lista de specialists."""
        r = repr(router)
        assert "SpecialistRouter" in r
        assert "test_domain" in r
        assert "alpha" in r
        assert "beta" in r
        assert "gamma" in r
