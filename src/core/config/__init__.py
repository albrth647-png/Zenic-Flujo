"""
src.core.config — Application configuration for Zenic-Flujo (HAT v2).

Subpackage layout:
    paths.py       — filesystem paths (BASE_DIR, DATA_DIR, DB_PATH, ...)
    secrets.py     — security-sensitive constants (PRODUCTION, SESSION_SECRET, ...)
    services.py    — service-level config (OLLAMA_*, WEB_*, LOG_*, SSO, OTEL, ...)
    validation.py  — validate_config() helper

The ``__init__`` re-exports every public symbol from the four modules so
existing imports such as ``from src.core.config import DB_PATH`` continue to
work without changes. Migration target for M1.3 of the HAT v2 plan.
"""
# ruff: noqa: F403, F405 — este __init__ es un facade que re-exporta
# todos los símbolos de los submódulos vía star imports.

# Re-export everything from the split modules.
from src.core.config.paths import *
from src.core.config.secrets import *
from src.core.config.services import *
from src.core.config.validation import validate_config

# Explicit re-export of validate_config (which is not in any module's
# wildcard namespace because it's a single function, not a * import).
__all__ = [
    "AGENT_MEMORY_DB_PATH",
    "API_MAX_REQUESTS",
    "API_WINDOW_MINUTES",
    # paths
    "BASE_DIR",
    "COMPLIANCE_DB_PATH",
    "DATA_DIR",
    "DB_PATH",
    "DB_WAL_MODE",
    "DOMAIN_DB_PATHS",
    "ERROR_BASE_DELAY_SECONDS",
    "ERROR_MAX_RETRIES",
    "ERROR_RETRY_MULTIPLIER",
    "ERROR_USE_FALLBACK",
    "FREE_TIER_ALLOWED_TOOLS",
    "FREE_TIER_MAX_WORKFLOWS",
    "LICENSE_SECRET_KEY",
    "LOGIN_MAX_ATTEMPTS",
    "LOGIN_WINDOW_MINUTES",
    "LOG_DATE_FORMAT",
    "LOG_DIR",
    "LOG_FILE",
    "LOG_FORMAT",
    "LOG_LEVEL",
    "MARKETPLACE_DB_PATH",
    "OLLAMA_BASE_URL",
    "OLLAMA_ENABLED",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT",
    "ORBITAL_DB_PATH",
    "PARTNERS_DB_PATH",
    # secrets
    "PRODUCTION",
    "PUSH_NOTIFICATIONS_DB_PATH",
    "SCHEDULE_INTERVAL_SECONDS",
    "SESSION_COOKIE_SECURE",
    "SESSION_EXPIRY_HOURS",
    "SESSION_SECRET",
    "SYNC_CLOUD_DB_PATH",
    "SYNC_QUEUE_DB_PATH",
    "TENANT_DB_PATH",
    "TOKEN_USAGE_DB_PATH",
    "TRIAL_DAYS",
    "WEBHOOK_API_KEY_ENABLED",
    "WEBHOOK_PORT",
    # services
    "WEB_HOST",
    "WEB_PORT",
    "WFD_API_V2_JWT_SECRET",
    "WFD_ENCRYPTION_MASTER_KEY",
    "WFD_OTEL_ENABLED",
    "WFD_OTEL_EXPORTER",
    "WFD_OTEL_EXPORTER_ENDPOINT",
    "WFD_OTEL_METRICS_PORT",
    "WFD_OTEL_SAMPLING_RATE",
    "WFD_OTEL_SERVICE_NAME",
    "WFD_SSO_BASE_URL",
    "WFD_SSO_KEYCLOAK_CLIENT_ID",
    "WFD_SSO_KEYCLOAK_REALM",
    "WFD_SSO_KEYCLOAK_URL",
    "WFD_SSO_SESSION_TTL",
    "WHATSAPP_ENCRYPTION_KEY",
    # validation
    "validate_config",
]
