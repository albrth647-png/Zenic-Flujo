"""Conector SumoLogic — Log Management and Analytics API."""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class SumoLogicConnector(BaseConnector):
    name = "sumologic"
    version = "1.0.0"
    description = "Gestiona logs, busquedas y dashboards en SumoLogic"
    category = "monitoring"
    icon = "activity"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._deployment: str = ""; self._access_id: str = ""; self._access_key: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._deployment = c.get("deployment", "us2")
            self._access_id = c.get("access_id", ""); self._access_key = c.get("access_key", "")
        if not self._access_id or not self._access_key:
            logger.error("SumoLogic: access_id y access_key requeridos"); return False
        self._http = HttpClient(base_url=f"https://api.{self._deployment}.sumologic.com/api/v1", connector_name=self.name)
        self._http.set_auth("Basic", username=self._access_id, password=self._access_key)
        self._connected = True; self._log_operation("connect", f"deployment={self._deployment}"); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"search": self._search, "get_collectors": self._get_collectors, "get_sources": self._get_sources,
                       "create_collector": self._create_collector, "get_dashboards": self._get_dashboards}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool: return bool(self._auth_provider and self._auth_provider.validate())
    def disconnect(self) -> bool: self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def _api(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kw)
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d.get("data", d)}
            return {"success": False, "error": d.get("errors", [{}])[0].get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _search(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("post", "/search/jobs", json={"query": p.get("query", ""), "from": p.get("from", "-1h"), "to": p.get("to", "now")})
    def _get_collectors(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/collectors", params=p)
    def _get_sources(self, p: dict[str, Any]) -> dict[str, Any]:
        coll_id = p.get("collector_id", ""); return self._api("get", f"/collectors/{coll_id}/sources", params=p) if coll_id else {"success": False, "error": "collector_id requerido"}
    def _create_collector(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("post", "/collectors", json=p)
    def _get_dashboards(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/dashboards", params=p)


SUMOLOGIC_SCHEMA = ConnectorSchema(name="sumologic", version="1.0.0", description="Gestiona logs y dashboards en SumoLogic",
    category="monitoring", icon="activity", author="Zenic-Flijo", actions=[
    ActionDefinition(name="search", description="Ejecuta una busqueda de logs", category="read"),
    ActionDefinition(name="get_collectors", description="Lista collectors", category="read"),
    ActionDefinition(name="get_sources", description="Lista fuentes de un collector", category="read"),
    ActionDefinition(name="create_collector", description="Crea un nuevo collector", category="write"),
    ActionDefinition(name="get_dashboards", description="Lista dashboards", category="read"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["access_id", "access_key"])])
