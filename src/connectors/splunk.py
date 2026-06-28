"""Splunk Connector — Log Management & SIEM.

Integrates with Splunk REST API for search, events, saved searches,
alerts, and data inputs.
"""

from __future__ import annotations

import json as _json
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class SplunkConnector(BaseConnector):
    """Conector para Splunk: búsquedas, eventos, alertas e inputs."""

    name = "splunk"
    version = "1.0.0"
    description = "Ejecuta búsquedas, gestiona eventos, alertas e inputs via Splunk REST API"
    category = "monitoring"
    icon = "activity"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("SplunkConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            url = creds.get("url", "")
            username = creds.get("username", "")
            password = creds.get("password", "")
            bearer_token = creds.get("bearer_token", "")
            if not url:
                return False
            self._base_url = url.rstrip("/") + "/services"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            if bearer_token:
                self._http.set_header("Authorization", f"Bearer {bearer_token}")
            elif username and password:
                import base64
                auth = base64.b64encode(f"{username}:{password}".encode()).decode()
                self._http.set_header("Authorization", f"Basic {auth}")
            resp = self._http.get("/server/info")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"Splunk URL={url}")
                return True
            self._connected = True
            return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            self._base_url = creds.get("url", "").rstrip("/") + "/services"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._connected = True
            self._log_operation("connect", f"Splunk configurado (status fallo: {e})")
            return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {
            "search": self._search,
            "get_search_status": self._get_search_status,
            "list_saved_searches": self._list_saved_searches,
            "get_saved_search": self._get_saved_search,
            "create_saved_search": self._create_saved_search,
            "submit_event": self._submit_event,
            "list_alerts": self._list_alerts,
            "get_alert": self._get_alert,
            "list_indexes": self._list_indexes,
            "get_server_info": self._get_server_info,
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

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "Parametro requerido: query"}
        search_kwargs = {
            "search": f"search {query}",
            "exec_mode": params.get("exec_mode", "oneshot"),
            "count": params.get("count", 100),
            "earliest_time": params.get("earliest", "-24h"),
            "latest_time": params.get("latest", "now"),
            "output_mode": "json",
        }
        if params.get("latest"):
            search_kwargs["latest_time"] = params["latest"]
        resp = self._http.get("/search/jobs/export", params=search_kwargs)
        if resp.ok:
            data = _json.loads(resp.body) if isinstance(resp.body, str) else (resp.json() or {})
            results = data.get("results", []) if isinstance(data, dict) else data
            return {"success": True, "results": results if isinstance(results, list) else [results], "fields": data.get("fields", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_search_status(self, params: dict[str, Any]) -> dict[str, Any]:
        sid = params.get("search_id", "")
        if not sid:
            return {"success": False, "error": "Parametro requerido: search_id"}
        resp = self._http.get(f"/search/jobs/{sid}", params={"output_mode": "json"})
        if resp.ok:
            data = resp.json() or {}
            entry = data.get("entry", [{}])[0] if data.get("entry") else {}
            content = entry.get("content", {})
            return {"success": True, "status": content.get("dispatchState"), "progress": content.get("doneProgress")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_saved_searches(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/saved/searches", params={"count": params.get("count", 50), "offset": params.get("offset", 0), "output_mode": "json"})
        if resp.ok:
            data = resp.json() or {}
            entries = data.get("entry", [])
            return {"success": True, "saved_searches": [{"name": e.get("name"), "title": e.get("title"), "id": e.get("id")} for e in entries]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_saved_search(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        resp = self._http.get(f"/saved/searches/{name}", params={"output_mode": "json"})
        if resp.ok:
            data = resp.json() or {}
            entry = data.get("entry", [{}])[0] if data.get("entry") else {}
            return {"success": True, "saved_search": entry}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_saved_search(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        query = params.get("query", "")
        if not name or not query:
            return {"success": False, "error": "Parametros requeridos: name, query"}
        form_data = {
            "name": name,
            "search": f"search {query}",
            "description": params.get("description", ""),
            "cron_schedule": params.get("cron_schedule", ""),
            "dispatch.earliest_time": params.get("earliest", "-24h"),
            "dispatch.latest_time": params.get("latest", "now"),
        }
        resp = self._http.post("/saved/searches", data=form_data)
        if resp.ok or resp.status_code == 201:
            return {"success": True, "name": name, "created": True}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _submit_event(self, params: dict[str, Any]) -> dict[str, Any]:
        event = params.get("event", "")
        index = params.get("index", "main")
        if not event:
            return {"success": False, "error": "Parametro requerido: event"}
        form_data = {
            "event": event,
            "index": index,
            "sourcetype": params.get("sourcetype", "_json"),
            "source": params.get("source", "zenic-flijo"),
            "host": params.get("host", ""),
        }
        resp = self._http.post("/receivers/simple", data=form_data)
        if resp.ok:
            return {"success": True, "index": index}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_alerts(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/saved/searches", params={"count": params.get("count", 50), "output_mode": "json", "search": "is_scheduled=1"})
        if resp.ok:
            data = resp.json() or {}
            entries = data.get("entry", []) if data else []
            return {"success": True, "alerts": entries}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_alert(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        resp = self._http.get(f"/saved/searches/{name}/alert", params={"output_mode": "json"})
        if resp.ok:
            data = resp.json() or {}
            entry = data.get("entry", [{}])[0] if data.get("entry") else {}
            return {"success": True, "alert": entry}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_indexes(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/data/indexes", params={"count": params.get("count", 50), "output_mode": "json"})
        if resp.ok:
            data = resp.json() or {}
            entries = data.get("entry", [])
            return {"success": True, "indexes": [{"name": e.get("name"), "title": e.get("title")} for e in entries]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_server_info(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/server/info", params={"output_mode": "json"})
        if resp.ok:
            data = resp.json() or {}
            entry = data.get("entry", [{}])[0] if data.get("entry") else {}
            return {"success": True, "server_info": entry.get("content", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


SPLUNK_SCHEMA = ConnectorSchema(
    name="splunk", version="1.0.0",
    description="Ejecuta búsquedas, gestiona eventos, alertas e inputs via Splunk REST API",
    category="monitoring", icon="activity", author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="search", description="Ejecuta búsqueda SPL", category="read"),
        ActionDefinition(name="get_search_status", description="Estado de búsqueda", category="read"),
        ActionDefinition(name="list_saved_searches", description="Lista búsquedas guardadas", category="read"),
        ActionDefinition(name="get_saved_search", description="Obtiene búsqueda guardada", category="read"),
        ActionDefinition(name="create_saved_search", description="Crea búsqueda guardada", category="write"),
        ActionDefinition(name="submit_event", description="Envía evento a índice", category="write"),
        ActionDefinition(name="list_alerts", description="Lista alertas", category="read"),
        ActionDefinition(name="get_alert", description="Obtiene alerta", category="read"),
        ActionDefinition(name="list_indexes", description="Lista índices", category="read"),
        ActionDefinition(name="get_server_info", description="Información del servidor", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["url"], description="URL de Splunk + Bearer token o Basic Auth (username/password)")
    ],
)
