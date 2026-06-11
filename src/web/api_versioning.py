"""
Zenic-Flijo — API Versioning Middleware

Implements API versioning via Flask Blueprint pattern:
- All current routes registered under /api/v1/ prefix
- Redirect from /api/XXX to /api/v1/XXX for backward compatibility
- Deprecation (Sunset) header on unversioned routes
- /api/versions endpoint listing available API versions

Task IDs: 0-4, 0-7, 0-8
"""

from flask import Blueprint, jsonify, redirect, request, url_for

# ── API Version Registry ──────────────────────────────────

API_VERSIONS = {
    "v1": {
        "version": "1.0.0",
        "status": "stable",
        "released": "2025-01-01",
        "sunset": None,
        "prefix": "/api/v1",
    },
}

CURRENT_VERSION = "v1"
SUNSET_DATE = "Sat, 01 Nov 2025 00:00:00 GMT"
DEPRECATION_LINK = '</api/versions>; rel="deprecation"'
DEPRECATION_MESSAGE = (
    "This unversioned API endpoint is deprecated. Please use /api/v1/ instead. See /api/versions for details."
)


# ── Versioned API Blueprint (v1) ─────────────────────────

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


@api_v1.route("/versions", methods=["GET"])
def api_versions():
    """List all available API versions with their status."""
    versions = []
    for key, meta in API_VERSIONS.items():
        versions.append(
            {
                "version": key,
                "api_version": meta["version"],
                "status": meta["status"],
                "released": meta["released"],
                "sunset": meta["sunset"],
                "prefix": meta["prefix"],
                "current": key == CURRENT_VERSION,
            }
        )
    return jsonify(
        {
            "current": CURRENT_VERSION,
            "versions": versions,
            "links": {
                "self": "/api/v1/versions",
                "unversioned_deprecated": "/api/",
            },
        }
    )


@api_v1.route("/health", methods=["GET"])
def api_health():
    """Health check endpoint for the versioned API."""
    return jsonify(
        {
            "status": "healthy",
            "api_version": CURRENT_VERSION,
            "api_version_number": API_VERSIONS[CURRENT_VERSION]["version"],
        }
    )


# ── Unversioned API Blueprint (backward compat) ──────────

api_legacy = Blueprint("api_legacy", __name__, url_prefix="/api")


@api_legacy.route("/versions", methods=["GET"])
def legacy_api_versions():
    """Redirect to versioned /api/v1/versions with deprecation headers."""
    response = redirect(url_for("api_v1.api_versions"), code=301)
    response.headers["Sunset"] = SUNSET_DATE
    response.headers["Link"] = DEPRECATION_LINK
    response.headers["Deprecation"] = "true"
    return response


@api_legacy.route("/health", methods=["GET"])
def legacy_api_health():
    """Redirect to versioned /api/v1/health with deprecation headers."""
    response = redirect(url_for("api_v1.api_health"), code=301)
    response.headers["Sunset"] = SUNSET_DATE
    response.headers["Link"] = DEPRECATION_LINK
    response.headers["Deprecation"] = "true"
    return response


# ── Deprecation Header Middleware ─────────────────────────


def add_deprecation_headers(response):
    """Add Sunset and Deprecation headers to unversioned /api/ routes.

    This function is registered as an after_request hook on the main
    Flask app. It detects requests to /api/ that are NOT already
    versioned (i.e., NOT /api/v1/) and adds deprecation headers.
    """
    path = request.path

    # Only apply to /api/ routes that are NOT versioned
    if path.startswith("/api/") and not _is_versioned_path(path):
        if "Sunset" not in response.headers:
            response.headers["Sunset"] = SUNSET_DATE
        if "Deprecation" not in response.headers:
            response.headers["Deprecation"] = "true"
        if "Link" not in response.headers:
            response.headers["Link"] = DEPRECATION_LINK

    # Add API version header to all API responses
    if path.startswith("/api/"):
        version = _extract_api_version(path)
        response.headers["X-API-Version"] = version

    return response


