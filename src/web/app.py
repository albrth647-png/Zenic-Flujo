"""
Workflow Determinista — Web App (Flask)
Fábrica de aplicación que registra todos los blueprints.
"""

from pathlib import Path

from flask import Flask, Response, jsonify

from src.core.config import SESSION_COOKIE_SECURE, SESSION_EXPIRY_HOURS, SESSION_SECRET
from src.core.logging import setup_logging
from src.web.blueprints import register_blueprints
from src.web.helpers import (
    _check_rate_limit,
    _login_attempts,
    _register_failed_login,
    _sanitize,
    check_free_tier,
    check_trial,
    login_required,
    require_role,
)

logger = setup_logging(__name__)

# M10.3: CSRF protection via flask-wtf. El paquete puede no estar instalado
# en entornos mínimos (CI, dev), por lo que se carga con fallback graceful:
# si flask_wtf no está disponible, csrf = None y create_app() omite la
# inicialización. En producción, ensure `pip install flask-wtf`.
try:
    from flask_wtf.csrf import CSRFProtect

    csrf = CSRFProtect()
except ImportError:  # pragma: no cover — depende del entorno
    csrf = None
    logger.warning(
        "flask-wtf no instalado — CSRF protection deshabilitada. "
        "Instalar con: pip install flask-wtf"
    )

# Re-export shared state and helpers for backward compatibility.
# Fix Sprint 3 bug #26: tests preexistentes (test_security_fase3, test_security_redteam)
# asumían que _sanitize, _check_rate_limit y _login_attempts estaban en app.py,
# pero viven en helpers.py. Re-exportar mantiene compatibilidad sin duplicar lógica.
__all__ = [
    "_sanitize",
    "_check_rate_limit",
    "_register_failed_login",
    "_login_attempts",
    "login_required",
    "require_role",
    "check_trial",
    "check_free_tier",
    "create_app",
    "csrf",
]


def create_app() -> Flask:
    """Crea y configura la aplicación Flask registrando todos los blueprints."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = SESSION_SECRET
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = SESSION_EXPIRY_HOURS * 3600

    # M10.3: Inicializar CSRF protection (si flask-wtf está disponible).
    # Los endpoints que sirven JSON puro (sin formularios HTML) deben eximirse
    # con @csrf.exempt — ver blueprints/auth.py y api_v2 (FastAPI, fuera de Flask).
    # CSRF: deshabilitado por defecto. El frontend es SPA (JSON API, no formularios).
    # Las APIs usan session cookies + auth, no requieren CSRF tokens.
    # Para producción con formularios HTML tradicionales, habilitar:
    #   app.config["WTF_CSRF_CHECK_DEFAULT"] = True
    app.config["WTF_CSRF_CHECK_DEFAULT"] = False
    if csrf is not None:
        csrf.init_app(app)
        logger.info("CSRF: WTF_CSRF_CHECK_DEFAULT=False (SPA usa JSON API)")
    else:
        logger.warning("CSRF protection NO habilitada — flask-wtf no disponible")

    # Registrar todos los blueprints
    register_blueprints(app)

    # ── SPA: React frontend ──────────────────────────────────

    @app.route("/app/<path:path>")
    @app.route("/app")
    def spa_serve(path="index.html"):
        spa_path = Path(__file__).parent / "static" / "spa" / "index.html"
        if spa_path.exists():
            return app.send_static_file("spa/index.html")
        return jsonify({"error": "SPA not built yet. Run: cd frontend && npm run build"}), 503

    # ── M10.3: /metrics endpoint (Prometheus, NO auth) ───────
    # Expuesto sin autenticación para que los scrape configs de k8s/helm
    # puedan leerlo con una ServiceMonitor básica. El endpoint admin
    # /api/admin/metrics/prometheus sigue disponible con auth para debugging
    # y para dashboards internos. NO exponer métricas sensibles (PII, secrets)
    # vía este endpoint — solo contadores/gauges/histogramas de telemetría.

    @app.route("/metrics")
    def metrics_prometheus_unauth():
        """Prometheus metrics endpoint — sin auth (para scrape configs).

        M10.3: Añadido para compatibilidad con k8s/helm scrape configs que
        usan /metrics. El endpoint /api/admin/metrics/prometheus sigue
        disponible con auth para debugging interno.
        """
        try:
            from src.core.observability.metrics.registry import MetricsRegistry

            registry = MetricsRegistry()
            metrics_text = registry.get_metrics()
        except Exception as exc:
            logger.error("Error generando métricas Prometheus: %s", exc)
            return Response(
                "# Error generating metrics\n",
                status=500,
                mimetype="text/plain; version=0.0.4; charset=utf-8",
            )
        return Response(
            metrics_text,
            mimetype="text/plain; version=0.0.4; charset=utf-8",
        )

    return app
