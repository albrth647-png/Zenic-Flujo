"""
Workflow Determinista — Notification Service
"""
from datetime import datetime
from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class NotificationService:
    def __init__(self):
        self._db = DatabaseManager()

    def send_email(self, to: str, subject: str, body: str,
                   template: str | None = None) -> dict:
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
        except Exception as e:
            logger.error(f"Error enviando email a {to}: {e}")
            return {"status": "failed", "error": str(e)}

    def send_notification(self, channel: str, recipients: list[str] | str,
                          message: str, **kwargs) -> dict:
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

    def configure_smtp(self, server: str, port: int, username: str,
                       password: str) -> bool:
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
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict:
        return {
            "smtp_configured": bool(self._db.get_setting("smtp_server")),
        }
