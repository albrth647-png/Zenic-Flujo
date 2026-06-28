"""
Blueprints — Compliance (SOC 2 Type II, GDPR, HIPAA)
"""

from contextlib import suppress

from flask import Blueprint, jsonify, request

from src.web.helpers import login_required, require_role

bp = Blueprint("compliance", __name__)


# ── API: SOC 2 Type II ─────────────────────────────────────

@bp.route("/api/compliance/typeii/periods", methods=["GET"])
@login_required
def api_typeii_periods():
    """List all SOC 2 Type II monitoring periods."""
    from src.compliance import SOC2TypeIIManager
    mgr = SOC2TypeIIManager.get_instance()
    periods = mgr.list_periods()
    subservices = mgr.list_subservices()
    return jsonify({
        "periods": [
            {
                "period_id": p.period_id,
                "name": p.name,
                "start_date": p.start_date,
                "end_date": p.end_date,
                "status": p.status.value if hasattr(p.status, 'value') else str(p.status),
                "test_count": p.controls_tested,
                "pass_rate": (p.controls_passed / max(p.controls_tested, 1)) if p.controls_tested > 0 else None,
                "monitoring_days": p.monitoring_days,
            }
            for p in (periods or [])
        ],
        "subservices": [
            {
                "subservice_id": s.subservice_id,
                "name": s.name,
                "type": s.reporting_method or "carve_out",
                "services_provided": s.services_provided,
                "has_soc_report": s.has_soc_report,
            }
            for s in (subservices or [])
        ],
    })


@bp.route("/api/compliance/typeii/periods", methods=["POST"])
@login_required
@require_role("editor")
def api_typeii_create_period():
    """Create a new SOC 2 Type II monitoring period."""
    import time

    from src.compliance import SOC2TypeIIManager
    data = request.get_json() or {}
    name = data.get("name", "")
    months = int(data.get("duration_months", 6))
    if not name:
        return jsonify({"error": "name es requerido"}), 400
    mgr = SOC2TypeIIManager.get_instance()
    now = time.time()
    period = mgr.create_monitoring_period(
        name=name,
        start_date=now,
        end_date=now + (months * 30 * 86400),
        description=data.get("description", ""),
    )
    return jsonify({"period_id": period.period_id, "name": name, "status": "created"}), 201


@bp.route("/api/compliance/typeii/periods/<period_id>/bridge-letter", methods=["POST"])
@login_required
@require_role("editor")
def api_typeii_bridge_letter(period_id):
    """Generate a bridge letter for monitoring period transitions."""
    from src.compliance import SOC2TypeIIManager
    mgr = SOC2TypeIIManager.get_instance()
    try:
        letter = mgr.generate_bridge_letter(period_id, period_id)
        return jsonify({"bridge_letter": letter})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/compliance/typeii/periods/<period_id>/tests", methods=["GET"])
