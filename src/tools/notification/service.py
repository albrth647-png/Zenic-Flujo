"""
Workflow Determinista — Notification Service
"""

from cryptography.fernet import Fernet

from src.config import WHATSAPP_ENCRYPTION_KEY
from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class NotificationService:
    def __init__(self):
        self._db = DatabaseManager()

    def send_email(self, to: str, subject: str, body: str, template: str | None = None) -> dict:
        smtp_server = self._db.get_setting("smtp_server")
        if not smtp_server:
            return {"status": "queued", "message": "SMTP no configurado, guardado en cola"}
        try:
            import smtplib
            from email.mime.text import MIMEText

            sender = self._db.get_setting("email_user", "")
            password = self._db.get_setting("email_password", "")
            port = int(self._db.get_setting("smtp_port", "587"))

            msg = MIMEText(body, "html" if template else "plain")
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = to

            with smtplib.SMTP(smtp_server, port) as server:
                server.starttls()
                server.login(sender, password)
                server.send_message(msg)

            logger.info(f"Email enviado a {to}: {subject}")
            return {"status": "sent", "to": to, "subject": subject}
        except (smtplib.SMTPException, OSError, ValueError) as e:
            logger.error(f"Error enviando email a {to}: {e}")
            return {"status": "failed", "error": str(e)}

    def send_notification(self, channel: str, recipients: list[str] | str, message: str, **kwargs) -> dict:
        if channel == "email":
            if isinstance(recipients, list):
                results = []
                for r in recipients:
                    results.append(self.send_email(r, kwargs.get("subject", ""), message))
                return {"status": "completed", "results": results}
            return self.send_email(recipients, kwargs.get("subject", ""), message)
        logger.info(f"Notificación ({channel}): {message}")
        return {"status": "logged", "channel": channel, "message": message[:100]}

    def send_birthday_emails(self) -> int:
        from datetime import date

        today = date.today()
        leads = self._db.fetchall(
            "SELECT * FROM leads WHERE strftime('%m-%d', substr(notes, 1, 10)) = ?",
            (today.strftime("%m-%d"),),
        )
        sent = 0
        for lead in leads:
            if lead.get("email"):
                result = self.send_email(
                    lead["email"],
                    "¡Feliz cumpleaños!",
                    f"Hola {lead['name']}, ¡feliz cumpleaños! 🎉",
                )
                if result.get("status") == "sent":
                    sent += 1
        return sent

    def configure_smtp(self, server: str, port: int, username: str, password: str) -> bool:
        self._db.set_setting("smtp_server", server)
        self._db.set_setting("smtp_port", str(port))
        self._db.set_setting("email_user", username)
        self._db.set_setting("email_password", password)
        logger.info("Configuración SMTP guardada")
        return True

    def test_connection(self) -> dict:
        smtp_server = self._db.get_setting("smtp_server")
        if not smtp_server:
            return {"status": "error", "message": "SMTP no configurado"}
        try:
            import smtplib

            port = int(self._db.get_setting("smtp_port", "587"))
            with smtplib.SMTP(smtp_server, port, timeout=10) as server:
                server.starttls()
                server.login(
                    self._db.get_setting("email_user", ""),
                    self._db.get_setting("email_password", ""),
                )
                return {"status": "ok", "message": "Conexión SMTP exitosa"}
        except (smtplib.SMTPException, OSError, ValueError) as e:
            return {"status": "error", "message": str(e)}

    # ── WhatsApp Cloud API ────────────────────────────────────

    def _get_whatsapp_token(self) -> str | None:
        """Obtiene y descifra el token WhatsApp."""
        encrypted = self._db.get_setting("whatsapp_token")
        if not encrypted:
            return None
        try:
            return self._decrypt_token(encrypted)
        except Exception as e:
            logger.error(f"Error descifrando token WhatsApp: {e}")
            return None

    def send_whatsapp(self, to: str, message: str) -> dict:
        """Envía un mensaje de texto vía WhatsApp Cloud API."""
        token = self._get_whatsapp_token()
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
                logger.info(f"WhatsApp enviado a {to}: {msg_id}")
                return {"status": "sent", "to": to, "message_id": msg_id}
            else:
                error = data.get("error", {}).get("message", str(data))
                logger.error(f"WhatsApp error a {to}: {error}")
                return {"status": "failed", "to": to, "error": error}

        except ImportError:
            return {"status": "error", "message": "requests library no instalada"}
        except requests.exceptions.ConnectionError:
            return {"status": "failed", "message": "Error de conexión con WhatsApp API"}
        except requests.exceptions.Timeout:
            return {"status": "failed", "message": "Timeout conectando con WhatsApp API"}
        except Exception as e:
            logger.error(f"WhatsApp exception: {e}")
            return {"status": "failed", "message": str(e)}

    def send_whatsapp_template(
        self, to: str, template_name: str, language_code: str = "es", components: list[dict] | None = None
    ) -> dict:
        """Envía un mensaje template (para fuera de ventana 24h)."""
        token = self._get_whatsapp_token()
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
                logger.info(f"WhatsApp template enviado a {to}: {template_name}")
                return {"status": "sent", "to": to, "message_id": msg_id}
            else:
                error = data.get("error", {}).get("message", str(data))
                logger.error(f"WhatsApp template error: {error}")
                return {"status": "failed", "error": error}

        except requests.exceptions.ConnectionError:
            return {"status": "failed", "message": "Error de conexión con WhatsApp API"}
        except Exception as e:
            logger.error(f"WhatsApp template exception: {e}")
            return {"status": "failed", "message": str(e)}

    @staticmethod
    def _encrypt_token(token: str) -> str:
        """Cifra el token WhatsApp antes de guardarlo."""
        f = Fernet(WHATSAPP_ENCRYPTION_KEY)
        return f.encrypt(token.encode()).decode()

    @staticmethod
    def _decrypt_token(encrypted: str) -> str:
        """Descifra el token WhatsApp al usarlo."""
        f = Fernet(WHATSAPP_ENCRYPTION_KEY)
        return f.decrypt(encrypted.encode()).decode()

    def configure_whatsapp(self, token: str, phone_number_id: str) -> bool:
        """Configura credenciales de WhatsApp Cloud API (token cifrado)."""
        encrypted = self._encrypt_token(token)
        self._db.set_setting("whatsapp_token", encrypted)
        self._db.set_setting("whatsapp_phone_number_id", phone_number_id)
        logger.info("Configuración WhatsApp guardada (token cifrado)")
        return True

    def get_whatsapp_status(self) -> dict:
        """Retorna estado de la configuración WhatsApp."""
        encrypted = self._db.get_setting("whatsapp_token")
        token = "" if not encrypted else (self._get_whatsapp_token() or "")
        phone_id = self._db.get_setting("whatsapp_phone_number_id")
        return {
            "whatsapp_configured": bool(token and phone_id),
            "has_token": bool(token),
            "has_phone_id": bool(phone_id),
        }

    def get_status(self) -> dict:
        return {
            "smtp_configured": bool(self._db.get_setting("smtp_server")),
            "whatsapp_configured": bool(
                self._db.get_setting("whatsapp_token") and self._db.get_setting("whatsapp_phone_number_id")
            ),
        }
