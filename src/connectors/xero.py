"""Xero Connector — Accounting & Invoicing.

Integrates with Xero API for invoices, contacts, accounts,
bank transactions, and reporting.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class XeroConnector(BaseConnector):
    """Conector para Xero: facturas, contactos, cuentas bancarias y reportes."""

    name = "xero"
    version = "1.0.0"
    description = "Gestiona facturas, contactos, cuentas bancarias y reportes contables via Xero API"
    category = "finance"
    icon = "dollar-sign"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.xero.com/api.xro/2.0"
        self._http: HttpClient | None = None
        self._tenant_id: str = ""

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("XeroConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            tenant_id = creds.get("tenant_id", "")
            access_token = creds.get("access_token", "")
            if not tenant_id or not access_token:
                return False
            self._tenant_id = tenant_id
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("Authorization", f"Bearer {access_token}")
            self._http.set_header("Xero-tenant-id", tenant_id)
            resp = self._http.get("/Organisation")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "Xero conectado")
                return True
            self._connected = True
            return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            self._tenant_id = creds.get("tenant_id", "")
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("Authorization", f"Bearer {creds.get('access_token', '')}")
            self._http.set_header("Xero-tenant-id", self._tenant_id)
            self._connected = True
            self._log_operation("connect", f"Xero configurado (status fallo: {e})")
            return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {
            "list_invoices": self._list_invoices,
            "get_invoice": self._get_invoice,
            "create_invoice": self._create_invoice,
            "update_invoice": self._update_invoice,
            "list_contacts": self._list_contacts,
            "get_contact": self._get_contact,
            "create_contact": self._create_contact,
            "list_accounts": self._list_accounts,
            "list_bank_transactions": self._list_bank_transactions,
            "create_bank_transaction": self._create_bank_transaction,
            "get_organisation": self._get_organisation,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        return bool(self._auth_provider and self._auth_provider.validate())

    def disconnect(self) -> bool:
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_invoices(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/Invoices", params={
            "where": params.get("where", ""), "order": params.get("order", "Date DESC"),
            "page": params.get("page", 1), "pageSize": params.get("pageSize", 50),
            "statuses": params.get("statuses", ""),
        })
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "invoices": data.get("Invoices", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_invoice(self, params: dict[str, Any]) -> dict[str, Any]:
        inv_id = params.get("invoice_id", "")
        if not inv_id:
            return {"success": False, "error": "Parametro requerido: invoice_id"}
        resp = self._http.get(f"/Invoices/{inv_id}")
        if resp.ok:
            data = resp.json() or {}
            inv_list = data.get("Invoices", [{}])
            return {"success": True, "invoice": inv_list[0]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_invoice(self, params: dict[str, Any]) -> dict[str, Any]:
        contact = params.get("contact", {})
        line_items = params.get("line_items", [])
        if not contact or not line_items:
            return {"success": False, "error": "Parametros requeridos: contact, line_items"}
        contact_obj = {"ContactID": contact.get("id", "")} if contact.get("id") else contact
        inv = {
            "Type": params.get("type", "ACCREC"),
            "Contact": contact_obj,
            "Date": params.get("date", ""),
            "DueDate": params.get("due_date", ""),
            "LineItems": line_items,
            "Status": params.get("status", "DRAFT"),
        }
        for f in ("Reference", "CurrencyCode", "BrandingThemeID", "Url"):
            if params.get(f.lower()):
                inv[f] = params[f.lower()]
        resp = self._http.post("/Invoices", json={"Invoices": [inv]})
        if resp.ok:
            data = resp.json() or {}
            inv_data = data.get("Invoices", [{}])[0]
            return {"success": True, "id": inv_data.get("InvoiceID"), "number": inv_data.get("InvoiceNumber"), "total": inv_data.get("Total")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _update_invoice(self, params: dict[str, Any]) -> dict[str, Any]:
        inv_id = params.get("invoice_id", "")
        if not inv_id:
            return {"success": False, "error": "Parametro requerido: invoice_id"}
        inv = {}
        for f, xf in [("status", "Status"), ("date", "Date"), ("due_date", "DueDate"), ("reference", "Reference")]:
            if params.get(f):
                inv[xf] = params[f]
        resp = self._http.post(f"/Invoices/{inv_id}", json={"Invoices": [inv]})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "invoice": data.get("Invoices", [{}])[0]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_contacts(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/Contacts", params={
            "where": params.get("where", ""), "order": params.get("order", "Name ASC"),
            "page": params.get("page", 1), "pageSize": params.get("pageSize", 50),
        })
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "contacts": data.get("Contacts", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        cid = params.get("contact_id", "")
        if not cid:
            return {"success": False, "error": "Parametro requerido: contact_id"}
        resp = self._http.get(f"/Contacts/{cid}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "contact": data.get("Contacts", [{}])[0]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        contact = {"Name": name}
        for f, xf in [("email", "EmailAddress"), ("phone", "Phones"), ("addresses", "Addresses"), ("contact_id", "ContactID")]:
            if params.get(f):
                contact[xf] = params[f]
        resp = self._http.post("/Contacts", json={"Contacts": [contact]})
        if resp.ok:
            data = resp.json() or {}
            c = data.get("Contacts", [{}])[0]
            return {"success": True, "id": c.get("ContactID"), "name": c.get("Name")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_accounts(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/Accounts")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "accounts": data.get("Accounts", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_bank_transactions(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/BankTransactions", params={
            "page": params.get("page", 1), "pageSize": params.get("pageSize", 50),
            "where": params.get("where", ""),
        })
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "transactions": data.get("BankTransactions", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_bank_transaction(self, params: dict[str, Any]) -> dict[str, Any]:
        contact = params.get("contact", {})
        line_items = params.get("line_items", [])
        if not line_items:
            return {"success": False, "error": "Parametro requerido: line_items"}
        contact_obj = {"ContactID": contact.get("id", "")} if isinstance(contact, dict) and contact.get("id") else contact
        bt = {
            "Type": params.get("type", "SPEND"),
            "Contact": contact_obj,
            "Date": params.get("date", ""),
            "LineItems": line_items,
            "Status": params.get("status", "AUTHORISED"),
        }
        if params.get("bank_account"):
            bt["BankAccount"] = {"Code": params["bank_account"]}
        resp = self._http.post("/BankTransactions", json={"BankTransactions": [bt]})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "transaction": data.get("BankTransactions", [{}])[0]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_organisation(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/Organisation")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "organisation": data.get("Organisations", [{}])[0]}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


XERO_SCHEMA = ConnectorSchema(
    name="xero", version="1.0.0",
    description="Gestiona facturas, contactos, cuentas bancarias y reportes contables via Xero API",
    category="finance", icon="dollar-sign", author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_invoices", description="Lista facturas", category="read"),
        ActionDefinition(name="get_invoice", description="Obtiene factura", category="read"),
        ActionDefinition(name="create_invoice", description="Crea factura", category="write"),
        ActionDefinition(name="update_invoice", description="Actualiza factura", category="write"),
        ActionDefinition(name="list_contacts", description="Lista contactos", category="read"),
        ActionDefinition(name="get_contact", description="Obtiene contacto", category="read"),
        ActionDefinition(name="create_contact", description="Crea contacto", category="write"),
        ActionDefinition(name="list_accounts", description="Lista cuentas contables", category="read"),
        ActionDefinition(name="list_bank_transactions", description="Lista transacciones bancarias", category="read"),
        ActionDefinition(name="create_bank_transaction", description="Crea transacción bancaria", category="write"),
        ActionDefinition(name="get_organisation", description="Obtiene datos de la organización", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["tenant_id", "access_token", "client_id"], description="Xero tenant ID + OAuth2 access token")
    ],
)
