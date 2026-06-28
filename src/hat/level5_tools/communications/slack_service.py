"""
Workflow Determinista — Slack Integration (Sprint 7)

Integra con Slack Web API para:
- Enviar mensajes a canales/DMs
- Listar canales
- Subir archivos
- Obtener info de usuario

Autenticación: Bot Token (guardado cifrado en DB)
"""

from src.core.db.sqlite_manager import DatabaseManager
from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)

SLACK_API = "https://slack.com/api"
try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


class SlackService:
    """Servicio de integración con Slack Web API."""

    def __init__(self):
        self._db = DatabaseManager()

    # ── Acciones principales ──────────────────────────────

    def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: str = "",
        blocks: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Envía un mensaje a un canal o DM de Slack.

        Args:
            channel: ID del canal o usuario (ej: "C0123ABC" o "@user")
            text: Texto del mensaje (max 40000 chars)
            thread_ts: Timestamp del padre para responder en hilo
            blocks: Bloques de formato richness (opcional)

        Returns:
            dict con: status, message_id, channel
        """
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Slack no configurado. Ve a Configuración → Integraciones."}

        if not text:
            return {"status": "error", "message": "El mensaje no puede estar vacío"}

        try:
            url = f"{SLACK_API}/chat.postMessage"
            headers = {"Authorization": f"Bearer {token}"}
            payload = {"channel": channel, "text": text}
            if thread_ts:
                payload["thread_ts"] = thread_ts
            if blocks:
                payload["blocks"] = blocks

            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            if data.get("ok"):
                ts = data.get("ts", "")
                logger.info(f"Slack: Mensaje enviado a {channel}")
                return {
                    "status": "sent",
                    "channel": channel,
                    "message_id": ts,
                }
            else:
                error = data.get("error", "Error desconocido")
                logger.error(f"Slack error a {channel}: {error}")
                return {"status": "failed", "error": error}

        except Exception as e:
            logger.error(f"Slack exception: {e}")
            return {"status": "failed", "error": str(e)}

    def list_channels(self, limit: int = 100) -> dict[str, Any]:
        """
        Lista los canales a los que el bot tiene acceso.

        Args:
            limit: Máximo de canales a retornar

        Returns:
            dict con: status, channels[]
        """
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Slack no configurado"}

        try:
            url = f"{SLACK_API}/conversations.list"
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(
                url,
                headers=headers,
                params={"types": "public_channel,private_channel", "limit": limit},
                timeout=15,
            )
            data = resp.json()

            if data.get("ok"):
                channels = [{"id": ch["id"], "name": ch["name"]} for ch in data.get("channels", [])]
                return {"status": "ok", "channels": channels, "count": len(channels)}
            else:
                return {"status": "failed", "error": data.get("error", "Error")}

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def upload_file(
        self,
        channels: str,
        file_path: str = "",
        content: str = "",
        filename: str = "file.txt",
        title: str = "",
    ) -> dict[str, Any]:
        """
        Sube un archivo a Slack.

        Args:
            channels: Canales destino (ej: "#general" o "C0123ABC")
            file_path: Ruta del archivo local (opcional)
            content: Contenido del archivo como string (opcional)
            filename: Nombre del archivo
            title: Título del archivo

        Returns:
            dict con: status, file_id
        """
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Slack no configurado"}

        if not file_path and not content:
            return {"status": "error", "message": "Proporciona file_path o content"}

        try:
            url = f"{SLACK_API}/files.upload"
            headers = {"Authorization": f"Bearer {token}"}

            form_data = {
                "channels": channels,
                "filename": filename,
                "title": title or filename,
            }
            if content:
                form_data["content"] = content

            if file_path:
                with open(file_path, "rb") as fh:
                    resp = requests.post(
                        url,
                        headers=headers,
                        data=form_data if content else None,
                        files={"file": fh},
                        timeout=30,
                    )
            else:
                resp = requests.post(
                    url,
                    headers=headers,
                    data=form_data if content else None,
                    timeout=30,
                )
            data = resp.json()

            if data.get("ok"):
                file_info = data.get("file", {})
                logger.info(f"Slack: Archivo {filename} subido a {channels}")
                return {
                    "status": "ok",
                    "file_id": file_info.get("id", ""),
                    "channels": channels,
                }
            else:
                return {"status": "failed", "error": data.get("error", "Error")}

        except Exception as e:
            logger.error(f"Slack upload_file exception: {e}")
            return {"status": "failed", "error": str(e)}

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        """Obtiene información de un usuario de Slack."""
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Slack no configurado"}

        try:
            url = f"{SLACK_API}/users.info"
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.get(url, headers=headers, params={"user": user_id}, timeout=10)
            data = resp.json()

            if data.get("ok"):
                user = data.get("user", {})
                return {
                    "status": "ok",
                    "user": {
                        "id": user.get("id"),
                        "name": user.get("name"),
                        "real_name": user.get("real_name"),
                        "email": user.get("profile", {}).get("email", ""),
                    },
                }
            else:
                return {"status": "failed", "error": data.get("error", "Error")}

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # ── Configuración ─────────────────────────────────────

    def configure(self, bot_token: str) -> bool:
        """Guarda el bot token de Slack."""
        self._db.set_setting("slack_bot_token", bot_token)
        logger.info("Slack: Bot token guardado")
        return True

    def test_connection(self) -> dict[str, Any]:
        """Verifica la conexión con Slack."""
        token = self._get_token()
        if not token:
            return {"status": "error", "message": "Slack no configurado"}

        try:
            url = f"{SLACK_API}/auth.test"
            headers = {"Authorization": f"Bearer {token}"}
            resp = requests.post(url, headers=headers, timeout=10)
            data = resp.json()

            if data.get("ok"):
                return {
                    "status": "ok",
                    "message": f"Conectado como {data.get('user', '?')} en {data.get('team', '?')}",
                    "user": data.get("user"),
                    "team": data.get("team"),
                }
            else:
                return {"status": "error", "message": data.get("error", "Token inválido")}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_status(self) -> dict[str, Any]:
        """Estado de la integración Slack."""
        token = self._get_token()
        return {
            "configured": bool(token),
            "has_token": bool(token),
        }

    def _get_token(self) -> str | None:
        """Obtiene el bot token desde la DB."""
        return self._db.get_setting("slack_bot_token") or None

    # ── Tool Definition ───────────────────────────────────

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        """Retorna la definición de la tool para el editor visual."""
        return {
            "tool": "slack",
            "name": "Slack",
            "description": "Envía mensajes y gestiona canales vía Slack",
            "actions": {
                "send_message": {
                    "name": "Enviar mensaje",
                    "description": "Envía un mensaje a un canal de Slack",
                    "params": [
                        {
                            "name": "channel",
                            "type": "string",
                            "required": True,
                            "label": "Canal",
                            "placeholder": "#general",
                        },
                        {
                            "name": "text",
                            "type": "string",
                            "required": True,
                            "label": "Mensaje",
                            "placeholder": "Hola desde un workflow",
                        },
                        {
                            "name": "thread_ts",
                            "type": "string",
                            "required": False,
                            "label": "Thread (responder en hilo)",
                        },
                    ],
                },
                "list_channels": {
                    "name": "Listar canales",
                    "description": "Lista los canales del workspace",
                    "params": [
                        {"name": "limit", "type": "number", "required": False, "default": 100, "label": "Límite"},
                    ],
                },
                "upload_file": {
                    "name": "Subir archivo",
                    "description": "Sube un archivo a un canal",
                    "params": [
                        {
                            "name": "channels",
                            "type": "string",
                            "required": True,
                            "label": "Canal destino",
                            "placeholder": "#general",
                        },
                        {"name": "content", "type": "string", "required": False, "label": "Contenido del archivo"},
                        {
                            "name": "filename",
                            "type": "string",
                            "required": False,
                            "default": "file.txt",
                            "label": "Nombre del archivo",
                        },
                    ],
                },
                "get_user_info": {
                    "name": "Info de usuario",
                    "description": "Obtiene información de un usuario",
                    "params": [
                        {
                            "name": "user_id",
                            "type": "string",
                            "required": True,
                            "label": "User ID",
                            "placeholder": "U0123ABC",
                        },
                    ],
                },
            },
        }
