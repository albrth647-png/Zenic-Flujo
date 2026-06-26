"""Security — RBAC Granular, MFA TOTP, BYOK Encryption, SSO, Secret Vault."""

from src.core.security.crypto import CryptoEngine
from src.core.security.encryption import EncryptionService
from src.core.security.key_manager import KeyManager
from src.core.security.mfa import MFAService
from src.core.security.rbac import RBACManager, require_permission
from src.core.security.sso import SSOService, register_sso_routes
from src.core.security.vault import SecretVault, VaultAuthError, VaultError, VaultLockedError

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
