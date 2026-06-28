"""
API v2 router para Fiscal Dispatcher — Facturación electrónica LATAM.

Endpoints REST para emitir, cancelar, verificar y obtener PDF de
comprobantes fiscales en los 7 países LATAM soportados.

Todos los endpoints requieren header `X-License-Key` con la licencia
activa del tenant. El dispatcher valida que el tier tenga
`fiscal_electronic=True` (reseller o enterprise).

Rutas:
    POST   /api/v2/fiscal/issue              Emite comprobante
    GET    /api/v2/fiscal/status/{country}/{tracking_id}
                                              Verifica estado en gobierno
    POST   /api/v2/fiscal/cancel              Cancela/anula comprobante
    GET    /api/v2/fiscal/pdf/{country}/{tracking_id}
                                              Descarga PDF (base64)
    GET    /api/v2/fiscal/countries           Lista países soportados

# Audience: External + SPA (FacturacionElectronicaPage)
# Purpose: Facturación electrónica LATAM (AFIP, SAT, SEFAZ, SII, DIAN, SUNAT, SRI). Usado por FacturacionElectronicaPage + integraciones externas.
"""

from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from src.hat.level5_tools.business.invoice.fiscal_dispatcher import (
    FiscalDispatcher,
    SUPPORTED_COUNTRIES,
)
from src.license.validator import LicenseValidator
from typing import Any

router = APIRouter(prefix="/api/v2/fiscal", tags=["fiscal"])

_dispatcher = FiscalDispatcher()
_license_validator = LicenseValidator()


# ── Models ───────────────────────────────────────────────────────────

class FiscalIssueRequest(BaseModel):
    """Body para POST /issue — emisión de comprobante fiscal."""
    country: str = Field(..., description="ISO-3166-1 alpha-2 (AR, MX, BR, CL, CO, PE, EC)")
    action_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parámetros específicos del país y operación (emisor, receptor, items, etc.)",
    )
    credentials: dict[str, Any] = Field(
        default_factory=dict,
        description="Credenciales del connector (cuit/rfc/cert_path/cert_password/ambiente).",
    )


class FiscalCancelRequest(BaseModel):
    """Body para POST /cancel — cancelación de comprobante."""
    country: str
    tracking_id: str = Field(..., description="CAE/UUID/CUFE/chave/TrackId del comprobante")
    motivo: str = Field(default="", description="Motivo de cancelación (requerido por algunos países)")
    credentials: dict[str, Any] = Field(default_factory=dict)


class FiscalResponse(BaseModel):
    """Respuesta estandarizada FiscalResult."""
    success: bool
    country: str
    action: str
    country_tracking_id: str = ""
    xml: str = ""
    pdf_base64: str = ""
    government_response: dict[str, Any] = {}
    reject_code: str = ""
    reject_message: str = ""
    error: str = ""
    dispatched_at: str = ""


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_license_type(x_license_key: str | None) -> str:
    """Resuelve el license_type desde el header X-License-Key.

    Si el header no está presente o la key es inválida, retorna "trial"
    (que no tiene fiscal_electronic → el dispatcher rechazará).
    """
    if not x_license_key:
        return "trial"
    try:
        result = _license_validator.validate(x_license_key)
        return result.get("type", "trial") if result.get("valid") else "trial"
    except Exception:
        return "trial"


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/countries")
async def list_supported_countries() -> dict[str, Any]:
    """Lista los países LATAM soportados y los disponibles actualmente."""
    available = _dispatcher.supported_countries()
    return {
        "supported": SUPPORTED_COUNTRIES,
        "available": available,
        "unavailable": [c for c in SUPPORTED_COUNTRIES if c not in available],
    }


@router.post("/issue", response_model=FiscalResponse)
async def issue_fiscal(
    req: FiscalIssueRequest,
    x_license_key: str | None = Header(default=None, alias="X-License-Key"),
) -> FiscalResponse:
    """Emite un comprobante fiscal electrónico en el país especificado.

    Requiere tier `reseller` o `enterprise` (fiscal_electronic=True).
    """
    license_type = _resolve_license_type(x_license_key)
    result = _dispatcher.dispatch(
        country=req.country,
        action="issue",
        params=req.action_params,
        license_type=license_type,
        credentials=req.credentials,
    )
    return FiscalResponse(**result)


@router.get("/status/{country}/{tracking_id}", response_model=FiscalResponse)
async def get_fiscal_status(
    country: str,
    tracking_id: str,
    x_license_key: str | None = Header(default=None, alias="X-License-Key"),
) -> FiscalResponse:
    """Verifica el estado de un comprobante fiscal en el gobierno del país."""
    license_type = _resolve_license_type(x_license_key)
    # Para verify necesitamos credenciales — se esperan en query params como dict codificado
    # En producción esto vendría del vault del tenant; aquí aceptamos header X-Fiscal-Creds
    # como JSON string para tests.
    result = _dispatcher.dispatch(
        country=country,
        action="verify",
        params={"tracking_id": tracking_id},
        license_type=license_type,
        credentials={},  # El connector debe resolver creds desde config del tenant
    )
    return FiscalResponse(**result)


@router.post("/cancel", response_model=FiscalResponse)
async def cancel_fiscal(
    req: FiscalCancelRequest,
    x_license_key: str | None = Header(default=None, alias="X-License-Key"),
) -> FiscalResponse:
    """Cancela/anula un comprobante fiscal emitido previamente."""
    license_type = _resolve_license_type(x_license_key)
    result = _dispatcher.dispatch(
        country=req.country,
        action="cancel",
        params={
            "tracking_id": req.tracking_id,
            "motivo": req.motivo,
        },
        license_type=license_type,
        credentials=req.credentials,
    )
    return FiscalResponse(**result)


@router.get("/pdf/{country}/{tracking_id}", response_model=FiscalResponse)
async def get_fiscal_pdf(
    country: str,
    tracking_id: str,
    x_license_key: str | None = Header(default=None, alias="X-License-Key"),
) -> FiscalResponse:
    """Obtiene el PDF (base64) de un comprobante fiscal."""
    license_type = _resolve_license_type(x_license_key)
    result = _dispatcher.dispatch(
        country=country,
        action="get_pdf",
        params={"tracking_id": tracking_id},
        license_type=license_type,
        credentials={},
    )
    return FiscalResponse(**result)
