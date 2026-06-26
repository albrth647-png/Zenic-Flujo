"""SSO subpackage — SAML, OIDC, Keycloak, sessions.

Original sso.py module has been moved here as service.py to avoid
the module/package name collision that previously required an
importlib hack.
"""
from src.core.security.sso.constants import (
    SSO_BASE_URL,
    SSO_SESSION_TTL,
    KEYCLOAK_URL,
    KEYCLOAK_REALM,
    SAML_NS,
    OIDC_STATE_PREFIX,
    SSO_SESSION_PREFIX,
)
from src.core.security.sso.provider_manager import (
    ensure_tables,
    configure_provider,
    get_providers,
    get_provider,
    remove_provider,
)
from src.core.security.sso.saml import SAMLHandler
from src.core.security.sso.oidc import OIDCHandler
from src.core.security.sso.keycloak import auto_configure_keycloak
from src.core.security.sso.session import (
    create_sso_session,
    validate_sso_session,
    logout_session,
    cleanup_expired_sessions,
    create_or_link_user,
    link_existing_user,
)
from src.core.security.sso.routes import register_sso_routes
from src.core.security.sso.service import SSOService

__all__ = [
    "SSOService", "SAMLHandler", "OIDCHandler",
    "ensure_tables", "configure_provider", "get_providers", "get_provider", "remove_provider",
    "create_sso_session", "validate_sso_session", "logout_session", "cleanup_expired_sessions",
    "create_or_link_user", "link_existing_user",
    "auto_configure_keycloak",
    "register_sso_routes",
    "SSO_BASE_URL", "SSO_SESSION_TTL", "KEYCLOAK_URL", "KEYCLOAK_REALM",
    "SAML_NS", "OIDC_STATE_PREFIX", "SSO_SESSION_PREFIX",
]
