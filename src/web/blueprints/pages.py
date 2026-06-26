"""
Blueprints — Páginas (rutas de templates HTML)

BUG C-4 (decisión Jinja vs React): el SPA React es ahora la UI principal y vive
bajo /app/*. Las rutas Jinja raíz (/dashboard, /chat, /editor, ...) se convierten
en redirecciones 301 a sus equivalentes en /app/* para no romper bookmarks viejos.

Fase 1 del PLAN_CORRECCIONES (sesión 5): los templates Jinja legacy y el JS/CSS
legacy (app.js, editor.js, chart.umd.min.js, orbital-visualizer.js, style.css,
manifest.json, sw.js) fueron ELIMINADOS porque ya no se sirven (todas las rutas
Jinja son redirecciones 301 al SPA). Solo se mantiene login.html porque /login
(Flask) aún lo renderiza con lógica de trial (LicenseValidator).

Mapeo de rutas Jinja → SPA:
  /              → /app  (que redirige a /app/dashboard)
  /dashboard     → /app/dashboard
  /chat          → /app/chat
  /editor        → /app/editor
  /workflows     → /app/workflows
  /workflows/<id>→ /app/workflows  (el SPA maneja el ID internamente)
  /settings      → /app/settings
  /dead-letter   → /app/admin      (DeadLetterTab vive en AdminPage)
  /compliance    → /app/compliance
  /airgap        → /app/airgap
  /partners      → /app/partners
  /orbital       → /app/orbital

/login se mantiene en Jinja porque tiene lógica de trial (LicenseValidator) que
el SPA maneja de forma diferente al arranque. Una migración futura de /login al
SPA requiere mover esa lógica de trial al AuthContext.
"""

from flask import Blueprint, redirect, url_for

from src.license.validator import LicenseValidator
from src.web.helpers import check_trial, login_required

bp = Blueprint("pages", __name__)


@bp.route("/")
@login_required
def index():
    # Antes: redirect a pages.dashboard_page (Jinja). Ahora: redirect al SPA.
    return redirect("/app")


@bp.route("/login")
def login_page():
    # Se mantiene en Jinja — ver nota del módulo sobre la lógica de trial.
    from flask import render_template, session

    if "user" in session:
        return redirect("/app")
    trial = LicenseValidator().get_trial_status()
    return render_template("login.html", trial=trial)


# ── Redirecciones 301 (permanentes) al SPA React ──────────────────────────
# Usamos 301 para que los navegadores cacheen la redirección y los bookmarks
# viejos se resuelvan rápido sin volver a pegarle al backend.

_LEGACY_TO_SPA = {
    "/dashboard": "/app/dashboard",
    "/chat": "/app/chat",
    "/editor": "/app/editor",
    "/workflows": "/app/workflows",
    "/settings": "/app/settings",
    "/dead-letter": "/app/admin",
    "/compliance": "/app/compliance",
    "/airgap": "/app/airgap",
    "/partners": "/app/partners",
    "/orbital": "/app/orbital",
}


def _make_redirect(legacy_path: str, spa_path: str):
    """Factory: crea una vista que redirige legacy_path → spa_path con 301."""

    @login_required
    def _redirect_view():
        return redirect(spa_path, code=301)

    _redirect_view.__name__ = f"redirect_{legacy_path.strip('/').replace('-', '_')}"
    return _redirect_view


# Registramos las redirecciones dinámicamente para no repetir boilerplate.
# check_trial() ya lo hace ProtectedRoute en el SPA, así que no lo duplicamos.
for _legacy, _spa in _LEGACY_TO_SPA.items():
    bp.route(_legacy)(_make_redirect(_legacy, _spa))


# /workflows/<id> no tiene equivalente directo en el SPA (el SPA usa /app/workflows
# y maneja el ID via query params o estado interno). Redirigimos ahí.
@bp.route("/workflows/<int:workflow_id>")
@login_required
def workflow_detail_page(workflow_id: int):
    return redirect(f"/app/workflows?id={workflow_id}", code=301)
