"""
Blueprints — Workflows CRUD, Historial y Export/Import
"""

from flask import Blueprint, jsonify, request, session

from src.schemas import ErrorResponse, StatusDeletedResponse, StatusResponse, WorkflowResponse
from src.web.helpers import _sanitize, check_free_tier, login_required, repo, require_role, workflow_subscriber
from src.workflow.repository import WorkflowDefinition

bp = Blueprint("workflows", __name__)


@bp.route("/api/workflows", methods=["GET"])
@login_required
def api_list_workflows():
    status = request.args.get("status")
    workflows = repo.list_all(status)
    return jsonify([WorkflowResponse(**w.to_dict()).model_dump() for w in workflows])


@bp.route("/api/workflows", methods=["POST"])
@login_required
@require_role("editor")
@check_free_tier()
def api_create_workflow():
    data = request.get_json() or {}
    try:
        wf = WorkflowDefinition(
            name=_sanitize(data.get("name", "")),
            description=_sanitize(data.get("description", "")),
            trigger_type=data.get("trigger_type", "manual"),
            trigger_config=data.get("trigger_config", {}),
            steps=data.get("steps", []),
        )
        created = repo.create(wf, user_id=session.get("user_id"))

        if created.trigger_type == "event":
            event_config = created.trigger_config
            event_type = event_config.get("event", "")
            if event_type:
                workflow_subscriber.subscribe(event_type, created.id)
        elif created.trigger_type == "webhook":
            workflow_subscriber.subscribe("webhook.received", created.id)

        return jsonify(WorkflowResponse(**created.to_dict()).model_dump()), 201
    except ValueError as e:
        return jsonify(ErrorResponse(error="validation_error", message=str(e)).model_dump()), 400


@bp.route("/api/workflows/<int:wf_id>", methods=["GET"])
@login_required
def api_get_workflow(wf_id):
    wf = repo.get(wf_id)
    if not wf:
        return jsonify(ErrorResponse(error="not_found", message="Workflow no encontrado").model_dump()), 404
    return jsonify(WorkflowResponse(**wf.to_dict()).model_dump())


@bp.route("/api/workflows/<int:wf_id>", methods=["PUT"])
@login_required
@require_role("editor")
def api_update_workflow(wf_id):
    data = request.get_json() or {}
    updated = repo.update(wf_id, data)
    if not updated:
        return jsonify(ErrorResponse(error="not_found", message="Workflow no encontrado").model_dump()), 404
    return jsonify(WorkflowResponse(**updated.to_dict()).model_dump())


@bp.route("/api/workflows/<int:wf_id>", methods=["DELETE"])
@login_required
@require_role("editor")
def api_delete_workflow(wf_id):
    from src.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()
    engine.pause(wf_id)
    # Limpiar suscripciones del workflow eliminado
    workflow_subscriber.unsubscribe_all(wf_id)
    repo.delete(wf_id)
    return jsonify(StatusDeletedResponse().model_dump())


@bp.route("/api/workflows/<int:wf_id>/activate", methods=["POST"])
@login_required
@require_role("editor")
def api_activate_workflow(wf_id):
    from src.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()
    result = engine.resume(wf_id)
    # Restaurar suscripciones via WorkflowSubscriber
    if result:
        wf = repo.get(wf_id)
        if wf and wf.trigger_type == "event":
            event_type = wf.trigger_config.get("event", "")
            if event_type:
                workflow_subscriber.subscribe(event_type, wf_id)
        elif wf and wf.trigger_type == "webhook":
            workflow_subscriber.subscribe("webhook.received", wf_id)
    return jsonify(StatusResponse(status="active" if result else "error").model_dump())


@bp.route("/api/workflows/<int:wf_id>/pause", methods=["POST"])
@login_required
@require_role("editor")
def api_pause_workflow(wf_id):
    from src.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()
    result = engine.pause(wf_id)
    # Eliminar suscripciones via WorkflowSubscriber
    if result:
        workflow_subscriber.unsubscribe_all(wf_id)
    return jsonify(StatusResponse(status="paused" if result else "error").model_dump())


@bp.route("/api/workflows/<int:wf_id>/<action>", methods=["POST"])
@login_required
@require_role("editor")
def api_workflow_action(wf_id, action):
    """Endpoint genérico para activate/pause - compatible con frontend actual."""
    from src.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()

    if action == "activate":
        result = engine.resume(wf_id)
        status = "active" if result else "error"
        if result:
            wf = repo.get(wf_id)
            if wf and wf.trigger_type == "event":
                event_type = wf.trigger_config.get("event", "")
                if event_type:
                    workflow_subscriber.subscribe(event_type, wf_id)
            elif wf and wf.trigger_type == "webhook":
                workflow_subscriber.subscribe("webhook.received", wf_id)
    elif action == "pause":
        result = engine.pause(wf_id)
        status = "paused" if result else "error"
        if result:
            workflow_subscriber.unsubscribe_all(wf_id)
    else:
        return jsonify({"error": "Acción inválida. Use 'activate' o 'pause'"}), 400

    if status == "error":
        return jsonify({"error": f"No se pudo {action} el workflow"}), 400
    return jsonify({"status": status})


