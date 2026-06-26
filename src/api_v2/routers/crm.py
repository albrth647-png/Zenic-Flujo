"""
API v2 router para CRM — espejo de Flask /api/tools/crm/*.

# Audience: External + SPA (MiNegocioPage usa /stats)
# Purpose: CRM stats (usado por MiNegocioPage) + CRUD clients/leads para integraciones externas.
"""

from __future__ import annotations


from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.hat.level5_tools.business.crm.service import CRMService

router = APIRouter(prefix="/api/v2/crm", tags=["crm"])

_svc = CRMService()


class LeadCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    source: str = "manual"
    notes: str | None = None


class LeadUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    stage: str | None = None
    notes: str | None = None


class ClientCreate(BaseModel):
    name: str
    fiscal_type: str = ""
    fiscal_id: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    country_code: str = "MX"
    currency: str = "MXN"
    lead_id: int | None = None


@router.get("/leads")
async def list_leads(
    stage: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return _svc.list_leads(stage=stage, limit=limit, offset=offset)


@router.post("/leads", status_code=201)
async def create_lead(lead: LeadCreate) -> dict:
    return _svc.create_lead(
        name=lead.name, email=lead.email, phone=lead.phone,
        company=lead.company, source=lead.source, notes=lead.notes,
    )


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: int) -> dict:
    lead = _svc.get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    return lead


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: int, updates: LeadUpdate) -> dict:
    lead = _svc.update_lead(lead_id, **updates.model_dump(exclude_none=True))
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    return lead


@router.delete("/leads/{lead_id}", status_code=204)
async def delete_lead(lead_id: int) -> None:
    if not _svc.delete_lead(lead_id):
        raise HTTPException(404, "Lead no encontrado")


@router.post("/leads/{lead_id}/advance")
async def advance_stage(lead_id: int) -> dict:
    lead = _svc.advance_stage(lead_id)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    return lead


@router.post("/leads/{lead_id}/convert-to-invoice")
async def convert_lead_to_invoice(lead_id: int, items: list[dict]) -> dict:
    """Convierte un Lead closed_won en Invoice con items."""
    lead = _svc.get_lead(lead_id)
    if not lead:
        raise HTTPException(404, "Lead no encontrado")
    from src.hat.level5_tools.business.invoice.service import InvoiceService
    return InvoiceService().create_invoice(
        client_name=lead["name"],
        client_email=lead.get("email"),
        client_phone=lead.get("phone"),
        items=items,
        lead_id=lead_id,
    )


# ── Clients ──────────────────────────────────────────────────────────

@router.get("/clients")
async def list_clients(limit: int = Query(50, le=200), offset: int = Query(0, ge=0)) -> list[dict]:
    return _svc.list_clients(limit=limit, offset=offset)


@router.post("/clients", status_code=201)
async def create_client(client: ClientCreate) -> dict:
    return _svc.create_client(**client.model_dump())


@router.get("/clients/{client_id}")
async def get_client(client_id: int) -> dict:
    client = _svc.get_client(client_id)
    if not client:
        raise HTTPException(404, "Cliente no encontrado")
    return client


@router.get("/stats")
async def get_crm_stats() -> dict:
    return _svc.get_stats()
