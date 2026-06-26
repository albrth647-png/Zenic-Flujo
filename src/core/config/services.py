"""
Service-level configuration for Zenic-Flujo.

Groups environment-driven settings for the web server, AI backend (Ollama),
logging output, SSO, OpenTelemetry and API v2 JWT. None of these values are
security-sensitive — they can be imported without triggering the production
guards defined in ``src.core.config.secrets``.
"""

import os

# ── Servidor web ───────────────────────────────────────────
WEB_HOST = os.environ.get("WFD_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WFD_WEB_PORT", "8080"))
WEBHOOK_PORT = int(os.environ.get("WFD_WEBHOOK_PORT", "8081"))

# ── Rate Limiting ──────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_MINUTES = 15
API_MAX_REQUESTS = 100
API_WINDOW_MINUTES = 15

# ── Schedule Worker ────────────────────────────────────────
SCHEDULE_INTERVAL_SECONDS = 60

# ── Webhook ────────────────────────────────────────────────
WEBHOOK_API_KEY_ENABLED = os.environ.get("WFD_WEBHOOK_API_KEY_ENABLED", "true").lower() == "true"

# ── Error Handler ──────────────────────────────────────────
ERROR_MAX_RETRIES = 3
ERROR_BASE_DELAY_SECONDS = 5
ERROR_RETRY_MULTIPLIER = 2
ERROR_USE_FALLBACK = True

# ── Trial ──────────────────────────────────────────────────
TRIAL_DAYS = 30

# ── Free Tier Limits ──────────────────────────────────────
FREE_TIER_MAX_WORKFLOWS = 3
FREE_TIER_ALLOWED_TOOLS = ["crm"]  # Solo CRM en free

# ── Ollama (AI Enhancement) ────────────────────────────────
OLLAMA_ENABLED = os.environ.get("WFD_OLLAMA_ENABLED", "false").lower() == "true"
OLLAMA_BASE_URL = os.environ.get("WFD_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("WFD_OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("WFD_OLLAMA_TIMEOUT", "30"))

# ── Logging ────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("WFD_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "zenic_flujo.log"

# ── SSO (Single Sign-On) ───────────────────────────────────
# These mirror the env vars consumed by src.core.security.sso.* modules.
WFD_SSO_BASE_URL = os.environ.get("WFD_SSO_BASE_URL", "http://localhost:8080")
WFD_SSO_SESSION_TTL = int(os.environ.get("WFD_SSO_SESSION_TTL", "28800"))
WFD_SSO_KEYCLOAK_URL = os.environ.get("WFD_SSO_KEYCLOAK_URL", "")
WFD_SSO_KEYCLOAK_REALM = os.environ.get("WFD_SSO_KEYCLOAK_REALM", "zenic-flijo")
WFD_SSO_KEYCLOAK_CLIENT_ID = os.environ.get("WFD_SSO_KEYCLOAK_CLIENT_ID", "zenic-flijo")

# ── OpenTelemetry (OTEL) ───────────────────────────────────
# These mirror the env vars consumed by src.core.observability.* modules.
WFD_OTEL_ENABLED = os.environ.get("WFD_OTEL_ENABLED", "false").lower() == "true"
WFD_OTEL_SERVICE_NAME = os.environ.get("WFD_OTEL_SERVICE_NAME", "zenic-flijo")
WFD_OTEL_EXPORTER = os.environ.get("WFD_OTEL_EXPORTER", "none")
WFD_OTEL_EXPORTER_ENDPOINT = os.environ.get("WFD_OTEL_EXPORTER_ENDPOINT", "localhost:4317")
WFD_OTEL_METRICS_PORT = int(os.environ.get("WFD_OTEL_METRICS_PORT", "9090"))
WFD_OTEL_SAMPLING_RATE = float(os.environ.get("WFD_OTEL_SAMPLING_RATE", "0.1"))

# ── API v2 JWT ─────────────────────────────────────────────
# Secret used to sign JWTs for the v2 API surface. In production this MUST
# be set via env var (≥32 chars); an empty default triggers a guard at use
# site (api_v2.auth) rather than at import time, to keep config import cheap.
WFD_API_V2_JWT_SECRET = os.environ.get("WFD_API_V2_JWT_SECRET", "")
