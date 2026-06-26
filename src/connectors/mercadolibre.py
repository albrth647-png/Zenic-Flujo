"""
Conector MercadoLibre — Marketplace LATAM via MercadoLibre API
=================================================================

Permite gestionar publicaciones, ordenes, preguntas y
envios en MercadoLibre via la API.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class MercadolibreConnector(BaseConnector):
    """Conector para MercadoLibre: publicaciones, ordenes y envios."""

    name = "mercadolibre"
    version = "1.0.0"
    description = "Gestiona publicaciones, ordenes y envios en MercadoLibre"
    category = "latam"
    icon = "shopping-bag"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.mercadolibre.com"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de MercadoLibre."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("MercadolibreConnector: credenciales OAuth2 no configuradas")
            return False
        try:
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            # MercadoLibre uses Bearer token from OAuth2
            access_token = self._auth_provider.get_credentials().get("access_token", "")
            if access_token:
                self._http.set_auth("Bearer", token=access_token)
            # Validate connection by fetching user info
            resp = self._http.get("/users/me")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "OAuth2 configurado para MercadoLibre")
                return True
            else:
                logger.error(f"MercadolibreConnector: fallo la validacion de credenciales - {resp.status_code}")
                self._http = None
                return False
        except HTTPClientError as e:
            logger.error(f"MercadolibreConnector: error de conexion - {e}")
            self._http = None
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector MercadoLibre.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_listing": self._create_listing,
            "get_listing": self._get_listing,
            "update_listing": self._update_listing,
            "list_orders": self._list_orders,
            "answer_question": self._answer_question,
            "get_shipment": self._get_shipment,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de MercadoLibre esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con MercadoLibre."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_listing(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una publicacion en MercadoLibre.

        Args:
            params: Debe contener 'title', 'category_id', 'price', 'currency_id',
                    'available_quantity', 'buying_mode', 'listing_type_id', 'condition', 'description'
        """
        title = params.get("title", "")
        price = params.get("price", 0)
        if not title or not price:
            return {"success": False, "error": "Parametros requeridos: title, price"}
        self._log_operation("create_listing", f"title={title[:50]}")

        payload: dict[str, Any] = {
            "title": title,
            "category_id": params.get("category_id", ""),
            "price": price,
            "currency_id": params.get("currency_id", "MXN"),
            "available_quantity": params.get("available_quantity", 1),
            "buying_mode": params.get("buying_mode", "buy_it_now"),
            "listing_type_id": params.get("listing_type_id", "gold_special"),
            "condition": params.get("condition", "new"),
        }
        if params.get("description"):
            payload["description"] = params["description"]
        if params.get("pictures"):
            payload["pictures"] = params["pictures"]

        try:
            resp = self._http.post("/items", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "id": data.get("id", ""),
                    "status": data.get("status", ""),
                    "permalink": data.get("permalink", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_listing(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene una publicacion por su ID.

        Args:
            params: Debe contener 'item_id'
        """
        item_id = params.get("item_id", "")
        if not item_id:
            return {"success": False, "error": "Parametro requerido: item_id"}
        self._log_operation("get_listing", f"id={item_id}")

        try:
            resp = self._http.get(f"/items/{item_id}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "id": data.get("id", item_id),
                    "status": data.get("status", ""),
                    "title": data.get("title", ""),
                    "price": data.get("price", 0),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _update_listing(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza una publicacion de MercadoLibre.

        Args:
            params: Debe contener 'item_id' y 'fields' (dict de campos a actualizar)
        """
        item_id = params.get("item_id", "")
        fields = params.get("fields", {})
        if not item_id or not fields:
            return {"success": False, "error": "Parametros requeridos: item_id, fields"}
        self._log_operation("update_listing", f"id={item_id}")

        try:
            resp = self._http.put(f"/items/{item_id}", json=fields)
            if resp.ok:
                data = resp.json() or {}
                return {"success": True, "id": item_id, "data": data}
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_orders(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista ordenes de MercadoLibre.

        Args:
            params: Opcionalmente 'seller', 'status', 'limit', 'offset'
        """
        self._log_operation("list_orders")

        query_params: dict[str, Any] = {}
        seller = params.get("seller", "")
        if seller:
            query_params["seller"] = seller
        status = params.get("status", "")
        if status:
            query_params["order.status"] = status
        query_params["limit"] = params.get("limit", 50)
        query_params["offset"] = params.get("offset", 0)

        try:
            resp = self._http.get("/orders/search", params=query_params)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "results": data.get("results", []),
                    "paging": data.get("paging", {"total": 0, "offset": 0, "limit": 50}),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _answer_question(self, params: dict[str, Any]) -> dict[str, Any]:
        """Responde una pregunta de un comprador.

        Args:
            params: Debe contener 'question_id' y 'text'
        """
        question_id = params.get("question_id", "")
        text = params.get("text", "")
        if not question_id or not text:
            return {"success": False, "error": "Parametros requeridos: question_id, text"}
        self._log_operation("answer_question", f"question={question_id}")

        try:
            resp = self._http.post("/answers", json={"question_id": question_id, "text": text})
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "question_id": question_id,
                    "status": data.get("status", "ANSWERED"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_shipment(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene informacion de un envio.

        Args:
            params: Debe contener 'shipment_id'
        """
        shipment_id = params.get("shipment_id", "")
        if not shipment_id:
            return {"success": False, "error": "Parametro requerido: shipment_id"}
        self._log_operation("get_shipment", f"id={shipment_id}")

        try:
            resp = self._http.get(f"/shipments/{shipment_id}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "id": str(data.get("id", shipment_id)),
                    "status": data.get("status", ""),
                    "tracking_number": data.get("tracking_number", ""),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


MERCADOLIBRE_SCHEMA = ConnectorSchema(
    name="mercadolibre",
    version="1.0.0",
    description="Gestiona publicaciones, ordenes y envios en MercadoLibre",
    category="latam",
    icon="shopping-bag",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_listing", description="Crea una publicacion", category="write"),
        ActionDefinition(name="get_listing", description="Obtiene una publicacion", category="read"),
        ActionDefinition(name="update_listing", description="Actualiza publicacion", category="write"),
        ActionDefinition(name="list_orders", description="Lista ordenes", category="read"),
        ActionDefinition(name="answer_question", description="Responde pregunta", category="write"),
        ActionDefinition(name="get_shipment", description="Obtiene info de envio", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="oauth2", required_fields=["client_id", "client_secret", "access_token"], description="MercadoLibre OAuth2")
    ],
)