@login_required
def api_typeii_period_tests(period_id):
    """Get test results for a monitoring period."""
    from src.compliance import SOC2TypeIIManager
    mgr = SOC2TypeIIManager.get_instance()
    try:
        tests = mgr.get_test_results(period_id=period_id)
        return jsonify({
            "tests": [
                {
                    "test_id": t.test_id,
                    "control_id": t.control_id,
                    "result": t.result.value if hasattr(t.result, 'value') else str(t.result),
                    "sample_size": t.sample_size,
                    "test_date": t.test_date,
                    "exceptions_found": t.exceptions_found,
                    "remediated": t.remediated,
                    "notes": t.notes,
                }
                for t in (tests or [])
            ]
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/compliance/typeii/subservices", methods=["POST"])
@login_required
@require_role("editor")
def api_typeii_create_subservice():
    """Add a subservice organization."""
    from src.compliance import SOC2TypeIIManager, SubserviceOrganization
    data = request.get_json() or {}
    name = data.get("name", "")
    reporting_method = data.get("type", "carve_out")
    if not name:
        return jsonify({"error": "name es requerido"}), 400
    mgr = SOC2TypeIIManager.get_instance()
    sub = SubserviceOrganization(name=name, reporting_method=reporting_method)
    sid = mgr.add_subservice(sub)
    return jsonify({"subservice_id": sid}), 201


@bp.route("/api/compliance/typeii/subservices/<subservice_id>", methods=["DELETE"])
@login_required
@require_role("editor")
def api_typeii_delete_subservice(subservice_id):
    """Delete a subservice organization."""
    from src.compliance import SOC2TypeIIManager
    mgr = SOC2TypeIIManager.get_instance()
    if subservice_id in mgr._subservices:
        del mgr._subservices[subservice_id]
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Subservice not found"}), 404


# ── API: Compliance (SOC 2, GDPR, HIPAA) ───────────────────

@bp.route("/api/compliance/overview")
@login_required
def api_compliance_overview():
    """Overview of all compliance frameworks: scores, stats, recommendations."""
    from src.compliance import ComplianceManager
    cm = ComplianceManager.get_instance()
    scores = cm.calculate_framework_scores()
    controls = cm.list_controls()
    return jsonify({
        "scores": scores,
        "controls_count": len(controls),
        "controls": [
            {
                "control_id": c.control_id,
                "name": c.name,
                "ref_code": c.ref_code,
                "framework": c.framework.value,
                "status": c.status.value,
                "risk_level": c.risk_level,
                "last_tested": c.last_tested,
                "remediation_notes": c.remediation_notes,
            }
            for c in controls
        ],
        "recommendations": cm._generate_recommendations(),
    })


@bp.route("/api/compliance/controls", methods=["GET"])
@login_required
def api_compliance_controls():
    """List compliance controls with optional framework/status filters."""
    from src.compliance import ComplianceFramework, ComplianceManager, ControlStatus
    cm = ComplianceManager.get_instance()
    framework_str = request.args.get("framework")
    status_str = request.args.get("status")
    risk_str = request.args.get("risk_level")

    framework = None
    if framework_str:
        with suppress(ValueError):
            framework = ComplianceFramework(framework_str)
    status = None
    if status_str:
        with suppress(ValueError):
            status = ControlStatus(status_str)

    controls = cm.list_controls(framework=framework, status=status, risk_level=risk_str)
    return jsonify({
        "controls": [
            {
                "control_id": c.control_id,
                "name": c.name,
                "description": c.description,
                "framework": c.framework.value,
                "ref_code": c.ref_code,
                "status": c.status.value,
                "risk_level": c.risk_level,
                "test_procedure": c.test_procedure,
                "implementation_guidance": c.implementation_guidance,
                "evidence_count": len(c.evidence_ids),
                "last_tested": c.last_tested,
                "remediation_notes": c.remediation_notes,
            }
            for c in controls
        ],
        "total": len(controls),
    })


@bp.route("/api/compliance/controls/<control_id>/status", methods=["PUT"])
@login_required
@require_role("editor")
def api_compliance_update_status(control_id):
    """Update the status of a compliance control."""
    from src.compliance import ComplianceManager, ControlStatus
    data = request.get_json() or {}
    status_str = data.get("status", "")
    try:
        status = ControlStatus(status_str)
    except ValueError:
        return jsonify({"error": f"Invalid status: {status_str}"}), 400
    cm = ComplianceManager.get_instance()
    success = cm.update_control_status(control_id, status, notes=data.get("notes", ""))
    if not success:
        return jsonify({"error": "Control not found"}), 404
    return jsonify({"status": "updated", "new_status": status.value})


@bp.route("/api/compliance/audit", methods=["GET"])
@login_required
def api_compliance_audit():
    """Get compliance audit trail."""
    from src.compliance import ComplianceManager
    cm = ComplianceManager.get_instance()
    limit = int(request.args.get("limit", 50))
    entries = cm.get_audit_trail(limit=limit)
    return jsonify({
        "entries": [
            {
                "entry_id": e.entry_id,
                "timestamp": e.timestamp,
                "actor": e.actor,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "details": e.details,
            }
            for e in entries
        ],
        "total": len(entries),
    })


@bp.route("/api/compliance/report", methods=["GET"])
@login_required
def api_compliance_report():
    """Generate comprehensive compliance report."""
    from src.compliance import ComplianceManager
    cm = ComplianceManager.get_instance()
    report = cm.generate_report()
    return jsonify(report)


@bp.route("/api/compliance/policies", methods=["GET"])
@login_required
def api_compliance_policies():
    """List compliance policies."""
    from src.compliance import ComplianceManager
    cm = ComplianceManager.get_instance()
    category = request.args.get("category")
    status = request.args.get("status")
    policies = cm.list_policies(category=category, status=status)
    return jsonify({
        "policies": [
            {
                "policy_id": p.policy_id,
                "name": p.name,
                "version": p.version,
                "category": p.category,
                "status": p.status,
                "approved_by": p.approved_by,
                "effective_date": p.effective_date,
            }
            for p in policies
        ]
    })


# ── API: GDPR ──────────────────────────────────────────────

@bp.route("/api/compliance/gdpr/consents", methods=["GET"])
@login_required
def api_gdpr_consents():
    from src.compliance.gdpr import ConsentManager
    cm = ConsentManager.get_instance()
    subject_id = request.args.get("subject_id")
    return jsonify({"consents": cm.get_consents(subject_id)})


@bp.route("/api/compliance/gdpr/dsars", methods=["GET"])
@login_required
def api_gdpr_dsars():
    from src.compliance.gdpr import ConsentManager
    cm = ConsentManager.get_instance()
    status_filter = request.args.get("status")
    return jsonify({"dsars": cm.list_dsars(status=status_filter)})


@bp.route("/api/compliance/gdpr/stats")
@login_required
def api_gdpr_stats():
    from src.compliance.gdpr import ConsentManager
    cm = ConsentManager.get_instance()
    return jsonify(cm.get_stats())


# ── API: HIPAA ─────────────────────────────────────────────

@bp.route("/api/compliance/hipaa/baas", methods=["GET"])
@login_required
def api_hipaa_baas():
    from src.compliance.hipaa import BAAManager
    bm = BAAManager.get_instance()
    status_filter = request.args.get("status")
    return jsonify({"baas": bm.list_baas(status=status_filter)})


@bp.route("/api/compliance/hipaa/phi", methods=["GET"])
@login_required
def api_hipaa_phi():
    from src.compliance.hipaa import BAAManager
    bm = BAAManager.get_instance()
    return jsonify({"phi_items": bm.list_phi_inventory()})


@bp.route("/api/compliance/hipaa/stats")
@login_required
def api_hipaa_stats():
    from src.compliance.hipaa import BAAManager
    bm = BAAManager.get_instance()
    return jsonify(bm.get_stats())
