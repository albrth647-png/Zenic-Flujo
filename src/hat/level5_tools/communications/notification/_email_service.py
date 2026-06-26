"""
EmailService — Gestión de correos electrónicos vía SMTP
=========================================================

Extraído de notification/service.py. Responsabilidad única: enviar
correos, configurar SMTP, probar conexión.
"""

import smtplib
from email.mime.text import MIMEText

from src.core.logging import setup_logging
from src.core.db.sqlite_manager import DatabaseManager

logger = setup_logging(__name__)


class EmailService:
    """Servicio de correo electrónico vía SMTP."""

    def __init__(self):
        self._db = DatabaseManager()

    def send_email(
        self, to: str, subject: str, body: str, template: str | None = None,
    ) -> dict:
        """Envía un correo electrónico vía SMTP."""
        smtp_server = self._db.get_setting("smtp_server")
        if not smtp_server:
            return {"status": "queued", "message": "SMTP no configurado, guardado en cola"}
        try:
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

            logger.info("Email enviado a %s: %s", to, subject)
            return {"status": "sent", "to": to, "subject": subject}
        except (smtplib.SMTPException, OSError, ValueError) as e:
            logger.error("Error enviando email a %s: %s", to, e)
            return {"status": "failed", "error": str(e)}

    def send_birthday_emails(self) -> int:
        """Envía emails de cumpleaños a leads con fecha de hoy."""
        from datetime import date

        today = date.today()
        leads = self._db.fetchall(
            "SELECT * FROM leads WHERE strftime('%%m-%%d', substr(notes, 1, 10)) = ?",
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
        """Configura credenciales SMTP."""
        self._db.set_setting("smtp_server", server)
        self._db.set_setting("smtp_port", str(port))
        self._db.set_setting("email_user", username)
        self._db.set_setting("email_password", password)
        logger.info("Configuración SMTP guardada")
        return True

    def test_connection(self) -> dict:
        """Prueba la conexión SMTP."""
        smtp_server = self._db.get_setting("smtp_server")
        if not smtp_server:
            return {"status": "error", "message": "SMTP no configurado"}
        try:
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
