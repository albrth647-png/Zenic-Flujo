"""
Conector Pipedrive — Gestion de Deals y CRM
===============================================

Permite gestionar deals, personas, organizaciones y
actividades via la API de Pipedrive usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class PipedriveConnector(BaseConnector):
    """Conector para Pipedrive: deals, personas, organizaciones y actividades."""

    name = "pipedrive"
    version = "1.0.0"
    description = "Gestiona deals, contactos y actividades via Pipedrive CRM"
    category = "crm_sales"
    icon = "trending-up"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.pipedrive.com/v1"
        self._http: HttpClient | None = None
        self._api_token: str = ""

    def connect(self) -> bool:
        """Establece conexion con la API de Pipedrive."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("PipedriveConnector: API Token no configurado")
            return False

        # Extract API token from auth provider
        self._api_token = getattr(self._auth_provider, "_api_key", "")
        if not self._api_token:
            # Try getting from apply_auth query params
            auth_request = self._auth_provider.apply_auth({"headers": {}, "params": {}})
            self._api_token = auth_request.get("params", {}).get("api_token", "")

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        # Pipedrive uses api_token as query param, but we can also set it as header
        self._http.set_header("Authorization", f"Bearer {self._api_token}")

        # Validate credentials with a lightweight API call
        try:
            response = self._http.get("/users/me", params={"api_token": self._api_token})
            if response.status_code == 401:
                logger.error("PipedriveConnector: API Token invalido (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"PipedriveConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "API Token configurado")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Pipedrive.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_deal": self._create_deal,
            "list_deals": self._list_deals,
            "create_person": self._create_person,
            "list_persons": self._list_persons,
            "create_organization": self._create_organization,
            "create_activity": self._create_activity,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el API Token de Pipedrive este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Pipedrive."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _add_token_param(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Add API token to query params for Pipedrive."""
        result = dict(params) if params else {}
        result["api_token"] = self._api_token
        return result

    def _create_deal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un deal en Pipedrive.

        Args:
            params: Debe contener 'title' y opcionalmente 'value', 'currency', 'stage_id'
        """
        title = params.get("title", "")
        if not title:
            return {"success": False, "error": "Parametro requerido: title"}
        self._log_operation("create_deal", f"title={title}")

        try:
            body = {k: v for k, v in params.items() if k != "api_token"}
            response = self._http.post("/deals", json=body, params={"api_token": self._api_token})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            deal_data = data.get("data", {})
            return {
                "success": True,
                "id": deal_data.get("id", ""),
                "title": deal_data.get("title", title),
                "status": deal_data.get("status", "open"),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_deals(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista deals de Pipedrive.

        Args:
            params: Opcionalmente 'limit', 'status', 'stage_id'
        """
        limit = params.get("limit", 20)
        start = params.get("start", 0)
        status = params.get("status", "")
        self._log_operation("list_deals", f"limit={limit}")

        try:
            query_params = self._add_token_param({"limit": limit, "start": start})
            if status:
                query_params["status"] = status
            response = self._http.get("/deals", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "data": data.get("data", []),
                "additional_data": data.get("additional_data", {"pagination": {"more_items_in_collection": False}}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_person(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una persona en Pipedrive.

        Args:
            params: Debe contener 'name' y opcionalmente 'email', 'phone'
        """
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        self._log_operation("create_person", f"name={name}")

        try:
            body = {k: v for k, v in params.items() if k != "api_token"}
            response = self._http.post("/persons", json=body, params={"api_token": self._api_token})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            person_data = data.get("data", {})
            return {
                "success": True,
                "id": person_data.get("id", ""),
                "name": person_data.get("name", name),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_persons(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista personas de Pipedrive.

        Args:
            params: Opcionalmente 'limit', 'search'
        """
        limit = params.get("limit", 20)
        start = params.get("start", 0)
        search = params.get("search", "")
        self._log_operation("list_persons", f"limit={limit}")

        try:
            query_params = self._add_token_param({"limit": limit, "start": start})
            if search:
                query_params["term"] = search
                response = self._http.get("/persons/search", params=query_params)
            else:
                response = self._http.get("/persons", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "data": data.get("data", []),
                "additional_data": data.get("additional_data", {"pagination": {"more_items_in_collection": False}}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_organization(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una organizacion en Pipedrive.

        Args:
            params: Debe contener 'name' y opcionalmente 'address', 'industry'
        """
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        self._log_operation("create_organization", f"name={name}")

        try:
            body = {k: v for k, v in params.items() if k != "api_token"}
            response = self._http.post("/organizations", json=body, params={"api_token": self._api_token})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            org_data = data.get("data", {})
            return {
                "success": True,
                "id": org_data.get("id", ""),
                "name": org_data.get("name", name),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_activity(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una actividad en Pipedrive.

        Args:
            params: Debe contener 'subject', 'type' y opcionalmente 'deal_id', 'due_date'
        """
        subject = params.get("subject", "")
        act_type = params.get("type", "")
        if not subject or not act_type:
            return {"success": False, "error": "Parametros requeridos: subject, type"}
        self._log_operation("create_activity", f"subject={subject}")

        try:
            body = {k: v for k, v in params.items() if k != "api_token"}
            response = self._http.post("/activities", json=body, params={"api_token": self._api_token})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            act_data = data.get("data", {})
            return {
                "success": True,
                "id": act_data.get("id", ""),
                "subject": act_data.get("subject", subject),
                "type": act_data.get("type", act_type),
                "done": act_data.get("done", False),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


PIPEDRIVE_SCHEMA = ConnectorSchema(
    name="pipedrive",
    version="1.0.0",
    description="Gestiona deals, contactos y actividades via Pipedrive CRM",
    category="crm_sales",
    icon="trending-up",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_deal", description="Crea un deal", category="write"),
        ActionDefinition(name="list_deals", description="Lista deals", category="read"),
        ActionDefinition(name="create_person", description="Crea una persona", category="write"),
        ActionDefinition(name="list_persons", description="Lista personas", category="read"),
        ActionDefinition(name="create_organization", description="Crea una organizacion", category="write"),
        ActionDefinition(name="create_activity", description="Crea una actividad", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_token"], description="Pipedrive API Token")
    ],
)
