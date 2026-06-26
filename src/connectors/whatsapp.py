"""
Conector WhatsApp Business — Cloud API de Meta
================================================

Permite enviar mensajes de texto, plantillas y multimedia via
WhatsApp Business Cloud API de Meta.

Acciones:
- send_text_message: Enviar mensaje de texto
- send_template_message: Enviar plantilla aprobada
- send_media_message: Enviar imagen, documento, video o audio
- test_connection: Verificar conexión con la API

Autenticación: Access Token + Phone Number ID
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)

# BUG-1 fix: unificado a v22.0 (antes v18.0 aquí y v22.0 en NotificationService,
# lo que causaba dos implementaciones paralelas con versiones distintas).
# v22.0 es la versión más reciente de Meta Cloud API.
WHATSAPP_API_BASE = "https://graph.facebook.com/v22.0"


class WhatsAppConnector(BaseConnector):
    """Conector para WhatsApp Business Cloud API de Meta."""

    name = "whatsapp"
    version = "1.0.0"
    description = "Envía mensajes de texto, plantillas y multimedia via WhatsApp Business"
    category = "communication"
    icon = "message-circle"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._phone_number_id: str = ""
        self._access_token: str = ""
        self._verify_token: str = ""
        self._app_secret: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de WhatsApp Business.

        Requiere Phone Number ID y Access Token de Meta Business Manager.
        """
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("WhatsAppConnector: credenciales no configuradas")
            return False

        # Extraer credenciales del auth provider
        self._phone_number_id = ""
        self._access_token = ""
        self._verify_token = ""
        self._app_secret = ""

        if hasattr(self._auth_provider, "_credentials"):
            creds = self._auth_provider._credentials
            self._phone_number_id = creds.get("phone_number_id", "")
            self._access_token = creds.get("access_token", "")
            self._verify_token = creds.get("verify_token", "")
            self._app_secret = creds.get("app_secret", "")

        if not self._phone_number_id:
            logger.error("WhatsAppConnector: phone_number_id es requerido")
            return False

        if not self._access_token:
            logger.error("WhatsAppConnector: access_token es requerido")
            return False

        # Configurar HTTP client con auth Bearer
        self._http = HttpClient(
            base_url=f"{WHATSAPP_API_BASE}/{self._phone_number_id}",
            connector_name=self.name,
        )
        self._http.set_header("Authorization", f"Bearer {self._access_token}")

        # Verificar conexion con un GET al perfil
        try:
            resp = self._http.get("")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"phone={self._phone_number_id[:6]}...")
                return True
            else:
                error_data = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
                err_msg = error_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                logger.error(f"WhatsAppConnector: conexion fallida: {err_msg}")
                return False
        except HTTPClientError as e:
            logger.error(f"WhatsAppConnector: error de conexion: {e}")
            return False
        except Exception as e:
            logger.error(f"WhatsAppConnector: error inesperado: {e}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector WhatsApp.

        Args:
            action: Nombre de la accion
            params: Parametros de la accion

        Returns:
            Resultado de la accion ejecutada
        """
        action_map: dict[str, Any] = {
            "send_text_message": self._send_text_message,
            "send_template_message": self._send_template_message,
            "send_media_message": self._send_media_message,
            "test_connection": self._test_connection,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de WhatsApp esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con WhatsApp API."""
        self._connected = False
        self._phone_number_id = ""
        self._access_token = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    # ── Acciones ─────────────────────────────────────────────

    def _send_text_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envía un mensaje de texto via WhatsApp.

        Args:
            params: Debe contener 'to' y 'text'. Opcional: 'preview_url'
        """
        to = params.get("to", "")
        text = params.get("text", "")
        preview_url = params.get("preview_url", False)

        if not to or not text:
            return {"success": False, "error": "Parametros requeridos: to, text"}

        self._log_operation("send_text", f"to={to}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"body": text, "preview_url": preview_url},
            }

            response = self._http.post("/messages", json=payload)

            if response.ok:
                data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                messages = data.get("messages", [])
                msg_id = messages[0].get("id", "") if messages else ""
                return {
                    "success": True,
                    "message_id": msg_id,
                    "to": to,
                    "status": "sent",
                }
            else:
                error_data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "error_code": error_info.get("code"),
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _send_template_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envía un mensaje con plantilla aprobada via WhatsApp.

        Args:
            params: Debe contener 'to' y 'template_name'. Opcional: 'language', 'components'
        """
        to = params.get("to", "")
        template_name = params.get("template_name", "")
        language = params.get("language", "en")
        components = params.get("components", [])

        if not to or not template_name:
            return {"success": False, "error": "Parametros requeridos: to, template_name"}

        self._log_operation("send_template", f"to={to}, template={template_name}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            template_payload = {
                "name": template_name,
                "language": {"code": language},
            }
            if components:
                template_payload["components"] = components

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "template",
                "template": template_payload,
            }

            response = self._http.post("/messages", json=payload)

            if response.ok:
                data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                messages = data.get("messages", [])
                msg_id = messages[0].get("id", "") if messages else ""
                return {
                    "success": True,
                    "message_id": msg_id,
                    "to": to,
                    "template_name": template_name,
                    "status": "sent",
                }
            else:
                error_data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "error_code": error_info.get("code"),
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _send_media_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envía un mensaje multimedia via WhatsApp.

        Args:
            params: Debe contener 'to', 'media_type' y 'media_url' o 'media_id'.
                    Opcional: 'caption', 'filename'
        """
        to = params.get("to", "")
        media_type = params.get("media_type", "")
        media_url = params.get("media_url", "")
        media_id = params.get("media_id", "")
        caption = params.get("caption", "")
        filename = params.get("filename", "")

        if not to:
            return {"success": False, "error": "Parametro requerido: to"}

        valid_types = {"image", "document", "video", "audio", "sticker"}
        if media_type not in valid_types:
            return {
                "success": False,
                "error": f"Tipo de medio invalido. Validos: {', '.join(sorted(valid_types))}",
            }

        if not media_url and not media_id:
            return {"success": False, "error": "Proporciona media_url o media_id"}

        self._log_operation("send_media", f"to={to}, type={media_type}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            media_obj: dict[str, Any] = {}
            if media_id:
                media_obj["id"] = media_id
            else:
                media_obj["link"] = media_url
            if caption and media_type not in ("audio", "sticker"):
                media_obj["caption"] = caption
            if filename and media_type == "document":
                media_obj["filename"] = filename

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": media_type,
                media_type: media_obj,
            }

            response = self._http.post("/messages", json=payload)

            if response.ok:
                data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                messages = data.get("messages", [])
                msg_id = messages[0].get("id", "") if messages else ""
                return {
                    "success": True,
                    "message_id": msg_id,
                    "to": to,
                    "media_type": media_type,
                    "status": "sent",
                }
            else:
                error_data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "error_code": error_info.get("code"),
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _test_connection(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Verifica la conexion con WhatsApp Business API.

        Returns:
            Dict con estado de la conexion e info del numero
        """
        if (not self._connected or not self._http) and not self.connect():
            return {"success": False, "error": "No se pudo conectar a WhatsApp API"}

        try:
            response = self._http.get("")

            if response.ok:
                data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                return {
                    "success": True,
                    "verified_name": data.get("verified_name", ""),
                    "display_phone_number": data.get("display_phone_number", ""),
                    "quality_rating": data.get("quality_rating", ""),
                    "code_verification_status": data.get("code_verification_status", ""),
                }
            else:
                error_data = response.json() if hasattr(response, "json") and callable(response.json) else {}
                err_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return {"success": False, "error": err_msg}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    # ── Webhook helpers (static) ─────────────────────────────

    @staticmethod
    def verify_webhook_challenge(mode: str, challenge: str, verify_token: str, expected_token: str) -> dict:
        """Verifica el challenge del webhook de WhatsApp (Meta verification flow).

        Args:
            mode: hub.mode recibido (debe ser "subscribe")
            challenge: hub.challenge recibido
            verify_token: hub.verify_token recibido
            expected_token: Token de verificacion configurado

        Returns:
            Dict con status y challenge si es valido
        """
        if mode == "subscribe" and verify_token == expected_token:
            return {"status": "ok", "challenge": challenge}
        return {"status": "error", "message": "Verificacion fallida: token o modo invalido"}

    @staticmethod
    def verify_webhook_signature(payload_body: bytes, signature: str, app_secret: str) -> bool:
        """Verifica la firma HMAC-SHA256 del webhook de WhatsApp.

        Args:
            payload_body: Cuerpo raw del request (bytes)
            signature: Header X-Hub-Signature-256 (formato: "sha256=<hex>")
            app_secret: App Secret de Meta

        Returns:
            True si la firma es valida
        """
        if not app_secret:
            return False
        if not signature or not signature.startswith("sha256="):
            return False

        expected_sig = hmac.new(
            app_secret.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        received_sig = signature.replace("sha256=", "")
        return hmac.compare_digest(expected_sig, received_sig)

    @staticmethod
    def process_webhook_payload(payload: dict) -> dict:
        """Procesa un payload de webhook entrante de WhatsApp.

        Args:
            payload: Payload JSON completo del webhook

        Returns:
            Dict con messages[], statuses[]
        """
        messages: list[dict] = []
        statuses: list[dict] = []

        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})

                    for msg in value.get("messages", []):
                        msg_info = {
                            "message_id": msg.get("id", ""),
                            "from": msg.get("from", ""),
                            "timestamp": msg.get("timestamp", ""),
                            "type": msg.get("type", ""),
                        }
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

                    for status in value.get("statuses", []):
                        status_info = {
                            "message_id": status.get("id", ""),
                            "status": status.get("status", ""),
                            "timestamp": status.get("timestamp", ""),
                            "recipient_id": status.get("recipient_id", ""),
                        }
                        if status.get("errors"):
                            status_info["errors"] = status["errors"]
                        statuses.append(status_info)

            return {"status": "ok", "messages": messages, "statuses": statuses}

        except Exception as e:
            return {"status": "error", "message": str(e)}


# Esquema del conector
WHATSAPP_SCHEMA = ConnectorSchema(
    name="whatsapp",
    version="1.0.0",
    description="Envía mensajes de texto, plantillas y multimedia via WhatsApp Business",
    category="communication",
    icon="message-circle",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="send_text_message", description="Envia un mensaje de texto", category="write"),
        ActionDefinition(name="send_template_message", description="Envia una plantilla aprobada", category="write"),
        ActionDefinition(name="send_media_message", description="Envia imagen, documento, video o audio", category="write"),
        ActionDefinition(name="test_connection", description="Verifica la conexion con WhatsApp API", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="bearer_token",
            required_fields=["phone_number_id", "access_token"],
            description="Credenciales de WhatsApp Business (Phone Number ID + Access Token)",
        )
    ],
)
