"""
SSO — Constantes de configuracion
"""

import os

# ── Configuracion desde variables de entorno ────────────────

SSO_BASE_URL: str = os.environ.get("WFD_SSO_BASE_URL", "http://localhost:8080")
SSO_SESSION_TTL: int = int(os.environ.get("WFD_SSO_SESSION_TTL", "28800"))
KEYCLOAK_URL: str | None = os.environ.get("WFD_SSO_KEYCLOAK_URL", None)
KEYCLOAK_REALM: str = os.environ.get("WFD_SSO_KEYCLOAK_REALM", "zenic-flijo")

# ── Namespaces XML para SAML ───────────────────────────────

SAML_NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig",
}

# ── Prefijos Redis ─────────────────────────────────────────

OIDC_STATE_PREFIX = "sso:oidc:state:"
SSO_SESSION_PREFIX = "sso:session:"
