"""
NotificationService — Fachada unificada de notificaciones
============================================================

API pública única. Delega en:
• :mod:`._email_service` — EmailService (SMTP, cumpleaños, test)
• :mod:`._whatsapp_service` — WhatsAppService (Cloud API, templates)

Retrocompatible: importaciones existentes no requieren cambios.

Evolución: 1 archivo (229 L) → 3 archivos (~80 L c/u)
"""

from src.core.logging import setup_logging
from src.hat.level5_tools.communications.notification._email_service import EmailService
from src.hat.level5_tools.communications.notification._whatsapp_service import WhatsAppService
from typing import Any

logger = setup_logging(__name__)


class NotificationService:
    """Servicio unificado de notificaciones (Email + WhatsApp).

    Delega en EmailService y WhatsAppService.
    API pública idéntica a la original.
    """

    def __init__(self):
        self._email = EmailService()
        self._whatsapp = WhatsAppService()

    # ── Email ──────────────────────────────────────────────────────

    def send_email(self, to: str, subject: str, body: str, template: str | None = None) -> dict[str, Any]:
        return self._email.send_email(to, subject, body, template=template)

    def send_notification(self, channel: str, recipients: list[str] | str, message: str, **kwargs) -> dict[str, Any]:
        if channel == "email":
            if isinstance(recipients, list):
                results = []
                for r in recipients:
                    results.append(self._email.send_email(r, kwargs.get("subject", ""), message))
                return {"status": "completed", "results": results}
            return self._email.send_email(recipients, kwargs.get("subject", ""), message)
        logger.info("Notificación (%s): %s", channel, message)
        return {"status": "logged", "channel": channel, "message": message[:100]}

    def send_birthday_emails(self) -> int:
        return self._email.send_birthday_emails()

    def configure_smtp(self, server: str, port: int, username: str, password: str) -> bool:
        return self._email.configure_smtp(server, port, username, password)

    def test_connection(self) -> dict[str, Any]:
        return self._email.test_connection()

    # ── WhatsApp ───────────────────────────────────────────────────

    def _get_whatsapp_token(self) -> str | None:
        return self._whatsapp._get_token()

    def send_whatsapp(self, to: str, message: str) -> dict[str, Any]:
        return self._whatsapp.send_message(to, message)

    def send_whatsapp_template(
        self, to: str, template_name: str, language_code: str = "es",
        components: list[dict] | None = None,
    ) -> dict[str, Any]:
        return self._whatsapp.send_template(to, template_name, language_code=language_code, components=components)

    def configure_whatsapp(self, token: str, phone_number_id: str) -> bool:
        return self._whatsapp.configure(token, phone_number_id)

    def get_whatsapp_status(self) -> dict[str, Any]:
        return self._whatsapp.get_status()

    @staticmethod
    def _encrypt_token(token: str) -> str:
        return WhatsAppService._encrypt_token(token)

    @staticmethod
    def _decrypt_token(encrypted: str) -> str:
        return WhatsAppService._decrypt_token(encrypted)

    # ── Estado general ─────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        smtp = bool(self._email._db.get_setting("smtp_server"))
        wa = self._whatsapp.get_status()
        return {
            "smtp_configured": smtp,
            "whatsapp_configured": wa.get("whatsapp_configured", False),
        }
