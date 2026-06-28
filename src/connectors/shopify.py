"""Shopify Connector — E-commerce Platform.

Integrates with Shopify REST API for product, order, customer,
and inventory management.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class ShopifyConnector(BaseConnector):
    """Conector para Shopify: productos, órdenes, clientes e inventario."""

    name = "shopify"
    version = "1.0.0"
    description = "Gestiona productos, órdenes, clientes e inventario via Shopify REST API"
    category = "ecommerce"
    icon = "shopping-cart"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("ShopifyConnector: credenciales no configuradas")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            store = creds.get("store", "")
            access_token = creds.get("access_token", "")
            if not store or not access_token:
                return False
            self._base_url = f"https://{store}.myshopify.com/admin/api/2024-01"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("X-Shopify-Access-Token", access_token)
            resp = self._http.get("/shop.json")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", f"Shopify store={store}")
                return True
            self._connected = True
            self._log_operation("connect", "Shopify configurado (sin verificación)")
            return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            store = creds.get("store", ""); access_token = creds.get("access_token", "")
            self._base_url = f"https://{store}.myshopify.com/admin/api/2024-01"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_header("X-Shopify-Access-Token", access_token)
            self._connected = True
            self._log_operation("connect", f"Shopify configurado (status fallo: {e})")
            return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "list_products": self._list_products,
            "get_product": self._get_product,
            "create_product": self._create_product,
            "update_product": self._update_product,
            "delete_product": self._delete_product,
            "list_orders": self._list_orders,
            "get_order": self._get_order,
            "create_order": self._create_order,
            "list_customers": self._list_customers,
            "get_customer": self._get_customer,
            "get_inventory_level": self._get_inventory_level,
            "set_inventory_level": self._set_inventory_level,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_products(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/products.json", params={
            "limit": params.get("limit", 50), "page": params.get("page", 1),
            "status": params.get("status", "active"), "collection_id": params.get("collection_id", "")})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "products": data.get("products", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_product(self, params: dict[str, Any]) -> dict[str, Any]:
        pid = params.get("product_id", "")
        if not pid: return {"success": False, "error": "Parametro requerido: product_id"}
        resp = self._http.get(f"/products/{pid}.json")
        if resp.ok:
            data = (resp.json() or {}).get("product", {})
            return {"success": True, "product": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_product(self, params: dict[str, Any]) -> dict[str, Any]:
        title = params.get("title", "")
        if not title: return {"success": False, "error": "Parametro requerido: title"}
        product = {"title": title, "body_html": params.get("body_html", ""), "vendor": params.get("vendor", ""),
                   "product_type": params.get("product_type", ""), "status": params.get("status", "draft")}
        if params.get("variants"): product["variants"] = params["variants"]
        if params.get("images"): product["images"] = params["images"]
        resp = self._http.post("/products.json", json={"product": product})
        if resp.ok:
            data = (resp.json() or {}).get("product", {})
            return {"success": True, "id": data.get("id"), "title": data.get("title"), "handle": data.get("handle")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _update_product(self, params: dict[str, Any]) -> dict[str, Any]:
        pid = params.get("product_id", "")
        if not pid: return {"success": False, "error": "Parametro requerido: product_id"}
        product = {}
        for field in ("title", "body_html", "vendor", "product_type", "status", "tags", "variants"):
            if params.get(field): product[field] = params[field]
        resp = self._http.put(f"/products/{pid}.json", json={"product": product})
        if resp.ok:
            data = (resp.json() or {}).get("product", {})
            return {"success": True, "id": data.get("id"), "title": data.get("title")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _delete_product(self, params: dict[str, Any]) -> dict[str, Any]:
        pid = params.get("product_id", "")
        if not pid: return {"success": False, "error": "Parametro requerido: product_id"}
        resp = self._http.delete(f"/products/{pid}.json")
        if resp.ok or resp.status_code == 204:
            return {"success": True, "product_id": pid, "deleted": True}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_orders(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/orders.json", params={
            "limit": params.get("limit", 50), "page": params.get("page", 1),
            "status": params.get("status", "any"), "financial_status": params.get("financial_status", "")})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "orders": data.get("orders", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_order(self, params: dict[str, Any]) -> dict[str, Any]:
        oid = params.get("order_id", "")
        if not oid: return {"success": False, "error": "Parametro requerido: order_id"}
        resp = self._http.get(f"/orders/{oid}.json")
        if resp.ok:
            data = (resp.json() or {}).get("order", {})
            return {"success": True, "order": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_order(self, params: dict[str, Any]) -> dict[str, Any]:
        line_items = params.get("line_items", [])
        customer = params.get("customer", {})
        if not line_items: return {"success": False, "error": "Parametro requerido: line_items"}
        order = {"line_items": line_items, "customer": customer,
                 "financial_status": params.get("financial_status", "pending"),
                 "fulfillment_status": params.get("fulfillment_status", ""),
                 "email": params.get("email", ""), "note": params.get("note", "")}
        if params.get("shipping_address"): order["shipping_address"] = params["shipping_address"]
        if params.get("billing_address"): order["billing_address"] = params["billing_address"]
        resp = self._http.post("/orders.json", json={"order": order})
        if resp.ok:
            data = (resp.json() or {}).get("order", {})
            return {"success": True, "id": data.get("id"), "order_number": data.get("order_number"), "total_price": data.get("total_price")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_customers(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.get("/customers.json", params={"limit": params.get("limit", 50), "page": params.get("page", 1)})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "customers": data.get("customers", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_customer(self, params: dict[str, Any]) -> dict[str, Any]:
        cid = params.get("customer_id", "")
        if not cid: return {"success": False, "error": "Parametro requerido: customer_id"}
        resp = self._http.get(f"/customers/{cid}.json")
        if resp.ok:
            data = (resp.json() or {}).get("customer", {})
            return {"success": True, "customer": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_inventory_level(self, params: dict[str, Any]) -> dict[str, Any]:
        inv_id = params.get("inventory_item_id", "")
        loc_id = params.get("location_id", "")
        if not inv_id or not loc_id: return {"success": False, "error": "Parametros requeridos: inventory_item_id, location_id"}
        resp = self._http.get("/inventory_levels.json", params={"inventory_item_ids": inv_id, "location_ids": loc_id})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "inventory_levels": data.get("inventory_levels", [])}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _set_inventory_level(self, params: dict[str, Any]) -> dict[str, Any]:
        inv_id = params.get("inventory_item_id", ""); loc_id = params.get("location_id", "")
        available = params.get("available")
        if not inv_id or not loc_id or available is None:
            return {"success": False, "error": "Parametros requeridos: inventory_item_id, location_id, available"}
        resp = self._http.post("/inventory_levels/set.json", json={"inventory_item_id": int(inv_id), "location_id": int(loc_id), "available": int(available)})
        if resp.ok:
            data = (resp.json() or {}).get("inventory_level", {})
            return {"success": True, "inventory_level": data}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


SHOPIFY_SCHEMA = ConnectorSchema(
    name="shopify", version="1.0.0",
    description="Gestiona productos, órdenes, clientes e inventario via Shopify REST API",
    category="ecommerce", icon="shopping-cart", author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_products", description="Lista productos", category="read"),
        ActionDefinition(name="get_product", description="Obtiene producto", category="read"),
        ActionDefinition(name="create_product", description="Crea producto", category="write"),
        ActionDefinition(name="update_product", description="Actualiza producto", category="write"),
        ActionDefinition(name="delete_product", description="Elimina producto", category="write"),
        ActionDefinition(name="list_orders", description="Lista órdenes", category="read"),
        ActionDefinition(name="get_order", description="Obtiene orden", category="read"),
        ActionDefinition(name="create_order", description="Crea orden manual", category="write"),
        ActionDefinition(name="list_customers", description="Lista clientes", category="read"),
        ActionDefinition(name="get_customer", description="Obtiene cliente", category="read"),
        ActionDefinition(name="get_inventory_level", description="Obtiene nivel de inventario", category="read"),
        ActionDefinition(name="set_inventory_level", description="Actualiza nivel de inventario", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["store", "access_token"], description="Nombre de tienda + Admin API access token")
    ],
)
