"""
SSO — Single Sign-On subpackage (SAML 2.0 + OIDC + Keycloak)
"""

from src.security.sso.constants import (
    KEYCLOAK_REALM,
    KEYCLOAK_URL,
    OIDC_STATE_PREFIX,
    SAML_NS,
    SSO_BASE_URL,
    SSO_SESSION_PREFIX,
    SSO_SESSION_TTL,
)
from src.security.sso.keycloak import auto_configure_keycloak
from src.security.sso.mapping import create_or_link_user, link_existing_user
from src.security.sso.oidc import OIDCHandler
from src.security.sso.routes import register_sso_routes
from src.security.sso.saml import SAMLHandler
from src.security.sso.service import SSOService
from src.security.sso.session import (
    cleanup_expired_sessions,
    create_sso_session,
    logout_session,
    validate_sso_session,
)

__all__ = [
    "KEYCLOAK_REALM",
    "KEYCLOAK_URL",
    "OIDC_STATE_PREFIX",
    "SAML_NS",
    "SSO_BASE_URL",
    "SSO_SESSION_PREFIX",
    "SSO_SESSION_TTL",
    "OIDCHandler",
    "SAMLHandler",
    "SSOService",
    "auto_configure_keycloak",
    "cleanup_expired_sessions",
    "create_or_link_user",
    "create_sso_session",
    "link_existing_user",
    "logout_session",
    "register_sso_routes",
    "validate_sso_session",
]
