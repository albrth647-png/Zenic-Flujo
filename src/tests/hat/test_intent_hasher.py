"""
Tests para orbital_n0/intent_hasher.py (F0-D7 sub-feature 1).
"""

from __future__ import annotations

import pytest

from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash, normalize_intent


class TestNormalizeIntent:
    def test_lowercases_text(self):
        assert normalize_intent("HELLO WORLD") == "hello world"

    def test_strips_whitespace(self):
        assert normalize_intent("  hello  ") == "hello"

    def test_removes_accents(self):
        assert normalize_intent("búscar infórmación") == "buscar informacion"

    def test_removes_punctuation(self):
        assert normalize_intent("hello, world! how's it?") == "hello world how s it"

    def test_collapses_multiple_spaces(self):
        assert normalize_intent("hello    world") == "hello world"

    def test_handles_none_input(self):
        assert normalize_intent(None) == ""  # type: ignore[arg-type]

    def test_handles_non_string_input(self):
        assert normalize_intent(123) == ""  # type: ignore[arg-type]

    def test_empty_string_returns_empty(self):
        assert normalize_intent("") == ""

    def test_handles_n_tilde(self):
        assert normalize_intent("niño") == "nino"

    def test_handles_umlaut(self):
        assert normalize_intent("pingüino") == "pinguino"


class TestComputeIntentHash:
    def test_returns_64_char_hex_string(self):
        h = compute_intent_hash("user1", "sess1", "buscar python")
        assert isinstance(h, str)
        assert len(h) == 64
        # Debe ser hex válido
        int(h, 16)  # raises ValueError si no es hex

    def test_deterministic_same_input_same_hash(self):
        h1 = compute_intent_hash("user1", "sess1", "buscar python")
        h2 = compute_intent_hash("user1", "sess1", "buscar python")
        assert h1 == h2

    def test_different_users_different_hash(self):
        h1 = compute_intent_hash("user1", "sess1", "buscar python")
        h2 = compute_intent_hash("user2", "sess1", "buscar python")
        assert h1 != h2

    def test_different_sessions_different_hash(self):
        h1 = compute_intent_hash("user1", "sess1", "buscar python")
        h2 = compute_intent_hash("user1", "sess2", "buscar python")
        assert h1 != h2

    def test_different_intent_different_hash(self):
        h1 = compute_intent_hash("user1", "sess1", "buscar python")
        h2 = compute_intent_hash("user1", "sess1", "buscar javascript")
        assert h1 != h2

    def test_normalized_intent_produces_same_hash(self):
        """Textos equivalentes tras normalización producen el mismo hash."""
        h1 = compute_intent_hash("user1", "sess1", "BUSCAR Python")
        h2 = compute_intent_hash("user1", "sess1", "buscar python")
        assert h1 == h2

    def test_accents_normalized_in_hash(self):
        """Acentos no afectan el hash."""
        h1 = compute_intent_hash("user1", "sess1", "búscar python")
        h2 = compute_intent_hash("user1", "sess1", "buscar python")
        assert h1 == h2

    def test_params_affect_hash(self):
        h1 = compute_intent_hash("user1", "sess1", "buscar", {"max_results": 5})
        h2 = compute_intent_hash("user1", "sess1", "buscar", {"max_results": 10})
        assert h1 != h2

    def test_params_order_doesnt_matter(self):
        """Keys ordenadas → params con keys en distinto orden producen mismo hash."""
        h1 = compute_intent_hash("user1", "sess1", "buscar", {"a": 1, "b": 2})
        h2 = compute_intent_hash("user1", "sess1", "buscar", {"b": 2, "a": 1})
        assert h1 == h2

    def test_none_params_equivalent_to_empty_dict(self):
        h1 = compute_intent_hash("user1", "sess1", "buscar", None)
        h2 = compute_intent_hash("user1", "sess1", "buscar", {})
        assert h1 == h2

    def test_invalid_user_id_raises_type_error(self):
        with pytest.raises(TypeError, match="user_id"):
            compute_intent_hash(123, "sess1", "buscar")  # type: ignore[arg-type]

    def test_invalid_session_id_raises_type_error(self):
        with pytest.raises(TypeError, match="session_id"):
            compute_intent_hash("user1", None, "buscar")  # type: ignore[arg-type]

    def test_handles_complex_params(self):
        """Params con valores anidados (dicts, lists) se serializan correctamente."""
        h = compute_intent_hash("u", "s", "test", {"nested": {"list": [1, 2, 3]}})
        assert len(h) == 64
