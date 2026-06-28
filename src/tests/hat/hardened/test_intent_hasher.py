"""Tests para intent/hasher — cálculo determinista de intent_hash.

Cubre:
- Determinismo: mismo input → mismo hash.
- Normalización: acentos, case, puntuación no afectan el hash.
- Sensibilidad a user_id, session_id, params.
- Formato: 64 char hex string (sha256).
- TypeError en inputs no-string.
"""
from __future__ import annotations

import hashlib

import pytest

from src.hat.level1_orchestrator.intent.hasher import compute_intent_hash
from src.hat.level1_orchestrator.intent.normalizer import normalize_intent

# ── Tests de determinismo ──────────────────────────────────────────────


class TestDeterminism:
    """El hash es determinista: mismo input → mismo output."""

    def test_same_input_same_hash(self) -> None:
        """Inputs idénticos producen hashes idénticos."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u1", "s1", "listar leads")
        assert h1 == h2

    def test_different_users_different_hash(self) -> None:
        """Diferente user_id → diferente hash."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u2", "s1", "listar leads")
        assert h1 != h2

    def test_different_sessions_different_hash(self) -> None:
        """Diferente session_id → diferente hash."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u1", "s2", "listar leads")
        assert h1 != h2

    def test_different_messages_different_hash(self) -> None:
        """Diferente message → diferente hash."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u1", "s1", "crear lead")
        assert h1 != h2


# ── Tests de formato ───────────────────────────────────────────────────


class TestFormat:
    """Formato del hash: 64 char hex string (sha256)."""

    def test_hash_is_64_char_hex(self) -> None:
        """El hash tiene 64 caracteres hexadecimales."""
        h = compute_intent_hash("u1", "s1", "test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_matches_sha256_of_payload(self) -> None:
        """El hash es el sha256 del payload esperado."""
        user_id, session_id, message = "u1", "s1", "listar leads"
        normalized = normalize_intent(message)
        payload = f"{user_id}|{session_id}|{normalized}|{{}}"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert compute_intent_hash(user_id, session_id, message) == expected


# ── Tests de normalización ─────────────────────────────────────────────


class TestNormalization:
    """La normalización hace que variaciones cosméticas produzcan el mismo hash."""

    def test_accented_vs_plain_same_hash(self) -> None:
        """'listar leads' y 'lístár léads' producen el mismo hash."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u1", "s1", "lístár léads")
        assert h1 == h2

    def test_case_insensitive(self) -> None:
        """Mayúsculas/minúsculas no afectan el hash."""
        h1 = compute_intent_hash("u1", "s1", "Listar Leads")
        h2 = compute_intent_hash("u1", "s1", "listar leads")
        assert h1 == h2

    def test_punctuation_ignored(self) -> None:
        """Puntuación no afecta el hash."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u1", "s1", "listar, leads!")
        assert h1 == h2

    def test_extra_whitespace_collapsed(self) -> None:
        """Espacios múltiples se colapsan."""
        h1 = compute_intent_hash("u1", "s1", "listar leads")
        h2 = compute_intent_hash("u1", "s1", "listar    leads")
        assert h1 == h2


# ── Tests de params ────────────────────────────────────────────────────


class TestParams:
    """Los params afectan el hash de forma determinista."""

    def test_different_params_different_hash(self) -> None:
        """Diferente params → diferente hash."""
        h1 = compute_intent_hash("u1", "s1", "test", {"a": 1})
        h2 = compute_intent_hash("u1", "s1", "test", {"a": 2})
        assert h1 != h2

    def test_same_params_same_hash(self) -> None:
        """Mismos params (aunque en distinto orden) → mismo hash."""
        h1 = compute_intent_hash("u1", "s1", "test", {"a": 1, "b": 2})
        h2 = compute_intent_hash("u1", "s1", "test", {"b": 2, "a": 1})
        assert h1 == h2

    def test_none_params_treated_as_empty(self) -> None:
        """params=None se trata como dict vacío."""
        h1 = compute_intent_hash("u1", "s1", "test", None)
        h2 = compute_intent_hash("u1", "s1", "test", {})
        assert h1 == h2


# ── Tests de validación de inputs ──────────────────────────────────────


class TestValidation:
    """Validación defensiva de inputs."""

    def test_non_string_user_id_raises(self) -> None:
        """user_id no-string → TypeError."""
        with pytest.raises(TypeError, match="user_id debe ser str"):
            compute_intent_hash(123, "s1", "test")  # type: ignore[arg-type]

    def test_non_string_session_id_raises(self) -> None:
        """session_id no-string → TypeError."""
        with pytest.raises(TypeError, match="session_id debe ser str"):
            compute_intent_hash("u1", None, "test")  # type: ignore[arg-type]

    def test_non_string_message_returns_hash(self) -> None:
        """message no-string se normaliza a '' (no raise)."""
        # normalize_intent retorna "" para inputs no-string
        h = compute_intent_hash("u1", "s1", 123)  # type: ignore[arg-type]
        assert isinstance(h, str)
        assert len(h) == 64
