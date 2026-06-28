"""
Blueprints — Marketplace / Plugins y Air-Gapped
"""

import json

from flask import Blueprint, jsonify, request, session

from src.web.helpers import db, login_required, require_role

bp = Blueprint("marketplace", __name__)


# ── API: Marketplace / Plugins ─────────────────────────────

@bp.route("/api/marketplace/connectors")
@login_required
def api_marketplace_connectors():
    """Lista todos los conectores del marketplace."""
    from src.sdk.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    all_connectors = registry.list_all()

    installed_rows = db.fetchall("SELECT connector_name FROM connector_configs")
    installed_names = {r["connector_name"] for r in installed_rows}

    query = request.args.get("query", "").lower()
    category = request.args.get("category")

    results = []
    for c in all_connectors:
        name = c.get("name", "")
        if query and query not in name.lower() and query not in c.get("description", "").lower():
            continue
        if category and c.get("category", "general") != category:
            continue
        results.append({
            "name": name,
            "version": c.get("version", "1.0.0"),
            "description": c.get("description", ""),
            "category": c.get("category", "general"),
            "icon": c.get("icon", "plug"),
            "author": c.get("author", ""),
            "rating": c.get("rating", 0.0),
            "installed": name in installed_names,
        })
    return jsonify({"connectors": results, "total": len(results)})


@bp.route("/api/marketplace/connectors/<name>")
@login_required
def api_marketplace_connector_detail(name):
    """Detalles de un conector específico."""
    from src.sdk.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    if not registry.exists(name):
        return jsonify({"error": "Conector no encontrado"}), 404

    metadata = registry.get_metadata(name) or {}
    metadata["name"] = name
    cls = registry.get(name)
    if cls:
        metadata["class_name"] = cls.__name__
        metadata["module"] = cls.__module__
        try:
            instance = cls()
            metadata["actions"] = instance.get_action_names()
            status = instance.get_status()
            metadata["status"] = {
                "connected": status.get("connected", False),
                "healthy": status.get("healthy", False),
                "circuit_breaker": status.get("circuit_breaker", {}),
            }
        except Exception:
            metadata["actions"] = []
            metadata["status"] = {"connected": False, "healthy": False}

    config = db.fetchone("SELECT * FROM connector_configs WHERE connector_name = ?", (name,))
    metadata["installed"] = config is not None
    if config:
        try:
            metadata["config"] = json.loads(config["config"])
        except Exception:
            metadata["config"] = {}

    return jsonify(metadata)


@bp.route("/api/marketplace/connectors/<name>/install", methods=["POST"])
@login_required
@require_role("editor")
def api_marketplace_install(name):
    """Instala un conector del marketplace."""
    from src.sdk.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    if not registry.exists(name):
        return jsonify({"error": "Conector no encontrado"}), 404

    existing = db.fetchone("SELECT id FROM connector_configs WHERE connector_name = ?", (name,))
    if existing:
        return jsonify({"status": "already_installed", "message": "El conector ya está instalado"})

    db.execute(
        "INSERT INTO connector_configs (connector_name, config, user_id) VALUES (?, ?, ?)",
        (name, '{}', session.get("user_id", 1)),
    )
    db.commit()
    db.audit("connector.installed", f"Conector '{name}' instalado", request.remote_addr)
    return jsonify({"status": "installed", "message": f"Conector '{name}' instalado exitosamente"})


@bp.route("/api/marketplace/connectors/<name>/uninstall", methods=["POST"])
@login_required
@require_role("editor")
def api_marketplace_uninstall(name):
    """Desinstala un conector."""
    db.execute("DELETE FROM connector_configs WHERE connector_name = ?", (name,))
    db.commit()
    db.audit("connector.uninstalled", f"Conector '{name}' desinstalado", request.remote_addr)
    return jsonify({"status": "uninstalled", "message": f"Conector '{name}' desinstalado"})


