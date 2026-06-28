"""
API v2 router para WhatsApp — gestión de mensajería WhatsApp Business Cloud API.

# Audience: External + SPA (SettingsWhatsAppTab)
# Purpose: Envío de mensajes WhatsApp, gestión de templates, y test de webhook.
#           Expone la funcionalidad de WhatsAppConnector vía API REST para
#           integraciones externas (SDK, móvil, partners) y para el SPA.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.connectors.whatsapp import WhatsAppConnector

router = APIRouter(prefix="/api/v2/whatsapp", tags=["whatsapp"])


# ── Schemas ──────────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    """Request para enviar un mensaje de texto WhatsApp."""
    to: str = Field(..., description="Número de teléfono destino (formato internacional sin +, ej: 521234567890)")
    text: str = Field(..., description="Texto del mensaje")
    preview_url: bool = Field(False, description="Si true, genera preview de URLs en el mensaje")


class SendTemplateRequest(BaseModel):
    """Request para enviar un mensaje template WhatsApp."""
    to: str = Field(..., description="Número destino")
    template_name: str = Field(..., description="Nombre del template aprobado en Meta")
    language: str = Field("es_MX", description="Código de idioma del template")
    components: list[dict[str, Any]] = Field(default_factory=list, description="Componentes del template")


class SendMediaRequest(BaseModel):
    """Request para enviar un mensaje con media WhatsApp."""
    to: str = Field(..., description="Número destino")
    media_type: str = Field(..., description="image | document | audio | video")
    media_url: str = Field(..., description="URL pública del media")
    caption: str = Field("", description="Caption opcional")


class WebhookTestRequest(BaseModel):
    """Request para simular un webhook de WhatsApp entrante (testing)."""
    from_phone: str = Field(..., description="Número remitente simulado")
    text: str = Field(..., description="Texto del mensaje simulado")


# ── Helper: obtener connector ────────────────────────────────────────────


def _get_connector() -> WhatsAppConnector:
    """Obtiene una instancia de WhatsAppConnector.

    En producción, las credenciales vienen de la configuración del tenant.
    Aquí usamos la configuración global por simplicidad.
    """
    try:
        return WhatsAppConnector()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"WhatsAppConnector no disponible: {e}") from e


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/send")
async def send_message(req: SendMessageRequest) -> dict[str, Any]:
    """Enviar un mensaje de texto WhatsApp.

    Requiere que WhatsApp esté configurado (credenciales en settings).
    Respeta la cuota del tier de licencia (trial: 10/mes).
    """
    connector = _get_connector()
    result = connector.execute("send_text_message", {
        "to": req.to,
        "text": req.text,
        "preview_url": req.preview_url,
    })
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/send-template")
async def send_template(req: SendTemplateRequest) -> dict[str, Any]:
    """Enviar un mensaje template WhatsApp (template aprobado en Meta)."""
    connector = _get_connector()
    result = connector.execute("send_template_message", {
        "to": req.to,
        "template_name": req.template_name,
        "language": req.language,
        "components": req.components,
    })
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/send-media")
async def send_media(req: SendMediaRequest) -> dict[str, Any]:
    """Enviar un mensaje con media (imagen, documento, audio, video) WhatsApp."""
    connector = _get_connector()
    result = connector.execute("send_media_message", {
        "to": req.to,
        "media_type": req.media_type,
        "media_url": req.media_url,
        "caption": req.caption,
    })
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/templates")
async def list_templates() -> dict[str, Any]:
    """Listar los templates de workflow que usan WhatsApp.

    Incluye templates de salida (notificaciones) y de entrada (trigger
    whatsapp.message.received) — ver Feature 6 en autopilot/templates.py.
    """
    try:
        from src.hat.level5_tools.automation.autopilot.templates import TEMPLATES
        whatsapp_templates = [
            {
                "name": t["name"],
                "label": t["label"],
                "description": t.get("description_es", ""),
                "trigger": t.get("trigger", {}),
                "is_inbound": t.get("trigger", {}).get("config", {}).get("event") == "whatsapp.message.received",
            }
            for t in TEMPLATES
            if any(
                step.get("tool") == "whatsapp"
                or step.get("trigger", {}).get("config", {}).get("event", "").startswith("whatsapp")
                for step in t.get("steps", [])
            )
            or t.get("trigger", {}).get("config", {}).get("event", "").startswith("whatsapp")
        ]
        return {
            "total": len(whatsapp_templates),
            "inbound": sum(1 for t in whatsapp_templates if t["is_inbound"]),
            "outbound": sum(1 for t in whatsapp_templates if not t["is_inbound"]),
            "templates": whatsapp_templates,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listando templates: {e}") from e


@router.post("/webhook-test")
async def webhook_test(req: WebhookTestRequest) -> dict[str, Any]:
    """Simular un webhook de WhatsApp entrante para testing.

    Publica un evento `whatsapp.message.received` en el EventBus para probar
    los templates de entrada (Feature 6) sin necesidad de un webhook real de Meta.
    Útil para desarrollo y QA.
    """
    try:
        from src.events.bus import EventBus
        # Crear un bus efímero para el test. En producción, el webhook real
        # usa el bus compartido vía current_app.config["event_bus"] (BUG-3 fix).
        bus = EventBus()
        msg = {
            "from": req.from_phone,
            "text": req.text,
            "timestamp": "2026-06-22T00:00:00Z",
            "message_id": f"test_{req.from_phone}_{hash(req.text) & 0xFFFFFFFF}",
        }
        bus.publish("whatsapp.message.received", msg)
        return {
            "success": True,
            "message": "Evento whatsapp.message.received publicado (bus efímero de test)",
            "published_event": msg,
            "note": "En producción, este evento se publica en el bus compartido y los subscribers del PymeOrchestrator + templates de entrada lo reciben.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en webhook-test: {e}") from e


@router.get("/status")
async def whatsapp_status() -> dict[str, Any]:
    """Estado de la configuración de WhatsApp.

    Indica si las credenciales están configuradas y qué versión de API se usa.
    """
    connector = _get_connector()
    is_valid = connector.validate()
    return {
        "configured": is_valid,
        "api_version": "v22.0",
        "api_base": "https://graph.facebook.com/v22.0",
        "actions_available": ["send_text_message", "send_template_message", "send_media_message", "test_connection"],
    }
