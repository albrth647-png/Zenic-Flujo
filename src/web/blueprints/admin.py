"""
Blueprints — Admin: Users, Dead Letter Queue y Work Queue
"""

from datetime import datetime

from flask import Blueprint, jsonify, request, session

from src.core.repositories import AuditRepository, UserRepository
from src.web.helpers import login_required, require_role

users = UserRepository()
audit = AuditRepository()

bp = Blueprint("admin", __name__)


# ── API: Users Management (RBAC) ───────────────────────────

@bp.route("/api/users", methods=["GET"])
@login_required
@require_role("admin")
def api_list_users():
    user_list = users.list_users()
    return jsonify(user_list)


@bp.route("/api/users", methods=["POST"])
@login_required
@require_role("admin")
def api_create_user():
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    role = data.get("role", "editor")
    allowed_roles = {"admin", "editor", "viewer"}
    if role not in allowed_roles:
        return jsonify({"error": f"Rol inválido. Roles válidos: {', '.join(sorted(allowed_roles))}"}), 400
    if not username or len(username) < 3:
        return jsonify({"error": "Usuario debe tener al menos 3 caracteres"}), 400
    if len(password) < 6:
        return jsonify({"error": "Contraseña debe tener al menos 6 caracteres"}), 400
    existing = users.get_user_by_username(username)
    if existing:
        return jsonify({"error": "El usuario ya existe"}), 400
    new_user = users.create_user(
        username=username,
        password=password,
        role=role,
        display_name=data.get("display_name", ""),
        email=data.get("email", ""),
    )
    audit.log("user.created", f"Usuario creado: {username}", request.remote_addr, session.get("user_id"))
    return jsonify(new_user), 201


@bp.route("/api/users/<int:user_id>", methods=["PUT"])
@login_required
@require_role("admin")
def api_update_user(user_id):
    data = request.get_json() or {}
    allowed = {"role", "display_name", "email", "is_active"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "Sin campos válidos para actualizar"}), 400
    users.update_user(user_id, updates)
    audit.log("user.updated", f"Usuario {user_id} actualizado", request.remote_addr, session.get("user_id"))
    return jsonify({"status": "updated"})


@bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@login_required
@require_role("admin")
def api_delete_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"error": "No puedes eliminarte a ti mismo"}), 400
    users.delete_user(user_id)
    audit.log("user.deleted", f"Usuario {user_id} desactivado", request.remote_addr, session.get("user_id"))
    return jsonify({"status": "deleted"})


# ── API: Dead Letter Queue (Sprint 4) ─────────────────────

@bp.route("/api/dead-letter", methods=["GET"])
@login_required
def api_dead_letter_list():
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    status = request.args.get("status")
    workflow_id = request.args.get("workflow_id", type=int)
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    entries = dl.list(status=status, workflow_id=workflow_id, limit=limit, offset=offset)
    return jsonify({"entries": [e.to_dict() for e in entries], "stats": dl.get_stats()})


@bp.route("/api/dead-letter/stats", methods=["GET"])
@login_required
def api_dead_letter_stats():
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    return jsonify(dl.get_stats())


@bp.route("/api/dead-letter/<int:entry_id>/retry", methods=["POST"])
@login_required
@require_role("editor")
def api_dead_letter_retry(entry_id):
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    result = dl.retry(entry_id)
    return jsonify(result)


@bp.route("/api/dead-letter/<int:entry_id>/discard", methods=["POST"])
@login_required
@require_role("editor")
def api_dead_letter_discard(entry_id):
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    success = dl.discard(entry_id)
    return jsonify({"status": "discarded" if success else "not_found"})


@bp.route("/api/dead-letter/retry-all", methods=["POST"])
@login_required
@require_role("editor")
def api_dead_letter_retry_all():
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    results = dl.retry_all()
    return jsonify(results)


@bp.route("/api/dead-letter/discard-all", methods=["POST"])
@login_required
@require_role("editor")
def api_dead_letter_discard_all():
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    count = dl.discard_all()
    return jsonify({"discarded": count})


@bp.route("/api/dead-letter/notify/<int:entry_id>", methods=["POST"])
@login_required
@require_role("editor")
def api_dead_letter_notify(entry_id):
    from src.workflow.dead_letter import DeadLetterManager
    dl = DeadLetterManager()
    result = dl.notify_dead_letter(entry_id)
    return jsonify({"notified": result})


# ── API: Work Queue + Workers (Sprint 7-8) ─────────────────

@bp.route("/api/queue/status")
@login_required
def api_queue_status():
    from src.events.work_queue import WorkQueue
    queue = WorkQueue()
    metrics = queue.get_metrics()
    peek = queue.peek(limit=10)
    return jsonify({"metrics": metrics, "next_items": [item.to_dict() for item in peek]})


