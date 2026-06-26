"""
Conector QuickBooks — Contabilidad via QuickBooks Online API
===============================================================

Permite gestionar facturas, clientes, productos y reportes
contables via la API de QuickBooks Online.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class QuickbooksConnector(BaseConnector):
    """Conector para QuickBooks: facturacion, contabilidad y reportes."""

    name = "quickbooks"
    version = "1.0.0"
    description = "Gestiona facturas, clientes y reportes contables via QuickBooks Online"
    category = "finance_payments"
    icon = "calculator"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://quickbooks.api.intuit.com/v3/company"
        self._http: HttpClient | None = None
        self._company_id: str = ""

    def connect(self) -> bool:
        """Establece conexion con la API de QuickBooks Online."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("QuickbooksConnector: credenciales OAuth2 no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            self._company_id = str(creds.get("company_id", creds.get("realm_id", "")))
            sandbox = creds.get("sandbox", False)

            if sandbox:
                self._base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company"

            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )

            # QuickBooks uses OAuth2 Bearer token
            access_token = creds.get("access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)

            # Validate by querying company info
            if self._company_id:
                resp = self._http.get(f"/{self._company_id}/companyinfo/{self._company_id}")
                if resp.ok:
                    self._connected = True
                    self._log_operation("connect", "OAuth2 configurado y validado para QuickBooks")
                    return True
                else:
                    # Still connect even if validation fails
                    self._connected = True
                    self._log_operation("connect", f"OAuth2 configurado (validacion fallo: HTTP {resp.status_code})")
                    return True
            else:
                self._connected = True
                self._log_operation("connect", "OAuth2 configurado para QuickBooks (sin company_id)")
                return True
        except HTTPClientError as e:
            logger.warning(f"QuickbooksConnector: error durante conexion - {e}")
            creds = self._auth_provider.get_credentials()
            self._company_id = str(creds.get("company_id", creds.get("realm_id", "")))
            sandbox = creds.get("sandbox", False)
            if sandbox:
                self._base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company"
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            access_token = creds.get("access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)
            self._connected = True
            self._log_operation("connect", f"OAuth2 configurado (validacion fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector QuickBooks.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_invoice": self._create_invoice,
            "list_invoices": self._list_invoices,
            "create_customer": self._create_customer,
            "list_customers": self._list_customers,
            "create_payment": self._create_payment,
            "get_report": self._get_report,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de QuickBooks esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con QuickBooks."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_invoice(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una factura en QuickBooks.

        Args:
            params: Debe contener 'customer_id', 'line_items' (lista de dicts)
        """
        customer_id = params.get("customer_id", "")
        line_items = params.get("line_items", [])
        if not customer_id or not line_items:
            return {"success": False, "error": "Parametros requeridos: customer_id, line_items"}
        self._log_operation("create_invoice", f"customer={customer_id}")

        # Build QuickBooks invoice payload
        qb_lines = []
        for item in line_items:
            line: dict[str, Any] = {
                "Amount": item.get("amount", 0),
                "DetailType": item.get("detail_type", "SalesItemLineDetail"),
                "SalesItemLineDetail": {
                    "ItemRef": {"value": item.get("item_id", "")},
                    "Qty": item.get("quantity", 1),
                    "UnitPrice": item.get("unit_price", item.get("amount", 0)),
                },
            }
            if item.get("description"):
                line["Description"] = item["description"]
            qb_lines.append(line)

        payload: dict[str, Any] = {
            "Line": qb_lines,
            "CustomerRef": {"value": str(customer_id)},
        }
        if params.get("bill_email"):
            payload["BillEmail"] = {"Address": params["bill_email"]}
        if params.get("due_date"):
            payload["DueDate"] = params["due_date"]
        if params.get("sales_term_ref"):
            payload["SalesTermRef"] = {"value": params["sales_term_ref"]}
        if params.get("private_note"):
            payload["PrivateNote"] = params["private_note"]

        try:
            resp = self._http.post(
                f"/{self._company_id}/invoice",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.ok:
                data = resp.json() or {}
                invoice = data.get("Invoice", data)
                return {
                    "success": True,
                    "invoice_id": invoice.get("Id", ""),
                    "status": invoice.get("EmailStatus", "Draft"),
                    "total": invoice.get("TotalAmt", 0.0),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                fault = error_body.get("Fault", {})
                errors = fault.get("Error", [])
                error_msg = errors[0].get("Message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_invoices(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista facturas de QuickBooks.

        Args:
            params: Opcionalmente 'limit', 'status', 'start_position'
        """
        self._log_operation("list_invoices")

        query_parts: list[str] = ["SELECT * FROM Invoice"]
        conditions: list[str] = []

        if params.get("status"):
            conditions.append(f"EmailStatus = '{params['status']}'")
        if params.get("customer_id"):
            conditions.append(f"CustomerRef = '{params['customer_id']}'")

        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))

        query_parts.append(f"STARTPOSITION {params.get('start_position', 1)}")
        query_parts.append(f"MAXRESULTS {params.get('limit', 100)}")

        query = " ".join(query_parts)

        try:
            resp = self._http.get(
                f"/{self._company_id}/query",
                params={"query": query},
            )
            if resp.ok:
                data = resp.json() or {}
                query_response = data.get("QueryResponse", {})
                invoices = query_response.get("Invoice", [])
                return {
                    "success": True,
                    "invoices": invoices,
                    "start_position": query_response.get("startPosition", 1),
                    "max_results": query_response.get("maxResults", 0),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                fault = error_body.get("Fault", {})
                errors = fault.get("Error", [])
                error_msg = errors[0].get("Message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_customer(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un cliente en QuickBooks.

        Args:
            params: Debe contener 'display_name' y opcionalmente 'email', 'phone'
        """
        display_name = params.get("display_name", "")
        if not display_name:
            return {"success": False, "error": "Parametro requerido: display_name"}
        self._log_operation("create_customer", f"name={display_name}")

        payload: dict[str, Any] = {
            "DisplayName": display_name,
        }
        if params.get("given_name"):
            payload["GivenName"] = params["given_name"]
        if params.get("family_name"):
            payload["FamilyName"] = params["family_name"]
        if params.get("email"):
            payload["PrimaryEmailAddr"] = {"Address": params["email"]}
        if params.get("phone"):
            payload["PrimaryPhone"] = {"FreeFormNumber": params["phone"]}
        if params.get("company_name"):
            payload["CompanyName"] = params["company_name"]
        if params.get("billing_address"):
            payload["BillAddr"] = params["billing_address"]
        if params.get("notes"):
            payload["Notes"] = params["notes"]

        try:
            resp = self._http.post(
                f"/{self._company_id}/customer",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.ok:
                data = resp.json() or {}
                customer = data.get("Customer", data)
                return {
                    "success": True,
                    "customer_id": customer.get("Id", ""),
                    "display_name": customer.get("DisplayName", display_name),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                fault = error_body.get("Fault", {})
                errors = fault.get("Error", [])
                error_msg = errors[0].get("Message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_customers(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista clientes de QuickBooks.

        Args:
            params: Opcionalmente 'limit', 'start_position'
        """
        self._log_operation("list_customers")

        # Validar y normalizar start_position y limit a enteros (evita SQL injection en Quickbooks Query Language).
        try:
            start_position = int(params.get('start_position', 1))
            limit = int(params.get('limit', 100))
        except (ValueError, TypeError):
            return {"success": False, "error": "start_position y limit deben ser enteros"}
        # Cotas razonables
        start_position = max(1, start_position)
        limit = max(1, min(limit, 1000))

        # Quickbooks Query Language (no SQL estándar). start_position y limit son enteros validados.
        query = f"SELECT * FROM Customer STARTPOSITION {start_position} MAXRESULTS {limit}"  # nosec B608 — enteros validados

        try:
            resp = self._http.get(
                f"/{self._company_id}/query",
                params={"query": query},
            )
            if resp.ok:
                data = resp.json() or {}
                query_response = data.get("QueryResponse", {})
                customers = query_response.get("Customer", [])
                return {
                    "success": True,
                    "customers": customers,
                    "start_position": query_response.get("startPosition", 1),
                    "max_results": query_response.get("maxResults", 0),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                fault = error_body.get("Fault", {})
                errors = fault.get("Error", [])
                error_msg = errors[0].get("Message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_payment(self, params: dict[str, Any]) -> dict[str, Any]:
        """Registra un pago en QuickBooks.

        Args:
            params: Debe contener 'customer_id', 'total_amount' y opcionalmente 'invoice_id'
        """
        customer_id = params.get("customer_id", "")
        total_amount = params.get("total_amount", 0)
        if not customer_id or not total_amount:
            return {"success": False, "error": "Parametros requeridos: customer_id, total_amount"}
        self._log_operation("create_payment", f"customer={customer_id}, amount={total_amount}")

        payload: dict[str, Any] = {
            "CustomerRef": {"value": str(customer_id)},
            "TotalAmt": str(total_amount),
        }

        # Link payment to specific invoice if provided
        if params.get("invoice_id"):
            payload["Line"] = [
                {
                    "Amount": str(total_amount),
                    "LinkedTxn": [
                        {
                            "TxnId": str(params["invoice_id"]),
                            "TxnType": "Invoice",
                        }
                    ],
                }
            ]

        if params.get("payment_method"):
            payload["PaymentMethodRef"] = {"value": params["payment_method"]}
        if params.get("payment_ref"):
            payload["PaymentRefNum"] = params["payment_ref"]
        if params.get("deposit_to_account"):
            payload["DepositToAccountRef"] = {"value": params["deposit_to_account"]}
        if params.get("private_note"):
            payload["PrivateNote"] = params["private_note"]

        try:
            resp = self._http.post(
                f"/{self._company_id}/payment",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.ok:
                data = resp.json() or {}
                payment = data.get("Payment", data)
                return {
                    "success": True,
                    "payment_id": payment.get("Id", ""),
                    "total": payment.get("TotalAmt", total_amount),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                fault = error_body.get("Fault", {})
                errors = fault.get("Error", [])
                error_msg = errors[0].get("Message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_report(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un reporte contable de QuickBooks.

        Args:
            params: Debe contener 'report_type' (ProfitAndLoss, BalanceSheet, CashFlow, etc.)
                    Opcionalmente 'start_date', 'end_date', 'accounting_method'
        """
        report_type = params.get("report_type", "")
        if not report_type:
            return {"success": False, "error": "Parametro requerido: report_type"}
        self._log_operation("get_report", f"type={report_type}")

        query_params: dict[str, Any] = {}
        if params.get("start_date"):
            query_params["start_date"] = params["start_date"]
        if params.get("end_date"):
            query_params["end_date"] = params["end_date"]
        if params.get("accounting_method"):
            query_params["accounting_method"] = params["accounting_method"]
        if params.get("summarize_column_by"):
            query_params["summarize_column_by"] = params["summarize_column_by"]
        if params.get("departments"):
            query_params["departments"] = params["departments"]

        try:
            resp = self._http.get(
                f"/{self._company_id}/reports/{report_type}",
                params=query_params if query_params else None,
            )
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "report_type": report_type,
                    "header": data.get("Header", {}),
                    "rows": data.get("Rows", {}),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                fault = error_body.get("Fault", {})
                errors = fault.get("Error", [])
                error_msg = errors[0].get("Message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


QUICKBOOKS_SCHEMA = ConnectorSchema(
    name="quickbooks",
    version="1.0.0",
    description="Gestiona facturas, clientes y reportes contables via QuickBooks Online",
    category="finance_payments",
    icon="calculator",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_invoice", description="Crea una factura", category="write"),
        ActionDefinition(name="list_invoices", description="Lista facturas", category="read"),
        ActionDefinition(name="create_customer", description="Crea un cliente", category="write"),
        ActionDefinition(name="list_customers", description="Lista clientes", category="read"),
        ActionDefinition(name="create_payment", description="Registra un pago", category="write"),
        ActionDefinition(name="get_report", description="Obtiene reporte contable", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["client_id", "client_secret", "access_token"], description="QuickBooks OAuth2")
    ],
)
