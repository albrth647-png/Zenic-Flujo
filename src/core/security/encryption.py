"""
Zenic-Flujo — BYOK Encryption Service
========================================

Servicio de cifrado Bring Your Own Key (BYOK) con soporte multi-tenant.

Componentes extraidos (reducido de 846 a ~300 lineas):
- key_manager.py: KeyManager (KEK, RSA, tenant keys, cache)
- crypto.py: CryptoEngine (AES-256-GCM, field-level encrypt/decrypt)

Funcionalidades originales preservadas:
- AES-256-GCM para cifrado de datos (cifrado autenticado)
- RSA-2048 para key wrapping (cifrar claves de tenant con KEK)
- HKDF para derivacion de claves
- BYOK: cada tenant puede proporcionar su propia clave maestra
- Rotacion de claves sin downtime
- Versionado de claves
- Key wrapping: las claves de tenant se envuelven con KEK
"""

from __future__ import annotations

import contextlib
import threading
from typing import Any

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from src.core.security.crypto import CryptoEngine
from src.core.security.key_manager import DEFAULT_TENANT, KeyManager

logger = setup_logging(__name__)


class EncryptionService:
    """
    Servicio de cifrado BYOK con soporte multi-tenant y rotacion de claves.

    Delega en KeyManager para gestion de claves y CryptoEngine para
    operaciones criptograficas de bajo nivel.
    """

    _instance: EncryptionService | None = None
    _lock = threading.RLock()

    def __new__(cls) -> EncryptionService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._initialized = True
            self._db = DatabaseManager()
            self._key_manager = KeyManager()
            self._crypto = CryptoEngine()
            self._ensure_tables()

            if self._key_manager.is_available:
                self._ensure_default_key()
                logger.info("EncryptionService: Inicializado correctamente")
            else:
                logger.warning("EncryptionService: cryptography no disponible. Modo limitado.")

    def _ensure_tables(self) -> None:
        """Crea las tablas de cifrado si no existen."""
        conn = self._db.get_connection()
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS encryption_keys (
                key_id          TEXT PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                key_type        TEXT NOT NULL DEFAULT 'AES-256-GCM',
                encrypted_key   TEXT NOT NULL,
                rsa_wrapped_key TEXT,
                version         INTEGER NOT NULL DEFAULT 1,
                is_active       INTEGER NOT NULL DEFAULT 1,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rotated_at      TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS encrypted_data (
                data_id         TEXT PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                key_version     INTEGER NOT NULL,
                encrypted_value TEXT NOT NULL,
                iv              TEXT NOT NULL,
                tag             TEXT NOT NULL,
                field_name      TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_enc_keys_tenant ON encryption_keys(tenant_id, is_active);
            CREATE INDEX IF NOT EXISTS idx_enc_keys_version ON encryption_keys(tenant_id, version);
            CREATE INDEX IF NOT EXISTS idx_enc_data_tenant ON encrypted_data(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_enc_data_field ON encrypted_data(tenant_id, field_name);
        """)
        conn.commit()

    def _ensure_default_key(self) -> None:
        """Asegura que exista una clave de cifrado por defecto utilizable."""
        existing = self._db.fetchone(
            "SELECT key_id, version FROM encryption_keys WHERE tenant_id = ? AND is_active = 1",
            (DEFAULT_TENANT,),
        )
        if existing:
            try:
                self._key_manager.unwrap_tenant_key(DEFAULT_TENANT, existing["version"])
                return
            except ValueError:
                logger.warning("EncryptionService: Clave por defecto no utilizable. Generando nueva.")
                self._db.execute(
                    "UPDATE encryption_keys SET is_active = 0 WHERE tenant_id = ? AND is_active = 1",
                    (DEFAULT_TENANT,),
                )
                self._db.commit()

        self._key_manager.generate_tenant_key(DEFAULT_TENANT)

    # ── API publica: Cifrado / Descifrado ────────────────

    def encrypt(self, plaintext: str, tenant_id: str | None = None, context: str | None = None) -> dict[str, Any]:
        """
        Cifra un texto plano usando la clave del tenant o la clave por defecto.

        Args:
            plaintext: Texto a cifrar
            tenant_id: ID del tenant (None = clave por defecto)
            context: Contexto adicional para derivacion de sub-clave (opcional)

        Returns:
            dict con ciphertext (base64), iv (base64), tag (base64), key_version
        """
        effective_tenant = tenant_id or DEFAULT_TENANT
        key_bytes, version, _effective = self._key_manager.get_active_key(effective_tenant)

        result = self._crypto.encrypt(plaintext, key_bytes, context)
        result["key_version"] = version

        self._db.audit(
            "encryption.encrypt",
            f"Dato cifrado para tenant '{effective_tenant}' con clave v{version}"
            + (f" (contexto: {context})" if context else ""),
        )
        return result

    def decrypt(self, ciphertext_dict: dict[str, Any], tenant_id: str | None = None) -> str:
        """
        Descifra un texto cifrado usando la version de clave correcta.

        Args:
            ciphertext_dict: dict con ciphertext, iv, tag, key_version
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            Texto plano descifrado
        """
        effective_tenant = tenant_id or DEFAULT_TENANT
        version = ciphertext_dict.get("key_version", 1)

        key_bytes: bytes | None = None
        try:
            key_bytes = self._key_manager.unwrap_tenant_key(effective_tenant, version)
        except ValueError:
            if effective_tenant != DEFAULT_TENANT:
                with contextlib.suppress(ValueError):
                    key_bytes = self._key_manager.unwrap_tenant_key(DEFAULT_TENANT, version)

        if key_bytes is None:
            raise ValueError(
                f"No se pudo desenvolver la clave: tenant '{effective_tenant}' version {version}"
            )

        return self._crypto.decrypt(ciphertext_dict, key_bytes)

    def encrypt_field(self, value: str, field_name: str, tenant_id: str | None = None) -> dict[str, Any]:
        """
        Cifrado a nivel de campo con derivacion de sub-clave por nombre.

        Args:
            value: Valor del campo a cifrar
            field_name: Nombre del campo
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            dict con ciphertext, iv, tag, key_version, field_name
        """
        effective_tenant = tenant_id or DEFAULT_TENANT
        key_bytes, version, _effective = self._key_manager.get_active_key(effective_tenant)
        result = self._crypto.encrypt_field(value, field_name, key_bytes)
        result["key_version"] = version
        return result

    def decrypt_field(self, value: dict[str, Any], field_name: str, tenant_id: str | None = None) -> str:
        """Descifrado a nivel de campo."""
        effective_tenant = tenant_id or DEFAULT_TENANT
        version = value.get("key_version", 1)
        key_bytes = self._key_manager.unwrap_tenant_key(effective_tenant, version)
        return self._crypto.decrypt_field(value, field_name, key_bytes)

    # ── API publica: Gestion de claves BYOK ──────────────

    def set_tenant_key(self, tenant_id: str, key_b64: str) -> dict[str, Any]:
        """Almacena la clave BYOK de un tenant (envuelta con KEK y RSA)."""
        result = self._key_manager.set_tenant_key(tenant_id, key_b64)
        if result.get("status") == "ok":
            self._db.audit(
                "encryption.byok_set",
                f"Clave BYOK v{result['version']} establecida para tenant '{tenant_id}'",
            )
        return result

    def remove_tenant_key(self, tenant_id: str) -> dict[str, Any]:
        """Elimina todas las claves de un tenant."""
        result = self._key_manager.remove_tenant_key(tenant_id)
        self._db.audit(
            "encryption.key_removed",
            f"Claves eliminadas para tenant '{tenant_id}' ({result.get('removed_count', 0)} claves)",
        )
        return result

    def rotate_tenant_key(self, tenant_id: str) -> dict[str, Any]:
        """Rota la clave de un tenant: genera nueva version."""
        return self._key_manager.rotate_tenant_key(tenant_id)

    def get_key_info(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Obtiene metadatos de las claves de un tenant."""
        effective_tenant = tenant_id or DEFAULT_TENANT
        return self._key_manager.get_key_info(effective_tenant)

    def re_encrypt_value(self, ciphertext_dict: dict[str, Any], tenant_id: str | None = None) -> dict[str, Any]:
        """Re-cifra un valor con la clave mas reciente del tenant."""
        plaintext = self.decrypt(ciphertext_dict, tenant_id)
        context = ciphertext_dict.get("context")
        return self.encrypt(plaintext, tenant_id, context)

    # ── Foso 1 — Compliance Reproducible: Ed25519 signing ──

    def sign_payload(self, payload: bytes, tenant_id: str | None = None) -> str:
        """Firma un payload con la clave Ed25519 del tenant.

        La clave Ed25519 del tenant se obtiene del KeyManager. Si el tenant
        no tiene clave Ed25519 configurada, se genera una automáticamente y
        se almacena (modo dev). En producción, la clave debe venir del HSM
        o key escrow del tenant (BYOK).

        Args:
            payload: Bytes a firmar (típicamente canonical_json output).
            tenant_id: ID del tenant. Default si None.

        Returns:
            Firma en base64.
        """
        from src.orbital.canonical_serializer import ed25519_sign

        effective_tenant = tenant_id or DEFAULT_TENANT
        priv_pem = self._key_manager.get_tenant_ed25519_private_key(effective_tenant)
        if priv_pem is None:
            # Modo dev: generar y almacenar automáticamente.
            # En producción esto debe fallar con error explícito.
            priv_pem = self._key_manager.generate_and_store_tenant_ed25519_key(effective_tenant)
        return ed25519_sign(payload, priv_pem)

    def verify_signature(
        self,
        payload: bytes,
        signature_b64: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Verifica una firma Ed25519 contra la clave pública del tenant.

        Args:
            payload: Bytes originales firmados.
            signature_b64: Firma en base64.
            tenant_id: ID del tenant cuya clave pública se usará.

        Returns:
            True si la firma es válida, False si no coincide o hay error.
        """
        from src.orbital.canonical_serializer import ed25519_verify

        effective_tenant = tenant_id or DEFAULT_TENANT
        pub_pem = self._key_manager.get_tenant_ed25519_public_key(effective_tenant)
        if pub_pem is None:
            return False
        return ed25519_verify(payload, signature_b64, pub_pem)
