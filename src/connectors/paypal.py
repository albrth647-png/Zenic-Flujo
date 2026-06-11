"""
Conector PayPal — Pagos y Transacciones via PayPal API
=========================================================

Permite crear, capturar y reembolsar pagos, gestionar
ordenes y consultar transacciones via la API de PayPal.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class PaypalConnector(BaseConnector):
    """Conector para PayPal: pagos, ordenes y transacciones."""

    name = "paypal"
    version = "1.0.0"
    description = "Crea y gestiona pagos, ordenes y transacciones via PayPal"
    category = "finance_payments"
    icon = "credit-card"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api-m.paypal.com"
        self._sandbox_url: str = "https://api-m.sandbox.paypal.com"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de PayPal."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("PaypalConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            sandbox = creds.get("sandbox", False)
            base_url = self._sandbox_url if sandbox else self._base_url

            self._http = HttpClient(
                base_url=base_url,
                connector_name=self.name,
            )

            # PayPal OAuth2: obtain access token using client_id/client_secret
            client_id = creds.get("client_id", "")
            client_secret = creds.get("client_secret", "")
            access_token = creds.get("access_token", "")

            if access_token:
                # Use provided access token directly
                self._http.set_auth("Bearer", token=access_token)
            elif client_id and client_secret:
                # Obtain access token via OAuth2 client credentials flow
                token_resp = self._http.post(
                    "/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                if token_resp.ok:
                    token_data = token_resp.json() or {}
                    new_token = token_data.get("access_token", "")
                    if new_token:
                        self._http.set_auth("Bearer", token=new_token)
                else:
                    # Fallback to Basic auth
                    self._http.set_auth("Basic", username=client_id, password=client_secret)
                    logger.warning(f"PaypalConnector: fallo al obtener token OAuth2 - {token_resp.status_code}")

            self._connected = True
            self._log_operation("connect", "OAuth2 configurado para PayPal")
            return True
        except HTTPClientError as e:
            logger.warning(f"PaypalConnector: error durante conexion - {e}")
            # Still set up client with available credentials
            creds = self._auth_provider.get_credentials() if self._auth_provider else {}
            sandbox = creds.get("sandbox", False)
            base_url = self._sandbox_url if sandbox else self._base_url
            self._http = HttpClient(
                base_url=base_url,
                connector_name=self.name,
            )
            access_token = creds.get("access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)
            self._connected = True
            self._log_operation("connect", f"OAuth2 configurado (token request fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector PayPal.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_order": self._create_order,
            "capture_order": self._capture_order,
            "get_order": self._get_order,
            "refund_payment": self._refund_payment,
            "list_transactions": self._list_transactions,
            "get_payment_details": self._get_payment_details,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de PayPal esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con PayPal."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una orden de pago en PayPal.

        Args:
            params: Debe contener 'intent' (CAPTURE/AUTHORIZE), 'amount', 'currency'
        """
        intent = params.get("intent", "CAPTURE")
        amount = params.get("amount", "")
        currency = params.get("currency", "USD")
        if not amount:
            return {"success": False, "error": "Parametro requerido: amount"}
        self._log_operation("create_order", f"amount={amount} {currency}")

        payload: dict[str, Any] = {
            "intent": intent,
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": str(amount),
                    }
                }
            ],
        }
        if params.get("description"):
            payload["purchase_units"][0]["description"] = params["description"]
        if params.get("custom_id"):
            payload["purchase_units"][0]["custom_id"] = params["custom_id"]
        if params.get("return_url") or params.get("cancel_url"):
            app_context: dict[str, str] = {}
            if params.get("return_url"):
                app_context["return_url"] = params["return_url"]
            if params.get("cancel_url"):
                app_context["cancel_url"] = params["cancel_url"]
            payload["application_context"] = app_context

        try:
            resp = self._http.post("/v2/checkout/orders", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "order_id": data.get("id", ""),
                    "status": data.get("status", "CREATED"),
                    "intent": intent,
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                detail = error_body.get("message", "")
                if not detail and isinstance(error_body.get("details"), list):
                    details_list = error_body.get("details", [])
                    detail = details_list[0].get("description", str(resp.body)) if details_list else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _capture_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Captura una orden de pago autorizada.

        Args:
            params: Debe contener 'order_id'
        """
        order_id = params.get("order_id", "")
        if not order_id:
            return {"success": False, "error": "Parametro requerido: order_id"}
        self._log_operation("capture_order", f"order={order_id}")

        try:
            resp = self._http.post(
                f"/v2/checkout/orders/{order_id}/capture",
                json={},
            )
            if resp.ok:
                data = resp.json() or {}
                capture_id = ""
                if data.get("purchase_units"):
                    pu = data["purchase_units"][0]
                    payments = pu.get("payments", {})
                    captures = payments.get("captures", [])
                    if captures:
                        capture_id = captures[0].get("id", "")
                return {
                    "success": True,
                    "order_id": order_id,
                    "status": data.get("status", "COMPLETED"),
                    "capture_id": capture_id,
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                detail = error_body.get("message", str(resp.body))
                if isinstance(error_body.get("details"), list):
                    details_list = error_body.get("details", [])
                    detail = details_list[0].get("description", detail) if details_list else detail
                return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_order(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene los detalles de una orden.

        Args:
            params: Debe contener 'order_id'
        """
        order_id = params.get("order_id", "")
        if not order_id:
            return {"success": False, "error": "Parametro requerido: order_id"}
        self._log_operation("get_order", f"order={order_id}")

        try:
            resp = self._http.get(f"/v2/checkout/orders/{order_id}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "order_id": data.get("id", order_id),
                    "status": data.get("status", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                detail = error_body.get("message", str(resp.body))
                return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _refund_payment(self, params: dict[str, Any]) -> dict[str, Any]:
        """Reembolsa un pago capturado.

        Args:
            params: Debe contener 'capture_id' y opcionalmente 'amount', 'note'
        """
        capture_id = params.get("capture_id", "")
        if not capture_id:
            return {"success": False, "error": "Parametro requerido: capture_id"}
        self._log_operation("refund_payment", f"capture={capture_id}")

        payload: dict[str, Any] = {}
        if params.get("amount") and params.get("currency"):
            payload["amount"] = {
                "value": str(params["amount"]),
                "currency_code": params.get("currency", "USD"),
            }
        if params.get("note"):
            payload["note"] = params["note"]

        try:
            resp = self._http.post(
                f"/v2/payments/captures/{capture_id}/refund",
                json=payload if payload else {},
            )
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "refund_id": data.get("id", ""),
                    "status": data.get("status", "COMPLETED"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                detail = error_body.get("message", str(resp.body))
                if isinstance(error_body.get("details"), list):
                    details_list = error_body.get("details", [])
                    detail = details_list[0].get("description", detail) if details_list else detail
                return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_transactions(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista transacciones de PayPal.

        Args:
            params: Opcionalmente 'start_date', 'end_date', 'limit', 'page'
        """
        self._log_operation("list_transactions")

        query_params: dict[str, Any] = {}
        start_date = params.get("start_date", "")
        end_date = params.get("end_date", "")
        if start_date:
            query_params["start_date"] = start_date
        if end_date:
            query_params["end_date"] = end_date
        if params.get("limit"):
            query_params["page_size"] = params["limit"]
        if params.get("page"):
            query_params["page"] = params["page"]

        try:
            resp = self._http.get("/v1/reporting/transactions", params=query_params if query_params else None)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "transactions": data.get("transaction_details", []),
                    "total": data.get("total_items", 0),
                    "page": data.get("page", 1),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                detail = error_body.get("message", str(resp.body))
                return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_payment_details(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene los detalles de un pago.

        Args:
            params: Debe contener 'payment_id'
        """
        payment_id = params.get("payment_id", "")
        if not payment_id:
            return {"success": False, "error": "Parametro requerido: payment_id"}
        self._log_operation("get_payment_details", f"payment={payment_id}")

        try:
            resp = self._http.get(f"/v2/payments/captures/{payment_id}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "payment_id": data.get("id", payment_id),
                    "status": data.get("status", ""),
                    "data": data,
                }
            else:
                # Try authorizations endpoint as fallback
                resp2 = self._http.get(f"/v2/payments/authorizations/{payment_id}")
                if resp2.ok:
                    data = resp2.json() or {}
                    return {
                        "success": True,
                        "payment_id": data.get("id", payment_id),
                        "status": data.get("status", ""),
                        "data": data,
                    }
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                detail = error_body.get("message", str(resp.body))
                return {"success": False, "error": f"HTTP {resp.status_code}: {detail}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


PAYPAL_SCHEMA = ConnectorSchema(
    name="paypal",
    version="1.0.0",
    description="Crea y gestiona pagos, ordenes y transacciones via PayPal",
    category="finance_payments",
    icon="credit-card",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_order", description="Crea una orden de pago", category="write"),
        ActionDefinition(name="capture_order", description="Captura una orden", category="write"),
        ActionDefinition(name="get_order", description="Obtiene detalles de orden", category="read"),
        ActionDefinition(name="refund_payment", description="Reembolsa un pago", category="write"),
        ActionDefinition(name="list_transactions", description="Lista transacciones", category="read"),
        ActionDefinition(name="get_payment_details", description="Obtiene detalles de pago", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["client_id", "client_secret"], description="PayPal OAuth2 Credentials")
    ],
)
