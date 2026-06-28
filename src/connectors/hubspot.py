"""
Conector HubSpot — CRM y Ventas via HubSpot API
===================================================

Permite gestionar contactos, empresas, deals, tickets y
engagements via la API de HubSpot CRM usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class HubspotConnector(BaseConnector):
    """Conector para HubSpot CRM: contactos, empresas, deals y tickets."""

    name = "hubspot"
    version = "1.0.0"
    description = "Gestiona contactos, empresas, deals y tickets via HubSpot CRM"
    category = "crm_sales"
    icon = "building"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.hubapi.com/crm/v3"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de HubSpot."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("HubspotConnector: credenciales no configuradas")
            return False

        # Extract access token from auth provider
        access_token = getattr(self._auth_provider, "_access_token", "") or getattr(self._auth_provider, "_api_key", "")
        if not access_token:
            # Try getting token from apply_auth
            auth_request = self._auth_provider.apply_auth({"headers": {}})
            access_token = auth_request.get("headers", {}).get("Authorization", "").replace("Bearer ", "")

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=access_token)

        # Validate credentials with a lightweight API call
        try:
            response = self._http.get("/contacts", params={"limit": 1})
            if response.status_code == 401:
                logger.error("HubspotConnector: credenciales invalidas (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"HubspotConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "Credenciales HubSpot configuradas")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector HubSpot.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_contact": self._create_contact,
            "get_contact": self._get_contact,
            "list_contacts": self._list_contacts,
            "create_deal": self._create_deal,
            "list_deals": self._list_deals,
            "create_ticket": self._create_ticket,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de HubSpot esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con HubSpot."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un contacto en HubSpot CRM.

        Args:
            params: Debe contener 'properties' (dict con email, firstname, lastname, etc.)
        """
        properties = params.get("properties", {})
        if not properties:
            return {"success": False, "error": "Parametro requerido: properties"}
        self._log_operation("create_contact", f"email={properties.get('email', 'N/A')}")

        try:
            response = self._http.post("/contacts", json={"properties": properties})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {"success": True, "id": data.get("id", ""), "properties": data.get("properties", properties)}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _get_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un contacto por ID o email.

        Args:
            params: Debe contener 'contact_id' o 'email'
        """
        contact_id = params.get("contact_id", "")
        email = params.get("email", "")
        if not contact_id and not email:
            return {"success": False, "error": "Requiere contact_id o email"}
        self._log_operation("get_contact", f"id={contact_id or email}")

        try:
            if contact_id:
                response = self._http.get(f"/contacts/{contact_id}")
            else:
                # Search by email using the search endpoint
                response = self._http.post("/contacts/search", json={
                    "filterGroups": [{"filters": [{"value": email, "propertyName": "email", "operator": "EQ"}]}],
                    "limit": 1,
                })
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            if not contact_id and email:
                # Extract from search results
                results = data.get("results", [])
                if not results:
                    return {"success": False, "error": f"Contacto no encontrado: {email}"}
                data = results[0]
            return {"success": True, "id": data.get("id", contact_id), "properties": data.get("properties", {})}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_contacts(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista contactos de HubSpot CRM.

        Args:
            params: Opcionalmente 'limit', 'after' y 'properties'
        """
        limit = params.get("limit", 20)
        after = params.get("after", "")
        properties = params.get("properties", "")
        self._log_operation("list_contacts", f"limit={limit}")

        try:
            query_params: dict[str, Any] = {"limit": limit}
            if after:
                query_params["after"] = after
            if properties:
                query_params["properties"] = properties

            response = self._http.get("/contacts", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "results": data.get("results", []),
                "total": len(data.get("results", [])),
                "paging": data.get("paging", {}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_deal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un deal en HubSpot CRM.

        Args:
            params: Debe contener 'properties' (dict con dealname, amount, dealstage, etc.)
        """
        properties = params.get("properties", {})
        if not properties:
            return {"success": False, "error": "Parametro requerido: properties"}
        self._log_operation("create_deal", f"deal={properties.get('dealname', 'N/A')}")

        try:
            response = self._http.post("/deals", json={"properties": properties})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {"success": True, "id": data.get("id", ""), "properties": data.get("properties", properties)}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_deals(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista deals de HubSpot CRM.

        Args:
            params: Opcionalmente 'limit', 'after' y 'properties'
        """
        limit = params.get("limit", 20)
        after = params.get("after", "")
        properties = params.get("properties", "")
        self._log_operation("list_deals", f"limit={limit}")

        try:
            query_params: dict[str, Any] = {"limit": limit}
            if after:
                query_params["after"] = after
            if properties:
                query_params["properties"] = properties

            response = self._http.get("/deals", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "results": data.get("results", []),
                "total": len(data.get("results", [])),
                "paging": data.get("paging", {}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_ticket(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un ticket en HubSpot CRM.

        Args:
            params: Debe contener 'properties' (dict con subject, content, hs_pipeline_stage, etc.)
        """
        properties = params.get("properties", {})
        if not properties:
            return {"success": False, "error": "Parametro requerido: properties"}
        self._log_operation("create_ticket", f"subject={properties.get('subject', 'N/A')}")

        try:
            response = self._http.post("/tickets", json={"properties": properties})
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {"success": True, "id": data.get("id", ""), "properties": data.get("properties", properties)}
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


HUBSPOT_SCHEMA = ConnectorSchema(
    name="hubspot",
    version="1.0.0",
    description="Gestiona contactos, empresas, deals y tickets via HubSpot CRM",
    category="crm_sales",
    icon="building",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_contact", description="Crea un contacto", category="write"),
        ActionDefinition(name="get_contact", description="Obtiene un contacto", category="read"),
        ActionDefinition(name="list_contacts", description="Lista contactos", category="read"),
        ActionDefinition(name="create_deal", description="Crea un deal", category="write"),
        ActionDefinition(name="list_deals", description="Lista deals", category="read"),
        ActionDefinition(name="create_ticket", description="Crea un ticket", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["access_token"], description="HubSpot OAuth2 Access Token")
    ],
)
