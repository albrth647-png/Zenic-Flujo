"""Zendesk Connector — Customer Support & Ticketing.

Integrates with Zendesk Support API for ticket management,
user management, and help center operations.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class ZendeskConnector(BaseConnector):
    """Conector para Zendesk: tickets, usuarios y centro de ayuda."""

    name = "zendesk"
    version = "1.0.0"
    description = "Gestiona tickets, usuarios y artículos del centro de ayuda via Zendesk Support API"
    category = "support"
    icon = "headphones"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("ZendeskConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            subdomain = creds.get("subdomain", "")
            email = creds.get("email", "")
            api_token = creds.get("api_token", "")
            if not subdomain or not api_token:
                return False
            self._base_url = f"https://{subdomain}.zendesk.com/api/v2"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            auth_str = f"{email}/token:{api_token}" if email else f"{api_token}:X"
            self._http.set_auth("Basic", username=auth_str.split(":")[0], password=":".join(auth_str.split(":")[1:]) if ":" in auth_str else api_token)
            resp = self._http.get("/tickets.json", params={"per_page": 1})
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"Zendesk subdomain={subdomain}")
                return True
            self._connected = True
            self._log_operation("connect", "Zendesk configurado (sin verificación)")
            return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            subdomain = creds.get("subdomain", "")
            email = creds.get("email", "")
            api_token = creds.get("api_token", "")
            self._base_url = f"https://{subdomain}.zendesk.com/api/v2"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            if email and api_token:
                self._http.set_auth("Basic", username=f"{email}/token", password=api_token)
            self._connected = True
            self._log_operation("connect", f"Zendesk configurado (status check fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "create_ticket": self._create_ticket,
            "get_ticket": self._get_ticket,
            "update_ticket": self._update_ticket,
            "list_tickets": self._list_tickets,
            "search_tickets": self._search_tickets,
            "add_comment": self._add_comment,
            "list_organizations": self._list_organizations,
            "create_user": self._create_user,
            "get_user": self._get_user,
            "list_articles": self._list_articles,
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
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_ticket(self, params: dict[str, Any]) -> dict[str, Any]:
        subject = params.get("subject", "")
        comment = params.get("comment", "")
        if not subject or not comment:
            return {"success": False, "error": "Parametros requeridos: subject, comment"}
        ticket = {"subject": subject, "comment": {"body": comment}}
        for field in ("priority", "type", "status", "assignee_id", "group_id", "organization_id", "tags", "custom_fields"):
            if params.get(field):
                ticket[field] = params[field]
        resp = self._http.post("/tickets.json", json={"ticket": ticket})
        if resp.ok:
            data = (resp.json() or {}).get("ticket", {})
            return {"success": True, "id": data.get("id"), "subject": data.get("subject"), "status": data.get("status", "new"), "priority": data.get("priority", "normal"), "url": data.get("url", "")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_ticket(self, params: dict[str, Any]) -> dict[str, Any]:
        ticket_id = params.get("ticket_id", "")
        if not ticket_id:
            return {"success": False, "error": "Parametro requerido: ticket_id"}
        resp = self._http.get(f"/tickets/{ticket_id}.json")
        if resp.ok:
            data = (resp.json() or {}).get("ticket", {})
            return {"success": True, "ticket": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _update_ticket(self, params: dict[str, Any]) -> dict[str, Any]:
        ticket_id = params.get("ticket_id", "")
        if not ticket_id:
            return {"success": False, "error": "Parametro requerido: ticket_id"}
        ticket = {}
        for field in ("subject", "priority", "type", "status", "assignee_id", "group_id", "tags", "custom_fields"):
            if params.get(field):
                ticket[field] = params[field]
        resp = self._http.put(f"/tickets/{ticket_id}.json", json={"ticket": ticket})
        if resp.ok:
            data = (resp.json() or {}).get("ticket", {})
            return {"success": True, "id": data.get("id"), "status": data.get("status")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_tickets(self, params: dict[str, Any]) -> dict[str, Any]:
        query_params = {"per_page": params.get("per_page", 25), "page": params.get("page", 1)}
        if params.get("status"):
            query_params["status"] = params["status"]
        resp = self._http.get("/tickets.json", params=query_params)
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "tickets": data.get("tickets", []), "count": data.get("count", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _search_tickets(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Parametro requerido: query"}
        resp = self._http.get("/search.json", params={"query": f"type:ticket {query}", "per_page": params.get("per_page", 25)})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "results": data.get("results", []), "count": data.get("count", 0)}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _add_comment(self, params: dict[str, Any]) -> dict[str, Any]:
        ticket_id = params.get("ticket_id", "")
        comment = params.get("comment", "")
        if not ticket_id or not comment:
            return {"success": False, "error": "Parametros requeridos: ticket_id, comment"}
        resp = self._http.put(f"/tickets/{ticket_id}.json", json={"ticket": {"comment": {"body": comment, "public": params.get("public", True)}}})
        if resp.ok:
            return {"success": True, "ticket_id": ticket_id}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_organizations(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/organizations.json", params={"per_page": params.get("per_page", 25), "page": params.get("page", 1)})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "organizations": data.get("organizations", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_user(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        email = params.get("email", "")
        if not name or not email:
            return {"success": False, "error": "Parametros requeridos: name, email"}
        user = {"name": name, "email": email}
        for field in ("role", "organization_id", "phone", "notes", "tags"):
            if params.get(field):
                user[field] = params[field]
        resp = self._http.post("/users.json", json={"user": user})
        if resp.ok:
            data = (resp.json() or {}).get("user", {})
            return {"success": True, "id": data.get("id"), "name": data.get("name"), "email": data.get("email"), "role": data.get("role")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_user(self, params: dict[str, Any]) -> dict[str, Any]:
        user_id = params.get("user_id", "")
        if not user_id:
            return {"success": False, "error": "Parametro requerido: user_id"}
        resp = self._http.get(f"/users/{user_id}.json")
        if resp.ok:
            data = (resp.json() or {}).get("user", {})
            return {"success": True, "user": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_articles(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/help_center/articles.json", params={"per_page": params.get("per_page", 25), "page": params.get("page", 1), "locale": params.get("locale", "")})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "articles": data.get("articles", []), "count": data.get("count", 0)}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


ZENDESK_SCHEMA = ConnectorSchema(
    name="zendesk",
    version="1.0.0",
    description="Gestiona tickets, usuarios y artículos del centro de ayuda via Zendesk Support API",
    category="support",
    icon="headphones",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_ticket", description="Crea ticket de soporte", category="write"),
        ActionDefinition(name="get_ticket", description="Obtiene ticket por ID", category="read"),
        ActionDefinition(name="update_ticket", description="Actualiza ticket", category="write"),
        ActionDefinition(name="list_tickets", description="Lista tickets", category="read"),
        ActionDefinition(name="search_tickets", description="Busca tickets", category="read"),
        ActionDefinition(name="add_comment", description="Agrega comentario a ticket", category="write"),
        ActionDefinition(name="list_organizations", description="Lista organizaciones", category="read"),
        ActionDefinition(name="create_user", description="Crea usuario", category="write"),
        ActionDefinition(name="get_user", description="Obtiene usuario", category="read"),
        ActionDefinition(name="list_articles", description="Lista artículos del centro de ayuda", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["subdomain", "email", "api_token"], description="Subdominio Zendesk + email + API token")
    ],
)
