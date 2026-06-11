"""
Conector Datadog — Metricas y Eventos via Datadog API
=========================================================

Permite enviar metricas, eventos, logs y gestionar
dashboards y monitores via la Datadog API.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class DatadogConnector(BaseConnector):
    """Conector para Datadog: metricas, eventos y monitoreo."""

    name = "datadog"
    version = "1.0.0"
    description = "Envia metricas, eventos y gestiona monitores via Datadog"
    category = "devops_monitoring"
    icon = "activity"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.datadoghq.com/api/v1"
        self._http: HttpClient | None = None
        self._api_key: str = ""
        self._application_key: str = ""

    def _get_credentials(self) -> tuple[str, str]:
        """Extract API key and Application key from the auth provider.

        Returns:
            Tuple of (api_key, application_key)
        """
        api_key = ""
        app_key = ""

        if not self._auth_provider:
            return "", ""

        # Try to extract via apply_auth on a dummy request
        request: dict[str, Any] = {"headers": {}, "params": {}}
        self._auth_provider.apply_auth(request)

        # Check headers for API keys
        headers = request.get("headers", {})
        if "DD-API-KEY" in headers:
            api_key = headers["DD-API-KEY"]
        if "DD-APPLICATION-KEY" in headers:
            app_key = headers["DD-APPLICATION-KEY"]

        # Check X-API-Key header (might be the api_key)
        if not api_key and "X-API-Key" in headers:
            api_key = headers["X-API-Key"]

        # Check query params
        params = request.get("params", {})
        if not api_key and "api_key" in params:
            api_key = params["api_key"]
        if not app_key and "application_key" in params:
            app_key = params["application_key"]

        # Try direct attribute access for common patterns
        if not api_key:
            for attr in ("_api_key", "_api_key_value", "_key"):
                if hasattr(self._auth_provider, attr):
                    val = getattr(self._auth_provider, attr, "")
                    if isinstance(val, str) and val:
                        api_key = val
                        break

        if not app_key:
            for attr in ("_application_key", "_app_key", "_app_key_value"):
                if hasattr(self._auth_provider, attr):
                    val = getattr(self._auth_provider, attr, "")
                    if isinstance(val, str) and val:
                        app_key = val
                        break

        # For APIKeyAuth, the api_key might be stored as a combined format
        # like "api_key:app_key" or just be the api_key
        if not app_key and api_key and ":" in api_key:
            parts = api_key.split(":", 1)
            api_key = parts[0]
            app_key = parts[1]

        return api_key, app_key

    def connect(self) -> bool:
        """Establece conexion con la Datadog API."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("DatadogConnector: API Key y Application Key no configuradas")
            return False

        api_key, app_key = self._get_credentials()
        if not api_key:
            logger.error("DatadogConnector: No se pudo extraer la API Key del auth provider")
            return False

        self._api_key = api_key
        self._application_key = app_key

        self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
        # Datadog uses DD-API-KEY and DD-APPLICATION-KEY headers
        self._http.set_header("DD-API-KEY", self._api_key)
        if self._application_key:
            self._http.set_header("DD-APPLICATION-KEY", self._application_key)

        # Validate credentials by fetching the authentication validation endpoint
        try:
            resp = self._http.get("/validate")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "API Key configurada y validada")
                return True
            else:
                logger.error(f"DatadogConnector: Validacion de API Key fallida - {resp.status_code}")
                self._http = None
                return False
        except HTTPClientError as e:
            logger.error(f"DatadogConnector: Error validando API Key - {e}")
            self._http = None
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Datadog.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "submit_metric": self._submit_metric,
            "query_metrics": self._query_metrics,
            "post_event": self._post_event,
            "list_monitors": self._list_monitors,
            "create_monitor": self._create_monitor,
            "list_dashboards": self._list_dashboards,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Datadog esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Datadog."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _submit_metric(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia una metrica a Datadog.

        Args:
            params: Debe contener 'series' (lista de dicts con metric, points, tags, etc.)
        """
        series = params.get("series", [])
        if not series:
            return {"success": False, "error": "Parametro requerido: series"}
        self._log_operation("submit_metric", f"series={len(series)}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        body: dict[str, Any] = {"series": series}

        try:
            resp = self._http.post("/series", json=body)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Datadog API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "status": data.get("status", "ok"),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"DatadogConnector submit_metric error: {e}")
            return {"success": False, "error": str(e)}

    def _query_metrics(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta metricas de Datadog.

        Args:
            params: Debe contener 'from_ts', 'to_ts' y 'query'
        """
        query = params.get("query", "")
        from_ts = params.get("from_ts", 0)
        to_ts = params.get("to_ts", 0)
        if not query or not from_ts or not to_ts:
            return {"success": False, "error": "Parametros requeridos: from_ts, to_ts, query"}
        self._log_operation("query_metrics", f"query={query[:80]}...")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {
            "query": query,
            "from": from_ts,
            "to": to_ts,
        }

        try:
            resp = self._http.get("/query", params=query_params)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Datadog API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "series": data.get("series", []),
                    "from_date": data.get("from_date", from_ts),
                    "to_date": data.get("to_date", to_ts),
                    "query": data.get("query", query),
                    "res_type": data.get("res_type", ""),
                    "message": data.get("message", ""),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"DatadogConnector query_metrics error: {e}")
            return {"success": False, "error": str(e)}

    def _post_event(self, params: dict[str, Any]) -> dict[str, Any]:
        """Publica un evento en Datadog.

        Args:
            params: Debe contener 'title' y 'text', opcionalmente 'priority', 'tags', 'alert_type',
                    'date_happened', 'source_type_name', 'aggregation_key', 'host'
        """
        title = params.get("title", "")
        text = params.get("text", "")
        if not title or not text:
            return {"success": False, "error": "Parametros requeridos: title, text"}
        self._log_operation("post_event", f"title={title[:50]}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        body: dict[str, Any] = {"title": title, "text": text}
        for key in ("priority", "tags", "alert_type", "date_happened",
                     "source_type_name", "aggregation_key", "host", "device_name"):
            if key in params:
                body[key] = params[key]

        try:
            resp = self._http.post("/events", json=body)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Datadog API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                event_data = data.get("event", data)
                return {
                    "success": True,
                    "event_id": event_data.get("id", ""),
                    "status": data.get("status", "ok"),
                    "url": event_data.get("url", ""),
                    "title": event_data.get("title", title),
                    "text": event_data.get("text", text),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"DatadogConnector post_event error: {e}")
            return {"success": False, "error": str(e)}

    def _list_monitors(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista monitores de Datadog.

        Args:
            params: Opcionalmente 'group_states', 'name', 'tags', 'monitor_tags',
                    'with_downtimes', 'page', 'per_page'
        """
        self._log_operation("list_monitors")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("group_states", "name", "tags", "monitor_tags",
                     "with_downtimes", "page", "per_page", "id_offset"):
            if key in params:
                query_params[key] = params[key]

        try:
            resp = self._http.get("/monitor", params=query_params if query_params else None)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Datadog API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, list):
                return {
                    "success": True,
                    "monitors": data,
                    "total_count": len(data),
                }
            if isinstance(data, dict):
                return {
                    "success": True,
                    "monitors": data.get("monitors", data.get("data", [])),
                    "total_count": data.get("total_count", 0),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"DatadogConnector list_monitors error: {e}")
            return {"success": False, "error": str(e)}

    def _create_monitor(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un monitor en Datadog.

        Args:
            params: Debe contener 'type', 'query' y opcionalmente 'options' (dict con thresholds, etc.),
                    'name', 'message', 'tags', 'priority'
        """
        monitor_type = params.get("type", "")
        query = params.get("query", "")
        if not monitor_type or not query:
            return {"success": False, "error": "Parametros requeridos: type, query"}
        self._log_operation("create_monitor", f"type={monitor_type}")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        body: dict[str, Any] = {"type": monitor_type, "query": query}
        for key in ("name", "message", "options", "tags", "priority",
                     "restricted_roles", "notify_no_data", "no_data_timeframe",
                     "notify_audit", "renotify_interval", "timeout_h",
                     "new_host_delay", "require_full_window",
                     "locked", "silenced"):
            if key in params:
                body[key] = params[key]

        try:
            resp = self._http.post("/monitor", json=body)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Datadog API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "id": data.get("id", ""),
                    "type": data.get("type", monitor_type),
                    "query": data.get("query", query),
                    "name": data.get("name", ""),
                    "state": data.get("state", {"overall_state": "No Data"}),
                    "created": data.get("created", ""),
                    "modified": data.get("modified", ""),
                    "options": data.get("options", {}),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"DatadogConnector create_monitor error: {e}")
            return {"success": False, "error": str(e)}

    def _list_dashboards(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista dashboards de Datadog.

        Args:
            params: Opcionalmente 'filter[shared]', 'count', 'start'
        """
        self._log_operation("list_dashboards")

        if not self._http:
            return {"success": False, "error": "Connector not connected"}

        query_params: dict[str, Any] = {}
        for key in ("filter[shared]", "count", "start"):
            if key in params:
                query_params[key] = params[key]

        try:
            resp = self._http.get("/dashboard", params=query_params if query_params else None)
            if not resp.ok:
                return {
                    "success": False,
                    "error": f"Datadog API error: {resp.status_code}",
                    "details": resp.body if isinstance(resp.body, (dict, str)) else None,
                }

            data = resp.json()
            if isinstance(data, dict):
                return {
                    "success": True,
                    "dashboards": data.get("dashboards", []),
                    "total_count": len(data.get("dashboards", [])),
                }
            return {"success": True, "data": data}

        except HTTPClientError as e:
            logger.error(f"DatadogConnector list_dashboards error: {e}")
            return {"success": False, "error": str(e)}


DATADOG_SCHEMA = ConnectorSchema(
    name="datadog",
    version="1.0.0",
    description="Envia metricas, eventos y gestiona monitores via Datadog",
    category="devops_monitoring",
    icon="activity",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="submit_metric", description="Envia una metrica", category="write"),
        ActionDefinition(name="query_metrics", description="Consulta metricas", category="read"),
        ActionDefinition(name="post_event", description="Publica un evento", category="write"),
        ActionDefinition(name="list_monitors", description="Lista monitores", category="read"),
        ActionDefinition(name="create_monitor", description="Crea un monitor", category="write"),
        ActionDefinition(name="list_dashboards", description="Lista dashboards", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_key", "application_key"], description="Datadog API Key + Application Key")
    ],
)
