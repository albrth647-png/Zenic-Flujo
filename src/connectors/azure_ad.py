"""Conector Azure AD — Microsoft Entra ID Graph API."""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class AzureADConnector(BaseConnector):
    name = "azure_ad"
    version = "1.0.0"
    description = "Gestiona usuarios, grupos y aplicaciones en Azure AD (Microsoft Graph)"
    category = "identity"
    icon = "shield"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tenant_id: str = ""
        self._client_id: str = ""
        self._client_secret: str = ""
        self._access_token: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials
            self._tenant_id = c.get("tenant_id", "")
            self._client_id = c.get("client_id", "")
            self._client_secret = c.get("client_secret", "")
        if not self._tenant_id or not self._client_id or not self._client_secret:
            logger.error("AzureAD: tenant_id, client_id y client_secret requeridos")
            return False
        try:
            auth_client = HttpClient(base_url=f"https://login.microsoftonline.com/{self._tenant_id}", connector_name=self.name)
            resp = auth_client.post("/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": self._client_id,
                "client_secret": self._client_secret, "scope": "https://graph.microsoft.com/.default",
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            if resp.ok:
                d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
                self._access_token = d.get("access_token", "")
                if not self._access_token: return False
                self._http = HttpClient(base_url="https://graph.microsoft.com/v1.0", connector_name=self.name)
                self._http.set_header("Authorization", f"Bearer {self._access_token}")
                self._connected = True
                self._log_operation("connect", f"tenant={self._tenant_id[:8]}...")
                return True
            return False
        except HTTPClientError as e: logger.error(f"AzureAD: {e}"); return False
        except Exception as e: logger.error(f"AzureAD: {e}"); return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"get_user": self._get_user, "list_users": self._list_users, "create_user": self._create_user,
                       "get_group": self._get_group, "list_groups": self._list_groups, "add_user_to_group": self._add_user_to_group,
                       "list_applications": self._list_applications}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool: return bool(self._auth_provider and self._auth_provider.validate())
    def disconnect(self) -> bool: self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    def _api(self, method: str, path: str, **kw: Any) -> dict:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kw)
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d.get("value", d)}
            return {"success": False, "error": d.get("error", {}).get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_user(self, p: dict) -> dict: return self._api("get", f"/users/{p.get('user_id', p.get('user_principal_name', ''))}")
    def _list_users(self, p: dict) -> dict: return self._api("get", "/users", params=p)
    def _create_user(self, p: dict) -> dict: return self._api("post", "/users", json=p)
    def _get_group(self, p: dict) -> dict: return self._api("get", f"/groups/{p.get('group_id', '')}")
    def _list_groups(self, p: dict) -> dict: return self._api("get", "/groups", params=p)
    def _add_user_to_group(self, p: dict) -> dict:
        return self._api("post", f"/groups/{p.get('group_id', '')}/members/$ref", json={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{p.get('user_id', '')}"})
    def _list_applications(self, p: dict) -> dict: return self._api("get", "/applications", params=p)


AZURE_AD_SCHEMA = ConnectorSchema(name="azure_ad", version="1.0.0", description="Gestiona usuarios, grupos y aplicaciones en Azure AD", category="identity", icon="shield", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_user", description="Obtiene un usuario por ID o UPN", category="read"),
    ActionDefinition(name="list_users", description="Lista usuarios del directorio", category="read"),
    ActionDefinition(name="create_user", description="Crea un nuevo usuario", category="write"),
    ActionDefinition(name="get_group", description="Obtiene un grupo por ID", category="read"),
    ActionDefinition(name="list_groups", description="Lista grupos del directorio", category="read"),
    ActionDefinition(name="add_user_to_group", description="Agrega un usuario a un grupo", category="write"),
    ActionDefinition(name="list_applications", description="Lista aplicaciones registradas", category="read"),
], auth_requirements=[AuthRequirement(auth_type="oauth2", required_fields=["tenant_id", "client_id", "client_secret"])])
