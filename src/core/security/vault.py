"""
Zenic-Flijo Secret Vault
Almacen cifrado para secretos del sistema con AES-256-GCM.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import threading
from pathlib import Path

from src.core.logging import setup_logging

_CRYPTOGRAPHY_AVAILABLE = False
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    pass

logger = setup_logging(__name__)

AES_KEY_SIZE = 32
GCM_NONCE_SIZE = 12
PBKDF2_ITERATIONS = 600000
VAULT_SALT_SIZE = 32
VAULT_VERSION = 1
VAULT_FILENAME = ".vault"

class VaultError(Exception): pass
class VaultLockedError(VaultError): pass
class VaultAuthError(VaultError): pass

class SecretVault:
    def __init__(self, vault_path=None):
        if vault_path is None:
            from src.core.config import DATA_DIR
            vault_path = DATA_DIR / VAULT_FILENAME
        self._path = Path(vault_path)
        self._lock = threading.RLock()
        self._key = None
        self._secrets = {}
        self._salt = None
        self._available = _CRYPTOGRAPHY_AVAILABLE
        if not self._available:
            logger.warning("SecretVault: cryptography no disponible.")
    @property
    def is_available(self): return self._available
    @property
    def is_unlocked(self): return self._key is not None
    @property
    def exists(self): return self._path.exists()
    def unlock(self, password):
        if not self._available: raise VaultError("cryptography no disponible")
        with self._lock:
            if self.exists: self._load(password)
            else: self._init(password)
    def lock(self):
        with self._lock: self._key = None; self._secrets = {}
    def change_password(self, old_password, new_password):
        with self._lock:
            if not self.exists: raise VaultError("Vault no existe")
            self.unlock(old_password)
            secrets_copy = dict(self._secrets)
            self._salt = os.urandom(VAULT_SALT_SIZE)
            self._key = self._derive_key(new_password, self._salt)
            self._secrets = secrets_copy
            self._save()
    def get(self, key, default=None):
        if self._key is None: raise VaultLockedError("Vault no desbloqueado.")
        with self._lock:
            encrypted = self._secrets.get(key)
            if encrypted is None: return default
            aesgcm = AESGCM(self._key)
            nonce = base64.b64decode(encrypted["nonce"])
            ciphertext = base64.b64decode(encrypted["ciphertext"])
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return json.loads(plaintext.decode("utf-8"))
    def set(self, key, value):
        if self._key is None: raise VaultLockedError("Vault no desbloqueado.")
        with self._lock:
            aesgcm = AESGCM(self._key)
            nonce = os.urandom(GCM_NONCE_SIZE)
            plaintext = json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            self._secrets[key] = {"nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(ciphertext).decode()}
            self._save()
    def delete(self, key):
        if self._key is None: raise VaultLockedError("Vault no desbloqueado.")
        with self._lock:
            if key in self._secrets: del self._secrets[key]; self._save(); return True
            return False
    def has(self, key):
        if self._key is None: raise VaultLockedError("Vault no desbloqueado.")
        return key in self._secrets
    def list_keys(self):
        if self._key is None: raise VaultLockedError("Vault no desbloqueado.")
        return list(self._secrets.keys())
    def _derive_key(self, password, salt):
        return PBKDF2HMAC(algorithm=hashes.SHA256(), length=AES_KEY_SIZE, salt=salt, iterations=PBKDF2_ITERATIONS).derive(password.encode("utf-8"))
    def _init(self, password):
        self._salt = os.urandom(VAULT_SALT_SIZE)
        self._key = self._derive_key(password, self._salt)
        self._secrets = {}; self._save()
    def _load(self, password):
        with open(self._path) as f: data = json.load(f)
        if data.get("version") != VAULT_VERSION: raise VaultError("Version no soportada")
        self._salt = base64.b64decode(data["salt"])
        self._key = self._derive_key(password, self._salt)
        verification = data.get("verification")
        if verification:
            try:
                aesgcm = AESGCM(self._key)
                nonce = base64.b64decode(verification["nonce"])
                ct = base64.b64decode(verification["ciphertext"])
                aesgcm.decrypt(nonce, ct, None)
            except Exception as e: self._key = None; raise VaultAuthError("Password incorrecto") from e
        self._secrets = data.get("secrets", {})
    def _save(self):
        aesgcm = AESGCM(self._key)
        nonce = os.urandom(GCM_NONCE_SIZE)
        verification_ct = aesgcm.encrypt(nonce, b"VALID", None)
        data = {"version": VAULT_VERSION, "salt": base64.b64encode(self._salt).decode() if self._salt else "", "pbkdf2_iterations": PBKDF2_ITERATIONS, "verification": {"nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(verification_ct).decode()}, "secrets": self._secrets}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)
        with contextlib.suppress(OSError): self._path.chmod(0o600)
