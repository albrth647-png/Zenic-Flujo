"""Conector New Relic — APM Monitoring and Observability API."""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class NewRelicConnector(BaseConnector):
    name = "new_relic"
    version = "1.0.0"
    description = "Monitorea aplicaciones, servidores y metricas en New Relic"
    category = "monitoring"
    icon = "bar-chart"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""; self._account_id: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._api_key = c.get("api_key", ""); self._account_id = c.get("account_id", "")
        if not self._api_key or not self._account_id:
            logger.error("NewRelic: api_key y account_id requeridos"); return False
        self._http = HttpClient(base_url="https://api.newrelic.com/v2", connector_name=self.name)
        self._http.set_header("X-Api-Key", self._api_key)
        self._connected = True; self._log_operation("connect", f"account={self._account_id}"); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"get_applications": self._get_applications, "get_application": self._get_application,
                       "get_deployments": self._get_deployments, "get_servers": self._get_servers,
                       "list_alerts": self._list_alerts, "nrql_query": self._nrql_query}
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
            if resp.ok: return {"success": True, "data": d}
            return {"success": False, "error": d.get("error", {}).get("title", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_applications(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/applications.json", params=p)
    def _get_application(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/applications/{p.get('app_id', '')}.json")
    def _get_deployments(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/applications/{p.get('app_id', '')}/deployments.json")
    def _get_servers(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/servers.json", params=p)
    def _list_alerts(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/alerts_events.json", params=p)
    def _nrql_query(self, p: dict[str, Any]) -> dict[str, Any]:
        query = p.get("query", ""); return self._api("get", f"/accounts/{self._account_id}/query", params={"nrql": query}) if query else {"success": False, "error": "query requerido"}


NEWRELIC_SCHEMA = ConnectorSchema(name="new_relic", version="1.0.0", description="Monitorea apps y metricas en New Relic",
    category="monitoring", icon="bar-chart", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_applications", description="Lista aplicaciones monitoreadas", category="read"),
    ActionDefinition(name="get_application", description="Obtiene detalle de aplicacion", category="read"),
    ActionDefinition(name="get_deployments", description="Lista deployments de una app", category="read"),
    ActionDefinition(name="get_servers", description="Lista servidores monitoreados", category="read"),
    ActionDefinition(name="list_alerts", description="Lista eventos de alerta", category="read"),
    ActionDefinition(name="nrql_query", description="Ejecuta consulta NRQL", category="read"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["api_key", "account_id"])])
