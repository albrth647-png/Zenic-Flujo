"""Conector Freshdesk — Customer Support Ticketing API."""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class FreshdeskConnector(BaseConnector):
    name = "freshdesk"
    version = "1.0.0"
    description = "Gestiona tickets, contactos y soluciones en Freshdesk"
    category = "support"
    icon = "headphones"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._domain: str = ""
        self._api_key: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            return False
        if hasattr(self._auth_provider, "_credentials"):
            creds = self._auth_provider._credentials
            self._domain = creds.get("domain", "")
            self._api_key = creds.get("api_key", "")
        if not self._domain or not self._api_key:
            logger.error("FreshdeskConnector: domain y api_key requeridos")
            return False
        self._http = HttpClient(base_url=f"https://{self._domain}.freshdesk.com/api/v2", connector_name=self.name)
        self._http.set_auth("Basic", username=self._api_key, password="X")
        self._connected = True
        self._log_operation("connect", f"domain={self._domain}")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"get_ticket": self._get_ticket, "create_ticket": self._create_ticket, "update_ticket": self._update_ticket,
                       "list_tickets": self._list_tickets, "get_contact": self._get_contact, "create_contact": self._create_contact}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool:
        return bool(self._auth_provider and self._auth_provider.validate())

    def disconnect(self) -> bool:
        self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    def _get(self, path: str, **kw: Any) -> dict:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = self._http.get(path, **kw); d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            return {"success": resp.ok, "data": d if resp.ok else d.get("errors", [{}])[0].get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _post(self, path: str, **kw: Any) -> dict:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = self._http.post(path, **kw); d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            return {"success": resp.ok, "data": d if resp.ok else d.get("errors", [{}])[0].get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_ticket(self, p: dict) -> dict: return self._get(f"/tickets/{p.get('ticket_id', '')}")
    def _create_ticket(self, p: dict) -> dict: return self._post("/tickets", json=p)
    def _update_ticket(self, p: dict) -> dict: return self._get(f"/tickets/{p.get('ticket_id', '')}", json=p.get("data", {}))
    def _list_tickets(self, p: dict) -> dict: return self._get("/tickets", params=p)
    def _get_contact(self, p: dict) -> dict: return self._get(f"/contacts/{p.get('contact_id', '')}")
    def _create_contact(self, p: dict) -> dict: return self._post("/contacts", json=p)


FRESHDESK_SCHEMA = ConnectorSchema(name="freshdesk", version="1.0.0", description="Gestiona tickets y contactos en Freshdesk", category="support", icon="headphones", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_ticket", description="Obtiene un ticket por ID", category="read"),
    ActionDefinition(name="create_ticket", description="Crea un nuevo ticket", category="write"),
    ActionDefinition(name="update_ticket", description="Actualiza un ticket existente", category="write"),
    ActionDefinition(name="list_tickets", description="Lista tickets con filtros", category="read"),
    ActionDefinition(name="get_contact", description="Obtiene un contacto por ID", category="read"),
    ActionDefinition(name="create_contact", description="Crea un nuevo contacto", category="write"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["domain", "api_key"])])
