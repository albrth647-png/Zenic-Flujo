"""
Path-related constants for Zenic-Flujo.

All filesystem paths (data dir, DBs, logs) are defined here so they can be
imported without pulling in secrets or service configuration.

Side effect on import: ``DATA_DIR`` is created with ``mkdir(parents=True,
exist_ok=True)``. This is intentional — it guarantees the data directory
exists before any DB or log file is opened.
"""

import os
from pathlib import Path

# ── Rutas base ──────────────────────────────────────────────
# BASE_DIR apunta al root del proyecto (padre de src/).
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parents[3]
DATA_DIR = Path(os.environ.get("WFD_DATA_DIR", Path.home() / ".workflow_determinista"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging directory ──────────────────────────────────────
LOG_DIR = Path(os.environ.get("WFD_LOG_DIR", DATA_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Base de datos (unificada) ──────────────────────────────
DB_PATH = DATA_DIR / "workflow_determinista.db"
DB_WAL_MODE = True

# ── DBs por dominio (fix Sprint 3 bug #36) ────────────────
# Antes cada módulo usaba db_path relativos como "marketplace.db",
# "compliance.db", etc., que se resolvían contra el CWD. Si la app
# se arrancaba desde otro directorio, se creaban DBs fantasma.
# Ahora todos los paths se construyen desde DATA_DIR (absoluto).
DOMAIN_DB_PATHS = {
    "marketplace":       DATA_DIR / "marketplace.db",
    "compliance":        DATA_DIR / "compliance.db",
    "push_notifications": DATA_DIR / "push_notifications.db",
    "sync_queue":        DATA_DIR / "sync_queue.db",
    "sync_cloud":        DATA_DIR / "sync_cloud.db",
    "partners":          DATA_DIR / "partners.db",
    "tenant":            DATA_DIR / "tenant.db",
    # Fix NEW-BUG-2 (verificación Sprint 4): paths relativos restantes
    # detectados por agente Explore — añadidos para completar bug #36.
    "agent_memory":      DATA_DIR / "agent_memory.db",
    "token_usage":       DATA_DIR / "token_usage.db",
}

# ── Accesores convenience (uno por DB) ─────────────────────
# Para que los módulos no tengan que importar el dict completo.
MARKETPLACE_DB_PATH = DOMAIN_DB_PATHS["marketplace"]
COMPLIANCE_DB_PATH = DOMAIN_DB_PATHS["compliance"]
PUSH_NOTIFICATIONS_DB_PATH = DOMAIN_DB_PATHS["push_notifications"]
SYNC_QUEUE_DB_PATH = DOMAIN_DB_PATHS["sync_queue"]
SYNC_CLOUD_DB_PATH = DOMAIN_DB_PATHS["sync_cloud"]
PARTNERS_DB_PATH = DOMAIN_DB_PATHS["partners"]
TENANT_DB_PATH = DOMAIN_DB_PATHS["tenant"]
AGENT_MEMORY_DB_PATH = DOMAIN_DB_PATHS["agent_memory"]
TOKEN_USAGE_DB_PATH = DOMAIN_DB_PATHS["token_usage"]

# ── Orbital (motor determinista) ───────────────────────────
ORBITAL_DB_PATH = Path(os.environ.get("WFD_ORBITAL_DB_PATH", DATA_DIR / "orbital.db"))
