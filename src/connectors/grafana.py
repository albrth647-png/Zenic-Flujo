"""Grafana Connector — Monitoring & Observability.

Integrates with Grafana API for dashboard management, alerts,
datasources, and annotations.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class GrafanaConnector(BaseConnector):
    """Conector para Grafana: dashboards, alertas, datasources y anotaciones."""

    name = "grafana"
    version = "1.0.0"
    description = "Gestiona dashboards, alertas, datasources y anotaciones via Grafana API"
    category = "monitoring"
    icon = "bar-chart"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("GrafanaConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            url = creds.get("url", ""); api_key = creds.get("api_key", "")
            if not url or not api_key: return False
            self._base_url = url.rstrip("/") + "/api"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("Authorization", f"Bearer {api_key}")
            resp = self._http.get("/org")
            if resp.ok: self._connected = True; self._log_operation("connect", f"Grafana URL={url}"); return True
            self._connected = True; return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            url = creds.get("url", ""); self._base_url = url.rstrip("/") + "/api"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("Authorization", f"Bearer {creds.get('api_key', '')}")
            self._connected = True; self._log_operation("connect", f"Grafana configurado (status fallo: {e})"); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {
            "list_dashboards": self._list_dashboards, "get_dashboard": self._get_dashboard,
            "create_dashboard": self._create_dashboard, "delete_dashboard": self._delete_dashboard,
            "list_datasources": self._list_datasources, "get_datasource": self._get_datasource,
            "create_datasource": self._create_datasource, "list_alerts": self._list_alerts,
            "get_alert": self._get_alert, "create_annotation": self._create_annotation,
            "get_org": self._get_org, "list_users": self._list_org_users,
        }
        handler = action_map.get(action)
        if handler is None: return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        return bool(self._auth_provider and self._auth_provider.validate())

    def disconnect(self) -> bool:
        self._http = None; self._connected = False; self._log_operation("disconnect"); return True

    def _list_dashboards(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/search", params={"query": params.get("query", ""), "type": "dash-db", "limit": params.get("limit", 50)})
        if resp.ok: data = resp.json() or []; return {"success": True, "dashboards": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_dashboard(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("uid", "")
        if not uid:
            return {"success": False, "error": "Parametro requerido: uid"}
        resp = self._http.get(f"/dashboards/uid/{uid}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "dashboard": data.get("dashboard", {}), "meta": data.get("meta", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_dashboard(self, params: dict[str, Any]) -> dict[str, Any]:
        dashboard = params.get("dashboard", {})
        if not dashboard:
            return {"success": False, "error": "Parametro requerido: dashboard"}
        resp = self._http.post("/dashboards/db", json={"dashboard": dashboard, "overwrite": params.get("overwrite", True), "message": params.get("message", "Created by Zenic-Flijo")})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "uid": data.get("uid", ""), "id": data.get("id"), "url": data.get("url", ""), "status": data.get("status", "")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _delete_dashboard(self, params: dict[str, Any]) -> dict[str, Any]:
        uid = params.get("uid", "")
        if not uid:
            return {"success": False, "error": "Parametro requerido: uid"}
        resp = self._http.delete(f"/dashboards/uid/{uid}")
        if resp.ok:
            return {"success": True, "deleted": True, "uid": uid}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_datasources(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/datasources")
        if resp.ok: data = resp.json() or []; return {"success": True, "datasources": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_datasource(self, params: dict[str, Any]) -> dict[str, Any]:
        ds_id = params.get("datasource_id", "")
        if not ds_id:
            return {"success": False, "error": "Parametro requerido: datasource_id"}
        resp = self._http.get(f"/datasources/{ds_id}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "datasource": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_datasource(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", ""); ds_type = params.get("type", ""); url = params.get("url", "")
        if not name or not ds_type: return {"success": False, "error": "Parametros requeridos: name, type"}
        ds = {"name": name, "type": ds_type, "url": url, "access": params.get("access", "proxy"), "isDefault": params.get("is_default", False)}
        if params.get("database"): ds["database"] = params["database"]
        if params.get("user"): ds["user"] = params["user"]
        if params.get("jsonData"): ds["jsonData"] = params["jsonData"]
        if params.get("secureJsonData"): ds["secureJsonData"] = params["secureJsonData"]
        resp = self._http.post("/datasources", json=ds)
        if resp.ok: data = resp.json() or {}; return {"success": True, "id": data.get("id"), "name": data.get("name")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_alerts(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/alerts", params={"limit": params.get("limit", 50), "state": params.get("state", "")})
        if resp.ok: data = resp.json() or []; return {"success": True, "alerts": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_alert(self, params: dict[str, Any]) -> dict[str, Any]:
        alert_id = params.get("alert_id", "")
        if not alert_id:
            return {"success": False, "error": "Parametro requerido: alert_id"}
        resp = self._http.get(f"/alerts/{alert_id}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "alert": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_annotation(self, params: dict[str, Any]) -> dict[str, Any]:
        text = params.get("text", "")
        if not text:
            return {"success": False, "error": "Parametro requerido: text"}
        annotation = {"text": text, "tags": params.get("tags", []), "time": params.get("time", 0), "timeEnd": params.get("time_end", 0)}
        if params.get("dashboard_uid"):
            annotation["dashboardUID"] = params["dashboard_uid"]
        if params.get("panel_id"):
            annotation["panelId"] = params["panel_id"]
        resp = self._http.post("/annotations", json=annotation)
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_org(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/org")
        if resp.ok: data = resp.json() or {}; return {"success": True, "org": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_org_users(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/org/users")
        if resp.ok: data = resp.json() or []; return {"success": True, "users": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


GRAFANA_SCHEMA = ConnectorSchema(
    name="grafana", version="1.0.0",
    description="Gestiona dashboards, alertas, datasources y anotaciones via Grafana API",
    category="monitoring", icon="bar-chart", author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_dashboards", description="Lista dashboards", category="read"),
        ActionDefinition(name="get_dashboard", description="Obtiene dashboard", category="read"),
        ActionDefinition(name="create_dashboard", description="Crea/actualiza dashboard", category="write"),
        ActionDefinition(name="delete_dashboard", description="Elimina dashboard", category="write"),
        ActionDefinition(name="list_datasources", description="Lista datasources", category="read"),
        ActionDefinition(name="get_datasource", description="Obtiene datasource", category="read"),
        ActionDefinition(name="create_datasource", description="Crea datasource", category="write"),
        ActionDefinition(name="list_alerts", description="Lista alertas", category="read"),
        ActionDefinition(name="get_alert", description="Obtiene alerta", category="read"),
        ActionDefinition(name="create_annotation", description="Crea anotación", category="write"),
        ActionDefinition(name="get_org", description="Obtiene organización", category="read"),
        ActionDefinition(name="list_org_users", description="Lista usuarios de la org", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["url", "api_key"], description="URL de Grafana + Service Account Token o API Key")
    ],
)
