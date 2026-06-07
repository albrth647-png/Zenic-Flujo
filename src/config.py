"""
Workflow Determinista — Configuración Global
"""
import os
from pathlib import Path

# ── Rutas base ──────────────────────────────────────────────
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
DATA_DIR = Path(os.environ.get("WFD_DATA_DIR", Path.home() / ".workflow_determinista"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Base de datos (unificada) ──────────────────────────────
DB_PATH = DATA_DIR / "workflow_determinista.db"
DB_WAL_MODE = True

# ── Servidor web ───────────────────────────────────────────
WEB_HOST = os.environ.get("WFD_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WFD_WEB_PORT", "8080"))
WEBHOOK_PORT = int(os.environ.get("WFD_WEBHOOK_PORT", "8081"))

# ── Sesiones ───────────────────────────────────────────────
SESSION_SECRET = os.environ.get(
    "WFD_SESSION_SECRET",
    "REDACTED_generar_aleatorio_64chars"
)
SESSION_EXPIRY_HOURS = 24

# ── Rate Limiting ──────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 10
LOGIN_WINDOW_MINUTES = 15
API_MAX_REQUESTS = 100
API_WINDOW_MINUTES = 15

# ── Schedule Worker ────────────────────────────────────────
SCHEDULE_INTERVAL_SECONDS = 60

# ── Webhook ────────────────────────────────────────────────
WEBHOOK_API_KEY_ENABLED = True  # Siempre True en producción

# ── Error Handler ──────────────────────────────────────────
ERROR_MAX_RETRIES = 3
ERROR_BASE_DELAY_SECONDS = 5
ERROR_RETRY_MULTIPLIER = 2
ERROR_USE_FALLBACK = True

# ── Trial ──────────────────────────────────────────────────
TRIAL_DAYS = 30

# ── License ────────────────────────────────────────────────
# ⚠️ CAMBIAR EN PRODUCCIÓN
LICENSE_SECRET_KEY = os.environ.get(
    "WFD_LICENSE_SECRET",
    "REDACTED_clave_maestra_hmac"
)

# ── Free Tier Limits ──────────────────────────────────────
FREE_TIER_MAX_WORKFLOWS = 3
FREE_TIER_ALLOWED_TOOLS = ["crm"]  # Solo CRM en free

# ── Logging ────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("WFD_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
