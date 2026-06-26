"""
Conector Microsoft Teams — Mensajes y Gestion de Teams
========================================================

Permite enviar mensajes a canales y chats de Microsoft Teams,
gestionar equipos, canales y reuniones via Microsoft Graph API.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TeamsConnector(BaseConnector):
    """Conector para Microsoft Teams: mensajes, canales y reuniones."""

    name = "teams"
    version = "1.0.0"
    description = "Envia mensajes y gestiona equipos y canales de Microsoft Teams"
    category = "communication"
    icon = "users"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://graph.microsoft.com/v1.0"
        self._access_token: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con Microsoft Graph API para Teams."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("TeamsConnector: credenciales OAuth2 no configuradas")
            return False

        # Extract access token from OAuth2 auth provider
        self._access_token = getattr(self._auth_provider, "_access_token", "")
        if not self._access_token and hasattr(self._auth_provider, "_credentials"):
            self._access_token = self._auth_provider._credentials.get("access_token", "")

        if not self._access_token:
            logger.error("TeamsConnector: access_token es requerido para Microsoft Graph API")
            return False

        # Set up HttpClient with Bearer token (Microsoft Graph uses Bearer auth)
        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=self._access_token)

        self._connected = True
        self._log_operation("connect", "OAuth2 configurado para Teams")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Teams.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "send_channel_message": self._send_channel_message,
            "send_chat_message": self._send_chat_message,
            "list_channels": self._list_channels,
            "create_channel": self._create_channel,
            "list_teams": self._list_teams,
            "create_meeting": self._create_meeting,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales OAuth2 esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Microsoft Teams."""
        self._connected = False
        self._access_token = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    def _refresh_token_if_needed(self) -> bool:
        """Refresh OAuth2 token if expired using the auth provider.

        Returns:
            True if token is valid (refreshed or not expired), False if refresh failed
        """
        if not self._auth_provider:
            return False

        if hasattr(self._auth_provider, "is_expired") and self._auth_provider.is_expired() and hasattr(self._auth_provider, "refresh"):
            refreshed = self._auth_provider.refresh()
            if refreshed:
                self._access_token = getattr(self._auth_provider, "_access_token", self._access_token)
                if self._http:
                    self._http.set_auth("Bearer", token=self._access_token)
                return True
            return False
        return True

    def _send_channel_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un mensaje a un canal de Teams.

        Args:
            params: Debe contener 'team_id', 'channel_id' y 'content'
        """
        team_id = params.get("team_id", "")
        channel_id = params.get("channel_id", "")
        content = params.get("content", "")
        content_type = params.get("content_type", "html")

        if not team_id or not channel_id or not content:
            return {"success": False, "error": "Parametros requeridos: team_id, channel_id, content"}

        self._log_operation("send_channel_message", f"team={team_id}, channel={channel_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            self._refresh_token_if_needed()

            payload: dict[str, Any] = {
                "body": {
                    "content": content,
                    "contentType": content_type,
                }
            }

            response = self._http.post(
                f"/teams/{team_id}/channels/{channel_id}/messages",
                json=payload,
            )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "message_id": data.get("id", ""),
                    "channel_id": data.get("channelId", channel_id),
                    "content": data.get("body", {}).get("content", ""),
                    "created_at": data.get("createdDateTime", ""),
                    "from": data.get("from", {}),
                }
            else:
                error_data = response.json() or {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_info.get("code", ""),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _send_chat_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un mensaje a un chat de Teams.

        Args:
            params: Debe contener 'chat_id' y 'content'
        """
        chat_id = params.get("chat_id", "")
        content = params.get("content", "")
        content_type = params.get("content_type", "html")

        if not chat_id or not content:
            return {"success": False, "error": "Parametros requeridos: chat_id, content"}

        self._log_operation("send_chat_message", f"chat={chat_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            self._refresh_token_if_needed()

            payload: dict[str, Any] = {
                "body": {
                    "content": content,
                    "contentType": content_type,
                }
            }

            response = self._http.post(
                f"/chats/{chat_id}/messages",
                json=payload,
            )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "message_id": data.get("id", ""),
                    "chat_id": data.get("chatId", chat_id),
                    "content": data.get("body", {}).get("content", ""),
                    "created_at": data.get("createdDateTime", ""),
                    "from": data.get("from", {}),
                }
            else:
                error_data = response.json() or {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_info.get("code", ""),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los canales de un equipo de Teams.

        Args:
            params: Debe contener 'team_id'
        """
        team_id = params.get("team_id", "")
        if not team_id:
            return {"success": False, "error": "Parametro requerido: team_id"}

        self._log_operation("list_channels", f"team={team_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            self._refresh_token_if_needed()

            response = self._http.get(f"/teams/{team_id}/channels")

            if response.ok:
                data = response.json() or {}
                channels = [
                    {
                        "id": ch.get("id", ""),
                        "display_name": ch.get("displayName", ""),
                        "description": ch.get("description", ""),
                        "membership_type": ch.get("membershipType", ""),
                        "created_at": ch.get("createdDateTime", ""),
                        "is_favorite_by_default": ch.get("isFavoriteByDefault", False),
                    }
                    for ch in data.get("value", [])
                ]
                return {
                    "success": True,
                    "channels": channels,
                    "team_id": team_id,
                    "total": len(channels),
                }
            else:
                error_data = response.json() or {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_info.get("code", ""),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _create_channel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un canal en un equipo de Teams.

        Args:
            params: Debe contener 'team_id', 'display_name' y opcionalmente 'description'
        """
        team_id = params.get("team_id", "")
        display_name = params.get("display_name", "")
        if not team_id or not display_name:
            return {"success": False, "error": "Parametros requeridos: team_id, display_name"}

        self._log_operation("create_channel", f"team={team_id}, name={display_name}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            self._refresh_token_if_needed()

            payload: dict[str, Any] = {
                "displayName": display_name,
            }
            if params.get("description"):
                payload["description"] = params["description"]
            if params.get("membership_type"):
                payload["membershipType"] = params["membership_type"]

            response = self._http.post(
                f"/teams/{team_id}/channels",
                json=payload,
            )

            if response.ok or response.status_code == 201:
                data = response.json() or {}
                return {
                    "success": True,
                    "channel_id": data.get("id", ""),
                    "display_name": data.get("displayName", display_name),
                    "description": data.get("description", ""),
                    "created_at": data.get("createdDateTime", ""),
                }
            else:
                error_data = response.json() or {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_info.get("code", ""),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_teams(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los equipos de Teams del usuario autenticado."""
        self._log_operation("list_teams")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            self._refresh_token_if_needed()

            response = self._http.get("/me/joinedTeams")

            if response.ok:
                data = response.json() or {}
                teams = [
                    {
                        "id": team.get("id", ""),
                        "display_name": team.get("displayName", ""),
                        "description": team.get("description", ""),
                        "is_archived": team.get("isArchived", False),
                    }
                    for team in data.get("value", [])
                ]
                return {
                    "success": True,
                    "teams": teams,
                    "total": len(teams),
                }
            else:
                error_data = response.json() or {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_info.get("code", ""),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _create_meeting(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una reunion en linea de Teams via Microsoft Graph API.

        Args:
            params: Debe contener 'subject', 'start_time', 'end_time' y opcionalmente 'attendees'
        """
        subject = params.get("subject", "")
        start_time = params.get("start_time", "")
        end_time = params.get("end_time", "")
        if not subject or not start_time or not end_time:
            return {"success": False, "error": "Parametros requeridos: subject, start_time, end_time"}

        self._log_operation("create_meeting", f"subject={subject}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            self._refresh_token_if_needed()

            # Microsoft Graph uses the /me/events endpoint to create online meetings
            start_timezone = params.get("start_timezone", "UTC")
            end_timezone = params.get("end_timezone", "UTC")

            payload: dict[str, Any] = {
                "subject": subject,
                "start": {
                    "dateTime": start_time,
                    "timeZone": start_timezone,
                },
                "end": {
                    "dateTime": end_time,
                    "timeZone": end_timezone,
                },
                "isOnlineMeeting": True,
                "onlineMeetingProvider": "teamsForBusiness",
            }

            if params.get("body"):
                payload["body"] = {"contentType": "html", "content": params["body"]}

            if params.get("attendees"):
                payload["attendees"] = [
                    {
                        "emailAddress": {"address": addr, "name": addr.split("@")[0] if "@" in addr else addr},
                        "type": "required",
                    }
                    for addr in params["attendees"]
                ]

            response = self._http.post("/me/events", json=payload)

            if response.ok or response.status_code == 201:
                data = response.json() or {}
                online_meeting = data.get("onlineMeeting", {})
                return {
                    "success": True,
                    "meeting_id": data.get("id", ""),
                    "subject": data.get("subject", subject),
                    "join_url": online_meeting.get("joinUrl", ""),
                    "start": data.get("start", {}),
                    "end": data.get("end", {}),
                    "organizer": data.get("organizer", {}),
                    "attendees": data.get("attendees", []),
                    "created_at": data.get("createdDateTime", ""),
                }
            else:
                error_data = response.json() or {}
                error_info = error_data.get("error", {})
                return {
                    "success": False,
                    "error": error_info.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_info.get("code", ""),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}


TEAMS_SCHEMA = ConnectorSchema(
    name="teams",
    version="1.0.0",
    description="Envia mensajes y gestiona equipos y canales de Microsoft Teams",
    category="communication",
    icon="users",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="send_channel_message", description="Envia un mensaje a un canal", category="write"),
        ActionDefinition(name="send_chat_message", description="Envia un mensaje a un chat", category="write"),
        ActionDefinition(name="list_channels", description="Lista canales del equipo", category="read"),
        ActionDefinition(name="create_channel", description="Crea un canal nuevo", category="write"),
        ActionDefinition(name="list_teams", description="Lista equipos de Teams", category="read"),
        ActionDefinition(name="create_meeting", description="Crea una reunion en linea", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="oauth2",
            required_fields=["client_id", "client_secret", "tenant_id"],
            description="Credenciales OAuth2 de Microsoft Azure AD",
        )
    ],
)