@bp.route("/api/workflows/<int:wf_id>/execute", methods=["POST"])
@login_required
@require_role("editor")
def api_workflow_execute(wf_id):
    """Ejecuta un workflow manualmente con trigger_data opcional del body."""
    from src.workflow.engine import WorkflowEngine

    body = request.get_json(silent=True) or {}
    trigger_data = body.get("trigger_data", {})
    engine = WorkflowEngine()
    try:
        result = engine.execute(wf_id, trigger_data)
        return jsonify(result.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/workflows/<int:wf_id>/history", methods=["GET"])
@login_required
def api_workflow_history(wf_id):
    """Lista el historial de ejecuciones de un workflow."""
    limit = int(request.args.get("limit", 50))
    executions = repo.list_executions(wf_id, limit)
    return jsonify([e.to_dict() for e in executions])


@bp.route("/api/workflows/<int:wf_id>/history/<int:exec_id>", methods=["GET"])
@login_required
def api_execution_detail(wf_id, exec_id):
    execution = repo.get_execution(exec_id)
    if not execution or execution.workflow_id != wf_id:
        return jsonify({"error": "Ejecución no encontrada"}), 404
    logs = repo.get_step_logs(exec_id)
    return jsonify({"execution": execution.to_dict(), "logs": logs})


@bp.route("/api/workflows/<int:wf_id>/export", methods=["GET"])
@login_required
def api_export_workflow(wf_id):
    exported = repo.export_workflow(wf_id)
    if not exported:
        return jsonify({"error": "Workflow no encontrado"}), 404
    return jsonify(exported)


@bp.route("/api/workflows/import", methods=["POST"])
@login_required
def api_import_workflow():
    data = request.get_json() or {}
    try:
        imported = repo.import_workflow(data)
        return jsonify(imported.to_dict()), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/workflows/<int:wf_id>/retry", methods=["POST"])
@login_required
@require_role("editor")
def api_retry_workflow(wf_id):
    from src.workflow.engine import WorkflowEngine
    engine = WorkflowEngine()
    try:
        result = engine.execute(wf_id)
        return jsonify(result.to_dict())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ─── Sprint 9: Versioning + Multi-entorno + Promoción ──────────────────
# Endpoints para gestionar versiones de workflows, entornos y promociones.
# Todos requieren login; los que mutan requieren rol editor.


@bp.route("/api/workflows/<int:wf_id>/versions", methods=["GET"])
@login_required
def api_list_workflow_versions(wf_id):
    """Lista las versiones de un workflow (las más recientes primero)."""
    from src.workflow.versioning import WorkflowVersionRepository

    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)
    # Limitar para evitar abuso
    limit = max(1, min(limit, 200))

    version_repo = WorkflowVersionRepository()
    versions = version_repo.list_versions(wf_id, limit=limit, offset=offset)
    total = version_repo.count_versions(wf_id)
    return jsonify({
        "workflow_id": wf_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "versions": [v.to_dict() for v in versions],
    })


@bp.route("/api/workflows/<int:wf_id>/versions/<int:version_number>", methods=["GET"])
@login_required
def api_get_workflow_version(wf_id, version_number):
    """Obtiene una versión específica de un workflow."""
    from src.workflow.versioning import WorkflowVersionRepository, VersionNotFoundError

    version_repo = WorkflowVersionRepository()
    version = version_repo.get_version(wf_id, version_number)
    if not version:
        return jsonify({"error": "Version not found"}), 404
    return jsonify(version.to_dict())


@bp.route("/api/workflows/<int:wf_id>/versions/<int:version_number>/rollback", methods=["POST"])
@login_required
@require_role("editor")
def api_rollback_workflow_version(wf_id, version_number):
    """
    Restaura el workflow a una versión anterior.
    Internamente crea una NUEVA versión con el contenido de la versión objetivo
    (no destruye el histórico, cumple el principio append-only del versioning).
    """
    from src.workflow.versioning import WorkflowVersionRepository

    version_repo = WorkflowVersionRepository()
    target_version = version_repo.get_version(wf_id, version_number)
    if not target_version:
        return jsonify({"error": "Version not found"}), 404

    # Aplicar el snapshot de la versión objetivo al workflow actual
    updated = repo.update(
        wf_id,
        {
            "name": target_version.name,
            "description": target_version.description,
            "trigger_type": target_version.trigger_type,
            "trigger_config": target_version.trigger_config,
            "steps": target_version.steps,
        },
        create_version=True,
        change_summary=f"Rollback a versión {version_number}",
        user_id=session.get("user_id", 1),
    )

    if not updated:
        return jsonify({"error": "Workflow not found"}), 404

    return jsonify({
        "status": "ok",
        "message": f"Workflow restaurado a versión {version_number}",
        "workflow": updated.to_dict(),
    })


