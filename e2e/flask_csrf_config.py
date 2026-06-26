"""M10: CSRF protection config para Flask.

Integrar en src/web/app.py del repo original:

    from e2e.flask_csrf_config import setup_csrf
    app = Flask(__name__)
    setup_csrf(app)

Requiere: pip install flask-wtf
"""
from __future__ import annotations

from typing import Any


def setup_csrf(app: Any) -> Any:
    """Configura CSRF protection en la app Flask.

    Args:
        app: Instancia de Flask app.

    Returns:
        La instancia de CSRFProtect instalada.
    """
    try:
        from flask_wtf.csrf import CSRFProtect
    except ImportError:
        import warnings
        warnings.warn(
            "flask-wtf no instalado. Ejecuta: pip install flask-wtf",
            stacklevel=2,
        )
        return None

    csrf = CSRFProtect()

    # Configurar SECRET_KEY si no está seteado
    if not app.config.get("SECRET_KEY"):
        import os
        app.config["SECRET_KEY"] = os.environ.get(
            "WFD_SESSION_SECRET",
            "dev-secret-change-in-production",
        )

    # Exentar API endpoints que no necesitan CSRF (JSON API)
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False

    # Solo aplicar CSRF a rutas que no son API
    csrf.init_app(app)

    # Middleware para exentar /api/* de CSRF
    @app.before_request
    def skip_csrf_for_api() -> None:
        """Exenta rutas /api/* de CSRF check (usan auth token en su lugar)."""
        from flask import request
        if request.path.startswith("/api/"):
            # Las APIs usan Authorization header, no CSRF token
            return  # CSRF skipped for API routes
        # Para rutas web (formularios), CSRF se aplica
        csrf.protect()

    return csrf


# Requirements adicionales
CSRF_REQUIREMENTS = [
    "flask-wtf>=1.2.0",
]
