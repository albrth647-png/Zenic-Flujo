"""
SSO — Single Sign-On subpackage (SAML 2.0 + OIDC + Keycloak)

Nota: SSOService se define en src/security/sso.py (módulo legacy) pero se
re-exporta aquí para que `from src.security.sso import SSOService` funcione
correctamente cuando Python resuelve el paquete (directorio) en lugar del
módulo. Esto elimina el ImportError que impedía cargar api_v2.app.
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
from src.security.sso.oidc import OIDCHandler
from src.security.sso.routes import register_sso_routes
from src.security.sso.saml import SAMLHandler
from src.security.sso.session import (
    cleanup_expired_sessions,
    create_or_link_user,
    create_sso_session,
    link_existing_user,
    logout_session,
    validate_sso_session,
)


# Re-export de SSOService desde el módulo legacy sso.py
# Import diferido vía importlib para evitar circular import (sso.py importa de este paquete).
# Cargamos sso.py como módulo "sso_legacy" para no chocar con el nombre del paquete.
def __getattr__(name):
    if name == "SSOService":
        import importlib.util
        import pathlib
        sso_py_path = pathlib.Path(__file__).parent.parent / "sso.py"
        if not sso_py_path.exists():
            raise ImportError(f"sso.py not found at {sso_py_path}")
        spec = importlib.util.spec_from_file_location("src.security.sso_legacy", sso_py_path)
        if spec is None or spec.loader is None:
            raise ImportError("Could not load sso.py spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.SSOService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
