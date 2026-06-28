"""
Workflow Determinista — WhatsApp Business Integration (Phase 0)

Integra con Meta Cloud API (WhatsApp Business) para:
- Enviar mensajes de texto
- Enviar mensajes con plantillas
- Enviar mensajes multimedia (imagen, documento, video)
- Recibir mensajes vía webhook (verificar + procesar)
- Rastrear estado de mensajes (sent, delivered, read)
- Verificar conexión y estado

Autenticación: Phone Number ID + Access Token (guardados en DB)
"""

import hashlib
import hmac
import time
from typing import Any

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

WHATSAPP_API = "https://graph.facebook.com/v18.0"
try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

# Rate limit: WhatsApp Cloud API permite ~80 mensajes/minuto
_RATE_LIMIT_WINDOW = 60  # segundos
_RATE_LIMIT_MAX = 75  # conservador por debajo de 80
_rate_limit_tracker: dict[str, list[float]] = {}


def _check_rate_limit(key: str = "default") -> bool:
    """Verifica rate limiting por ventana deslizante."""
    now = time.time()
    if key not in _rate_limit_tracker:
        _rate_limit_tracker[key] = []
    _rate_limit_tracker[key] = [t for t in _rate_limit_tracker[key] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_tracker[key]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_tracker[key].append(now)
    return True


class WhatsAppService:
    """Servicio de integración con WhatsApp Business Cloud API."""

    def __init__(self) -> None:
        self._db = DatabaseManager()

    # ── Acciones principales ──────────────────────────────

    def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
    ) -> dict[str, Any]:
        """
        Envía un mensaje de texto vía WhatsApp.

        Args:
            to: Número de teléfono destino (formato internacional, ej: "5215512345678")
            text: Texto del mensaje (max 4096 chars)
            preview_url: Si True, genera preview de URLs en el mensaje

        Returns:
            dict con: status, message_id, to
        """
        phone_number_id, access_token = self._get_credentials()
        if not phone_number_id or not access_token:
            return {"status": "error", "message": "WhatsApp no configurado. Ve a Configuración → Integraciones."}

        if not to:
            return {"status": "error", "message": "El número destino es requerido"}

        if not text:
            return {"status": "error", "message": "El mensaje no puede estar vacío"}

        if len(text) > 4096:
            text = text[:4093] + "..."

        if not _check_rate_limit("send"):
            return {"status": "error", "message": "Rate limit alcanzado. Intenta de nuevo en un momento."}

        try:
            url = f"{WHATSAPP_API}/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": text, "preview_url": preview_url},
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            if "messages" in data:
                msg_id = data["messages"][0].get("id", "")
                logger.info(f"WhatsApp: Mensaje de texto enviado a {to}")
                return {
                    "status": "sent",
                    "to": to,
                    "message_id": msg_id,
                }
            else:
                error = data.get("error", {}).get("message", "Error desconocido")
                error_code = data.get("error", {}).get("code", 0)
                logger.error(f"WhatsApp error enviando a {to}: {error} (code: {error_code})")
                return {"status": "failed", "error": error, "error_code": error_code}

        except Exception as e:
            logger.error(f"WhatsApp exception: {e}")
            return {"status": "failed", "error": str(e)}

    def send_template_message(
        self,
        to: str,
        template_name: str,
        language: str = "en",
        components: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Envía un mensaje con plantilla (template) vía WhatsApp.

        Las plantillas deben estar pre-aprobadas en Meta Business Manager.

        Args:
            to: Número de teléfono destino
            template_name: Nombre de la plantilla aprobada
            language: Código de idioma (ej: "en", "es")
            components: Componentes de la plantilla (header, body, button)

        Returns:
            dict con: status, message_id, to
        """
        phone_number_id, access_token = self._get_credentials()
        if not phone_number_id or not access_token:
            return {"status": "error", "message": "WhatsApp no configurado"}

        if not to or not template_name:
            return {"status": "error", "message": "Número destino y nombre de plantilla son requeridos"}

        if not _check_rate_limit("send"):
            return {"status": "error", "message": "Rate limit alcanzado"}

        try:
            url = f"{WHATSAPP_API}/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            template_payload: dict[str, Any] = {
                "name": template_name,
                "language": {"code": language},
            }
            if components:
                template_payload["components"] = components

            payload: dict[str, Any] = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "template",
                "template": template_payload,
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            if "messages" in data:
                msg_id = data["messages"][0].get("id", "")
                logger.info(f"WhatsApp: Template '{template_name}' enviado a {to}")
                return {
                    "status": "sent",
                    "to": to,
                    "message_id": msg_id,
                    "template_name": template_name,
                }
            else:
                error = data.get("error", {}).get("message", "Error desconocido")
                error_code = data.get("error", {}).get("code", 0)
                logger.error(f"WhatsApp template error a {to}: {error}")
                return {"status": "failed", "error": error, "error_code": error_code}

        except Exception as e:
            logger.error(f"WhatsApp send_template exception: {e}")
            return {"status": "failed", "error": str(e)}

    def send_media_message(
        self,
        to: str,
        media_type: str,
        media_url: str = "",
        media_id: str = "",
        caption: str = "",
        filename: str = "",
    ) -> dict[str, Any]:
        """
        Envía un mensaje multimedia (imagen, documento, video, audio) vía WhatsApp.

        Args:
            to: Número de teléfono destino
            media_type: Tipo de medio ("image", "document", "video", "audio", "sticker")
            media_url: URL del archivo multimedia (alternativa a media_id)
            media_id: ID del archivo subido previamente a WhatsApp (alternativa a media_url)
            caption: Pie de foto/descripción (no disponible para audio/sticker)
            filename: Nombre del archivo (solo para documentos)

        Returns:
            dict con: status, message_id, to
        """
        phone_number_id, access_token = self._get_credentials()
        if not phone_number_id or not access_token:
            return {"status": "error", "message": "WhatsApp no configurado"}

        if not to:
            return {"status": "error", "message": "El número destino es requerido"}

        valid_types = {"image", "document", "video", "audio", "sticker"}
        if media_type not in valid_types:
            return {"status": "error", "message": f"Tipo de medio inválido. Válidos: {', '.join(sorted(valid_types))}"}

        if not media_url and not media_id:
            return {"status": "error", "message": "Proporciona media_url o media_id"}

        if not _check_rate_limit("send"):
            return {"status": "error", "message": "Rate limit alcanzado"}

        try:
            url = f"{WHATSAPP_API}/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            media_obj: dict[str, Any] = {}
            if media_id:
                media_obj["id"] = media_id
            else:
                media_obj["link"] = media_url
            if caption and media_type not in ("audio", "sticker"):
                media_obj["caption"] = caption
            if filename and media_type == "document":
                media_obj["filename"] = filename

            payload: dict[str, Any] = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": media_type,
                media_type: media_obj,
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            data = resp.json()

            if "messages" in data:
                msg_id = data["messages"][0].get("id", "")
                logger.info(f"WhatsApp: Mensaje {media_type} enviado a {to}")
                return {
                    "status": "sent",
                    "to": to,
                    "message_id": msg_id,
                    "media_type": media_type,
                }
            else:
                error = data.get("error", {}).get("message", "Error desconocido")
                error_code = data.get("error", {}).get("code", 0)
                logger.error(f"WhatsApp media error a {to}: {error}")
                return {"status": "failed", "error": error, "error_code": error_code}

        except Exception as e:
            logger.error(f"WhatsApp send_media exception: {e}")
            return {"status": "failed", "error": str(e)}

    # ── Webhook ───────────────────────────────────────────

    def verify_webhook(self, mode: str, challenge: str, verify_token: str) -> dict[str, Any]:
        """
        Verifica el webhook de WhatsApp (Meta verification flow).

        Args:
            mode: hub.mode recibido (debe ser "subscribe")
            challenge: hub.challenge recibido (retornar para verificar)
            verify_token: hub.verify_token recibido (debe coincidir con el configurado)

        Returns:
            dict con: status, challenge (si verificación exitosa)
        """
        expected_token = self._db.get_setting("whatsapp_verify_token") or None

        if not expected_token:
            logger.warning("WhatsApp: verify_token no configurado")
            return {"status": "error", "message": "Webhook no configurado"}

        if mode == "subscribe" and verify_token == expected_token:
            logger.info("WhatsApp: Webhook verificado exitosamente")
            return {"status": "ok", "challenge": challenge}
        else:
            logger.warning("WhatsApp: Verificación de webhook fallida")
            return {"status": "error", "message": "Verificación fallida: token o modo inválido"}

    def process_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Procesa un payload de webhook entrante de WhatsApp.

        Extrae mensajes y estados de los mensajes del payload.

        Args:
            payload: Payload JSON completo del webhook

        Returns:
            dict con: status, messages[], statuses[]
        """
        messages: list[dict] = []
        statuses: list[dict] = []

        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    # Procesar mensajes entrantes
                    for msg in value.get("messages", []):
                        msg_info = {
                            "message_id": msg.get("id", ""),
                            "from": msg.get("from", ""),
                            "timestamp": msg.get("timestamp", ""),
                            "type": msg.get("type", ""),
                        }
                        # Extraer contenido según tipo
                        msg_type = msg.get("type", "")
                        if msg_type == "text":
                            msg_info["text"] = msg.get("text", {}).get("body", "")
                        elif msg_type in ("image", "document", "video", "audio"):
                            msg_info["media"] = msg.get(msg_type, {})
                        elif msg_type == "location":
                            msg_info["location"] = msg.get("location", {})
                        elif msg_type == "contacts":
                            msg_info["contacts"] = msg.get("contacts", [])

                        messages.append(msg_info)

                    # Procesar estados de mensajes
                    for status in value.get("statuses", []):
                        status_info = {
                            "message_id": status.get("id", ""),
                            "status": status.get("status", ""),  # sent, delivered, read
                            "timestamp": status.get("timestamp", ""),
                            "recipient_id": status.get("recipient_id", ""),
                        }
                        if status.get("errors"):
                            status_info["errors"] = status["errors"]
                        statuses.append(status_info)

            result: dict[str, Any] = {
                "status": "ok",
                "messages": messages,
                "statuses": statuses,
            }

            if messages:
                logger.info(f"WhatsApp: {len(messages)} mensaje(s) entrante(s) procesados")
            if statuses:
                logger.info(f"WhatsApp: {len(statuses)} actualización(es) de estado procesadas")

            return result

        except Exception as e:
            logger.error(f"WhatsApp process_webhook exception: {e}")
            return {"status": "error", "message": str(e)}

    def verify_webhook_signature(self, payload_body: bytes, signature: str) -> bool:
        """
        Verifica la firma HMAC-SHA256 del webhook de WhatsApp.

        Args:
            payload_body: Cuerpo raw del request (bytes)
            signature: Header X-Hub-Signature-256 (formato: "sha256=<hex>")

        Returns:
            True si la firma es válida, False en caso contrario
        """
        app_secret = self._db.get_setting("whatsapp_app_secret") or None
        if not app_secret:
            logger.warning("WhatsApp: app_secret no configurado, no se puede verificar firma")
            return False

        if not signature or not signature.startswith("sha256="):
            return False

        expected_sig = hmac.new(
            app_secret.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        received_sig = signature.removeprefix("sha256=")

        return hmac.compare_digest(expected_sig, received_sig)

    # ── Configuración ─────────────────────────────────────

    def configure(self, phone_number_id: str, access_token: str, verify_token: str = "", app_secret: str = "") -> bool:
        """
        Guarda las credenciales de WhatsApp Business.

        Args:
            phone_number_id: ID del número de teléfono (desde Meta Business Manager)
            access_token: Token de acceso de la aplicación
            verify_token: Token de verificación del webhook (configurado en Meta)
            app_secret: App Secret para verificar firmas de webhook

        Returns:
            True si se guardaron correctamente
        """
        self._db.set_setting("whatsapp_phone_number_id", phone_number_id)
        self._db.set_setting("whatsapp_access_token", access_token)
        if verify_token:
            self._db.set_setting("whatsapp_verify_token", verify_token)
        if app_secret:
            self._db.set_setting("whatsapp_app_secret", app_secret)
        logger.info("WhatsApp: Credenciales guardadas")
        return True

    def test_connection(self) -> dict[str, Any]:
        """
        Verifica la conexión con WhatsApp Business API.

        Returns:
            dict con: status, message, phone_number info
        """
        phone_number_id, access_token = self._get_credentials()
        if not phone_number_id or not access_token:
            return {"status": "error", "message": "WhatsApp no configurado"}

        try:
            url = f"{WHATSAPP_API}/{phone_number_id}"
            headers = {"Authorization": f"Bearer {access_token}"}
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()

            if "verified_name" in data or "display_phone_number" in data:
                display_name = data.get("verified_name", data.get("display_phone_number", "Conectado"))
                display_number = data.get("display_phone_number", "")
                return {
                    "status": "ok",
                    "message": f"Conectado como {display_name}",
                    "verified_name": display_name,
                    "display_phone_number": display_number,
                    "quality_rating": data.get("quality_rating", ""),
                }
            else:
                error = data.get("error", {}).get("message", "Token o Phone Number ID inválido")
                return {"status": "error", "message": error}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict[str, Any]:
        """Estado de la integración WhatsApp."""
        phone_number_id, access_token = self._get_credentials()
        verify_token = self._db.get_setting("whatsapp_verify_token") or None
        app_secret = self._db.get_setting("whatsapp_app_secret") or None
        return {
            "configured": bool(phone_number_id and access_token),
            "has_phone_number_id": bool(phone_number_id),
            "has_access_token": bool(access_token),
            "has_webhook_config": bool(verify_token),
            "has_signature_verification": bool(app_secret),
        }

    def _get_credentials(self) -> tuple[str | None, str | None]:
        """Obtiene las credenciales desde la DB."""
        phone_number_id = self._db.get_setting("whatsapp_phone_number_id") or None
        access_token = self._db.get_setting("whatsapp_access_token") or None
        return phone_number_id, access_token

    # ── Tool Definition ───────────────────────────────────

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "whatsapp",
            "name": "WhatsApp",
            "description": "Envía mensajes y plantillas vía WhatsApp Business",
            "actions": {
                "send_text_message": {
                    "name": "Enviar mensaje de texto",
                    "description": "Envía un mensaje de texto vía WhatsApp",
                    "params": [
                        {
                            "name": "to",
                            "type": "string",
                            "required": True,
                            "label": "Número destino",
                            "placeholder": "5215512345678",
                        },
                        {
                            "name": "text",
                            "type": "string",
                            "required": True,
                            "label": "Mensaje",
                            "placeholder": "Hola desde un workflow",
                        },
                        {
                            "name": "preview_url",
                            "type": "boolean",
                            "required": False,
                            "default": False,
                            "label": "Preview de URL",
                        },
                    ],
                },
                "send_template_message": {
                    "name": "Enviar plantilla",
                    "description": "Envía un mensaje usando una plantilla aprobada",
                    "params": [
                        {
                            "name": "to",
                            "type": "string",
                            "required": True,
                            "label": "Número destino",
                            "placeholder": "5215512345678",
                        },
                        {
                            "name": "template_name",
                            "type": "string",
                            "required": True,
                            "label": "Nombre de plantilla",
                            "placeholder": "hello_world",
                        },
                        {
                            "name": "language",
                            "type": "select",
                            "options": ["en", "es", "pt", "fr", "de"],
                            "required": False,
                            "default": "en",
                            "label": "Idioma",
                        },
                    ],
                },
                "send_media_message": {
                    "name": "Enviar multimedia",
                    "description": "Envía imagen, documento, video o audio",
                    "params": [
                        {
                            "name": "to",
                            "type": "string",
                            "required": True,
                            "label": "Número destino",
                            "placeholder": "5215512345678",
                        },
                        {
                            "name": "media_type",
                            "type": "select",
                            "options": ["image", "document", "video", "audio"],
                            "required": True,
                            "label": "Tipo de medio",
                        },
                        {
                            "name": "media_url",
                            "type": "string",
                            "required": True,
                            "label": "URL del archivo",
                            "placeholder": "https://ejemplo.com/imagen.jpg",
                        },
                        {
                            "name": "caption",
                            "type": "string",
                            "required": False,
                            "label": "Descripción",
                        },
                    ],
                },
            },
        }
