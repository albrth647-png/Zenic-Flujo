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

# Re-export everything from the split modules.
from src.core.config.paths import *  # noqa: F401, F403
from src.core.config.secrets import *  # noqa: F401, F403
from src.core.config.services import *  # noqa: F401, F403
from src.core.config.validation import validate_config  # noqa: F401

# Explicit re-export of validate_config (which is not in any module's
# wildcard namespace because it's a single function, not a * import).
__all__ = [
    # paths
    "BASE_DIR",
    "DATA_DIR",
    "LOG_DIR",
    "DB_PATH",
    "DB_WAL_MODE",
    "DOMAIN_DB_PATHS",
    "MARKETPLACE_DB_PATH",
    "COMPLIANCE_DB_PATH",
    "PUSH_NOTIFICATIONS_DB_PATH",
    "SYNC_QUEUE_DB_PATH",
    "SYNC_CLOUD_DB_PATH",
    "PARTNERS_DB_PATH",
    "TENANT_DB_PATH",
    "AGENT_MEMORY_DB_PATH",
    "TOKEN_USAGE_DB_PATH",
    "ORBITAL_DB_PATH",
    # secrets
    "PRODUCTION",
    "SESSION_SECRET",
    "SESSION_EXPIRY_HOURS",
    "SESSION_COOKIE_SECURE",
    "LICENSE_SECRET_KEY",
    "WHATSAPP_ENCRYPTION_KEY",
    "WFD_ENCRYPTION_MASTER_KEY",
    # services
    "WEB_HOST",
    "WEB_PORT",
    "WEBHOOK_PORT",
    "LOGIN_MAX_ATTEMPTS",
    "LOGIN_WINDOW_MINUTES",
    "API_MAX_REQUESTS",
    "API_WINDOW_MINUTES",
    "SCHEDULE_INTERVAL_SECONDS",
    "WEBHOOK_API_KEY_ENABLED",
    "ERROR_MAX_RETRIES",
    "ERROR_BASE_DELAY_SECONDS",
    "ERROR_RETRY_MULTIPLIER",
    "ERROR_USE_FALLBACK",
    "TRIAL_DAYS",
    "FREE_TIER_MAX_WORKFLOWS",
    "FREE_TIER_ALLOWED_TOOLS",
    "OLLAMA_ENABLED",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LOG_DATE_FORMAT",
    "LOG_FILE",
    "WFD_SSO_BASE_URL",
    "WFD_SSO_SESSION_TTL",
    "WFD_SSO_KEYCLOAK_URL",
    "WFD_SSO_KEYCLOAK_REALM",
    "WFD_SSO_KEYCLOAK_CLIENT_ID",
    "WFD_OTEL_ENABLED",
    "WFD_OTEL_SERVICE_NAME",
    "WFD_OTEL_EXPORTER",
    "WFD_OTEL_EXPORTER_ENDPOINT",
    "WFD_OTEL_METRICS_PORT",
    "WFD_OTEL_SAMPLING_RATE",
    "WFD_API_V2_JWT_SECRET",
    # validation
    "validate_config",
]
