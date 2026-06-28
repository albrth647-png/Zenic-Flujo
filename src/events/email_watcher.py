"""
Workflow Determinista — EmailWatcher
Monitorea un buzón IMAP en busca de correos entrantes.
"""

import threading
import time
from collections.abc import Callable

from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class EmailWatcher(threading.Thread):
    """
    Monitorea un buzón IMAP y emite eventos cuando llegan correos.

    Requiere configuración SMTP/IMAP en settings:
    - imap_server
    - imap_port (default: 993)
    - email_user
    - email_password
    - email_check_interval (default: 300 segundos)
    """

    def __init__(self, callback: Callable | None = None):
        super().__init__(daemon=True)
        self._callback = callback
        self._running = False
        self._interval = 300  # 5 minutos por defecto
        self._last_uids: set[str] = set()
        self._db = DatabaseManager()

    def run(self) -> None:
        """Hilo principal de monitoreo."""
        self._running = True
        logger.info("EmailWatcher iniciado")

        while self._running:
            try:
                self._check_config_and_poll()
            except (ConnectionError, OSError, ImportError, ValueError) as e:
                logger.warning(f"Error en EmailWatcher: {e}")

            time.sleep(self._interval)

    def stop(self) -> None:
        """Detiene el monitoreo."""
        self._running = False
        logger.info("EmailWatcher detenido")

    def _check_config_and_poll(self) -> None:
        """Verifica configuración y realiza polling si está configurado."""
        imap_server = self._db.get_setting("imap_server")
        if not imap_server:
            return  # No configurado, silenciosamente omitir

        try:
            interval_str = self._db.get_setting("email_check_interval", "300")
            self._interval = int(interval_str)
        except (ValueError, TypeError):
            self._interval = 300

        self._poll_imap()

    def _poll_imap(self) -> None:
        """Conecta al servidor IMAP y busca nuevos correos."""
        try:
            import email as email_lib
            import imaplib
            from email.header import decode_header

            server = self._db.get_setting("imap_server", "")
            port_str = self._db.get_setting("imap_port", "993")
            user = self._db.get_setting("email_user", "")
            password = self._db.get_setting("email_password", "")

            if not all([server, user, password]):
                return

            port = int(port_str)

            # Conectar
            if port == 993:
                mail = imaplib.IMAP4_SSL(server, port)
            else:
                mail = imaplib.IMAP4(server, port)
                mail.starttls()

            mail.login(user, password)
            mail.select("INBOX")

            # Buscar todos los correos
            _, messages = mail.search(None, "ALL")
            current_uids = set(messages[0].split()) if messages[0] else set()

            # Detectar nuevos
            new_uids = current_uids - self._last_uids

            if new_uids and self._last_uids:  # Ignorar primera ejecución
                for uid in new_uids:
                    _, msg_data = mail.fetch(uid, "(RFC822)")
                    if msg_data and msg_data[0]:
                        raw_email = msg_data[0][1]
                        email_message = email_lib.message_from_bytes(raw_email)

                        subject = ""
                        sender = ""
                        body = ""

                        if email_message["Subject"]:
                            decoded = decode_header(email_message["Subject"])
                            subject = decoded[0][0] if isinstance(decoded[0][0], str) else ""
                            if isinstance(subject, bytes):
                                subject = subject.decode("utf-8", errors="ignore")

                        if email_message["From"]:
                            sender = email_message["From"]

                        # Extraer cuerpo
                        if email_message.is_multipart():
                            for part in email_message.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                    break
                        else:
                            body = email_message.get_payload(decode=True).decode("utf-8", errors="ignore")

                        self._emit(
                            "email.received",
                            {
                                "subject": subject,
                                "from": sender,
                                "body_preview": body[:500],
                                "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                            },
                        )

            self._last_uids = current_uids
            mail.logout()

        except ImportError:
            logger.warning("imaplib no disponible en esta plataforma")
        except (OSError, ValueError) as e:
            logger.warning(f"Error conectando a IMAP: {e}")

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Emite un evento de correo recibido."""
        if self._callback:
            try:
                self._callback(event_type, data)
            except Exception as e:
                logger.error(f"Error en callback de EmailWatcher: {e}")
