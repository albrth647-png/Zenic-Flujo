"""
Zenic-Flujo — Crypto Operations
=================================

Operaciones criptograficas de bajo nivel: cifrado y descifrado AES-256-GCM,
derivacion de sub-claves, cifrado a nivel de campo.

Separado de encryption.py para reducir el tamano del god class.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from src.core.logging import setup_logging

# ── Cryptography lazy loading ────────────────────────────
_CRYPTOGRAPHY_AVAILABLE = False
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    pass

logger = setup_logging(__name__)

# ── Constantes ──────────────────────────────────────────

AES_KEY_SIZE: int = 32  # 256 bits
GCM_NONCE_SIZE: int = 12  # 96 bits
GCM_TAG_SIZE: int = 16  # 128 bits
HKDF_INFO_PREFIX: str = "zenic-flijo-encryption"


class CryptoEngine:
    """
    Operaciones criptograficas de bajo nivel.

    Proporciona cifrado/descifrado AES-256-GCM, derivacion de sub-claves
    via HKDF, y operaciones a nivel de campo.

    No gestiona claves de tenant; recibe las claves ya resueltas.
    """

    def __init__(self) -> None:
        self._available = _CRYPTOGRAPHY_AVAILABLE
        if not self._available:
            logger.warning(
                "CryptoEngine: cryptography no disponible. "
                "Operaciones criptograficas NO disponibles."
            )

    @property
    def is_available(self) -> bool:
        """Indica si el modulo cryptography esta disponible."""
        return self._available

    # ── Derivacion de sub-claves ─────────────────────────

    def derive_sub_key(self, master_key: bytes, context: str) -> bytes:
        """
        Deriva una sub-clave usando HKDF con el contexto proporcionado.

        Args:
            master_key: Clave maestra del tenant
            context: Contexto para la derivacion (ej. nombre de campo)

        Returns:
            Sub-clave derivada de 256 bits
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE,
            salt=None,
            info=f"{HKDF_INFO_PREFIX}-subkey-{context}".encode(),
        )
        return hkdf.derive(master_key)

    # ── Cifrado / Descifrado ─────────────────────────────

    def encrypt(self, plaintext: str, key_bytes: bytes, context: str | None = None) -> dict[str, Any]:
        """
        Cifra un texto plano usando AES-256-GCM.

        Args:
            plaintext: Texto a cifrar
            key_bytes: Clave AES-256 en bytes
            context: Contexto opcional para derivacion de sub-clave

        Returns:
            dict con ciphertext (base64), iv (base64), tag (base64), key_version
        """
        if context:
            key_bytes = self.derive_sub_key(key_bytes, context)

        nonce = os.urandom(GCM_NONCE_SIZE)
        aesgcm = AESGCM(key_bytes)
        ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        ciphertext = ct_with_tag[:-GCM_TAG_SIZE]
        tag = ct_with_tag[-GCM_TAG_SIZE:]

        result = {
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "iv": base64.b64encode(nonce).decode(),
            "tag": base64.b64encode(tag).decode(),
        }
        if context:
            result["context"] = context
        return result

    def decrypt(self, ciphertext_dict: dict[str, Any], key_bytes: bytes) -> str:
        """
        Descifra un texto cifrado usando AES-256-GCM.

        Args:
            ciphertext_dict: dict con ciphertext, iv, tag, opcional context
            key_bytes: Clave AES-256 en bytes

        Returns:
            Texto plano descifrado
        """
        context = ciphertext_dict.get("context")
        if context:
            key_bytes = self.derive_sub_key(key_bytes, context)

        ciphertext = base64.b64decode(ciphertext_dict["ciphertext"])
        nonce = base64.b64decode(ciphertext_dict["iv"])
        tag = base64.b64decode(ciphertext_dict["tag"])

        aesgcm = AESGCM(key_bytes)
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
        return plaintext.decode("utf-8")

    def encrypt_field(self, value: str, field_name: str, key_bytes: bytes) -> dict[str, Any]:
        """
        Cifra un campo con derivacion de sub-clave por nombre de campo.

        Args:
            value: Valor del campo a cifrar
            field_name: Nombre del campo (usado para derivar sub-clave)
            key_bytes: Clave maestra en bytes

        Returns:
            dict con ciphertext, iv, tag, field_name
        """
        result = self.encrypt(value, key_bytes, context=field_name)
        result["field_name"] = field_name
        return result

    def decrypt_field(self, value: dict[str, Any], field_name: str, key_bytes: bytes) -> str:
        """
        Descifra un campo previamente cifrado.

        Args:
            value: dict con ciphertext, iv, tag
            field_name: Nombre del campo (usado para derivar sub-clave)
            key_bytes: Clave maestra en bytes

        Returns:
            Valor del campo descifrado
        """
        value_with_context = {**value, "context": field_name}
        return self.decrypt(value_with_context, key_bytes)
