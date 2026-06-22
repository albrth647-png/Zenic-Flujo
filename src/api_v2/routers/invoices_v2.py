"""API v2 router para Invoices — espejo de Flask."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.hat.level5_tools.business.invoice.service import InvoiceService

router = APIRouter(prefix="/api/v2/invoices", tags=["invoices"])

_svc = InvoiceService()


class InvoiceCreate(BaseModel):
    client_name: str
    client_email: str | None = None
    items: list[dict] = []
    tax_rate: float = 0.16
    discount: float = 0.0
    due_days: int = 30
    notes: str | None = None
    lead_id: int | None = None
    client_id: int | None = None
    currency: str = "MXN"


@router.get("/")
async def list_invoices(status: str | None = None, limit: int = Query(50, le=200)) -> list[dict]:
    return _svc.list_invoices(status=status, limit=limit)


@router.post("/", status_code=201)
async def create_invoice(inv: InvoiceCreate) -> dict:
    return _svc.create_invoice(**inv.model_dump())


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: int) -> dict:
    inv = _svc.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(404, "Factura no encontrada")
    return inv


@router.post("/{invoice_id}/mark-paid")
async def mark_paid(invoice_id: int) -> dict:
    inv = _svc.mark_paid(invoice_id)
    if not inv:
        raise HTTPException(404, "Factura no encontrada")
    return inv


@router.post("/{invoice_id}/cancel")
async def cancel_invoice(invoice_id: int) -> dict:
    inv = _svc.cancel(invoice_id)
    if not inv:
        raise HTTPException(404, "Factura no encontrada")
    return inv


@router.get("/overdue")
async def get_overdue() -> list[dict]:
    return _svc.get_overdue_invoices()


@router.get("/stats")
async def get_invoice_stats() -> dict:
    return _svc.get_stats()
