"""
HAT-ORBITAL API v2 — Routes.

Endpoint FastAPI v2 para HAT. Recibe requests del usuario y delega al
HATRouter del Nivel 0.

Implementado en F0-D7.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.logging import setup_logging

logger = setup_logging(__name__)

router = APIRouter(prefix="/api/hat", tags=["hat"])


class HATRequest(BaseModel):
    """Request del endpoint /chat."""

    user_id: str = Field(..., description="ID del usuario", min_length=1)
    session_id: str = Field(..., description="ID de la sesión", min_length=1)
    message: str = Field(..., description="Mensaje del usuario", min_length=1)
    context: dict[str, object] = Field(
        default_factory=dict, description="Contexto adicional opcional",
    )


class HATResponse(BaseModel):
    """Response del endpoint /chat."""

    dispatch_id: str = Field(..., description="ID único del despacho")
    domain: str = Field(..., description="Dominio ganador (research/build/operate/clarify)")
    response: str = Field(..., description="Texto de respuesta al usuario")
    orbital_resonance: float = Field(..., description="Resonancia ORBITAL final [0, 1]")
    anti_dup_layer_hit: str = Field(..., description="Capa anti-doble-llamada activada")
    duration_ms: int = Field(..., description="Duración total en ms")
    facts_updated: list[str] = Field(
        default_factory=list, description="Facts actualizados en el Ledger",
    )
    status: str = Field(..., description="Estado final (completed/failed/clarify)")


@router.post("/chat", response_model=HATResponse)
async def chat(request: HATRequest) -> HATResponse:
    """Endpoint principal HAT.

    Procesa el mensaje del usuario a través del HATRouter singleton:
    1. Calcula intent_hash (anti-doble capa 1+2)
    2. Carga sesión del Ledger
    3. Ruteo por resonancia ORBITAL
    4. FSM desambiguación si necesario
    5. Despacha al supervisor del dominio ganador
    6. Persiste + sintetiza respuesta

    M8 hardening: usa ``get_hat_router()`` singleton en vez de instanciar
    ``HATRouter()`` en cada request — evita crear Ledgers/Contextos
    duplicados y reduce latencia.

    Args:
        request: HATRequest con user_id, session_id, message y context opcional.

    Returns:
        HATResponse con la respuesta sintetizada.

    Raises:
        HTTPException 400: Si el request es inválido (ValueError).
        HTTPException 500: Si el HATRouter falla internamente.
    """
    try:
        # M8 hardening: singleton HATRouter via get_hat_router()
        # evita instanciar en cada request (LedgerRepository, OrbitalContext, etc.)
        from src.hat.bootstrap import get_hat_router

        logger.info("HAT chat request: user=%s, session=%s, message=%.80s",
                     request.user_id, request.session_id, request.message)

        router_instance = get_hat_router()
        result = router_instance.handle(
            user_id=request.user_id,
            session_id=request.session_id,
            message=request.message,
            context=request.context,
        )

        logger.info("HAT chat response: user=%s, dispatch=%.12s, domain=%s, status=%s, duration=%dms",
                     request.user_id, result.get("dispatch_id", "?"),
                     result.get("domain", "?"), result.get("status", "?"),
                     result.get("duration_ms", 0))
        return HATResponse(**result)
    except ValueError as exc:
        logger.error("HAT chat ValueError: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise  # Re-raise HTTPExceptions sin envolver
    except Exception as exc:
        logger.exception("HAT chat unexpected error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Error interno HAT: {exc}",
        ) from exc


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check del endpoint HAT."""
    logger.debug("Health check called")
    return {"status": "ok", "module": "hat", "version": "f0-d7"}