@bp.route("/api/marketplace/categories")
@login_required
def api_marketplace_categories():
    """Lista categorías del marketplace con conteo."""
    from src.sdk.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    all_connectors = registry.list_all()

    counts: dict[str, int] = {}
    for c in all_connectors:
        cat = c.get("category", "general")
        counts[cat] = counts.get(cat, 0) + 1

    icon_map = {
        "ai": "brain", "communication": "mail", "crm": "users",
        "database": "database", "devops": "git-branch", "finance": "credit-card",
        "messaging": "message-circle", "monitoring": "activity",
        "productivity": "zap", "storage": "hard-drive", "social": "share-2",
        "general": "plug",
    }
    categories = []
    for cat_name in icon_map:
        categories.append({"name": cat_name, "count": counts.get(cat_name, 0), "icon": icon_map[cat_name]})

    return jsonify(categories)


@bp.route("/api/marketplace/stats")
@login_required
def api_marketplace_stats():
    """Estadísticas del marketplace."""
    from src.sdk.registry import ConnectorRegistry
    registry = ConnectorRegistry()
    all_connectors = registry.list_all()
    categories = {c.get("category", "general") for c in all_connectors}
    return jsonify({
        "total_connectors": len(all_connectors),
        "total_categories": len(categories),
        "featured_connectors": [c.get("name", "") for c in all_connectors[:5]],
    })


# ── API: Air-Gapped ────────────────────────────────────────

@bp.route("/api/airgap/status")
@login_required
def api_airgap_status():
    """Run all air-gapped validation checks."""
    from src.airgap import get_instance as get_airgap
    cfg = get_airgap()
    if not cfg.enabled:
        return jsonify({"valid": False, "checks": {}, "message": "Air-gapped mode is disabled"})
    try:
        result = cfg.validate()
        checks = result.get("checks", {})
        return jsonify({
            "valid": result.get("all_passed", False),
            "checks": checks,
            "all_passed": result.get("all_passed", False),
        })
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 500


@bp.route("/api/airgap/config")
@login_required
def api_airgap_config():
    """Get air-gapped configuration including connector lists."""
    from src.airgap import CLOUD_CONNECTORS, LOCAL_CONNECTORS
    from src.airgap import get_instance as get_airgap
    cfg = get_airgap()
    summary = cfg.get_status_summary() if cfg.enabled else {"mode": "online"}
    return jsonify({
        "cloud_connectors": CLOUD_CONNECTORS,
        "local_connectors": LOCAL_CONNECTORS,
        "internal_dns": cfg.registry_mirror or "",
        "mode": summary.get("mode", "online"),
        "version": "1.0.0",
    })


@bp.route("/api/airgap/license", methods=["POST"])
@login_required
@require_role("admin")
def api_airgap_create_license():
    """Create an offline air-gapped license."""
    import secrets

    from src.airgap import get_instance as get_airgap
    data = request.get_json() or {}
    customer = data.get("client", "")
    days = int(data.get("days", 365))
    if not customer:
        return jsonify({"error": "client es requerido"}), 400
    cfg = get_airgap()
    try:
        license_key = f"ag-{secrets.token_hex(16)}"
        result = cfg.create_airgap_license(
            customer_name=customer,
            license_key=license_key,
            expiry_days=days,
        )
        return jsonify({
            "license_key": license_key,
            "customer": customer,
            "days": days,
            "signature": result.get("signature", ""),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/airgap/license/verify", methods=["POST"])
@login_required
def api_airgap_verify_license():
    """Verify an offline air-gapped license file."""
    from src.airgap import get_instance as get_airgap
    data = request.get_json() or {}
    license_key = data.get("license_key", "")
    if not license_key:
        return jsonify({"valid": False, "error": "license_key requerido"}), 400
    cfg = get_airgap()
    result = cfg.verify_airgap_license()
    return jsonify({
        "valid": result.get("valid", False),
        "error": result.get("error"),
        "customer": result.get("customer", ""),
        "days_remaining": result.get("days_remaining", 0),
    })