def _is_versioned_path(path: str) -> bool:
    """Check if a path already includes a version prefix like /api/v1/."""
    return any(path.startswith(f"/api/{version_key}/") or path == f"/api/{version_key}" for version_key in API_VERSIONS)


def _extract_api_version(path: str) -> str:
    """Extract the API version from a path string.

    Returns the version key (e.g., 'v1') or 'unversioned' for legacy paths.
    """
    parts = path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "api":
        potential_version = parts[1]
        if potential_version in API_VERSIONS:
            return potential_version
    return "unversioned"


# ── Redirect Handler for Unversioned Routes ──────────────


def handle_unversioned_api_redirects(app):
    """Register catch-all redirect for unversioned /api/* routes.

    When a request comes in to /api/some/endpoint (without version prefix),
    redirect to /api/v1/some/endpoint with a 301 and deprecation headers.
    This only applies to routes NOT already registered under /api/v1/.
    """

    @app.errorhandler(404)
    def api_redirect_404(error):
        """Intercept 404s on /api/ paths and try redirecting to versioned endpoint."""
        path = request.path

        # Only handle /api/ paths that aren't already versioned
        if not path.startswith("/api/") or _is_versioned_path(path):
            return error

        # Build the versioned path
        versioned_path = f"/api/{CURRENT_VERSION}{path[4:]}"  # Replace /api/ with /api/v1/

        # Don't redirect if the versioned path would be the same
        if versioned_path == path:
            return error

        # Redirect with deprecation headers
        response = redirect(versioned_path, code=301)
        response.headers["Sunset"] = SUNSET_DATE
        response.headers["Link"] = DEPRECATION_LINK
        response.headers["Deprecation"] = "true"
        response.headers["X-Deprecated-Redirect"] = f"{path} -> {versioned_path}"
        return response

    return app


# ── Registration Helper ───────────────────────────────────


def register_api_versioning(app):
    """Register all API versioning blueprints and hooks on the Flask app.

    Usage in app factory:
        from src.web.api_versioning import register_api_versioning
        app = Flask(__name__)
        register_api_versioning(app)

    This will:
    1. Register /api/v1/* blueprint (versioned routes)
    2. Register /api/* blueprint (legacy unversioned routes with redirects)
    3. Add after_request hook for deprecation headers on all /api/ responses
    4. Add 404 handler to redirect unversioned /api/* to /api/v1/*
    """
    # Register versioned blueprint
    app.register_blueprint(api_v1)

    # Register legacy (unversioned) blueprint
    app.register_blueprint(api_legacy)

    # Add deprecation headers to all /api/ responses
    app.after_request(add_deprecation_headers)

    # Add redirect handler for unversioned API routes
    handle_unversioned_api_redirects(app)

    return app


# ── Route Re-registration Helper ──────────────────────────

# Map of existing unversioned API routes to their v1 equivalents.
# When the app factory registers routes on the main app, this helper
# can re-register them under the /api/v1/ prefix.
_ROUTE_REGISTRY: list[dict] = []


def record_api_route(rule: str, endpoint: str, methods: list[str], view_func):
    """Record an API route for dual-registration (versioned + unversioned).

    This is used during app setup to track which routes should be
    available under both /api/ and /api/v1/.
    """
    _ROUTE_REGISTRY.append(
        {
            "rule": rule,
            "endpoint": endpoint,
            "methods": methods,
            "view_func": view_func,
        }
    )


def register_versioned_routes(app):
    """Register all recorded API routes under /api/v1/ prefix.

    Call this after all routes have been registered on the main app.
    It will duplicate each /api/* route to /api/v1/*.
    """
    for entry in _ROUTE_REGISTRY:
        rule = entry["rule"]
        if rule.startswith("/api/"):
            # Build versioned rule: /api/workflows -> /api/v1/workflows
            versioned_rule = f"/api/{CURRENT_VERSION}{rule[4:]}"
            endpoint_name = f"v1_{entry['endpoint']}"

            import contextlib

            with contextlib.suppress(AssertionError):
                app.add_url_rule(
                    versioned_rule,
                    endpoint=endpoint_name,
                    view_func=entry["view_func"],
                    methods=entry["methods"],
                )
