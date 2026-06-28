"""
Conector Zoho CRM — Gestion de CRM via Zoho API
===================================================

Permite gestionar leads, contactos, cuentas, deals y
actividades via la API de Zoho CRM usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class ZohoCrmConnector(BaseConnector):
    """Conector para Zoho CRM: leads, contactos, cuentas y deals."""

    name = "zoho_crm"
    version = "1.0.0"
    description = "Gestiona leads, contactos, cuentas y deals via Zoho CRM"
    category = "crm_sales"
    icon = "briefcase"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://www.zohoapis.com/crm/v3"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Zoho CRM."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("ZohoCrmConnector: credenciales OAuth2 no configuradas")
            return False

        # Extract access token from auth provider
        access_token = getattr(self._auth_provider, "_access_token", "")
        if not access_token:
            auth_request = self._auth_provider.apply_auth({"headers": {}})
            access_token = auth_request.get("headers", {}).get("Authorization", "").replace("Bearer ", "")

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=access_token)

        # Validate credentials with a lightweight API call
        try:
            response = self._http.get("/settings/modules")
            if response.status_code == 401:
                logger.error("ZohoCrmConnector: credenciales invalidas (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"ZohoCrmConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "OAuth2 configurado para Zoho CRM")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Zoho CRM.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_lead": self._create_lead,
            "list_leads": self._list_leads,
            "create_contact": self._create_contact,
            "list_contacts": self._list_contacts,
            "create_deal": self._create_deal,
            "search_records": self._search_records,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Zoho CRM esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Zoho CRM."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_lead(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un lead en Zoho CRM.

        Args:
            params: Debe contener 'data' (lista de dicts con campos del lead)
        """
        data = params.get("data", [])
        if not data:
            return {"success": False, "error": "Parametro requerido: data"}
        self._log_operation("create_lead", f"records={len(data)}")

        try:
            body = {"data": data}
            trigger = params.get("trigger", [])
            if trigger:
                body["trigger"] = trigger
            response = self._http.post("/Leads", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_leads(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista leads de Zoho CRM.

        Args:
            params: Opcionalmente 'page', 'per_page', 'fields'
        """
        page = params.get("page", 1)
        per_page = params.get("per_page", 20)
        fields = params.get("fields", "")
        self._log_operation("list_leads", f"page={page}")

        try:
            query_params: dict[str, Any] = {"page": page, "per_page": per_page}
            if fields:
                query_params["fields"] = fields
            response = self._http.get("/Leads", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
                "info": result.get("info", {"count": 0, "more_records": False}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un contacto en Zoho CRM.

        Args:
            params: Debe contener 'data' (lista de dicts con campos del contacto)
        """
        data = params.get("data", [])
        if not data:
            return {"success": False, "error": "Parametro requerido: data"}
        self._log_operation("create_contact", f"records={len(data)}")

        try:
            body = {"data": data}
            trigger = params.get("trigger", [])
            if trigger:
                body["trigger"] = trigger
            response = self._http.post("/Contacts", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _list_contacts(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista contactos de Zoho CRM.

        Args:
            params: Opcionalmente 'page', 'per_page'
        """
        page = params.get("page", 1)
        per_page = params.get("per_page", 20)
        self._log_operation("list_contacts", f"page={page}")

        try:
            query_params: dict[str, Any] = {"page": page, "per_page": per_page}
            response = self._http.get("/Contacts", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
                "info": result.get("info", {"count": 0, "more_records": False}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_deal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un deal en Zoho CRM.

        Args:
            params: Debe contener 'data' (lista de dicts con campos del deal)
        """
        data = params.get("data", [])
        if not data:
            return {"success": False, "error": "Parametro requerido: data"}
        self._log_operation("create_deal", f"records={len(data)}")

        try:
            body = {"data": data}
            trigger = params.get("trigger", [])
            if trigger:
                body["trigger"] = trigger
            response = self._http.post("/Deals", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _search_records(self, params: dict[str, Any]) -> dict[str, Any]:
        """Busca registros en un modulo de Zoho CRM.

        Args:
            params: Debe contener 'module' y 'criteria' (o 'email', 'phone', 'word')
        """
        module = params.get("module", "")
        criteria = params.get("criteria", "")
        email = params.get("email", "")
        phone = params.get("phone", "")
        word = params.get("word", "")
        if not module or not (criteria or email or phone or word):
            return {"success": False, "error": "Parametros requeridos: module, y al menos un criterio de busqueda"}
        self._log_operation("search_records", f"module={module}")

        try:
            query_params: dict[str, Any] = {}
            if criteria:
                query_params["criteria"] = criteria
            if email:
                query_params["email"] = email
            if phone:
                query_params["phone"] = phone
            if word:
                query_params["word"] = word
            if params.get("page"):
                query_params["page"] = params["page"]
            if params.get("per_page"):
                query_params["per_page"] = params["per_page"]

            response = self._http.get(f"/{module}/search", params=query_params)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            result = response.json()
            return {
                "success": True,
                "data": result.get("data", []),
                "info": result.get("info", {"count": 0, "more_records": False}),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


ZOHO_CRM_SCHEMA = ConnectorSchema(
    name="zoho_crm",
    version="1.0.0",
    description="Gestiona leads, contactos, cuentas y deals via Zoho CRM",
    category="crm_sales",
    icon="briefcase",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_lead", description="Crea un lead", category="write"),
        ActionDefinition(name="list_leads", description="Lista leads", category="read"),
        ActionDefinition(name="create_contact", description="Crea un contacto", category="write"),
        ActionDefinition(name="list_contacts", description="Lista contactos", category="read"),
        ActionDefinition(name="create_deal", description="Crea un deal", category="write"),
        ActionDefinition(name="search_records", description="Busca registros", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["client_id", "client_secret", "access_token"], description="Zoho OAuth2")
    ],
)
