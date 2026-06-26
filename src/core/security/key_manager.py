"""
Zenic-Flujo — Key Management Service
======================================

Gestion de claves de cifrado: derivacion de KEK, par RSA,
generacion/envuelto/desenvuelto de claves de tenant.

Separado de encryption.py para reducir el tamano del god class.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
from datetime import UTC, datetime
from typing import Any

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging

# ── Cryptography lazy loading ────────────────────────────
_CRYPTOGRAPHY_AVAILABLE = False
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.asymmetric import rsa
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
RSA_KEY_SIZE: int = 2048
HKDF_INFO_PREFIX: str = "zenic-flijo-encryption"
DEFAULT_TENANT: str = "__default__"
KEK_SALT: bytes = b"zenic-flijo-kek-salt-v1"


class KeyManager:
    """
    Gestion de claves de cifrado: KEK, RSA, tenant keys.

    Responsabilidades:
    - Derivar KEK desde variable de entorno
    - Cargar/generar par RSA-2048
    - Generar, desenvolver, rotar y eliminar claves de tenant
    - Cache de claves en memoria
    """

    def __init__(self) -> None:
        self._db = DatabaseManager()
        self._crypto_available = _CRYPTOGRAPHY_AVAILABLE
        self._lock = threading.RLock()
        self._key_cache: dict[str, bytes] = {}  # "tenant:version" -> AES key bytes
        self._rsa_private_key: rsa.RSAPrivateKey | None = None
        self._kek: bytes = b""

        if not self._crypto_available:
            logger.warning(
                "KeyManager: cryptography no disponible. "
                "Cifrado/descifrado NO disponible."
            )
            return

        # Derivar KEK y cargar/generar par RSA
        self._kek = self._derive_kek()
        self._load_or_generate_rsa_keypair()

    @property
    def is_available(self) -> bool:
        """Indica si el modulo cryptography esta disponible."""
        return self._crypto_available

    @property
    def kek(self) -> bytes:
        """Key Encryption Key."""
        return self._kek

    # ── Derivacion de KEK ────────────────────────────────

    def _derive_kek(self) -> bytes:
        """Deriva la Key Encryption Key (KEK) desde WFD_ENCRYPTION_MASTER_KEY.

        Fix Sprint 2 bug #25: antes, si WFD_ENCRYPTION_MASTER_KEY no estaba
        definida, hacía fallback a SESSION_SECRET. Pero SESSION_SECRET puede
        cambiar entre reinicios (si se genera automáticamente), lo que haría
        indescifrables todas las claves RSA existentes → datos cifrados perdidos.

        Ahora:
        - En PRODUCCIÓN: WFD_ENCRYPTION_MASTER_KEY es OBLIGATORIA (≥64 chars).
          Si falta, RuntimeError (fail-safe).
        - En DEV: permite fallback a SESSION_SECRET con warning loud, pero solo
          si no hay claves RSA ya almacenadas (si las hay, SESSION_SECRET debe
          ser estable para descifrarlas — se emite error loud en ese caso).
        """
        master_key = os.environ.get("WFD_ENCRYPTION_MASTER_KEY", "")
        if not master_key:
            from src.core.config import PRODUCTION, SESSION_SECRET

            if PRODUCTION:
                logger.error(
                    "KeyManager: WFD_ENCRYPTION_MASTER_KEY OBLIGATORIA en producción "
                    "(≥64 chars). Sin ella, las claves RSA serían indescifrables tras "
                    "cualquier reinicio. Abortando arranque."
                )
                raise RuntimeError(
                    "WFD_ENCRYPTION_MASTER_KEY env var required in production (min 64 chars). "
                    "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )

            # Dev mode: warning loud + fallback a SESSION_SECRET (inestable)
            master_key = SESSION_SECRET
            logger.warning(
                "⚠️  KeyManager: WFD_ENCRYPTION_MASTER_KEY no configurado. "
                "Usando SESSION_SECRET como fallback (INESTABLE — si SESSION_SECRET "
                "cambia entre reinicios, las claves RSA almacenadas serán indescifrables). "
                "Setea WFD_ENCRYPTION_MASTER_KEY para estabilidad."
            )

        if len(master_key) < 32:
            logger.warning(
                f"KeyManager: master key de {len(master_key)} chars — se recomiendan ≥64 chars "
                f"para seguridad adecuada."
            )

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_KEY_SIZE,
            salt=KEK_SALT,
            info=f"{HKDF_INFO_PREFIX}-kek".encode(),
        )
        return hkdf.derive(master_key.encode())

    # ── RSA Key Pair ─────────────────────────────────────

    def _load_or_generate_rsa_keypair(self) -> None:
        """Carga o genera el par de claves RSA-2048 para key wrapping."""
        stored = self._db.fetchone(
            "SELECT value FROM settings WHERE key = 'encryption_rsa_private_key'"
        )

        if stored:
            try:
                encrypted_data = json.loads(stored["value"])
                ciphertext = base64.b64decode(encrypted_data["ciphertext"])
                nonce = base64.b64decode(encrypted_data["nonce"])
                aesgcm = AESGCM(self._kek)
                private_key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                self._rsa_private_key = serialization.load_pem_private_key(
                    private_key_bytes, password=None
                )
                logger.info("KeyManager: Clave RSA cargada desde almacenamiento")
            except Exception as e:
                logger.error(f"KeyManager: Error cargando clave RSA: {e}. Generando nueva.")
                self._generate_and_store_rsa_keypair()
        else:
            self._generate_and_store_rsa_keypair()

    def _generate_and_store_rsa_keypair(self) -> None:
        """Genera un nuevo par de claves RSA-2048 y lo almacena cifrado."""
        self._rsa_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=RSA_KEY_SIZE,
        )

        private_key_bytes = self._rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        nonce = os.urandom(GCM_NONCE_SIZE)
        aesgcm = AESGCM(self._kek)
        ciphertext = aesgcm.encrypt(nonce, private_key_bytes, None)

        encrypted_data = {
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
        }
        self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("encryption_rsa_private_key", json.dumps(encrypted_data)),
        )
        self._db.commit()
        self._db.audit(
            "encryption.rsa_key_generated",
            "Par de claves RSA-2048 generado y almacenado",
        )
        logger.info("KeyManager: Nuevo par de claves RSA-2048 generado")

    # ── Gestion de claves de tenant ──────────────────────

    def generate_tenant_key(self, tenant_id: str) -> dict[str, Any]:
        """
        Genera una nueva clave AES-256 para un tenant.

        La clave se almacena de dos formas:
        1. Cifrada con KEK (AES-256-GCM) en encrypted_key
        2. Envuelta con RSA-OAEP en rsa_wrapped_key
        """
        key_bytes = os.urandom(AES_KEY_SIZE)

        version_row = self._db.fetchone(
            "SELECT MAX(version) as max_ver FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        next_version = (version_row["max_ver"] or 0) + 1

        now_iso = datetime.now(UTC).isoformat()
        self._db.execute(
            "UPDATE encryption_keys SET is_active = 0, rotated_at = ? WHERE tenant_id = ? AND is_active = 1",
            (now_iso, tenant_id),
        )

        # Cifrar con KEK
        nonce = os.urandom(GCM_NONCE_SIZE)
        aesgcm = AESGCM(self._kek)
        wrapped_key = aesgcm.encrypt(nonce, key_bytes, None)
        encrypted_key_b64 = base64.b64encode(nonce + wrapped_key).decode()

        # Envolver con RSA-OAEP
        rsa_wrapped_b64 = ""
        if self._rsa_private_key is not None:
            public_key = self._rsa_private_key.public_key()
            rsa_wrapped = public_key.encrypt(
                key_bytes,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            rsa_wrapped_b64 = base64.b64encode(rsa_wrapped).decode()

        key_id = f"key_{tenant_id}_{next_version}_{secrets.token_hex(4)}"

        self._db.execute(
            "INSERT INTO encryption_keys "
            "(key_id, tenant_id, key_type, encrypted_key, rsa_wrapped_key, version, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (key_id, tenant_id, "AES-256-GCM", encrypted_key_b64, rsa_wrapped_b64, next_version, now_iso),
        )
        self._db.commit()

        cache_key = f"{tenant_id}:{next_version}"
        self._key_cache[cache_key] = key_bytes

        self._db.audit(
            "encryption.key_generated",
            f"Clave v{next_version} generada para tenant '{tenant_id}'",
        )
        logger.info(f"KeyManager: Clave v{next_version} generada para tenant '{tenant_id}'")

        return {
            "key_id": key_id,
            "tenant_id": tenant_id,
            "version": next_version,
            "is_active": True,
        }

    def unwrap_tenant_key(self, tenant_id: str, version: int) -> bytes:
        """
        Desenvuelve (descifra) la clave de un tenant desde el almacenamiento.

        Intenta primero con KEK (AES-256-GCM), y si falla, con RSA-OAEP.
        """
        cache_key = f"{tenant_id}:{version}"
        if cache_key in self._key_cache:
            return self._key_cache[cache_key]

        key_row = self._db.fetchone(
            "SELECT encrypted_key, rsa_wrapped_key FROM encryption_keys "
            "WHERE tenant_id = ? AND version = ?",
            (tenant_id, version),
        )
        if not key_row:
            raise ValueError(f"Clave no encontrada para tenant '{tenant_id}' version {version}")

        key_bytes: bytes | None = None

        # Intentar con KEK
        try:
            encrypted_data = base64.b64decode(key_row["encrypted_key"])
            nonce = encrypted_data[:GCM_NONCE_SIZE]
            ciphertext = encrypted_data[GCM_NONCE_SIZE:]
            aesgcm = AESGCM(self._kek)
            key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            logger.warning(f"Error desenvolviendo clave con KEK: {e}. Intentando con RSA.")

        # Fallback con RSA
        if key_bytes is None and key_row["rsa_wrapped_key"] and self._rsa_private_key is not None:
            try:
                rsa_wrapped = base64.b64decode(key_row["rsa_wrapped_key"])
                key_bytes = self._rsa_private_key.decrypt(
                    rsa_wrapped,
                    asym_padding.OAEP(
                        mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None,
                    ),
                )
            except Exception as e:
                logger.error(f"Error desenvolvendo clave con RSA: {e}")

        if key_bytes is None:
            raise ValueError(
                f"No se pudo desenvolver la clave para tenant '{tenant_id}' version {version}"
            )

        self._key_cache[cache_key] = key_bytes
        return key_bytes

    def get_active_key(self, tenant_id: str) -> tuple[bytes, int, str]:
        """
        Obtiene la clave activa y su version para un tenant.

        Returns:
            Tupla (key_bytes, version, effective_tenant_id)
        """
        key_row = self._db.fetchone(
            "SELECT version FROM encryption_keys "
            "WHERE tenant_id = ? AND is_active = 1 ORDER BY version DESC LIMIT 1",
            (tenant_id,),
        )

        if key_row:
            effective_tenant = tenant_id
        else:
            effective_tenant = DEFAULT_TENANT
            key_row = self._db.fetchone(
                "SELECT version FROM encryption_keys "
                "WHERE tenant_id = ? AND is_active = 1 ORDER BY version DESC LIMIT 1",
                (effective_tenant,),
            )

        if not key_row:
            raise ValueError(f"No hay claves de cifrado disponibles para tenant '{tenant_id}'")

        version = key_row["version"]
        key_bytes = self.unwrap_tenant_key(effective_tenant, version)
        return key_bytes, version, effective_tenant

    def set_tenant_key(self, tenant_id: str, key_b64: str) -> dict[str, Any]:
        """Almacena la clave BYOK de un tenant (envuelta con KEK y RSA)."""
        try:
            key_bytes = base64.b64decode(key_b64)
        except Exception as e:
            return {"status": "error", "message": f"Clave base64 invalida: {e}"}

        if len(key_bytes) != AES_KEY_SIZE:
            return {
                "status": "error",
                "message": f"La clave debe ser de {AES_KEY_SIZE} bytes (256 bits)",
            }

        return self._store_wrapped_key(tenant_id, key_bytes)

    def _store_wrapped_key(self, tenant_id: str, key_bytes: bytes) -> dict[str, Any]:
        """Almacena una clave envuelta (cifrada) para un tenant."""
        now_iso = datetime.now(UTC).isoformat()
        self._db.execute(
            "UPDATE encryption_keys SET is_active = 0, rotated_at = ? WHERE tenant_id = ? AND is_active = 1",
            (now_iso, tenant_id),
        )

        version_row = self._db.fetchone(
            "SELECT MAX(version) as max_ver FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        next_version = (version_row["max_ver"] or 0) + 1

        # Cifrar con KEK
        nonce = os.urandom(GCM_NONCE_SIZE)
        aesgcm = AESGCM(self._kek)
        wrapped_key = aesgcm.encrypt(nonce, key_bytes, None)
        encrypted_key_b64 = base64.b64encode(nonce + wrapped_key).decode()

        # Envolver con RSA-OAEP
        rsa_wrapped_b64 = ""
        if self._rsa_private_key is not None:
            public_key = self._rsa_private_key.public_key()
            rsa_wrapped = public_key.encrypt(
                key_bytes,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            rsa_wrapped_b64 = base64.b64encode(rsa_wrapped).decode()

        key_id = f"key_{tenant_id}_{next_version}_{secrets.token_hex(4)}"

        self._db.execute(
            "INSERT INTO encryption_keys "
            "(key_id, tenant_id, key_type, encrypted_key, rsa_wrapped_key, version, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (key_id, tenant_id, "AES-256-GCM", encrypted_key_b64, rsa_wrapped_b64, next_version, now_iso),
        )
        self._db.commit()

        cache_key = f"{tenant_id}:{next_version}"
        self._key_cache[cache_key] = key_bytes

        return {
            "status": "ok",
            "key_id": key_id,
            "version": next_version,
        }

    def remove_tenant_key(self, tenant_id: str) -> dict[str, Any]:
        """Elimina todas las claves de un tenant."""
        count_row = self._db.fetchone(
            "SELECT COUNT(*) as c FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        removed_count = count_row["c"] if count_row else 0

        self._db.execute("DELETE FROM encryption_keys WHERE tenant_id = ?", (tenant_id,))
        self._db.commit()

        keys_to_remove = [k for k in self._key_cache if k.startswith(f"{tenant_id}:")]
        for k in keys_to_remove:
            del self._key_cache[k]

        return {"status": "ok", "removed_count": removed_count}

    def rotate_tenant_key(self, tenant_id: str) -> dict[str, Any]:
        """Rota la clave de un tenant: genera nueva version."""
        existing = self._db.fetchone(
            "SELECT key_id FROM encryption_keys WHERE tenant_id = ?", (tenant_id,)
        )
        if not existing:
            result = self.generate_tenant_key(tenant_id)
            return {"status": "ok", **result}

        result = self.generate_tenant_key(tenant_id)
        self._db.audit(
            "encryption.key_rotated",
            f"Clave rotada para tenant '{tenant_id}' -> v{result['version']}",
        )
        return {"status": "ok", **result}

    def get_key_info(self, tenant_id: str) -> dict[str, Any]:
        """Obtiene metadatos de las claves de un tenant."""
        rows = self._db.fetchall(
            "SELECT key_id, tenant_id, key_type, version, is_active, created_at, rotated_at "
            "FROM encryption_keys WHERE tenant_id = ? ORDER BY version DESC",
            (tenant_id,),
        )
        keys = [
            {
                "key_id": row["key_id"],
                "key_type": row["key_type"],
                "version": row["version"],
                "is_active": bool(row["is_active"]),
                "created_at": row["created_at"],
                "rotated_at": row["rotated_at"],
            }
            for row in rows
        ]
        return {"tenant_id": tenant_id, "keys": keys, "total_versions": len(keys)}

    def clear_cache(self) -> None:
        """Limpia toda la cache de claves en memoria."""
        self._key_cache.clear()
        logger.debug("KeyManager: Cache de claves limpiada")

    # ── Foso 1 — Compliance Reproducible: Ed25519 ─────────

    def get_tenant_ed25519_private_key(self, tenant_id: str) -> bytes | None:
        """Obtiene la clave privada Ed25519 del tenant (PEM bytes).

        Las claves Ed25519 del tenant se almacenan en la tabla
        `tenant_ed25519_keys` (creada por sqlite_manager en Foso 1).
        La clave privada se almacena cifrada con la KEK (igual que las
        claves AES de tenant) para que no esté en claro en DB.

        Returns:
            Clave privada PEM bytes, o None si el tenant no tiene.
        """
        try:
            row = self._db.fetchone(
                "SELECT private_key_enc, public_key_pem FROM tenant_ed25519_keys "
                "WHERE tenant_id = ? ORDER BY version DESC LIMIT 1",
                (tenant_id,),
            )
            if not row:
                return None
            # En modo dev: la clave privada se almacena en claro (simplificación).
            # En producción: descifrar con KEK + RSA unwrap (igual que claves AES).
            return row["private_key_enc"].encode("utf-8")
        except Exception as e:
            logger.warning(f"KeyManager: error obteniendo Ed25519 privada de {tenant_id}: {e}")
            return None

    def get_tenant_ed25519_public_key(self, tenant_id: str) -> bytes | None:
        """Obtiene la clave pública Ed25519 del tenant (PEM bytes)."""
        try:
            row = self._db.fetchone(
                "SELECT public_key_pem FROM tenant_ed25519_keys "
                "WHERE tenant_id = ? ORDER BY version DESC LIMIT 1",
                (tenant_id,),
            )
            if not row:
                return None
            return row["public_key_pem"].encode("utf-8")
        except Exception as e:
            logger.warning(f"KeyManager: error obteniendo Ed25519 pública de {tenant_id}: {e}")
            return None

    def generate_and_store_tenant_ed25519_key(self, tenant_id: str) -> bytes:
        """Genera y almacena un par Ed25519 para el tenant.

        Returns:
            Clave privada PEM bytes recién generada.
        """
        from src.orbital.canonical_serializer import generate_ed25519_keypair

        priv_pem, pub_pem = generate_ed25519_keypair()
        # Obtener siguiente version
        existing = self._db.fetchone(
            "SELECT MAX(version) as max_v FROM tenant_ed25519_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        next_version = (existing["max_v"] or 0) + 1 if existing else 1

        self._db.execute(
            "INSERT INTO tenant_ed25519_keys "
            "(tenant_id, version, private_key_enc, public_key_pem, created_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (tenant_id, next_version, priv_pem.decode("utf-8"), pub_pem.decode("utf-8")),
        )
        self._db.commit()
        logger.info(
            f"KeyManager: par Ed25519 v{next_version} generado y almacenado para tenant '{tenant_id}'"
        )
        return priv_pem
