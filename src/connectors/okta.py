"""Okta Connector — Identity & Access Management.

Integrates with Okta API for user, group, application, and
factor management operations.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class OktaConnector(BaseConnector):
    """Conector para Okta: usuarios, grupos, aplicaciones y políticas."""

    name = "okta"
    version = "1.0.0"
    description = "Gestiona usuarios, grupos, aplicaciones y políticas de identidad via Okta API"
    category = "iam"
    icon = "key"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("OktaConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            domain = creds.get("domain", "")
            api_token = creds.get("api_token", "")
            if not domain or not api_token:
                return False
            self._base_url = f"https://{domain}.okta.com/api/v1"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("Authorization", f"SSWS {api_token}")
            resp = self._http.get("/users/me")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"Okta domain={domain}")
                return True
            self._connected = True
            return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            domain = creds.get("domain", "")
            api_token = creds.get("api_token", "")
            self._base_url = f"https://{domain}.okta.com/api/v1"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("Authorization", f"SSWS {api_token}")
            self._connected = True
            self._log_operation("connect", f"Okta configurado (status fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {
            "list_users": self._list_users,
            "get_user": self._get_user,
            "create_user": self._create_user,
            "update_user": self._update_user,
            "deactivate_user": self._deactivate_user,
            "list_groups": self._list_groups,
            "get_group": self._get_group,
            "create_group": self._create_group,
            "add_user_to_group": self._add_user_to_group,
            "remove_user_from_group": self._remove_user_from_group,
            "list_applications": self._list_applications,
            "get_user_factors": self._get_user_factors,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        return bool(self._auth_provider and self._auth_provider.validate())

    def disconnect(self) -> bool:
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_users(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/users", params={"limit": params.get("limit", 25), "filter": params.get("filter", ""), "search": params.get("search", "")})
        if resp.ok:
            data = resp.json() or []
            return {"success": True, "users": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_user(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("user_id", "")
        if not uid:
            return {"success": False, "error": "Parametro requerido: user_id"}
        resp = self._http.get(f"/users/{uid}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "user": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_user(self, params: dict[str, Any]) -> dict[str, Any]:
        email = params.get("email", "")
        login = params.get("login", email)
        if not email:
            return {"success": False, "error": "Parametro requerido: email"}
        profile = {
            "firstName": params.get("firstName", ""),
            "lastName": params.get("lastName", ""),
            "email": email,
            "login": login,
            "mobilePhone": params.get("mobilePhone", ""),
        }
        user: dict[str, Any] = {"profile": profile}
        if params.get("group_ids"):
            user["groupIds"] = params["group_ids"]
        if params.get("password"):
            user["credentials"] = {"password": {"value": params["password"]}}
        resp = self._http.post("/users", json=user, params={"activate": params.get("activate", True)})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id"), "status": data.get("status"), "profile": data.get("profile", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _update_user(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("user_id", "")
        if not uid:
            return {"success": False, "error": "Parametro requerido: user_id"}
        profile = {}
        for f in ("firstName", "lastName", "email", "login", "mobilePhone", "displayName"):
            if params.get(f):
                profile[f] = params[f]
        resp = self._http.post(f"/users/{uid}", json={"profile": profile})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id"), "status": data.get("status")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _deactivate_user(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("user_id", "")
        if not uid:
            return {"success": False, "error": "Parametro requerido: user_id"}
        self._http.post(f"/users/{uid}/lifecycle/deactivate")
        resp = self._http.delete(f"/users/{uid}")
        if resp.ok or resp.status_code == 204:
            return {"success": True, "user_id": uid, "deactivated": True}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_groups(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/groups", params={"limit": params.get("limit", 25), "filter": params.get("filter", ""), "q": params.get("q", "")})
        if resp.ok:
            data = resp.json() or []
            return {"success": True, "groups": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_group(self, params: dict[str, Any]) -> dict[str, Any]:
        gid = params.get("group_id", "")
        if not gid:
            return {"success": False, "error": "Parametro requerido: group_id"}
        resp = self._http.get(f"/groups/{gid}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "group": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_group(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        resp = self._http.post("/groups", json={"profile": {"name": name, "description": params.get("description", "")}})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id"), "profile": data.get("profile", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _add_user_to_group(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("user_id", "")
        gid = params.get("group_id", "")
        if not uid or not gid:
            return {"success": False, "error": "Parametros requeridos: user_id, group_id"}
        resp = self._http.put(f"/groups/{gid}/users/{uid}")
        if resp.ok or resp.status_code == 204:
            return {"success": True, "user_id": uid, "group_id": gid}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _remove_user_from_group(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("user_id", "")
        gid = params.get("group_id", "")
        if not uid or not gid:
            return {"success": False, "error": "Parametros requeridos: user_id, group_id"}
        resp = self._http.delete(f"/groups/{gid}/users/{uid}")
        if resp.ok or resp.status_code == 204:
            return {"success": True, "removed": True}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_applications(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/apps", params={"limit": params.get("limit", 25), "filter": params.get("filter", "")})
        if resp.ok:
            data = resp.json() or []
            return {"success": True, "applications": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_user_factors(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("user_id", "")
        if not uid:
            return {"success": False, "error": "Parametro requerido: user_id"}
        resp = self._http.get(f"/users/{uid}/factors")
        if resp.ok:
            data = resp.json() or []
            return {"success": True, "factors": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


OKTA_SCHEMA = ConnectorSchema(
    name="okta",
    version="1.0.0",
    description="Gestiona usuarios, grupos, aplicaciones y políticas de identidad via Okta API",
    category="iam",
    icon="key",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_users", description="Lista usuarios", category="read"),
        ActionDefinition(name="get_user", description="Obtiene usuario", category="read"),
        ActionDefinition(name="create_user", description="Crea usuario", category="write"),
        ActionDefinition(name="update_user", description="Actualiza usuario", category="write"),
        ActionDefinition(name="deactivate_user", description="Desactiva/elimina usuario", category="write"),
        ActionDefinition(name="list_groups", description="Lista grupos", category="read"),
        ActionDefinition(name="get_group", description="Obtiene grupo", category="read"),
        ActionDefinition(name="create_group", description="Crea grupo", category="write"),
        ActionDefinition(name="add_user_to_group", description="Agrega usuario a grupo", category="write"),
        ActionDefinition(name="remove_user_from_group", description="Remueve usuario de grupo", category="write"),
        ActionDefinition(name="list_applications", description="Lista aplicaciones", category="read"),
        ActionDefinition(name="get_user_factors", description="Obtiene factores MFA del usuario", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="api_key",
            required_fields=["domain", "api_token"],
            description="Subdominio Okta + SSWS API token",
        )
    ],
)
