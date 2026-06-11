"""Compliance API Routes — REST endpoints for SOC 2 compliance management.

Provides HTTP API for:
- Compliance control management
- Evidence collection
- Audit trail queries
- Policy management
- Compliance scoring and reporting
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api_v2.dependencies import require_permission
from src.compliance import (
    ComplianceControl,
    ComplianceManager,
    ControlStatus,
    EvidenceType,
    PolicyDocument,
    TrustServiceCriteria,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/score", summary="Get compliance score")
async def get_compliance_score(
    _: Any = Depends(require_permission("compliance", "read")),
) -> dict[str, Any]:
    """Get the current SOC 2 compliance score with breakdown by criteria."""
    manager = ComplianceManager.get_instance()
    return manager.calculate_compliance_score()


@router.get("/report", summary="Generate compliance report")
async def generate_report(
    _: Any = Depends(require_permission("compliance", "read")),
) -> dict[str, Any]:
    """Generate a comprehensive SOC 2 Type I compliance report."""
    manager = ComplianceManager.get_instance()
    return manager.generate_report()


# ── Controls ────────────────────────────────────────────────


@router.get("/controls", summary="List compliance controls")
async def list_controls(
    criteria: str | None = Query(None, description="Filter by TSC criteria"),
    status: str | None = Query(None, description="Filter by status"),
    risk_level: str | None = Query(None, description="Filter by risk level"),
    _: Any = Depends(require_permission("compliance", "read")),
) -> dict[str, Any]:
    """List SOC 2 compliance controls with optional filters."""
    manager = ComplianceManager.get_instance()
    filter_criteria = TrustServiceCriteria(criteria) if criteria else None
    filter_status = ControlStatus(status) if status else None
    controls = manager.list_controls(
        criteria=filter_criteria, status=filter_status, risk_level=risk_level
    )
    return {
        "controls": [
            {
                "control_id": c.control_id,
                "name": c.name,
                "ref_code": c.ref_code,
                "criteria": c.criteria.value,
                "status": c.status.value,
                "risk_level": c.risk_level,
                "evidence_count": len(c.evidence_ids),
                "last_tested": c.last_tested,
            }
            for c in controls
        ],
        "count": len(controls),
    }


@router.put("/controls/{control_id}/status", summary="Update control status")
async def update_control_status(
    control_id: str,
    status: str,
    notes: str = "",
    _: Any = Depends(require_permission("compliance", "update")),
) -> dict[str, Any]:
    """Update the status of a compliance control."""
    manager = ComplianceManager.get_instance()
    new_status = ControlStatus(status)
    success = manager.update_control_status(control_id, new_status, notes)
    if not success:
        raise HTTPException(status_code=404, detail=f"Control not found: {control_id}")
    return {"control_id": control_id, "status": status}


# ── Evidence ────────────────────────────────────────────────


@router.post("/evidence", summary="Collect compliance evidence")
async def collect_evidence(
    control_id: str,
    evidence_type: str,
    description: str,
    content: str,
    collected_by: str = "system",
    _: Any = Depends(require_permission("compliance", "create")),
) -> dict[str, Any]:
    """Collect evidence for a compliance control."""
    manager = ComplianceManager.get_instance()
    ev_type = EvidenceType(evidence_type)
    evidence = manager.collect_evidence(
        control_id=control_id,
        evidence_type=ev_type,
        description=description,
        content=content,
        collected_by=collected_by,
    )
    return {
        "evidence_id": evidence.evidence_id,
        "control_id": control_id,
        "type": evidence_type,
        "content_hash": evidence.content_hash,
        "verified": evidence.verified,
    }


# ── Audit Trail ─────────────────────────────────────────────


@router.get("/audit", summary="Query audit trail")
async def get_audit_trail(
    actor: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    limit: int = Query(100),
    _: Any = Depends(require_permission("compliance", "read")),
) -> dict[str, Any]:
    """Query the compliance audit trail."""
    manager = ComplianceManager.get_instance()
    entries = manager.get_audit_trail(
        actor=actor,
        action=action,
        resource_type=resource_type,
        limit=limit,
    )
    return {
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
        "count": len(entries),
    }


# ── Policies ────────────────────────────────────────────────


@router.get("/policies", summary="List compliance policies")
async def list_policies(
    category: str | None = Query(None),
    status: str | None = Query(None),
    _: Any = Depends(require_permission("compliance", "read")),
) -> dict[str, Any]:
    """List compliance policy documents."""
    manager = ComplianceManager.get_instance()
    policies = manager.list_policies(category=category, status=status)
    return {
        "policies": [
            {
                "policy_id": p.policy_id,
                "name": p.name,
                "category": p.category,
                "version": p.version,
                "status": p.status,
                "approved_by": p.approved_by,
            }
            for p in policies
        ],
        "count": len(policies),
    }


@router.post("/policies", summary="Create a compliance policy")
async def create_policy(
    name: str,
    category: str,
    content: str,
    version: str = "1.0",
    _: Any = Depends(require_permission("compliance", "create")),
) -> dict[str, Any]:
    """Create a new compliance policy document."""
    manager = ComplianceManager.get_instance()
    policy = PolicyDocument(
        name=name,
        category=category,
        content=content,
        version=version,
    )
    policy_id = manager.create_policy(policy)
    return {"policy_id": policy_id, "status": "created"}


@router.post("/policies/{policy_id}/approve", summary="Approve a policy")
async def approve_policy(
    policy_id: str,
    approved_by: str,
    _: Any = Depends(require_permission("compliance", "update")),
) -> dict[str, Any]:
    """Approve a compliance policy document."""
    manager = ComplianceManager.get_instance()
    success = manager.approve_policy(policy_id, approved_by)
    if not success:
        raise HTTPException(status_code=404, detail=f"Policy not found: {policy_id}")
    return {"policy_id": policy_id, "status": "approved"}


# ── Stats ───────────────────────────────────────────────────


@router.get("/stats", summary="Get compliance statistics")
async def get_compliance_stats(
    _: Any = Depends(require_permission("compliance", "read")),
) -> dict[str, Any]:
    """Get compliance manager statistics."""
    manager = ComplianceManager.get_instance()
    return manager.get_stats()
