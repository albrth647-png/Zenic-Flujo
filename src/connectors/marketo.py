"""
Conector Marketo — Marketing Automation REST API
==================================================

Permite gestionar leads, campañas, emails y actividades
de marketing via Marketo REST API.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class MarketoConnector(BaseConnector):
    """Conector para Marketo REST API."""

    name = "marketo"
    version = "1.0.0"
    description = "Gestiona leads, campanas y actividades de marketing via Marketo"
    category = "marketing"
    icon = "trending-up"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client_id: str = ""
        self._client_secret: str = ""
        self._munchkin_id: str = ""
        self._base_url: str = ""
        self._access_token: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("MarketoConnector: credenciales no configuradas")
            return False

        if hasattr(self._auth_provider, "_credentials"):
            creds = self._auth_provider._credentials
            self._client_id = creds.get("client_id", "")
            self._client_secret = creds.get("client_secret", "")
            self._munchkin_id = creds.get("munchkin_id", "")

        if not self._client_id or not self._client_secret or not self._munchkin_id:
            logger.error("MarketoConnector: client_id, client_secret y munchkin_id requeridos")
            return False

        self._base_url = f"https://{self._munchkin_id}.mktorest.com"

        # Obtener access token via OAuth2
        try:
            identity_url = f"https://{self._munchkin_id}.mktorest.com/identity"
            auth_client = HttpClient(base_url=identity_url, connector_name=self.name)
            resp = auth_client.get(
                "/oauth/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            if resp.ok:
                data = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
                self._access_token = data.get("access_token", "")
                if not self._access_token:
                    return False

                self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
                self._http.set_header("Authorization", f"Bearer {self._access_token}")
                self._connected = True
                self._log_operation("connect", f"munchkin={self._munchkin_id}")
                return True
            return False
        except HTTPClientError as e:
            logger.error(f"MarketoConnector: error de conexion: {e}")
            return False
        except Exception as e:
            logger.error(f"MarketoConnector: error inesperado: {e}")
            return False

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "get_lead": self._get_lead,
            "create_lead": self._create_lead,
            "update_lead": self._update_lead,
            "get_campaigns": self._get_campaigns,
            "trigger_campaign": self._trigger_campaign,
            "get_activities": self._get_activities,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        self._connected = False
        self._access_token = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def _api_call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self._http:
            return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kwargs)
            data = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok and data.get("success", False):
                return {"success": True, "data": data.get("result", [])}
            return {"success": False, "error": data.get("errors", [{}])[0].get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_lead(self, params: dict[str, Any]) -> dict[str, Any]:
        lead_id = params.get("lead_id", "")
        email = params.get("email", "")
        if lead_id:
            return self._api_call("get", f"/rest/v1/lead/{lead_id}.json")
        if email:
            return self._api_call("get", "/rest/v1/leads.json", params={"filterType": "email", "filterValues": email})
        return {"success": False, "error": "lead_id o email requerido"}

    def _create_lead(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._api_call("post", "/rest/v1/leads.json", json={"action": "createOnly", "input": [params]})

    def _update_lead(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._api_call("post", "/rest/v1/leads.json", json={"action": "updateOnly", "input": [params]})

    def _get_campaigns(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._api_call("get", "/rest/v1/campaigns.json", params=params)

    def _trigger_campaign(self, params: dict[str, Any]) -> dict[str, Any]:
        campaign_id = params.get("campaign_id", "")
        if not campaign_id:
            return {"success": False, "error": "campaign_id requerido"}
        return self._api_call("post", f"/rest/v1/campaigns/{campaign_id}/trigger.json", json={"input": params.get("leads", [])})

    def _get_activities(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._api_call("get", "/rest/v1/activities.json", params=params)


MARKETO_SCHEMA = ConnectorSchema(
    name="marketo", version="1.0.0", description="Gestiona leads, campanas y actividades de marketing",
    category="marketing", icon="trending-up", author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="get_lead", description="Obtiene un lead por ID o email", category="read"),
        ActionDefinition(name="create_lead", description="Crea un nuevo lead", category="write"),
        ActionDefinition(name="update_lead", description="Actualiza un lead existente", category="write"),
        ActionDefinition(name="get_campaigns", description="Lista campanas disponibles", category="read"),
        ActionDefinition(name="trigger_campaign", description="Ejecuta una campana para leads", category="write"),
        ActionDefinition(name="get_activities", description="Obtiene actividades de lead", category="read"),
    ],
    auth_requirements=[AuthRequirement(auth_type="oauth2", required_fields=["client_id", "client_secret", "munchkin_id"])],
)
