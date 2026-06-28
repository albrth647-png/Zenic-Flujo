"""
Blueprints — Partnership Program
"""

from flask import Blueprint, jsonify, request

from src.web.helpers import login_required, require_role

bp = Blueprint("partnership", __name__)


@bp.route("/api/partners/overview")
@login_required
def api_partners_overview():
    """Partners overview with list, stats, and analytics."""
    from src.partnership import PartnershipService
    svc = PartnershipService.get_instance()
    try:
        result = svc.list_partners()
        partners = result.get("partners", [])
        stats = svc.get_stats()
    except Exception:
        partners = []
        stats = {}
    return jsonify({
        "partners": [
            {
                "partner_id": p.get("partner_id", ""),
                "name": p.get("company_name", p.get("contact_name", "")),
                "email": p.get("contact_email", ""),
                "tier": p.get("tier", "community"),
                "status": p.get("status", "applicant"),
                "revenue_share": p.get("revenue_share_pct", 0) / 100.0,
                "connectors_published": p.get("connector_count", 0),
                "rating": p.get("rating", 0.0),
            }
            for p in partners
        ],
        "stats": {
            "total": stats.get("total_partners", len(partners)),
            "active": sum(1 for p in partners if p.get("status") == "active"),
            "by_tier": stats.get("by_tier", {}),
        },
    })


@bp.route("/api/partners/register", methods=["POST"])
@login_required
@require_role("editor")
def api_partners_register():
    """Register a new partner."""
    from src.partnership import PartnerRegistration, PartnershipService, PartnerTier
    data = request.get_json() or {}
    company = data.get("name", data.get("company", ""))
    contact = data.get("contact", data.get("name", ""))
    email = data.get("email", "")
    if not company or not email:
        return jsonify({"error": "name (company) y email son requeridos"}), 400
    svc = PartnershipService.get_instance()
    reg = PartnerRegistration(
        company_name=company,
        contact_name=contact or company,
        contact_email=email,
        website=data.get("website", ""),
        description=data.get("description", ""),
        country=data.get("country", ""),
        tier=PartnerTier.COMMUNITY,
    )
    result = svc.register(reg)
    if result.get("success"):
        return jsonify({"partner_id": result["partner_id"], "status": "registered"}), 201
    return jsonify({"error": result.get("error", "Error registrando partner")}), 400


@bp.route("/api/partners/<partner_id>/approve", methods=["POST"])
@login_required
@require_role("editor")
def api_partners_approve(partner_id):
    """Approve a partner registration."""
    from src.partnership import PartnershipService
    svc = PartnershipService.get_instance()
    success = svc.approve(partner_id)
    return jsonify({"status": "approved" if success else "not_found"})


@bp.route("/api/partners/<partner_id>/promote", methods=["POST"])
@login_required
@require_role("editor")
def api_partners_promote(partner_id):
    """Promote a partner to a higher tier."""
    from src.partnership import PartnershipService, PartnerTier
    data = request.get_json() or {}
    target_tier = data.get("target_tier", "silver")
    try:
        tier = PartnerTier(target_tier)
    except ValueError:
        return jsonify({"error": f"Tier inválido: {target_tier}"}), 400
    svc = PartnershipService.get_instance()
    try:
        result = svc.promote(partner_id, tier)
        if result.get("success"):
            return jsonify({"new_tier": result["new_tier"]})
        return jsonify({"error": result.get("error", "No se pudo promover")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/api/partners/tiers")
@login_required
def api_partners_tiers():
    """Get tier definitions with requirements and benefits."""
    from src.partnership import TIER_DEFINITIONS, PartnerTier
    definitions = {}
    for tier in PartnerTier:
        td = TIER_DEFINITIONS.get(tier, {})
        definitions[tier.value] = {
            "display_name": tier.value.capitalize(),
            "min_connectors": td.get("min_connectors", 0),
            "min_installs": td.get("min_installs", 0),
            "min_rating": td.get("min_rating", 0.0),
            "revenue_share": td.get("revenue_share_pct", 0) / 100.0,
            "benefits": [b.value for b in td.get("benefits", [])],
        }
    return jsonify({"definitions": definitions})


@bp.route("/api/partners/benefits", methods=["GET"])
@login_required
def api_partners_benefits_list():
    """List all partner benefits."""
    from src.partnership import PartnershipService
    svc = PartnershipService.get_instance()
    all_benefits = []
    try:
        pr = svc.list_partners()
        for p in pr.get("partners", []):
            pid = p.get("partner_id", "")
            if pid:
                all_benefits.extend(svc.get_partner_benefits(pid))
    except Exception:
        pass
    return jsonify({"benefits": all_benefits})


@bp.route("/api/partners/benefits", methods=["POST"])
@login_required
@require_role("editor")
def api_partners_create_benefit():
    """Create a new benefit for a partner."""
    from src.partnership import PartnerBenefitType, PartnershipService
    data = request.get_json() or {}
    partner_id = data.get("partner_id", "")
    name = data.get("name", "")
    if not partner_id or not name:
        return jsonify({"error": "partner_id y name son requeridos"}), 400
    svc = PartnershipService.get_instance()
    try:
        btype = PartnerBenefitType(name)
    except ValueError:
        btype = PartnerBenefitType.REVENUE_SHARE
    bid = svc._create_benefit(
        partner_id=partner_id,
        benefit_type=btype,
        description=data.get("description", ""),
        value=data.get("value", ""),
    )
    return jsonify({"benefit_id": bid}), 201


@bp.route("/api/partners/benefits/<benefit_id>/revoke", methods=["POST"])
@login_required
@require_role("admin")
def api_partners_revoke_benefit(benefit_id):
    """Revoke a benefit from a partner."""
    from src.partnership import PartnershipService
    svc = PartnershipService.get_instance()
    success = svc.revoke_benefit(benefit_id)
    if not success:
        return jsonify({"error": "Beneficio no encontrado"}), 404
    return jsonify({"status": "revoked"})


@bp.route("/api/partners/activity")
@login_required
def api_partners_activity():
    """Get partner activity timeline."""
    from src.partnership import PartnershipService
    svc = PartnershipService.get_instance()
    all_activities = []
    try:
        pr = svc.list_partners()
        for p in pr.get("partners", []):
            pid = p.get("partner_id", "")
            if pid:
                all_activities.extend(svc.get_activities(pid, limit=20))
        all_activities.sort(key=lambda a: a.get("performed_at", ""), reverse=True)
    except Exception:
        pass
    return jsonify({"activities": all_activities[:50]})
