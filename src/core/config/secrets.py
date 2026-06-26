"""
Security-sensitive constants for Zenic-Flujo.

All secrets (SESSION_SECRET, LICENSE_SECRET_KEY, WFD_ENCRYPTION_MASTER_KEY)
MUST be provided via environment variables in production. If they are missing
in production mode (``WFD_PRODUCTION=true``), the module raises ``RuntimeError``
at import time — the system refuses to boot with insecure defaults.

In development mode, missing secrets are auto-generated per-session and a
warning is emitted via ``warnings.warn``.

Dead code removed (M1.3):
    The legacy ``_INSECURE_SESSION_DEFAULT`` and ``_INSECURE_LICENSE_DEFAULT``
    constants were never used as actual fallback values — they were only
    referenced by ``validate_config()`` to detect "default usage", but the
    new import-time guard already raises in production. Both constants and
    their comparison branches have been eliminated.
"""

import base64
import hashlib
import os
import secrets as _secrets
import warnings

# ── Modo de ejecución ───────────────────────────────────────
# PRODUCTION=true implica validación estricta de secrets.
PRODUCTION = os.environ.get("WFD_PRODUCTION", "false").lower() == "true"

# ── Sesiones ───────────────────────────────────────────────
# En producción: WFD_SESSION_SECRET DEBE establecerse (mínimo 32 caracteres).
# En desarrollo: si no se establece, se genera uno aleatorio por sesión.
_session_secret_env = os.environ.get("WFD_SESSION_SECRET", "")

if _session_secret_env:
    SESSION_SECRET = _session_secret_env
elif PRODUCTION:
    raise RuntimeError(
        "SEGURIDAD: WFD_SESSION_SECRET no configurado en modo producción. "
        "Establezca la variable de entorno WFD_SESSION_SECRET con un valor "
        "aleatorio de al menos 64 caracteres antes de desplegar."
    )
else:
    # Modo desarrollo: generar secret aleatorio y advertir
    SESSION_SECRET = _secrets.token_urlsafe(48)
    warnings.warn(
        "WFD_SESSION_SECRET no configurado. Se generó un secret aleatorio para "
        "esta sesión. Configure WFD_SESSION_SECRET antes de desplegar en producción.",
        stacklevel=2,
    )

SESSION_EXPIRY_HOURS = 24
SESSION_COOKIE_SECURE = os.environ.get("WFD_SESSION_SECURE", "false").lower() == "true"

# ── License ────────────────────────────────────────────────
# En producción: WFD_LICENSE_SECRET DEBE establecerse.
# En desarrollo: si no se establece, se genera uno aleatorio.
_license_secret_env = os.environ.get("WFD_LICENSE_SECRET", "")

if _license_secret_env:
    LICENSE_SECRET_KEY = _license_secret_env
elif PRODUCTION:
    raise RuntimeError(
        "SEGURIDAD: WFD_LICENSE_SECRET no configurado en modo producción. "
        "Establezca la variable de entorno WFD_LICENSE_SECRET con un valor "
        "aleatorio de al menos 64 caracteres antes de desplegar."
    )
else:
    # Modo desarrollo: generar clave aleatoria y advertir
    LICENSE_SECRET_KEY = _secrets.token_urlsafe(48)
    warnings.warn(
        "WFD_LICENSE_SECRET no configurado. Se generó una clave aleatoria para "
        "esta sesión. Configure WFD_LICENSE_SECRET antes de desplegar en producción.",
        stacklevel=2,
    )

# ── Encryption ────────────────────────────────────────────
# Derivada de SESSION_SECRET para cifrar tokens sensibles (WhatsApp, etc.)
WHATSAPP_ENCRYPTION_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(SESSION_SECRET.encode()).digest()
)

# ── Master encryption key (BYOK / KeyManager) ─────────────
# En producción: WFD_ENCRYPTION_MASTER_KEY es OBLIGATORIA (≥64 chars).
# En desarrollo: si no se establece, se deja vacía y KeyManager advertirá.
WFD_ENCRYPTION_MASTER_KEY = os.environ.get("WFD_ENCRYPTION_MASTER_KEY", "")
if PRODUCTION and len(WFD_ENCRYPTION_MASTER_KEY) < 64:
    raise RuntimeError(
        "SEGURIDAD: WFD_ENCRYPTION_MASTER_KEY no configurada o demasiado corta "
        "en modo producción. Establezca la variable de entorno con un valor "
        "aleatorio de al menos 64 caracteres antes de desplegar."
    )
