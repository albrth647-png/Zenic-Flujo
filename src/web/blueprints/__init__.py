"""
Registro de blueprints para la web app.
"""

from src.web.blueprints import (
    admin,
    auth,
    compliance,
    integrations,
    marketplace,
    nlu,
    orbital,
    pages,
    partnership,
    reports,
    sync,
    tools,
    workflows,
)
from src.web.sse import _patch_engine_for_sse, sse_bp


def register_blueprints(app):
    """Registra todos los blueprints de la aplicación Flask."""
    app.register_blueprint(pages.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(workflows.bp)
    app.register_blueprint(nlu.bp)
    app.register_blueprint(orbital.bp)
    app.register_blueprint(tools.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(marketplace.bp)
    app.register_blueprint(integrations.bp)
    app.register_blueprint(compliance.bp)
    app.register_blueprint(partnership.bp)
    app.register_blueprint(sync.bp)
    app.register_blueprint(sse_bp)

    # Patch engine to broadcast SSE events
    _patch_engine_for_sse()
