"""Conector WooCommerce — E-commerce REST API."""

from __future__ import annotations

import base64
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class WooCommerceConnector(BaseConnector):
    name = "woocommerce"
    version = "1.0.0"
    description = "Gestiona productos, ordenes y clientes en WooCommerce"
    category = "ecommerce"
    icon = "shopping-cart"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._store_url: str = ""
        self._consumer_key: str = ""
        self._consumer_secret: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials
            self._store_url = c.get("store_url", "").rstrip("/")
            self._consumer_key = c.get("consumer_key", "")
            self._consumer_secret = c.get("consumer_secret", "")
        if not self._store_url or not self._consumer_key or not self._consumer_secret:
            logger.error("WooCommerce: store_url, consumer_key y consumer_secret requeridos")
            return False
        auth_str = base64.b64encode(f"{self._consumer_key}:{self._consumer_secret}".encode()).decode()
        self._http = HttpClient(base_url=f"{self._store_url}/wp-json/wc/v3", connector_name=self.name)
        self._http.set_header("Authorization", f"Basic {auth_str}")
        self._connected = True
        self._log_operation("connect", f"store={self._store_url}")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"get_products": self._get_products, "get_product": self._get_product, "create_product": self._create_product,
                       "get_orders": self._get_orders, "get_order": self._get_order, "create_order": self._create_order,
                       "get_customers": self._get_customers, "get_customer": self._get_customer}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool:
        return bool(self._auth_provider and self._auth_provider.validate())

    def disconnect(self) -> bool:
        self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def _api(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kw)
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d}
            return {"success": False, "error": d.get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_products(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/products", params=p)
    def _get_product(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/products/{p.get('product_id', '')}")
    def _create_product(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("post", "/products", json=p)
    def _get_orders(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/orders", params=p)
    def _get_order(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/orders/{p.get('order_id', '')}")
    def _create_order(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("post", "/orders", json=p)
    def _get_customers(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/customers", params=p)
    def _get_customer(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/customers/{p.get('customer_id', '')}")


WOOCOMMERCE_SCHEMA = ConnectorSchema(name="woocommerce", version="1.0.0", description="Gestiona productos, ordenes y clientes en WooCommerce", category="ecommerce", icon="shopping-cart", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_products", description="Lista productos", category="read"),
    ActionDefinition(name="get_product", description="Obtiene un producto por ID", category="read"),
    ActionDefinition(name="create_product", description="Crea un nuevo producto", category="write"),
    ActionDefinition(name="get_orders", description="Lista ordenes", category="read"),
    ActionDefinition(name="get_order", description="Obtiene una orden por ID", category="read"),
    ActionDefinition(name="create_order", description="Crea una nueva orden", category="write"),
    ActionDefinition(name="get_customers", description="Lista clientes", category="read"),
    ActionDefinition(name="get_customer", description="Obtiene un cliente por ID", category="read"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["store_url", "consumer_key", "consumer_secret"])])
