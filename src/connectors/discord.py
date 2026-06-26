"""
Conector Discord — Bot de Mensajes para Discord
==================================================

Permite enviar mensajes a canales de Discord, gestionar roles,
crear embeds y administrar servidores via la API de Discord Bot.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class DiscordConnector(BaseConnector):
    """Conector para Discord: mensajes, roles y gestion de servidor."""

    name = "discord"
    version = "1.0.0"
    description = "Envia mensajes, gestiona roles y administra servidores de Discord"
    category = "communication"
    icon = "message-circle"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._bot_token: str = ""
        self._base_url: str = "https://discord.com/api/v10"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Discord Bot."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("DiscordConnector: Bot Token no configurado")
            return False

        self._bot_token = getattr(self._auth_provider, "_api_key", "")

        if not self._bot_token:
            logger.error("DiscordConnector: Bot Token es requerido")
            return False

        # Set up HttpClient with Bot token auth
        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        # Discord uses "Bot" prefix for bot tokens
        self._http.set_auth("Bearer", token=self._bot_token)
        # Override the Authorization header to use "Bot" prefix instead of "Bearer"
        self._http.set_header("Authorization", f"Bot {self._bot_token}")

        self._connected = True
        self._log_operation("connect", "Bot token configurado")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Discord.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "send_message": self._send_message,
            "send_embed": self._send_embed,
            "list_channels": self._list_channels,
            "get_channel_messages": self._get_channel_messages,
            "add_role": self._add_role,
            "remove_role": self._remove_role,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Bot Token de Discord este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Discord."""
        self._connected = False
        self._bot_token = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un mensaje de texto a un canal de Discord.

        Args:
            params: Debe contener 'channel_id' y 'content'
        """
        channel_id = params.get("channel_id", "")
        content = params.get("content", "")
        if not channel_id or not content:
            return {"success": False, "error": "Parametros requeridos: channel_id, content"}

        self._log_operation("send_message", f"channel={channel_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload: dict[str, Any] = {"content": content}
            if params.get("tts"):
                payload["tts"] = params["tts"]

            response = self._http.post(f"/channels/{channel_id}/messages", json=payload)

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "message_id": data.get("id", ""),
                    "channel_id": data.get("channel_id", channel_id),
                    "content": data.get("content", ""),
                    "author": data.get("author", {}).get("username", ""),
                    "timestamp": data.get("timestamp", ""),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _send_embed(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un mensaje con embed a un canal de Discord.

        Args:
            params: Debe contener 'channel_id' y 'embed' (dict con title, description, etc.)
        """
        channel_id = params.get("channel_id", "")
        embed = params.get("embed", {})
        if not channel_id or not embed:
            return {"success": False, "error": "Parametros requeridos: channel_id, embed"}

        self._log_operation("send_embed", f"channel={channel_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload: dict[str, Any] = {"embeds": [embed]}
            if params.get("content"):
                payload["content"] = params["content"]

            response = self._http.post(f"/channels/{channel_id}/messages", json=payload)

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "message_id": data.get("id", ""),
                    "channel_id": data.get("channel_id", channel_id),
                    "embeds": data.get("embeds", []),
                    "timestamp": data.get("timestamp", ""),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los canales de un servidor de Discord.

        Args:
            params: Debe contener 'guild_id'
        """
        guild_id = params.get("guild_id", "")
        if not guild_id:
            return {"success": False, "error": "Parametro requerido: guild_id"}

        self._log_operation("list_channels", f"guild={guild_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            response = self._http.get(f"/guilds/{guild_id}/channels")

            if response.ok:
                data = response.json() or []
                channels = [
                    {
                        "id": ch.get("id", ""),
                        "name": ch.get("name", ""),
                        "type": ch.get("type", 0),
                        "position": ch.get("position", 0),
                        "parent_id": ch.get("parent_id"),
                        "topic": ch.get("topic", ""),
                        "nsfw": ch.get("nsfw", False),
                    }
                    for ch in data
                ]
                return {
                    "success": True,
                    "channels": channels,
                    "guild_id": guild_id,
                    "total": len(channels),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _get_channel_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene mensajes de un canal de Discord.

        Args:
            params: Debe contener 'channel_id' y opcionalmente 'limit'
        """
        channel_id = params.get("channel_id", "")
        if not channel_id:
            return {"success": False, "error": "Parametro requerido: channel_id"}

        limit = params.get("limit", 50)
        self._log_operation("get_channel_messages", f"channel={channel_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            query_params: dict[str, Any] = {"limit": min(limit, 100)}
            if params.get("before"):
                query_params["before"] = params["before"]
            if params.get("after"):
                query_params["after"] = params["after"]

            response = self._http.get(f"/channels/{channel_id}/messages", params=query_params)

            if response.ok:
                data = response.json() or []
                messages = [
                    {
                        "id": msg.get("id", ""),
                        "content": msg.get("content", ""),
                        "author": {
                            "id": msg.get("author", {}).get("id", ""),
                            "username": msg.get("author", {}).get("username", ""),
                            "bot": msg.get("author", {}).get("bot", False),
                        },
                        "timestamp": msg.get("timestamp", ""),
                        "edited_timestamp": msg.get("edited_timestamp"),
                        "type": msg.get("type", 0),
                        "attachments": msg.get("attachments", []),
                    }
                    for msg in data
                ]
                return {
                    "success": True,
                    "messages": messages,
                    "channel_id": channel_id,
                    "total": len(messages),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _add_role(self, params: dict[str, Any]) -> dict[str, Any]:
        """Asigna un rol a un miembro del servidor.

        Args:
            params: Debe contener 'guild_id', 'user_id' y 'role_id'
        """
        guild_id = params.get("guild_id", "")
        user_id = params.get("user_id", "")
        role_id = params.get("role_id", "")
        if not guild_id or not user_id or not role_id:
            return {"success": False, "error": "Parametros requeridos: guild_id, user_id, role_id"}

        self._log_operation("add_role", f"user={user_id}, role={role_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            response = self._http.put(f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

            if response.ok or response.status_code == 204:
                return {
                    "success": True,
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "role_id": role_id,
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _remove_role(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remueve un rol de un miembro del servidor.

        Args:
            params: Debe contener 'guild_id', 'user_id' y 'role_id'
        """
        guild_id = params.get("guild_id", "")
        user_id = params.get("user_id", "")
        role_id = params.get("role_id", "")
        if not guild_id or not user_id or not role_id:
            return {"success": False, "error": "Parametros requeridos: guild_id, user_id, role_id"}

        self._log_operation("remove_role", f"user={user_id}, role={role_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            response = self._http.delete(f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}")

            if response.ok or response.status_code == 204:
                return {
                    "success": True,
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "role_id": role_id,
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}


DISCORD_SCHEMA = ConnectorSchema(
    name="discord",
    version="1.0.0",
    description="Envia mensajes, gestiona roles y administra servidores de Discord",
    category="communication",
    icon="message-circle",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="send_message", description="Envia un mensaje de texto", category="write"),
        ActionDefinition(name="send_embed", description="Envia un mensaje con embed", category="write"),
        ActionDefinition(name="list_channels", description="Lista canales del servidor", category="read"),
        ActionDefinition(name="get_channel_messages", description="Obtiene mensajes del canal", category="read"),
        ActionDefinition(name="add_role", description="Asigna un rol a un miembro", category="write"),
        ActionDefinition(name="remove_role", description="Remueve un rol de un miembro", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["bot_token"], description="Discord Bot Token")
    ],
)
