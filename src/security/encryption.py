"""
Workflow Determinista — BYOK Encryption Service (Phase 1)

Servicio de cifrado Bring Your Own Key (BYOK) con soporte multi-tenant.

Funcionalidades:
- Cada tenant puede proporcionar su propia clave maestra de cifrado (BYOK)
- Si no se proporciona clave BYOK, el sistema genera una clave por defecto
- Rotación de claves sin downtime: nueva clave cifra datos nuevos, clave antigua descifra existentes
- Versionado de claves: rastrea qué versión de clave cifró cada dato
- Key wrapping: las claves de tenant se envuelven (cifran) con KEK

Tipos de cifrado:
- AES-256-GCM para cifrado de datos (cifrado autenticado)
- RSA-2048 para key wrapping (cifrar claves de tenant con KEK)
- HKDF para derivación de claves (derivar sub-claves desde la clave maestra)
"""

import base64
import json
import os
import secrets
import threading
from datetime import UTC, datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

# ── Constantes ──────────────────────────────────────────

AES_KEY_SIZE: int = 32  # 256 bits
GCM_NONCE_SIZE: int = 12  # 96 bits
GCM_TAG_SIZE: int = 16  # 128 bits
RSA_KEY_SIZE: int = 2048
HKDF_INFO_PREFIX: str = "zenic-flijo-encryption"
DEFAULT_TENANT: str = "__default__"
KEK_SALT: bytes = b"zenic-flijo-kek-salt-v1"


