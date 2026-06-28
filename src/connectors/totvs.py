"""Conector Totvs — ERP brasileiro Protheus API REST."""

from __future__ import annotations

import base64
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class TotvsConnector(BaseConnector):
    name = "totvs"
    version = "1.1.0"
    description = "Integra con Totvs Protheus via REST API para datos maestros, fiscais e financeiros"
    category = "erp"
    icon = "database"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""; self._username: str = ""; self._password: str = ""
        self._company: str = ""; self._branch: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._base_url = c.get("base_url", "").rstrip("/")
            self._username = c.get("username", ""); self._password = c.get("password", "")
            self._company = c.get("company", "01"); self._branch = c.get("branch", "01")
        if not self._base_url or not self._username or not self._password:
            logger.error("Totvs: base_url, username y password requeridos"); return False
        auth = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        self._http = HttpClient(base_url=f"{self._base_url}/api/v1", connector_name=self.name)
        self._http.set_header("Authorization", f"Basic {auth}")
        self._http.set_header("company", self._company)
        self._http.set_header("branch", self._branch)
        self._connected = True; self._log_operation("connect", f"totvs={self._base_url}"); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {
            # Read actions (existentes)
            "get_products": self._get_products,
            "get_customers": self._get_customers,
            "get_suppliers": self._get_suppliers,
            "get_invoices": self._get_invoices,
            "get_sales_orders": self._get_sales_orders,
            "get_financial": self._get_financial,
            # Write actions (Foso 2 SF7)
            "create_product": self._create_product,
            "update_product": self._update_product,
            "create_customer": self._create_customer,
            "update_customer": self._update_customer,
            "create_invoice": self._create_invoice,
            "create_sales_order": self._create_sales_order,
            "post_financial_entry": self._post_financial_entry,
        }
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool: return bool(self._auth_provider and self._auth_provider.validate())
    def disconnect(self) -> bool: self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def _api(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kw)
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d.get("items", d)}
            return {"success": False, "error": d.get("error", {}).get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_products(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/products", params=p)
    def _get_customers(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/customers", params=p)
    def _get_suppliers(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/suppliers", params=p)
    def _get_invoices(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/invoices", params=p)
    def _get_sales_orders(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/sales-orders", params=p)
    def _get_financial(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/financial", params=p)

    # ── Write actions (Foso 2 SF7) ───────────────────────────────────
    # Totvs Protheus REST API acepta POST/PUT sobre los mismos endpoints
    # con body JSON. La respuesta incluye el recurso creado/actualizado.
    def _create_product(self, p: dict[str, Any]) -> dict[str, Any]:
        """Crea un producto (SB1) en Protheus."""
        return self._api("post", "/products", json=p)

    def _update_product(self, p: dict[str, Any]) -> dict[str, Any]:
        """Actualiza un producto existente por product_id."""
        pid = p.pop("product_id", None)
        if not pid:
            return {"success": False, "error": "product_id requerido"}
        return self._api("put", f"/products/{pid}", json=p)

    def _create_customer(self, p: dict[str, Any]) -> dict[str, Any]:
        """Crea un cliente (SA1) en Protheus."""
        return self._api("post", "/customers", json=p)

    def _update_customer(self, p: dict[str, Any]) -> dict[str, Any]:
        """Actualiza un cliente existente por customer_id."""
        cid = p.pop("customer_id", None)
        if not cid:
            return {"success": False, "error": "customer_id requerido"}
        return self._api("put", f"/customers/{cid}", json=p)

    def _create_invoice(self, p: dict[str, Any]) -> dict[str, Any]:
        """Crea una factura (SF2+SD2) en Protheus."""
        return self._api("post", "/invoices", json=p)

    def _create_sales_order(self, p: dict[str, Any]) -> dict[str, Any]:
        """Crea un pedido de venta (SC5+SC6) en Protheus."""
        return self._api("post", "/sales-orders", json=p)

    def _post_financial_entry(self, p: dict[str, Any]) -> dict[str, Any]:
        """Crea un título financiero (SE1 o SE2) en Protheus.

        El campo `entry_type` ("receivable" | "payable") determina si se
        registra en SE1 (cuentas a cobrar) o SE2 (cuentas a pagar).
        """
        entry_type = p.pop("entry_type", "receivable")
        endpoint = "/financial/receivables" if entry_type == "receivable" else "/financial/payables"
        return self._api("post", endpoint, json=p)


TOTVS_SCHEMA = ConnectorSchema(name="totvs", version="1.1.0", description="Integra con Totvs Protheus para ERP brasileiro (read + write)",
    category="erp", icon="database", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_products", description="Lista productos del ERP", category="read"),
    ActionDefinition(name="get_customers", description="Lista clientes del ERP", category="read"),
    ActionDefinition(name="get_suppliers", description="Lista proveedores del ERP", category="read"),
    ActionDefinition(name="get_invoices", description="Lista facturas del ERP", category="read"),
    ActionDefinition(name="get_sales_orders", description="Lista pedidos de venta", category="read"),
    ActionDefinition(name="get_financial", description="Lista movimientos financieros", category="read"),
    ActionDefinition(name="create_product", description="Crea un producto (SB1)", category="write"),
    ActionDefinition(name="update_product", description="Actualiza un producto por product_id", category="write"),
    ActionDefinition(name="create_customer", description="Crea un cliente (SA1)", category="write"),
    ActionDefinition(name="update_customer", description="Actualiza un cliente por customer_id", category="write"),
    ActionDefinition(name="create_invoice", description="Crea una factura (SF2+SD2)", category="write"),
    ActionDefinition(name="create_sales_order", description="Crea un pedido de venta (SC5+SC6)", category="write"),
    ActionDefinition(name="post_financial_entry", description="Crea un título financiero (SE1/SE2)", category="write"),
], auth_requirements=[AuthRequirement(auth_type="basic", required_fields=["base_url", "username", "password"])])
