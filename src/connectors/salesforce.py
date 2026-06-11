"""
Conector Salesforce — CRUD via Salesforce REST API
=====================================================

Permite crear, leer, actualizar y eliminar registros en
objetos de Salesforce via la REST API usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class SalesforceConnector(BaseConnector):
    """Conector para Salesforce: CRUD en objetos y consultas SOQL."""

    name = "salesforce"
    version = "1.0.0"
    description = "Gestiona registros en objetos de Salesforce via REST API"
    category = "crm_sales"
    icon = "database"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._instance_url: str = ""
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con Salesforce via OAuth2."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("SalesforceConnector: credenciales OAuth2 no configuradas")
            return False

        # Extract instance URL and access token from auth provider
        self._instance_url = getattr(self._auth_provider, "_instance_url", "") or "https://login.salesforce.com"
        access_token = getattr(self._auth_provider, "_access_token", "")

        if not access_token:
            # Try getting token from apply_auth
            auth_request = self._auth_provider.apply_auth({"headers": {}})
            access_token = auth_request.get("headers", {}).get("Authorization", "").replace("Bearer ", "")

        self._base_url = f"{self._instance_url}/services/data/v58.0"
        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=access_token)

        # Validate credentials with a lightweight API call
        try:
            response = self._http.get("", timeout=10)
            if response.status_code == 401:
                logger.error("SalesforceConnector: credenciales invalidas (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"SalesforceConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "OAuth2 configurado para Salesforce")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Salesforce.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "query": self._query,
            "create_record": self._create_record,
            "get_record": self._get_record,
            "update_record": self._update_record,
            "delete_record": self._delete_record,
            "describe_object": self._describe_object,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Salesforce esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Salesforce."""
        self._http = None
        self._connected = False
        self._instance_url = ""
        self._base_url = ""
        self._log_operation("disconnect")
        return True

    def _query(self, params: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta una consulta SOQL en Salesforce.

        Args:
            params: Debe contener 'soql' (consulta SOQL)
        """
        soql = params.get("soql", "")
        if not soql:
            return {"success": False, "error": "Parametro requerido: soql"}
        self._log_operation("query", f"soql={soql[:80]}...")

        try:
            response = self._http.get("/query", params={"q": soql})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "records": data.get("records", []),
                "totalSize": data.get("totalSize", 0),
                "done": data.get("done", True),
                "nextRecordsUrl": data.get("nextRecordsUrl", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_record(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un registro en un objeto de Salesforce.

        Args:
            params: Debe contener 'object' y 'fields' (dict de campos)
        """
        obj = params.get("object", "")
        fields = params.get("fields", {})
        if not obj or not fields:
            return {"success": False, "error": "Parametros requeridos: object, fields"}
        self._log_operation("create_record", f"object={obj}")

        try:
            response = self._http.post(f"/sobjects/{obj}", json=fields)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("id", ""),
                "object": obj,
                "errors": data.get("errors", []),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _get_record(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un registro por ID de objeto.

        Args:
            params: Debe contener 'object', 'record_id' y opcionalmente 'fields'
        """
        obj = params.get("object", "")
        record_id = params.get("record_id", "")
        fields = params.get("fields", "")
        if not obj or not record_id:
            return {"success": False, "error": "Parametros requeridos: object, record_id"}
        self._log_operation("get_record", f"object={obj}, id={record_id}")

        try:
            query_params: dict[str, Any] = {}
            if fields:
                query_params["fields"] = fields
            response = self._http.get(f"/sobjects/{obj}/{record_id}", params=query_params if query_params else None)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("Id", record_id),
                "object": obj,
                "fields": data,
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _update_record(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza un registro en un objeto de Salesforce.

        Args:
            params: Debe contener 'object', 'record_id' y 'fields'
        """
        obj = params.get("object", "")
        record_id = params.get("record_id", "")
        fields = params.get("fields", {})
        if not obj or not record_id or not fields:
            return {"success": False, "error": "Parametros requeridos: object, record_id, fields"}
        self._log_operation("update_record", f"object={obj}, id={record_id}")

        try:
            response = self._http.patch(f"/sobjects/{obj}/{record_id}", json=fields)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            # Salesforce returns 204 No Content on success
            return {"success": True, "id": record_id, "object": obj}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _delete_record(self, params: dict[str, Any]) -> dict[str, Any]:
        """Elimina un registro de un objeto de Salesforce.

        Args:
            params: Debe contener 'object' y 'record_id'
        """
        obj = params.get("object", "")
        record_id = params.get("record_id", "")
        if not obj or not record_id:
            return {"success": False, "error": "Parametros requeridos: object, record_id"}
        self._log_operation("delete_record", f"object={obj}, id={record_id}")

        try:
            response = self._http.delete(f"/sobjects/{obj}/{record_id}")
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            return {"success": True, "id": record_id, "deleted": True}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _describe_object(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene la metadata de un objeto de Salesforce.

        Args:
            params: Debe contener 'object'
        """
        obj = params.get("object", "")
        if not obj:
            return {"success": False, "error": "Parametro requerido: object"}
        self._log_operation("describe_object", f"object={obj}")

        try:
            response = self._http.get(f"/sobjects/{obj}/describe")
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "object": obj,
                "fields": data.get("fields", []),
                "recordTypeInfos": data.get("recordTypeInfos", []),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


SALESFORCE_SCHEMA = ConnectorSchema(
    name="salesforce",
    version="1.0.0",
    description="Gestiona registros en objetos de Salesforce via REST API",
    category="crm_sales",
    icon="database",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="query", description="Ejecuta consulta SOQL", category="read"),
        ActionDefinition(name="create_record", description="Crea un registro", category="write"),
        ActionDefinition(name="get_record", description="Obtiene un registro", category="read"),
        ActionDefinition(name="update_record", description="Actualiza un registro", category="write"),
        ActionDefinition(name="delete_record", description="Elimina un registro", category="delete"),
        ActionDefinition(name="describe_object", description="Describe metadata de objeto", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["client_id", "client_secret", "access_token"], description="Salesforce OAuth2")
    ],
)