class EncryptionService:
    """Servicio de cifrado BYOK con soporte multi-tenant y rotación de claves.

    Cada tenant puede proporcionar su propia clave AES-256 (BYOK). Las claves
    se almacenan cifradas (wrapped) con una Key Encryption Key (KEK) derivada
    de WFD_ENCRYPTION_MASTER_KEY o SESSION_SECRET. Se usa RSA-2048 como
    mecanismo adicional de key wrapping.

    El versionado de claves permite rotación sin downtime: las claves antiguas
    se conservan para descifrar datos existentes, mientras que la clave activa
    se usa para cifrar datos nuevos.
    """

    _instance: "EncryptionService | None" = None
    _lock = threading.RLock()

    def __new__(cls) -> "EncryptionService":
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
            self._ensure_tables()

            # Caché de claves desenvueltas en memoria
            self._key_cache: dict[str, bytes] = {}  # "tenant:version" -> AES key bytes
            self._rsa_private_key: rsa.RSAPrivateKey | None = None

            # Derivar KEK y cargar/generar par RSA
            self._kek = self._derive_kek()
            self._load_or_generate_rsa_keypair()

            # Asegurar que existe una clave por defecto
            self._ensure_default_key()

            logger.info("EncryptionService: Inicializado correctamente")

    # ── Inicialización de tablas ──────────────────────────

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

            CREATE INDEX IF NOT EXISTS idx_enc_keys_tenant
                ON encryption_keys(tenant_id, is_active);
            CREATE INDEX IF NOT EXISTS idx_enc_keys_version
                ON encryption_keys(tenant_id, version);
            CREATE INDEX IF NOT EXISTS idx_enc_data_tenant
                ON encrypted_data(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_enc_data_field
                ON encrypted_data(tenant_id, field_name);
        """)
        conn.commit()

    # ── Derivación de KEK ────────────────────────────────

    def _derive_kek(self) -> bytes:
        """Deriva la Key Encryption Key (KEK) desde variable de entorno o SESSION_SECRET.

        Orden de precedencia:
        1. WFD_ENCRYPTION_MASTER_KEY (recomendado para producción)
        2. SESSION_SECRET (fallback para desarrollo)
        """
        master_key = os.environ.get("WFD_ENCRYPTION_MASTER_KEY", "")
        if not master_key:
            from src.config import SESSION_SECRET

            master_key = SESSION_SECRET
            logger.warning(
                "EncryptionService: WFD_ENCRYPTION_MASTER_KEY no configurado. "
                "Usando SESSION_SECRET como fallback. Configure WFD_ENCRYPTION_MASTER_KEY "
                "para mayor seguridad."
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
        """Carga o genera el par de claves RSA-2048 para key wrapping.

        La clave privada RSA se almacena cifrada con el KEK (AES-256-GCM).
        """
        stored = self._db.fetchone("SELECT value FROM settings WHERE key = 'encryption_rsa_private_key'")

        if stored:
            try:
                encrypted_data = json.loads(stored["value"])
                ciphertext = base64.b64decode(encrypted_data["ciphertext"])
                nonce = base64.b64decode(encrypted_data["nonce"])
                aesgcm = AESGCM(self._kek)
                private_key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                self._rsa_private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
                logger.info("EncryptionService: Clave RSA cargada desde almacenamiento")
            except Exception as e:
                logger.error(f"EncryptionService: Error cargando clave RSA: {e}. Generando nueva.")
                self._generate_and_store_rsa_keypair()
        else:
            self._generate_and_store_rsa_keypair()

    def _generate_and_store_rsa_keypair(self) -> None:
        """Genera un nuevo par de claves RSA-2048 y lo almacena cifrado."""
        self._rsa_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=RSA_KEY_SIZE,
        )

        # Serializar clave privada en PEM
        private_key_bytes = self._rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Cifrar con KEK (AES-256-GCM)
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
        logger.info("EncryptionService: Nuevo par de claves RSA-2048 generado")

    # ── Gestión de claves de tenant (interno) ────────────

    def _ensure_default_key(self) -> None:
        """Asegura que exista una clave de cifrado por defecto utilizable.

        Si la clave activa no se puede desenvolver (ej. KEK cambió por
        rotación de SESSION_SECRET), la desactiva y genera una nueva.
        """
        existing = self._db.fetchone(
            "SELECT key_id, version FROM encryption_keys WHERE tenant_id = ? AND is_active = 1",
            (DEFAULT_TENANT,),
        )
        if existing:
            # Verificar que la clave activa se puede desenvolver
            try:
                self._unwrap_tenant_key(DEFAULT_TENANT, existing["version"])
                return  # Clave utilizable, no hacer nada
            except ValueError:
                logger.warning(
                    "EncryptionService: Clave por defecto no se puede desenvolver "
                    "(¿KEK cambiado?). Desactivando y generando nueva."
                )
                # Desactivar claves inutilizables
                self._db.execute(
                    "UPDATE encryption_keys SET is_active = 0 WHERE tenant_id = ? AND is_active = 1",
                    (DEFAULT_TENANT,),
                )
                self._db.commit()
                # Limpiar caché obsoleta
                stale_keys = [k for k in self._key_cache if k.startswith(f"{DEFAULT_TENANT}:")]
                for k in stale_keys:
                    del self._key_cache[k]

        self._generate_tenant_key(DEFAULT_TENANT)

    def _generate_tenant_key(self, tenant_id: str) -> dict:
        """Genera una nueva clave AES-256 para un tenant.

        La clave se almacena de dos formas:
        1. Cifrada con KEK (AES-256-GCM) en encrypted_key
        2. Envuelta con RSA-OAEP en rsa_wrapped_key

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con key_id, tenant_id, version, is_active
        """
        # Generar clave AES-256 aleatoria
        key_bytes = os.urandom(AES_KEY_SIZE)

        # Obtener la siguiente versión
        version_row = self._db.fetchone(
            "SELECT MAX(version) as max_ver FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        next_version = (version_row["max_ver"] or 0) + 1

        # Desactivar claves anteriores del tenant
        now_iso = datetime.now(UTC).isoformat()
        self._db.execute(
            "UPDATE encryption_keys SET is_active = 0, rotated_at = ? WHERE tenant_id = ? AND is_active = 1",
            (now_iso, tenant_id),
        )

        # Cifrar la clave con KEK (AES-256-GCM)
        nonce = os.urandom(GCM_NONCE_SIZE)
        aesgcm = AESGCM(self._kek)
        wrapped_key = aesgcm.encrypt(nonce, key_bytes, None)
        # Combinar nonce + ciphertext+tag para almacenamiento
        encrypted_key_b64 = base64.b64encode(nonce + wrapped_key).decode()

        # Envolver la clave con RSA-OAEP
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

        # Generar ID único
        key_id = f"key_{tenant_id}_{next_version}_{secrets.token_hex(4)}"

        # Almacenar en BD
        self._db.execute(
            """INSERT INTO encryption_keys
               (key_id, tenant_id, key_type, encrypted_key, rsa_wrapped_key, version, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                key_id,
                tenant_id,
                "AES-256-GCM",
                encrypted_key_b64,
                rsa_wrapped_b64,
                next_version,
                now_iso,
            ),
        )
        self._db.commit()

        # Cachear la clave en memoria
        cache_key = f"{tenant_id}:{next_version}"
        self._key_cache[cache_key] = key_bytes

        self._db.audit(
            "encryption.key_generated",
            f"Clave v{next_version} generada para tenant '{tenant_id}'",
        )
        logger.info(f"EncryptionService: Clave v{next_version} generada para tenant '{tenant_id}'")

        return {
            "key_id": key_id,
            "tenant_id": tenant_id,
            "version": next_version,
            "is_active": True,
        }

    def _unwrap_tenant_key(self, tenant_id: str, version: int) -> bytes:
        """Desenvuelve (descifra) la clave de un tenant desde el almacenamiento.

        Intenta primero con KEK (AES-256-GCM), y si falla, con RSA-OAEP.

        Args:
            tenant_id: ID del tenant
            version: Versión de la clave

        Returns:
            Clave AES-256 en bytes

        Raises:
            ValueError: Si no se encuentra o no se puede desenvolver la clave
        """
        cache_key = f"{tenant_id}:{version}"
        if cache_key in self._key_cache:
            return self._key_cache[cache_key]

        key_row = self._db.fetchone(
            "SELECT encrypted_key, rsa_wrapped_key FROM encryption_keys WHERE tenant_id = ? AND version = ?",
            (tenant_id, version),
        )
        if not key_row:
            raise ValueError(f"Clave no encontrada para tenant '{tenant_id}' versión {version}")

        key_bytes: bytes | None = None

        # Intentar desenvolver con KEK (AES-256-GCM)
        try:
            encrypted_data = base64.b64decode(key_row["encrypted_key"])
            nonce = encrypted_data[:GCM_NONCE_SIZE]
            ciphertext = encrypted_data[GCM_NONCE_SIZE:]
            aesgcm = AESGCM(self._kek)
            key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            logger.warning(f"Error desenvolviendo clave con KEK: {e}. Intentando con RSA.")

        # Fallback: intentar con RSA-OAEP
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
            raise ValueError(f"No se pudo desenvolver la clave para tenant '{tenant_id}' versión {version}")

        # Cachear en memoria
        self._key_cache[cache_key] = key_bytes
        return key_bytes

    def _get_active_key(self, tenant_id: str) -> tuple[bytes, int, str]:
        """Obtiene la clave activa y su versión para un tenant.

        Si el tenant no tiene clave propia, usa la clave por defecto.

        Args:
            tenant_id: ID del tenant

        Returns:
            Tupla (key_bytes, version, effective_tenant_id)
        """
        # Buscar clave activa del tenant
        key_row = self._db.fetchone(
            "SELECT version FROM encryption_keys WHERE tenant_id = ? AND is_active = 1 ORDER BY version DESC LIMIT 1",
            (tenant_id,),
        )

        if key_row:
            effective_tenant = tenant_id
        else:
            # Fallback a clave por defecto
            effective_tenant = DEFAULT_TENANT
            key_row = self._db.fetchone(
                "SELECT version FROM encryption_keys WHERE tenant_id = ? AND is_active = 1 "
                "ORDER BY version DESC LIMIT 1",
                (effective_tenant,),
            )

        if not key_row:
            raise ValueError(f"No hay claves de cifrado disponibles para tenant '{tenant_id}'")

        version = key_row["version"]
        key_bytes = self._unwrap_tenant_key(effective_tenant, version)
        return key_bytes, version, effective_tenant

    # ── Derivación de sub-claves ─────────────────────────

    def _derive_sub_key(self, master_key: bytes, context: str) -> bytes:
        """Deriva una sub-clave usando HKDF con el contexto proporcionado.

        Esto permite que cada campo o contexto use una clave diferente
        (separación de claves), lo que es una buena práctica de seguridad.

        Args:
            master_key: Clave maestra del tenant
            context: Contexto para la derivación (ej. nombre de campo)

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

    # ── API pública: Cifrado / Descifrado ────────────────

    def encrypt(self, plaintext: str, tenant_id: str | None = None, context: str | None = None) -> dict:
        """Cifra un texto plano usando la clave del tenant o la clave por defecto.

        Utiliza AES-256-GCM para cifrado autenticado. Cada operación de cifrado
        genera un nonce (IV) único, garantizando que textos iguales producen
        cifrados diferentes.

        Args:
            plaintext: Texto a cifrar
            tenant_id: ID del tenant (None = clave por defecto)
            context: Contexto adicional para derivación de sub-clave (opcional)

        Returns:
            dict con: ciphertext (base64), iv (base64), tag (base64), key_version
        """
        effective_tenant = tenant_id or DEFAULT_TENANT
        key_bytes, version, _effective = self._get_active_key(effective_tenant)

        # Derivar sub-clave si hay contexto (separación de claves por campo)
        if context:
            key_bytes = self._derive_sub_key(key_bytes, context)

        # Cifrar con AES-256-GCM
        nonce = os.urandom(GCM_NONCE_SIZE)
        aesgcm = AESGCM(key_bytes)
        # AESGCM.encrypt retorna ciphertext + tag concatenados
        ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        ciphertext = ct_with_tag[:-GCM_TAG_SIZE]
        tag = ct_with_tag[-GCM_TAG_SIZE:]

        result = {
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "iv": base64.b64encode(nonce).decode(),
            "tag": base64.b64encode(tag).decode(),
            "key_version": version,
        }

        # Incluir contexto en el resultado para que decrypt pueda derivar la sub-clave
        if context:
            result["context"] = context

        self._db.audit(
            "encryption.encrypt",
            f"Dato cifrado para tenant '{effective_tenant}' con clave v{version}"
            + (f" (contexto: {context})" if context else ""),
        )
        return result

    def decrypt(self, ciphertext_dict: dict, tenant_id: str | None = None) -> str:
        """Descifra un texto cifrado usando la versión de clave correcta.

        El key_version en el ciphertext_dict indica qué versión de clave
        se usó para cifrar, lo que permite descifrar datos aunque la clave
        haya sido rotada.

        Args:
            ciphertext_dict: dict con ciphertext, iv, tag, key_version
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            Texto plano descifrado

        Raises:
            ValueError: Si no se encuentra la clave para descifrar
        """
        effective_tenant = tenant_id or DEFAULT_TENANT
        version = ciphertext_dict.get("key_version", 1)

        # Intentar desenvolver la clave del tenant; si falla, probar con default
        key_bytes: bytes | None = None
        try:
            key_bytes = self._unwrap_tenant_key(effective_tenant, version)
        except ValueError:
            if effective_tenant != DEFAULT_TENANT:
                import contextlib

                with contextlib.suppress(ValueError):
                    key_bytes = self._unwrap_tenant_key(DEFAULT_TENANT, version)

        if key_bytes is None:
            raise ValueError(
                f"No se pudo desenvolver la clave para descifrar: tenant '{effective_tenant}' versión {version}"
            )

        # Derivar sub-clave si hay contexto
        context = ciphertext_dict.get("context")
        if context:
            key_bytes = self._derive_sub_key(key_bytes, context)

        # Descifrar con AES-256-GCM
        ciphertext = base64.b64decode(ciphertext_dict["ciphertext"])
        nonce = base64.b64decode(ciphertext_dict["iv"])
        tag = base64.b64decode(ciphertext_dict["tag"])

        aesgcm = AESGCM(key_bytes)
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)

        return plaintext.decode("utf-8")

    def encrypt_field(self, value: str, field_name: str, tenant_id: str | None = None) -> dict:
        """Cifrado a nivel de campo con derivación de sub-clave por nombre de campo.

        Cada campo se cifra con una sub-clave derivada mediante HKDF usando
        el nombre del campo como contexto. Esto proporciona separación de
        claves: comprometer la clave de un campo no compromete otros.

        Args:
            value: Valor del campo a cifrar
            field_name: Nombre del campo (usado para derivar sub-clave)
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            dict con: ciphertext, iv, tag, key_version, field_name
        """
        result = self.encrypt(value, tenant_id, context=field_name)
        result["field_name"] = field_name
        return result

    def decrypt_field(self, value: dict, field_name: str, tenant_id: str | None = None) -> str:
        """Descifrado a nivel de campo.

        Args:
            value: dict con ciphertext, iv, tag, key_version
            field_name: Nombre del campo (usado para derivar sub-clave)
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            Valor del campo descifrado
        """
        value_with_context = {**value, "context": field_name}
        return self.decrypt(value_with_context, tenant_id)

    # ── API pública: Gestión de claves BYOK ──────────────

    def set_tenant_key(self, tenant_id: str, key_b64: str) -> dict:
        """Almacena la clave BYOK de un tenant (envuelta con KEK y RSA).

        La clave proporcionada por el tenant se envuelve (cifra) con:
        1. KEK (AES-256-GCM) → encrypted_key
        2. RSA-OAEP → rsa_wrapped_key

        NUNCA se almacena la clave del tenant en texto plano.

        Args:
            tenant_id: ID del tenant
            key_b64: Clave del tenant en base64 (debe ser de 256 bits / 32 bytes)

        Returns:
            dict con: status, key_id, tenant_id, version
        """
        try:
            key_bytes = base64.b64decode(key_b64)
        except Exception as e:
            return {"status": "error", "message": f"Clave base64 inválida: {e}"}

        if len(key_bytes) != AES_KEY_SIZE:
            return {
                "status": "error",
                "message": f"La clave debe ser de {AES_KEY_SIZE} bytes (256 bits)",
            }

        # Desactivar claves anteriores
        now_iso = datetime.now(UTC).isoformat()
        self._db.execute(
            "UPDATE encryption_keys SET is_active = 0, rotated_at = ? WHERE tenant_id = ? AND is_active = 1",
            (now_iso, tenant_id),
        )

        # Obtener siguiente versión
        version_row = self._db.fetchone(
            "SELECT MAX(version) as max_ver FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        next_version = (version_row["max_ver"] or 0) + 1

        # Cifrar con KEK (AES-256-GCM)
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

        # Generar ID único
        key_id = f"key_{tenant_id}_{next_version}_{secrets.token_hex(4)}"

        # Almacenar
        self._db.execute(
            """INSERT INTO encryption_keys
               (key_id, tenant_id, key_type, encrypted_key, rsa_wrapped_key, version, is_active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                key_id,
                tenant_id,
                "AES-256-GCM",
                encrypted_key_b64,
                rsa_wrapped_b64,
                next_version,
                now_iso,
            ),
        )
        self._db.commit()

        # Cachear en memoria
        cache_key = f"{tenant_id}:{next_version}"
        self._key_cache[cache_key] = key_bytes

        self._db.audit(
            "encryption.byok_set",
            f"Clave BYOK v{next_version} establecida para tenant '{tenant_id}'",
        )
        logger.info(f"EncryptionService: Clave BYOK v{next_version} establecida para tenant '{tenant_id}'")

        return {
            "status": "ok",
            "key_id": key_id,
            "tenant_id": tenant_id,
            "version": next_version,
        }

    def remove_tenant_key(self, tenant_id: str) -> dict:
        """Elimina todas las claves de un tenant.

        ADVERTENCIA: Los datos cifrados con estas claves no podrán ser
        descifrados después de eliminarlas.

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con: status, removed_count
        """
        count_row = self._db.fetchone(
            "SELECT COUNT(*) as c FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        removed_count = count_row["c"] if count_row else 0

        self._db.execute(
            "DELETE FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        self._db.commit()

        # Limpiar caché
        keys_to_remove = [k for k in self._key_cache if k.startswith(f"{tenant_id}:")]
        for k in keys_to_remove:
            del self._key_cache[k]

        self._db.audit(
            "encryption.key_removed",
            f"Claves eliminadas para tenant '{tenant_id}' ({removed_count} claves)",
        )
        logger.info(f"EncryptionService: {removed_count} clave(s) eliminada(s) para tenant '{tenant_id}'")

        return {"status": "ok", "removed_count": removed_count}

    def rotate_tenant_key(self, tenant_id: str) -> dict:
        """Rota la clave de un tenant: genera nueva versión, marca la anterior como inactiva.

        La clave anterior se mantiene para descifrar datos existentes.
        Los datos nuevos se cifran con la nueva clave activa.
        La re-ecncripción de datos existentes puede hacerse de forma
        perezosa (al leer) o en lote (batch).

        Args:
            tenant_id: ID del tenant

        Returns:
            dict con: status, key_id, version
        """
        # Si el tenant no tiene clave, crear una
        existing = self._db.fetchone(
            "SELECT key_id FROM encryption_keys WHERE tenant_id = ?",
            (tenant_id,),
        )
        if not existing:
            result = self._generate_tenant_key(tenant_id)
            return {"status": "ok", **result}

        # Generar nueva versión (desactiva la anterior automáticamente)
        result = self._generate_tenant_key(tenant_id)

        self._db.audit(
            "encryption.key_rotated",
            f"Clave rotada para tenant '{tenant_id}' → v{result['version']}",
        )
        return {"status": "ok", **result}

    def get_key_info(self, tenant_id: str | None = None) -> dict:
        """Obtiene metadatos de las claves de un tenant.

        Args:
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            dict con: tenant_id, keys (lista de versiones con metadatos), total_versions
        """
        effective_tenant = tenant_id or DEFAULT_TENANT

        rows = self._db.fetchall(
            """SELECT key_id, tenant_id, key_type, version, is_active, created_at, rotated_at
               FROM encryption_keys
               WHERE tenant_id = ?
               ORDER BY version DESC""",
            (effective_tenant,),
        )

        keys = []
        for row in rows:
            keys.append(
                {
                    "key_id": row["key_id"],
                    "key_type": row["key_type"],
                    "version": row["version"],
                    "is_active": bool(row["is_active"]),
                    "created_at": row["created_at"],
                    "rotated_at": row["rotated_at"],
                }
            )

        return {
            "tenant_id": effective_tenant,
            "keys": keys,
            "total_versions": len(keys),
        }

    def re_encrypt_value(self, ciphertext_dict: dict, tenant_id: str | None = None) -> dict:
        """Re-cifra un valor con la clave más reciente del tenant.

        Útil después de una rotación de clave para migrar datos a la nueva
        versión. Descifra con la versión original y re-cifra con la activa.

        Args:
            ciphertext_dict: dict con ciphertext, iv, tag, key_version
            tenant_id: ID del tenant (None = clave por defecto)

        Returns:
            dict con: ciphertext, iv, tag, key_version (nueva versión)
        """
        # Descifrar con la versión original
        plaintext = self.decrypt(ciphertext_dict, tenant_id)

        # Re-cifrar con la clave activa actual
        context = ciphertext_dict.get("context")
        return self.encrypt(plaintext, tenant_id, context)
