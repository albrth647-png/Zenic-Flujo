"""
Blueprints — Sync Cloud E2E (export/import cifrado)
"""

import hmac

from flask import Blueprint, jsonify, request, session

from src.web.helpers import login_required, require_role

bp = Blueprint("sync", __name__)


@bp.route("/api/sync/config", methods=["GET"])
@login_required
def api_sync_config():
    """Get sync configuration."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    config = engine.get_config(tenant_id)
    return jsonify(config.to_dict() if config else {"enabled": False})


@bp.route("/api/sync/config", methods=["PUT"])
@login_required
@require_role("admin")
def api_sync_update_config():
    """Update sync configuration."""
    from src.sync.engine import SyncEngine
    from src.sync.models import ConflictStrategy, SyncConfig
    engine = SyncEngine.get_instance()
    data = request.get_json() or {}
    tenant_id = str(session.get("user_id", 1))

    config = SyncConfig(
        tenant_id=tenant_id,
        enabled=data.get("enabled", False),
        sync_interval_minutes=data.get("sync_interval_minutes", 60),
        conflict_strategy=ConflictStrategy(data.get("conflict_strategy", "timestamp_wins")),
        target_url=data.get("target_url", ""),
        auto_sync=data.get("auto_sync", False),
        include_credentials=data.get("include_credentials", False),
    )

    new_key = data.get("target_api_key", "")
    if new_key and new_key != "••••••••":
        config.target_api_key = new_key

    result = engine.configure(tenant_id, config)
    return jsonify(result)


@bp.route("/api/sync/key/generate", methods=["POST"])
@login_required
@require_role("admin")
def api_sync_generate_key():
    """Generate a new E2E encryption key for sync."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    result = engine.generate_sync_key(tenant_id)
    return jsonify(result)


@bp.route("/api/sync/export", methods=["POST"])
@login_required
@require_role("editor")
def api_sync_export():
    """Export workflows to an E2E encrypted package."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    data = request.get_json() or {}
    workflow_ids = data.get("workflow_ids", [])
    include_creds = data.get("include_credentials", False)

    if not workflow_ids:
        return jsonify({"error": "workflow_ids es requerido"}), 400

    try:
        pkg = engine.export_workflows(tenant_id, workflow_ids, include_creds)
        return jsonify({
            "status": "ok",
            "package_id": pkg.package_id,
            "workflow_count": pkg.workflow_count,
            "payload_encrypted": pkg.payload_encrypted,
            "payload_iv": pkg.payload_iv,
            "payload_tag": pkg.payload_tag,
            "hmac_signature": pkg.hmac_signature,
            "key_version": pkg.key_version,
            "source_instance_id": pkg.source_instance_id,
            "created_at": pkg.created_at,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/sync/import", methods=["POST"])
@login_required
@require_role("editor")
def api_sync_import():
    """Import workflows from an E2E encrypted package."""
    from src.sync.engine import SyncEngine
    from src.sync.models import ConflictStrategy, SyncPackage
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    data = request.get_json() or {}

    pkg = SyncPackage(
        package_id=data.get("package_id", ""),
        source_instance_id=data.get("source_instance_id", ""),
        source_version=data.get("source_version", "1.0.0"),
        created_at=data.get("created_at", 0),
        payload_encrypted=data.get("payload_encrypted", ""),
        payload_iv=data.get("payload_iv", ""),
        payload_tag=data.get("payload_tag", ""),
        key_version=data.get("key_version", 1),
        hmac_signature=data.get("hmac_signature", ""),
        workflow_count=data.get("workflow_count", 0),
    )

    strategy_str = data.get("conflict_strategy", "timestamp_wins")
    try:
        strategy = ConflictStrategy(strategy_str)
    except ValueError:
        strategy = ConflictStrategy.TIMESTAMP_WINS

    result = engine.import_package(tenant_id, pkg, strategy)
    return jsonify(result)


@bp.route("/api/sync/push", methods=["POST"])
@login_required
@require_role("editor")
def api_sync_push():
    """Push encrypted package to remote target."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    data = request.get_json() or {}
    workflow_ids = data.get("workflow_ids", [])

    if not workflow_ids:
        return jsonify({"error": "workflow_ids es requerido"}), 400

    try:
        pkg = engine.export_workflows(tenant_id, workflow_ids)
        result = engine.push_package(tenant_id, pkg)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/sync/receive", methods=["POST"])
def api_sync_receive():
    """Receive an encrypted package from a remote instance.

    Requiere autenticación via API key obligatoria (no opcional):
    headers X-Sync-Source + X-Sync-API-Key deben estar presentes.
    Sin ellos → 401. Vector de ataque cerrado.
    """
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    data = request.get_json() or {}
    source_instance = request.headers.get("X-Sync-Source", "")
    api_key = request.headers.get("X-Sync-API-Key", "")

    # Auth OBLIGATORIA: ambos headers deben estar presentes y ser válidos.
    if not api_key or not source_instance:
        return jsonify({
            "status": "error",
            "message": "X-Sync-Source and X-Sync-API-Key headers are required",
        }), 401

    config = engine.get_config(source_instance)
    if not config or not config.target_api_key:
        # Source instance no reconocido o sin API key configurada
        return jsonify({
            "status": "error",
            "message": "Unknown source instance or API key not configured",
        }), 401

    if not hmac.compare_digest(api_key, config.target_api_key):
        return jsonify({"status": "error", "message": "Invalid API key"}), 401

    result = engine.receive_package(data)
    return jsonify(result)


@bp.route("/api/sync/history")
@login_required
def api_sync_history():
    """Get sync history."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    limit = int(request.args.get("limit", 20))
    return jsonify({"history": engine.get_history(tenant_id, limit)})


@bp.route("/api/sync/stats")
@login_required
def api_sync_stats():
    """Get sync statistics."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    stats = engine.get_stats(tenant_id)
    return jsonify(stats)


@bp.route("/api/sync/config", methods=["DELETE"])
@login_required
@require_role("admin")
def api_sync_delete_config():
    """Delete sync configuration and all sync data."""
    from src.sync.engine import SyncEngine
    engine = SyncEngine.get_instance()
    tenant_id = str(session.get("user_id", 1))
    result = engine.delete_config(tenant_id)
    return jsonify(result)
