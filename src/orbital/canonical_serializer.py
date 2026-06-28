"""Serialización determinista + hashing + firma Ed25519 para Compliance Reproducible.

Foso 1 — Compliance Reproducible Banca LATAM.

Garantías:
- canonical_json: mismo dict en cualquier orden → mismos bytes (sort_keys + separators compactos)
- sha256_hex: SHA-256 determinista
- ed25519_sign / ed25519_verify: firma Ed25519 (Curve25519) sobre bytes canónicos

Uso típico (Foso 1):
    payload = canonical_json(orbital_result.to_dict())
    result_hash = sha256_hex(payload)
    signature = ed25519_sign(payload, tenant_private_key_pem)
    # Verificación:
    ed25519_verify(payload, signature, tenant_public_key_pem)  # → True

Fundamento: Brouwer Fixed Point Theorem (1911) garantiza que un mapeo continuo
de un convex compact set a sí mismo tiene un punto fijo. ORBITAL converge a ese
punto fijo de forma determinista → mismo input → mismo hash → misma firma.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_json(obj: object) -> bytes:
    """Serializa a JSON determinista: claves ordenadas, sin espacios, UTF-8.

    Garantiza que el mismo dict (en cualquier orden) produzca los mismos bytes.
    Esto es CRÍTICO para reproducibilidad: sin canonicalización, hashes del
    "mismo" dict variarían según el orden de inserción de Python.

    Soporta: dict, list, str, int, float, bool, None, datetime, date, dataclass,
    set (ordenado), objetos con .to_dict().

    Args:
        obj: Objeto a serializar.

    Returns:
        Bytes UTF-8 del JSON canónico.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default_serializer,
    ).encode("utf-8")


# legítimo: retorna valor serializable, tipo dinámico
def _default_serializer(obj: object) -> Any:
    """Fallback para tipos no-JSON estándar. Debe ser determinista."""
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)  # ordenado para determinismo
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    # Último recurso: string determinista
    return str(obj)


def sha256_hex(payload: bytes) -> str:
    """SHA-256 hex digest (64 caracteres lowercase).

    Args:
        payload: Bytes a hashear.

    Returns:
        Hex digest de 64 caracteres.
    """
    return hashlib.sha256(payload).hexdigest()


def ed25519_sign(payload: bytes, private_key_pem: bytes) -> str:
    """Firma Ed25519 sobre payload, retorna base64.

    Ed25519 es determinista: misma clave + mismo payload → misma firma.
    Esto permite verificar la firma sin acceso a la clave privada.

    Args:
        payload: Bytes a firmar (típicamente canonical_json + sha256_hex output).
        private_key_pem: Clave privada Ed25519 en formato PEM (PKCS8).

    Returns:
        Firma en base64 (86 caracteres).
    """
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(
            f"La clave PEM no es Ed25519 privada (es {type(key).__name__}). "
            "Compliance Reproducible requiere Ed25519."
        )
    signature = key.sign(payload)
    return base64.b64encode(signature).decode("ascii")


def ed25519_verify(payload: bytes, signature_b64: str, public_key_pem: bytes) -> bool:
    """Verifica firma Ed25519. Retorna True si coincide.

    Args:
        payload: Bytes originales que se firmaron.
        signature_b64: Firma en base64.
        public_key_pem: Clave pública Ed25519 en formato PEM (SubjectPublicKeyInfo).

    Returns:
        True si la firma es válida, False en caso contrario o si hay error.
    """
    try:
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            return False
        signature = base64.b64decode(signature_b64)
        key.verify(signature, payload)
        return True
    except Exception:
        return False


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Genera un par Ed25519 para tests y setup inicial.

    Returns:
        Tuple (private_key_pem, public_key_pem) en formato PEM.
    """
    private_key = Ed25519PrivateKey.generate()
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


def extract_public_key_pem(private_key_pem: bytes) -> bytes:
    """Extrae la clave pública PEM desde una clave privada PEM.

    Útil para almacenar la pública en DB y conservar la privada en HSM/key escrow.
    """
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
