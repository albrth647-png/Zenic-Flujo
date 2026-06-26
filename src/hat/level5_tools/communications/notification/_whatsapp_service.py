"""
WhatsAppService — Mensajería vía WhatsApp Cloud API
=====================================================

Extraído de notification/service.py. Responsabilidad única: enviar
mensajes y templates de WhatsApp, cifrado/descifrado de tokens.
"""

from src.core.config import WHATSAPP_ENCRYPTION_KEY
from src.core.logging import setup_logging
from src.core.db.sqlite_manager import DatabaseManager

logger = setup_logging(__name__)


class WhatsAppService:
    """Servicio de mensajería WhatsApp Cloud API."""

    def __init__(self):
        self._db = DatabaseManager()

    def _get_token(self) -> str | None:
        """Obtiene y descifra el token WhatsApp."""
        encrypted = self._db.get_setting("whatsapp_token")
        if not encrypted:
            return None
        try:
            return self._decrypt_token(encrypted)
        except Exception as e:
            logger.error("Error descifrando token WhatsApp: %s", e)
            return None

    def send_message(self, to: str, message: str) -> dict:
        """Envía un mensaje de texto vía WhatsApp Cloud API."""
        token = self._get_token()
        phone_number_id = self._db.get_setting("whatsapp_phone_number_id")

        if not token or not phone_number_id:
            return {"status": "error", "message": "WhatsApp no configurado. Ve a Configuración."}

        try:
            import requests

            url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": message},
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            if resp.status_code == 200 and data.get("messages"):
                msg_id = data["messages"][0].get("id", "")
                logger.info("WhatsApp enviado a %s: %s", to, msg_id)
                return {"status": "sent", "to": to, "message_id": msg_id}

            error = data.get("error", {}).get("message", str(data))
            logger.error("WhatsApp error a %s: %s", to, error)
            return {"status": "failed", "to": to, "error": error}

        except ImportError:
            return {"status": "error", "message": "requests library no instalada"}
        except requests.exceptions.ConnectionError:
            return {"status": "failed", "message": "Error de conexión con WhatsApp API"}
        except requests.exceptions.Timeout:
            return {"status": "failed", "message": "Timeout conectando con WhatsApp API"}
        except Exception as e:
            logger.error("WhatsApp exception: %s", e)
            return {"status": "failed", "message": str(e)}

    def send_template(
        self, to: str, template_name: str, language_code: str = "es",
        components: list[dict] | None = None,
    ) -> dict:
        """Envía un mensaje template (para fuera de ventana 24h)."""
        token = self._get_token()
        phone_number_id = self._db.get_setting("whatsapp_phone_number_id")

        if not token or not phone_number_id:
            return {"status": "error", "message": "WhatsApp no configurado"}

        try:
            import requests

            url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload: dict = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                },
            }
            if components:
                payload["template"]["components"] = components

            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            if resp.status_code == 200 and data.get("messages"):
                msg_id = data["messages"][0].get("id", "")
                logger.info("WhatsApp template enviado a %s: %s", to, template_name)
                return {"status": "sent", "to": to, "message_id": msg_id}

            error = data.get("error", {}).get("message", str(data))
            logger.error("WhatsApp template error: %s", error)
            return {"status": "failed", "error": error}

        except requests.exceptions.ConnectionError:
            return {"status": "failed", "message": "Error de conexión con WhatsApp API"}
        except Exception as e:
            logger.error("WhatsApp template exception: %s", e)
            return {"status": "failed", "message": str(e)}

    def configure(self, token: str, phone_number_id: str) -> bool:
        """Configura credenciales de WhatsApp Cloud API (token cifrado)."""
        encrypted = self._encrypt_token(token)
        self._db.set_setting("whatsapp_token", encrypted)
        self._db.set_setting("whatsapp_phone_number_id", phone_number_id)
        logger.info("Configuración WhatsApp guardada (token cifrado)")
        return True

    def get_status(self) -> dict:
        """Retorna estado de la configuración WhatsApp."""
        encrypted = self._db.get_setting("whatsapp_token")
        token = "" if not encrypted else (self._get_token() or "")
        phone_id = self._db.get_setting("whatsapp_phone_number_id")
        return {
            "whatsapp_configured": bool(token and phone_id),
            "has_token": bool(token),
            "has_phone_id": bool(phone_id),
        }

    @staticmethod
    def _encrypt_token(token: str) -> str:
        """Cifra el token WhatsApp antes de guardarlo."""
        from cryptography.fernet import Fernet
        f = Fernet(WHATSAPP_ENCRYPTION_KEY)
        return f.encrypt(token.encode()).decode()

    @staticmethod
    def _decrypt_token(encrypted: str) -> str:
        """Descifra el token WhatsApp al usarlo."""
        from cryptography.fernet import Fernet
        f = Fernet(WHATSAPP_ENCRYPTION_KEY)
        return f.decrypt(encrypted.encode()).decode()
