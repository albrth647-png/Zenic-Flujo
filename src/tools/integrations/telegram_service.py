"""
Workflow Determinista — Telegram Integration (Sprint 7)

Integra con Telegram Bot API para:
- Enviar mensajes de texto
- Enviar mensajes con teclado inline
- Enviar fotos y documentos
- Obtener actualizaciones del bot
- Gestionar chats

Autenticación: Bot Token (guardado cifrado en DB)
"""

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging

logger = setup_logging(__name__)

TELEGRAM_API = "https://api.telegram.org"
try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class TelegramService:
    """Servicio de integración con Telegram Bot API."""

    def __init__(self):
        self._db = DatabaseManager()

    # ── Acciones principales ──────────────────────────────

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "",
        reply_to_message_id: int = 0,
    ) -> dict:
        """
        Envía un mensaje de texto a un chat de Telegram.

        Args:
            chat_id: ID del chat (numérico o @username)
            text: Texto del mensaje (max 4096 chars)
            parse_mode: "HTML" o "Markdown" (opcional)
            reply_to_message_id: ID del mensaje al que responder

        Returns:
            dict con: status, message_id, chat_id
        """
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Telegram no configurado. Ve a Configuración → Integraciones."}

        if not text:
            return {"status": "error", "message": "El mensaje no puede estar vacío"}

        if len(text) > 4096:
            text = text[:4093] + "..."

        try:
            url = f"{TELEGRAM_API}/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()

            if data.get("ok"):
                msg = data.get("result", {})
                logger.info(f"Telegram: Mensaje enviado a {chat_id}")
                return {
                    "status": "sent",
                    "chat_id": chat_id,
                    "message_id": msg.get("message_id"),
                }
            else:
                error = data.get("description", "Error desconocido")
                logger.error(f"Telegram error a {chat_id}: {error}")
                return {"status": "failed", "error": error}

        except Exception as e:
            logger.error(f"Telegram exception: {e}")
            return {"status": "failed", "error": str(e)}

    def send_photo(
        self,
        chat_id: str,
        photo: str,
        caption: str = "",
    ) -> dict:
        """
        Envía una foto a un chat de Telegram.

        Args:
            chat_id: ID del chat
            photo: URL de la foto o file_id
            caption: Pie de foto (opcional, max 1024 chars)

        Returns:
            dict con: status, message_id
        """
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Telegram no configurado"}

        try:
            url = f"{TELEGRAM_API}/bot{token}/sendPhoto"
            payload = {"chat_id": chat_id, "photo": photo}
            if caption:
                payload["caption"] = caption[:1024]

            resp = requests.post(url, json=payload, timeout=30)
            data = resp.json()

            if data.get("ok"):
                logger.info(f"Telegram: Foto enviada a {chat_id}")
                return {
                    "status": "sent",
                    "chat_id": chat_id,
                    "message_id": data.get("result", {}).get("message_id"),
                }
            else:
                return {"status": "failed", "error": data.get("description", "Error")}

        except Exception as e:
            logger.error(f"Telegram send_photo exception: {e}")
            return {"status": "failed", "error": str(e)}

    def get_updates(
        self,
        offset: int = 0,
        limit: int = 100,
        timeout: int = 0,
    ) -> dict:
        """
        Obtiene actualizaciones pendientes del bot.

        Args:
            offset: Identificador del último update procesado
            limit: Máximo de updates a obtener
            timeout: Timeout largo para long polling

        Returns:
            dict con: status, updates[]
        """
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Telegram no configurado"}

        try:
            url = f"{TELEGRAM_API}/bot{token}/getUpdates"
            params = {"limit": limit, "timeout": timeout}
            if offset:
                params["offset"] = offset

            resp = requests.get(url, params=params, timeout=timeout + 10)
            data = resp.json()

            if data.get("ok"):
                updates = data.get("result", [])
                return {
                    "status": "ok",
                    "updates": updates,
                    "count": len(updates),
                }
            else:
                return {"status": "failed", "error": data.get("description", "Error")}

        except Exception as e:
            logger.error(f"Telegram get_updates exception: {e}")
            return {"status": "failed", "error": str(e)}

    def get_chat(self, chat_id: str) -> dict:
        """Obtiene información de un chat."""
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Telegram no configurado"}

        try:
            url = f"{TELEGRAM_API}/bot{token}/getChat"
            resp = requests.get(url, params={"chat_id": chat_id}, timeout=10)
            data = resp.json()

            if data.get("ok"):
                return {"status": "ok", "chat": data.get("result", {})}
            else:
                return {"status": "failed", "error": data.get("description", "Error")}

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ── Configuración ─────────────────────────────────────

    def configure(self, bot_token: str) -> bool:
        """Guarda el token del bot de Telegram."""
        self._db.set_setting("telegram_bot_token", bot_token)
        logger.info("Telegram: Bot token guardado")
        return True

    def test_connection(self) -> dict:
        """Verifica la conexión con el bot de Telegram."""
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Telegram no configurado"}

        try:
            url = f"{TELEGRAM_API}/bot{token}/getMe"
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if data.get("ok"):
                bot = data.get("result", {})
                return {
                    "status": "ok",
                    "message": f"Bot conectado: @{bot.get('username', 'unknown')}",
                    "bot_name": bot.get("first_name", ""),
                    "bot_username": bot.get("username", ""),
                }
            else:
                return {"status": "error", "message": data.get("description", "Token inválido")}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict:
        """Estado de la integración Telegram."""
        token = self._get_token()
        return {
            "configured": bool(token),
            "has_token": bool(token),
        }

    def _get_token(self) -> str | None:
        """Obtiene el bot token desde la DB."""
        return self._db.get_setting("telegram_bot_token") or None

    # ── Tool Definition ───────────────────────────────────

    @staticmethod
    def get_tool_definition() -> dict:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "telegram",
            "name": "Telegram",
            "description": "Envía mensajes y gestiona chats vía Telegram Bot",
            "actions": {
                "send_message": {
                    "name": "Enviar mensaje",
                    "description": "Envía un mensaje de texto a un chat",
                    "params": [
                        {
                            "name": "chat_id",
                            "type": "string",
                            "required": True,
                            "label": "Chat ID",
                            "placeholder": "123456789",
                        },
                        {
                            "name": "text",
                            "type": "string",
                            "required": True,
                            "label": "Mensaje",
                            "placeholder": "Hola, esto es un workflow",
                        },
                        {
                            "name": "parse_mode",
                            "type": "select",
                            "options": ["", "HTML", "Markdown"],
                            "required": False,
                            "label": "Formato",
                        },
                    ],
                },
                "send_photo": {
                    "name": "Enviar foto",
                    "description": "Envía una foto a un chat",
                    "params": [
                        {"name": "chat_id", "type": "string", "required": True, "label": "Chat ID"},
                        {"name": "photo", "type": "string", "required": True, "label": "URL de la foto"},
                        {"name": "caption", "type": "string", "required": False, "label": "Pie de foto"},
                    ],
                },
                "get_updates": {
                    "name": "Obtener updates",
                    "description": "Obtiene actualizaciones pendientes del bot",
                    "params": [
                        {"name": "offset", "type": "number", "required": False, "default": 0, "label": "Offset"},
                        {"name": "limit", "type": "number", "required": False, "default": 100, "label": "Límite"},
                    ],
                },
                "get_chat": {
                    "name": "Info del chat",
                    "description": "Obtiene información de un chat",
                    "params": [
                        {"name": "chat_id", "type": "string", "required": True, "label": "Chat ID"},
                    ],
                },
            },
        }
