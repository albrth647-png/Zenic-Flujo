"""Conector PagerDuty — Incident Management API."""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class PagerDutyConnector(BaseConnector):
    name = "pagerduty"
    version = "1.0.0"
    description = "Gestiona incidentes, alertas y on-call en PagerDuty"
    category = "monitoring"
    icon = "alert-triangle"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""; self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._api_key = c.get("api_key", "")
        if not self._api_key: logger.error("PagerDuty: api_key requerida"); return False
        self._http = HttpClient(base_url="https://api.pagerduty.com", connector_name=self.name)
        self._http.set_header("Authorization", f"Token token={self._api_key}")
        self._http.set_header("Accept", "application/vnd.pagerduty+json;version=2")
        self._connected = True; self._log_operation("connect"); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"trigger_incident": self._trigger_incident, "list_incidents": self._list_incidents,
                       "get_incident": self._get_incident, "resolve_incident": self._resolve_incident,
                       "list_services": self._list_services, "list_escalation_policies": self._list_escalation_policies,
                       "list_oncalls": self._list_oncalls}
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
            return {"success": False, "error": d.get("error", {}).get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _trigger_incident(self, p: dict[str, Any]) -> dict[str, Any]:
        return self._api("post", "/incidents", json={"incident": {"type": "incident", "title": p.get("title", ""),
            "service": {"id": p.get("service_id", ""), "type": "service_reference"},
            "urgency": p.get("urgency", "high"), "body": {"type": "incident_body", "details": p.get("details", "")}}})
    def _list_incidents(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/incidents", params=p)
    def _get_incident(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/incidents/{p.get('incident_id', '')}")
    def _resolve_incident(self, p: dict[str, Any]) -> dict[str, Any]:
        return self._api("put", f"/incidents/{p.get('incident_id', '')}", json={"incident": {"type": "incident", "status": "resolved"}})
    def _list_services(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/services", params=p)
    def _list_escalation_policies(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/escalation_policies", params=p)
    def _list_oncalls(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/oncalls", params=p)


PAGERDUTY_SCHEMA = ConnectorSchema(name="pagerduty", version="1.0.0", description="Gestiona incidentes y alertas en PagerDuty",
    category="monitoring", icon="alert-triangle", author="Zenic-Flijo", actions=[
    ActionDefinition(name="trigger_incident", description="Dispara un nuevo incidente", category="write"),
    ActionDefinition(name="list_incidents", description="Lista incidentes con filtros", category="read"),
    ActionDefinition(name="get_incident", description="Obtiene detalle de incidente", category="read"),
    ActionDefinition(name="resolve_incident", description="Resuelve un incidente", category="write"),
    ActionDefinition(name="list_services", description="Lista servicios", category="read"),
    ActionDefinition(name="list_escalation_policies", description="Lista politicas de escalacion", category="read"),
    ActionDefinition(name="list_oncalls", description="Lista turnos on-call", category="read"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["api_key"])])
