"""
Conector Square — Pagos y Punto de Venta via Square API
==========================================================

Permite procesar pagos, gestionar clientes, inventario
y transacciones via la API de Square.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class SquareConnector(BaseConnector):
    """Conector para Square: pagos, clientes y punto de venta."""

    name = "square"
    version = "1.0.0"
    description = "Procesa pagos y gestiona clientes e inventario via Square"
    category = "finance_payments"
    icon = "shopping-cart"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://connect.squareup.com/v2"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Square."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("SquareConnector: Access Token no configurado")
            return False
        try:
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            # Square uses Bearer token (access_token)
            creds = self._auth_provider.get_credentials()
            access_token = creds.get("access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)

            # Set Square-specific headers
            self._http.set_header("Square-Version", "2024-01-18")
            environment = creds.get("environment", "production")
            if environment == "sandbox":
                self._http.set_header("X-Square-Environment", "sandbox")

            # Validate by listing locations (basic health check)
            resp = self._http.get("/locations")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "Access Token configurado y validado")
                return True
            else:
                # Still connect even if validation fails
                self._connected = True
                self._log_operation("connect", f"Access Token configurado (validacion fallo: HTTP {resp.status_code})")
                return True
        except HTTPClientError as e:
            logger.warning(f"SquareConnector: error durante conexion - {e}")
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            creds = self._auth_provider.get_credentials()
            access_token = creds.get("access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)
            self._http.set_header("Square-Version", "2024-01-18")
            self._connected = True
            self._log_operation("connect", f"Access Token configurado (validacion fallo: {e})")
            return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Square.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_payment": self._create_payment,
            "list_payments": self._list_payments,
            "create_customer": self._create_customer,
            "list_customers": self._list_customers,
            "create_refund": self._create_refund,
            "list_catalog": self._list_catalog,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Access Token de Square este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Square."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_payment(self, params: dict[str, Any]) -> dict[str, Any]:
        """Procesa un pago via Square.

        Args:
            params: Debe contener 'source_id', 'amount_money' (dict con amount y currency)
                    y opcionalmente 'idempotency_key'
        """
        source_id = params.get("source_id", "")
        amount_money = params.get("amount_money", {})
        if not source_id or not amount_money:
            return {"success": False, "error": "Parametros requeridos: source_id, amount_money"}
        self._log_operation("create_payment", f"amount={amount_money}")

        payload: dict[str, Any] = {
            "source_id": source_id,
            "amount_money": amount_money,
        }
        if params.get("idempotency_key"):
            payload["idempotency_key"] = params["idempotency_key"]
        if params.get("reference_id"):
            payload["reference_id"] = params["reference_id"]
        if params.get("note"):
            payload["note"] = params["note"]
        if params.get("autocomplete") is not None:
            payload["autocomplete"] = params["autocomplete"]
        if params.get("customer_id"):
            payload["customer_id"] = params["customer_id"]
        if params.get("location_id"):
            payload["location_id"] = params["location_id"]
        if params.get("app_fee_money"):
            payload["app_fee_money"] = params["app_fee_money"]

        try:
            resp = self._http.post("/payments", json=payload)
            if resp.ok:
                data = resp.json() or {}
                payment = data.get("payment", {})
                return {
                    "success": True,
                    "payment_id": payment.get("id", ""),
                    "status": payment.get("status", "COMPLETED"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("detail", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_payments(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista pagos de Square.

        Args:
            params: Opcionalmente 'begin_time', 'end_time', 'limit', 'cursor', 'location_id'
        """
        self._log_operation("list_payments")

        query_params: dict[str, Any] = {}
        if params.get("begin_time"):
            query_params["begin_time"] = params["begin_time"]
        if params.get("end_time"):
            query_params["end_time"] = params["end_time"]
        if params.get("limit"):
            query_params["limit"] = params["limit"]
        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]
        if params.get("location_id"):
            query_params["location_id"] = params["location_id"]
        if params.get("sort_order"):
            query_params["sort_order"] = params["sort_order"]

        try:
            resp = self._http.get("/payments", params=query_params if query_params else None)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "payments": data.get("payments", []),
                    "cursor": data.get("cursor", None),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("detail", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_customer(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un cliente en Square.

        Args:
            params: Debe contener 'email_address' o 'phone_number' y opcionalmente
                    'given_name', 'family_name'
        """
        email = params.get("email_address", "")
        phone = params.get("phone_number", "")
        if not email and not phone:
            return {"success": False, "error": "Requiere email_address o phone_number"}
        self._log_operation("create_customer", f"email={email or phone}")

        payload: dict[str, Any] = {}
        if email:
            payload["email_address"] = email
        if phone:
            payload["phone_number"] = phone
        if params.get("given_name"):
            payload["given_name"] = params["given_name"]
        if params.get("family_name"):
            payload["family_name"] = params["family_name"]
        if params.get("nickname"):
            payload["nickname"] = params["nickname"]
        if params.get("idempotency_key"):
            payload["idempotency_key"] = params["idempotency_key"]
        if params.get("address"):
            payload["address"] = params["address"]
        if params.get("birthday"):
            payload["birthday"] = params["birthday"]
        if params.get("company_name"):
            payload["company_name"] = params["company_name"]
        if params.get("reference_id"):
            payload["reference_id"] = params["reference_id"]
        if params.get("note"):
            payload["note"] = params["note"]

        try:
            resp = self._http.post("/customers", json=payload)
            if resp.ok:
                data = resp.json() or {}
                customer = data.get("customer", {})
                return {
                    "success": True,
                    "customer_id": customer.get("id", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("detail", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_customers(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista clientes de Square.

        Args:
            params: Opcionalmente 'cursor', 'limit', 'sort_field', 'sort_order'
        """
        self._log_operation("list_customers")

        query_params: dict[str, Any] = {}
        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]
        if params.get("limit"):
            query_params["limit"] = params["limit"]
        if params.get("sort_field"):
            query_params["sort_field"] = params["sort_field"]
        if params.get("sort_order"):
            query_params["sort_order"] = params["sort_order"]

        try:
            resp = self._http.get("/customers", params=query_params if query_params else None)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "customers": data.get("customers", []),
                    "cursor": data.get("cursor", None),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("detail", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_refund(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un reembolso en Square.

        Args:
            params: Debe contener 'payment_id', 'amount_money' y opcionalmente 'reason'
        """
        payment_id = params.get("payment_id", "")
        amount_money = params.get("amount_money", {})
        if not payment_id or not amount_money:
            return {"success": False, "error": "Parametros requeridos: payment_id, amount_money"}
        self._log_operation("create_refund", f"payment={payment_id}")

        payload: dict[str, Any] = {
            "payment_id": payment_id,
            "amount_money": amount_money,
        }
        if params.get("idempotency_key"):
            payload["idempotency_key"] = params["idempotency_key"]
        if params.get("reason"):
            payload["reason"] = params["reason"]
        if params.get("app_fee_money"):
            payload["app_fee_money"] = params["app_fee_money"]

        try:
            resp = self._http.post("/refunds", json=payload)
            if resp.ok:
                data = resp.json() or {}
                refund = data.get("refund", {})
                return {
                    "success": True,
                    "refund_id": refund.get("id", ""),
                    "status": refund.get("status", "COMPLETED"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("detail", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_catalog(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista objetos del catalogo de Square.

        Args:
            params: Opcionalmente 'types', 'limit', 'cursor'
        """
        self._log_operation("list_catalog")

        query_params: dict[str, Any] = {}
        if params.get("types"):
            query_params["types"] = params["types"]
        if params.get("limit"):
            query_params["limit"] = params["limit"]
        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]

        try:
            resp = self._http.get("/catalog/list", params=query_params if query_params else None)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "objects": data.get("objects", []),
                    "cursor": data.get("cursor", None),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("detail", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


SQUARE_SCHEMA = ConnectorSchema(
    name="square",
    version="1.0.0",
    description="Procesa pagos y gestiona clientes e inventario via Square",
    category="finance_payments",
    icon="shopping-cart",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_payment", description="Procesa un pago", category="write"),
        ActionDefinition(name="list_payments", description="Lista pagos", category="read"),
        ActionDefinition(name="create_customer", description="Crea un cliente", category="write"),
        ActionDefinition(name="list_customers", description="Lista clientes", category="read"),
        ActionDefinition(name="create_refund", description="Crea un reembolso", category="write"),
        ActionDefinition(name="list_catalog", description="Lista catalogo", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["access_token"], description="Square Access Token")
    ],
)
