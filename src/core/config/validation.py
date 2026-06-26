"""
Configuration validation for Zenic-Flujo.

``validate_config()`` returns a list of human-readable warnings about
soft misconfigurations (e.g. short secrets, missing cookie-secure flag in
production). Hard misconfigurations (missing secrets in production) are
already caught at import time by ``src.core.config.secrets``.

Dead code removed (M1.3):
    The previous implementation compared SESSION_SECRET and LICENSE_SECRET_KEY
    against the ``_INSECURE_SESSION_DEFAULT`` / ``_INSECURE_LICENSE_DEFAULT``
    sentinel constants. Those sentinels were never actually assigned to the
    real secrets (the import-time guard raises before that can happen), so
    the comparisons were dead code. Both sentinels and their branches have
    been removed.
"""

from src.core.config.secrets import (
    LICENSE_SECRET_KEY,
    PRODUCTION,
    SESSION_COOKIE_SECURE,
    SESSION_SECRET,
)


def validate_config() -> list[str]:
    """
    Valida la configuración del sistema y retorna una lista de advertencias.

    En producción, los secrets faltantes causan RuntimeError al importar.
    Esta función permite detectar problemas adicionales en cualquier modo.

    Returns:
        Lista de mensajes de advertencia (vacía si todo está bien)
    """
    warnings_list: list[str] = []

    # Verificar que SESSION_SECRET tenga suficiente entropía
    if len(SESSION_SECRET) < 32:
        warnings_list.append(
            f"SESSION_SECRET tiene solo {len(SESSION_SECRET)} caracteres. "
            "Se recomienda al menos 64 caracteres para producción."
        )

    # Verificar que LICENSE_SECRET_KEY tenga suficiente entropía
    if len(LICENSE_SECRET_KEY) < 32:
        warnings_list.append(
            f"LICENSE_SECRET_KEY tiene solo {len(LICENSE_SECRET_KEY)} caracteres. "
            "Se recomienda al menos 64 caracteres para producción."
        )

    # Verificar que SESSION_COOKIE_SECURE esté activado en producción
    if PRODUCTION and not SESSION_COOKIE_SECURE:
        warnings_list.append(
            "SESSION_COOKIE_SECURE está desactivado en modo producción. "
            "Active WFD_SESSION_SECURE=true para cookies seguras sobre HTTPS."
        )

    return warnings_list
