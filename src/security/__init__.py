"""Security — RBAC Granular, MFA TOTP, BYOK Encryption, SSO, Secret Vault."""

from src.security.crypto import CryptoEngine
from src.security.encryption import EncryptionService
from src.security.key_manager import KeyManager
from src.security.mfa import MFAService
from src.security.rbac import RBACManager, require_permission
from src.security.sso import SSOService, register_sso_routes
from src.security.vault import SecretVault, VaultAuthError, VaultError, VaultLockedError

__all__ = [
    "CryptoEngine",
    "EncryptionService",
    "KeyManager",
    "MFAService",
    "RBACManager",
    "SSOService",
    "SecretVault",
    "VaultAuthError",
    "VaultError",
    "VaultLockedError",
    "register_sso_routes",
    "require_permission",
]