@bp.route("/api/workflows/<int:wf_id>/environments", methods=["GET"])
@login_required
def api_list_workflow_environments(wf_id):
    """Lista los entornos donde está presente el workflow."""
    from src.workflow.versioning import EnvironmentService

    env_service = EnvironmentService()
    environments = env_service.list_environments(wf_id)
    return jsonify({
        "workflow_id": wf_id,
        "environments": [e.to_dict() for e in environments],
    })


@bp.route("/api/workflows/<int:wf_id>/environments/<environment>", methods=["POST"])
@login_required
@require_role("editor")
def api_assign_workflow_to_environment(wf_id, environment):
    """Asigna un workflow a un entorno (dev, staging, prod)."""
    from src.workflow.versioning import EnvironmentService, EnvironmentNotFoundError

    if environment not in ("dev", "staging", "prod"):
        return jsonify({"error": f"Invalid environment: {environment}"}), 400

    body = request.get_json(silent=True) or {}
    notes = body.get("notes", "")
    promoted_from = body.get("promoted_from")
    promoted_by = session.get("user_id", 1)

    # Verificar que el workflow existe
    wf = repo.get(wf_id)
    if not wf:
        return jsonify({"error": "Workflow not found"}), 404

    env_service = EnvironmentService()
    env = env_service.assign_to_environment(
        workflow_id=wf_id,
        environment=environment,
        promoted_from=promoted_from,
        promoted_by=promoted_by,
        notes=notes,
    )
    return jsonify(env.to_dict())


@bp.route("/api/workflows/<int:wf_id>/environments/<environment>", methods=["DELETE"])
@login_required
@require_role("editor")
def api_remove_workflow_from_environment(wf_id, environment):
    """Elimina la asociación de un workflow con un entorno."""
    from src.workflow.versioning import EnvironmentService

    if environment not in ("dev", "staging", "prod"):
        return jsonify({"error": f"Invalid environment: {environment}"}), 400

    env_service = EnvironmentService()
    deleted = env_service.remove_from_environment(wf_id, environment)
    if not deleted:
        return jsonify({"error": "Workflow not assigned to that environment"}), 404
    return jsonify({"status": "deleted"})


@bp.route("/api/workflows/<int:wf_id>/promote", methods=["POST"])
@login_required
@require_role("editor")
def api_promote_workflow(wf_id):
    """
    Promueve un workflow de un entorno a otro (dev→staging o staging→prod).

    Body JSON:
        {
            "source_env": "dev",
            "target_env": "staging",
            "notes": "Promoción para QA"  // opcional
        }
    """
    from src.workflow.versioning import (
        PromotionService,
        InvalidPromotionError,
        EnvironmentNotFoundError,
    )

    body = request.get_json(silent=True) or {}
    source_env = body.get("source_env")
    target_env = body.get("target_env")
    notes = body.get("notes", "")

    if not source_env or not target_env:
        return jsonify({
            "error": "Se requieren source_env y target_env"
        }), 400

    # Verificar que el workflow existe
    wf = repo.get(wf_id)
    if not wf:
        return jsonify({"error": "Workflow not found"}), 404

    # Construir definition desde el workflow actual
    workflow_definition = wf.to_dict()

    promotion_service = PromotionService()
    try:
        promotion = promotion_service.promote(
            workflow_id=wf_id,
            source_env=source_env,
            target_env=target_env,
            workflow_definition=workflow_definition,
            promoted_by=session.get("user_id", 1),
            notes=notes,
        )
    except InvalidPromotionError as e:
        return jsonify({"error": str(e)}), 400
    except EnvironmentNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify(promotion.to_dict()), 201


@bp.route("/api/workflows/<int:wf_id>/promotions", methods=["GET"])
@login_required
def api_list_workflow_promotions(wf_id):
    """Lista el histórico de promociones de un workflow."""
    from src.workflow.versioning import PromotionService

    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit, 200))

    promotion_service = PromotionService()
    promotions = promotion_service.list_promotions(wf_id, limit=limit)
    summary = promotion_service.get_promotion_history_summary(wf_id)
    return jsonify({
        "workflow_id": wf_id,
        "total": len(promotions),
        "promotions": [p.to_dict() for p in promotions],
        "summary_by_target_env": summary,
    })
