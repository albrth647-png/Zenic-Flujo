"""
Workflow Determinista — Ed25519 Key Management
Genera, almacena y carga pares de claves Ed25519 para licencias asimétricas.
La clave privada se cifra con una contraseña derivada del admin (PBKDF2).
"""

import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import DATA_DIR
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

KEYS_DIR = DATA_DIR / "license_keys"
KEYS_DIR.mkdir(parents=True, exist_ok=True)

PRIVATE_KEY_FILE = KEYS_DIR / "private_key.enc"
PUBLIC_KEY_FILE = KEYS_DIR / "public_key.pem"
METADATA_FILE = KEYS_DIR / "metadata.json"

SALT_FILE = KEYS_DIR / "key_salt.bin"
SALT_SIZE = 16
PBKDF2_ITERATIONS = 600_000


def _derive_key(password: str, salt: bytes) -> bytes:
    """Deriva clave de cifrado desde password + salt usando PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode())


def _encrypt_private_key(private_key: ed25519.Ed25519PrivateKey, password: str) -> tuple[bytes, bytes]:
    """Cifra la clave privada con AES-GCM usando clave derivada del password."""
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ciphertext = aesgcm.encrypt(nonce, private_bytes, None)
    return salt + nonce + ciphertext, salt


def _decrypt_private_key(encrypted_data: bytes, password: str) -> ed25519.Ed25519PrivateKey:
    """Descifra la clave privada con AES-GCM."""
    salt = encrypted_data[:SALT_SIZE]
    nonce = encrypted_data[SALT_SIZE:SALT_SIZE + 12]
    ciphertext = encrypted_data[SALT_SIZE + 12:]
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    private_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)


def generate_keypair(admin_password: str) -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """
    Genera un nuevo par de claves Ed25519.
    Guarda la clave privada cifrada con admin_password.
    Guarda la clave pública en formato PEM (sin cifrar, para embeber en binario).
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    encrypted_private, salt = _encrypt_private_key(private_key, admin_password)

    with open(PRIVATE_KEY_FILE, "wb") as f:
        f.write(encrypted_private)
    with open(SALT_FILE, "wb") as f:
        f.write(salt)

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(PUBLIC_KEY_FILE, "wb") as f:
        f.write(public_pem)

    metadata = {
        "algorithm": "Ed25519",
        "created_at": __import__("datetime").datetime.now().isoformat(),
    }
    with open(METADATA_FILE, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Par de claves Ed25519 generado y guardado en {KEYS_DIR}")
    return private_key, public_key


def load_private_key(admin_password: str) -> ed25519.Ed25519PrivateKey | None:
    """Carga la clave privada descifrándola con admin_password."""
    if not PRIVATE_KEY_FILE.exists():
        return None
    with open(PRIVATE_KEY_FILE, "rb") as f:
        encrypted_data = f.read()
    try:
        return _decrypt_private_key(encrypted_data, admin_password)
    except Exception as e:
        logger.error(f"Error descifrando clave privada: {e}")
        return None


def load_public_key() -> ed25519.Ed25519PublicKey | None:
    """Carga la clave pública desde archivo PEM."""
    if not PUBLIC_KEY_FILE.exists():
        return None
    with open(PUBLIC_KEY_FILE, "rb") as f:
        public_pem = f.read()
    return serialization.load_pem_public_key(public_pem)


def get_embedded_public_key() -> str:
    """Retorna la clave pública en formato PEM como string para embeber en el binario."""
    if not PUBLIC_KEY_FILE.exists():
        return ""
    with open(PUBLIC_KEY_FILE) as f:
        return f.read()


def keys_exist() -> bool:
    """Verifica si ya existe un par de claves generado."""
    return PRIVATE_KEY_FILE.exists() and PUBLIC_KEY_FILE.exists()
