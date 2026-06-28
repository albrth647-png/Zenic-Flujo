"""Tests Fase 1A — Foso 1: canonical_serializer + Ed25519 + hashing determinista.

Cubre:
- canonical_json: determinismo (mismo dict en cualquier orden → mismos bytes)
- sha256_hex: determinismo + diferente para distinto input
- ed25519_sign/verify: firma determinista, verificación correcta, rechazo de falsos
- generate_ed25519_keypair: par PEM válido
- extract_public_key_pem: extrae pública desde privada
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="foso1_1a_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


class TestCanonicalJson:
    """canonical_json debe ser determinista."""

    def test_same_dict_different_order_same_bytes(self):
        """Mismo dict en cualquier orden de claves → mismos bytes."""
        from src.orbital.canonical_serializer import canonical_json

        d1 = {"b": 2, "a": 1, "c": [3, 2, 1]}
        d2 = {"c": [3, 2, 1], "a": 1, "b": 2}
        assert canonical_json(d1) == canonical_json(d2)

    def test_no_whitespace(self):
        """No debe haber espacios en el output (separators compactos)."""
        from src.orbital.canonical_serializer import canonical_json

        result = canonical_json({"a": 1, "b": 2})
        assert b" " not in result, f"canonical_json no debe tener espacios: {result!r}"

    def test_nested_dicts_deterministic(self):
        """Dicts anidados también se ordenan."""
        from src.orbital.canonical_serializer import canonical_json

        d1 = {"outer": {"z": 1, "a": 2}, "list": [{"b": 1, "a": 2}]}
        d2 = {"list": [{"a": 2, "b": 1}], "outer": {"a": 2, "z": 1}}
        assert canonical_json(d1) == canonical_json(d2)

    def test_set_serialized_sorted(self):
        """Los sets se serializan ordenados para determinismo."""
        from src.orbital.canonical_serializer import canonical_json

        s1 = {3, 1, 2}
        s2 = {2, 3, 1}
        assert canonical_json({"s": s1}) == canonical_json({"s": s2})

    def test_datetime_isoformat(self):
        """datetime se serializa como ISO 8601."""
        from datetime import datetime

        from src.orbital.canonical_serializer import canonical_json

        dt = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)
        result = canonical_json({"dt": dt})
        assert b"2026-06-21T12:00:00+00:00" in result


class TestSha256Hex:
    """sha256_hex debe ser determinista."""

    def test_same_input_same_hash(self):
        from src.orbital.canonical_serializer import sha256_hex

        assert sha256_hex(b"hola") == sha256_hex(b"hola")

    def test_different_input_different_hash(self):
        from src.orbital.canonical_serializer import sha256_hex

        assert sha256_hex(b"hola") != sha256_hex(b"holo")

    def test_returns_64_char_hex(self):
        from src.orbital.canonical_serializer import sha256_hex

        h = sha256_hex(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_known_vector(self):
        """SHA-256("hello") = 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824."""
        from src.orbital.canonical_serializer import sha256_hex

        assert sha256_hex(b"hello") == (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )


class TestEd25519:
    """Ed25519 sign/verify end-to-end."""

    @pytest.fixture(scope="class")
    def keypair(self):
        from src.orbital.canonical_serializer import generate_ed25519_keypair

        return generate_ed25519_keypair()

    def test_sign_returns_base64(self, keypair):
        from src.orbital.canonical_serializer import ed25519_sign

        priv_pem, _ = keypair
        sig = ed25519_sign(b"mensaje", priv_pem)
        # Ed25519 signature = 64 bytes. Base64 con padding = 88 chars.
        assert len(sig) == 88
        import base64
        # 64 bytes decoded
        raw = base64.b64decode(sig)
        assert len(raw) == 64

    def test_sign_is_deterministic(self, keypair):
        """Ed25519 es determinista: misma clave + mismo payload → misma firma."""
        from src.orbital.canonical_serializer import ed25519_sign

        priv_pem, _ = keypair
        sig1 = ed25519_sign(b"mensaje", priv_pem)
        sig2 = ed25519_sign(b"mensaje", priv_pem)
        assert sig1 == sig2

    def test_verify_valid_signature(self, keypair):
        from src.orbital.canonical_serializer import ed25519_sign, ed25519_verify

        priv_pem, pub_pem = keypair
        payload = b"mensaje de prueba"
        sig = ed25519_sign(payload, priv_pem)
        assert ed25519_verify(payload, sig, pub_pem) is True

    def test_verify_rejects_tampered_payload(self, keypair):
        from src.orbital.canonical_serializer import ed25519_sign, ed25519_verify

        priv_pem, pub_pem = keypair
        sig = ed25519_sign(b"mensaje original", priv_pem)
        assert ed25519_verify(b"mensaje alterado", sig, pub_pem) is False

    def test_verify_rejects_wrong_key(self, keypair):
        from src.orbital.canonical_serializer import (
            ed25519_sign,
            ed25519_verify,
            generate_ed25519_keypair,
        )

        priv1, _ = keypair
        _, pub2 = generate_ed25519_keypair()  # diferente par
        sig = ed25519_sign(b"mensaje", priv1)
        assert ed25519_verify(b"mensaje", sig, pub2) is False

    def test_verify_rejects_invalid_pem(self):
        from src.orbital.canonical_serializer import ed25519_verify

        # PEM basura
        result = ed25519_verify(b"x", "fake_sig", b"not-a-pem")
        assert result is False

    def test_extract_public_key_from_private(self, keypair):
        from src.orbital.canonical_serializer import extract_public_key_pem

        priv_pem, expected_pub = keypair
        extracted_pub = extract_public_key_pem(priv_pem)
        assert extracted_pub == expected_pub

    def test_sign_rejects_non_ed25519_key(self):
        """Si la clave PEM no es Ed25519, debe lanzar ValueError."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        from src.orbital.canonical_serializer import ed25519_sign

        # Generar clave RSA (no Ed25519)
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rsa_pem = rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with pytest.raises(ValueError, match="Ed25519"):
            ed25519_sign(b"test", rsa_pem)