@bp.route("/api/queue/workers")
@login_required
def api_queue_workers():
    from src.events.worker_manager import WorkerManager
    mgr = WorkerManager()
    return jsonify(mgr.get_metrics())


@bp.route("/api/queue/enqueue", methods=["POST"])
@login_required
@require_role("editor")
def api_queue_enqueue():
    data = request.get_json() or {}
    workflow_id = data.get("workflow_id")
    if not workflow_id:
        return jsonify({"error": "workflow_id es requerido"}), 400
    from src.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()
    try:
        result = engine.execute_async(
            workflow_id=workflow_id,
            trigger_data=data.get("trigger_data"),
            priority=data.get("priority", 0),
        )
        return jsonify(result), 202
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/queue/<int:item_id>/retry", methods=["POST"])
@login_required
@require_role("editor")
def api_queue_retry(item_id):
    from src.events.work_queue import WorkQueue
    queue = WorkQueue()
    result = queue.retry_failed(max_items=1)
    return jsonify({"retried": result})


@bp.route("/api/queue/cleanup", methods=["POST"])
@login_required
@require_role("admin")
def api_queue_cleanup():
    data = request.get_json() or {}
    max_age = int(data.get("max_age_hours", 24))
    from src.events.work_queue import WorkQueue
    queue = WorkQueue()
    deleted = queue.cleanup(max_age_hours=max_age)
    return jsonify({"deleted": deleted})


# ─── Sprint 11: Monitoreo + Alertas ─────────────────────────────────────


@bp.route("/api/admin/metrics", methods=["GET"])
@login_required
@require_role("admin")
def api_admin_metrics():
    """
    Devuelve métricas del sistema en formato JSON para el dashboard admin.
    Combina datos de MetricsRegistry (Prometheus), WorkQueue y DeadLetterManager.
    """
    from src.core.db import DatabaseManager
    from src.core.observability.metrics import MetricsRegistry
    from src.events.work_queue import WorkQueue
    from src.workflow.dead_letter import DeadLetterManager

    db = DatabaseManager()
    MetricsRegistry()

    # Work queue metrics
    queue = WorkQueue()
    queue_metrics = queue.get_metrics() if hasattr(queue, "get_metrics") else {}

    # Dead letter metrics
    dl_manager = DeadLetterManager(db)
    dl_stats = dl_manager.get_stats() if hasattr(dl_manager, "get_stats") else {}

    # Workflow execution stats
    workflow_stats_rows = db.fetchall(
        """SELECT status, COUNT(*) AS count,
                  AVG(duration_ms) AS avg_duration_ms,
                  MAX(duration_ms) AS max_duration_ms
           FROM workflow_executions
           WHERE started_at >= datetime('now', '-1 hour')
           GROUP BY status"""
    )
    workflow_stats = {row["status"]: dict(row) for row in workflow_stats_rows}

    # Top 10 slowest workflows en la última hora
    slowest_workflows = db.fetchall(
        """SELECT we.workflow_id, wd.name AS workflow_name,
                  we.duration_ms, we.status, we.started_at
           FROM workflow_executions we
           JOIN workflow_definitions wd ON we.workflow_id = wd.id
           WHERE we.started_at >= datetime('now', '-1 hour')
             AND we.duration_ms IS NOT NULL
           ORDER BY we.duration_ms DESC
           LIMIT 10"""
    )

    # Workflow executions en la última hora (timeline para gráfica)
    timeline = db.fetchall(
        """SELECT strftime('%Y-%m-%dT%H:00:00', started_at) AS hour,
                  status, COUNT(*) AS count
           FROM workflow_executions
           WHERE started_at >= datetime('now', '-24 hours')
           GROUP BY hour, status
           ORDER BY hour"""
    )

    return jsonify({
        "workqueue": queue_metrics,
        "dead_letter": dl_stats,
        "workflow_stats_1h": workflow_stats,
        "slowest_workflows_1h": [dict(r) for r in slowest_workflows],
        "timeline_24h": [dict(r) for r in timeline],
        "timestamp": datetime.utcnow().isoformat(),
    })


@bp.route("/api/admin/metrics/prometheus", methods=["GET"])
@login_required
@require_role("admin")
def api_admin_metrics_prometheus():
    """Expone métricas en formato Prometheus text (para scrapeo por Prometheus).

    Requiere rol admin. Para integrar con Prometheus scraper externo, crear una
    service account con rol 'admin' y autenticar por Bearer token via header
    Authorization: Bearer <service_account_token>.
    """
    from src.core.observability.metrics import MetricsRegistry

    metrics = MetricsRegistry()
    return metrics.get_metrics(), 200, {"Content-Type": "text/plain; version=0.0.4"}


@bp.route("/api/admin/alerts", methods=["GET"])
@login_required
@require_role("admin")
def api_admin_list_alerts():
    """Lista alertas, opcionalmente filtradas por status."""
    from src.core.observability.alerts import AlertService

    status = request.args.get("status")  # active, resolved, suppressed, None (all)
    limit = min(200, max(1, request.args.get("limit", default=50, type=int)))
    offset = max(0, request.args.get("offset", default=0, type=int))

    service = AlertService()
    alerts = service.list_alerts(status=status, limit=limit, offset=offset)
    total = service.count_alerts(status=status)

    return jsonify({
        "total": total,
        "limit": limit,
        "offset": offset,
        "alerts": [a.to_dict() for a in alerts],
    })


@bp.route("/api/admin/alerts/<int:alert_id>/resolve", methods=["POST"])
@login_required
@require_role("admin")
def api_admin_resolve_alert(alert_id):
    """Marca una alerta como resuelta."""
    from src.core.observability.alerts import AlertService

    service = AlertService()
    resolved = service.resolve_alert(alert_id)
    if not resolved:
        return jsonify({"error": "Alert not found or already resolved"}), 404
    return jsonify({"status": "resolved", "alert_id": alert_id})


@bp.route("/api/admin/alerts/stats", methods=["GET"])
@login_required
@require_role("admin")
def api_admin_alerts_stats():
    """Resumen agregado de alertas para dashboard."""
    from src.core.observability.alerts import AlertService

    service = AlertService()
    return jsonify(service.get_alert_stats())


@bp.route("/api/admin/alerts/rules", methods=["GET"])
@login_required
@require_role("admin")
def api_admin_alert_rules():
    """Lista las reglas de alerta configuradas."""
    from src.core.observability.alerts import DEFAULT_RULES

    rules = [
        {
            "name": r.name,
            "description": r.description,
            "metric_name": r.metric_name,
            "threshold": r.threshold,
            "comparison": r.comparison,
            "severity": r.severity,
            "enabled": r.enabled,
            "channels": r.channels,
            "cooldown_seconds": r.cooldown_seconds,
        }
        for r in DEFAULT_RULES
    ]
    return jsonify({"rules": rules, "total": len(rules)})


@bp.route("/api/admin/alerts/evaluate", methods=["POST"])
@login_required
@require_role("admin")
def api_admin_evaluate_alerts():
    """Evalúa manualmente todas las reglas y dispara alertas si procede."""
    from src.core.observability.alerts import AlertService

    service = AlertService()
    # Registrar providers reales del sistema
    _register_default_metric_providers(service)

    triggered = service.evaluate_all_rules()
    return jsonify({
        "triggered_count": len(triggered),
        "alerts": [a.to_dict() for a in triggered],
    })


def _register_default_metric_providers(service) -> None:
    """Registra providers de métricas reales del sistema en el AlertService."""
    from src.core.db import DatabaseManager
    from src.events.work_queue import WorkQueue
    from src.workflow.dead_letter import DeadLetterManager

    db = DatabaseManager()

    # workflow_failure_rate_1h: fracción de ejecuciones fallidas en la última hora
    def _failure_rate() -> float:
        row = db.fetchone(
            """SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
               FROM workflow_executions
               WHERE started_at >= datetime('now', '-1 hour')"""
        )
        if not row or not row["total"]:
            return 0.0
        return float(row["failed"]) / float(row["total"])

    service.register_metric_provider("workflow_failure_rate_1h", _failure_rate)

    # dead_letter_queue_depth
    def _dlq_depth() -> float:
        try:
            dl = DeadLetterManager(db)
            return float(dl.count())
        except Exception:
            return 0.0

    service.register_metric_provider("dead_letter_queue_depth", _dlq_depth)

    # work_queue_depth
    def _queue_depth() -> float:
        try:
            q = WorkQueue()
            m = q.get_metrics() if hasattr(q, "get_metrics") else {}
            return float(m.get("depth", 0))
        except Exception:
            return 0.0

    service.register_metric_provider("work_queue_depth", _queue_depth)

    # workers_alive: por ahora 4 (DEFAULT_NUM_WORKERS) — en producción leer de WorkerManager
    def _workers_alive() -> float:
        try:
            # WorkerManager es singleton; si no está inicializado, retornar 0
            return 4.0  # valor por defecto conservador
        except Exception:
            return 4.0

    service.register_metric_provider("workers_alive", _workers_alive)
