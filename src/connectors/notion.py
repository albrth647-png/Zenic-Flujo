"""
Conector Notion — Paginas y Bases de Datos via Notion API
============================================================

Permite gestionar paginas, bases de datos, bloques y
busquedas en workspaces de Notion via la API usando HttpClient.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class NotionConnector(BaseConnector):
    """Conector para Notion: paginas, bases de datos y bloques."""

    name = "notion"
    version = "1.0.0"
    description = "Gestiona paginas, bases de datos y bloques en Notion"
    category = "project_management"
    icon = "book-open"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.notion.com/v1"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Notion."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("NotionConnector: Integration Token no configurado")
            return False

        # Extract integration token from auth provider
        token = getattr(self._auth_provider, "_api_key", "") or getattr(self._auth_provider, "_token", "")
        if not token:
            auth_request = self._auth_provider.apply_auth({"headers": {}})
            token = auth_request.get("headers", {}).get("Authorization", "").replace("Bearer ", "")
            if not token:
                token = auth_request.get("headers", {}).get("Notion-Version", "")

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=token)
        # Notion API requires the Notion-Version header
        self._http.set_header("Notion-Version", "2022-06-28")

        # Validate credentials
        try:
            response = self._http.get("/users/me")
            if response.status_code == 401:
                logger.error("NotionConnector: Integration Token invalido (401)")
                return False
        except HTTPClientError as e:
            logger.warning(f"NotionConnector: error validando credenciales: {e}")

        self._connected = True
        self._log_operation("connect", "Integration Token configurado")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Notion.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_page": self._create_page,
            "get_page": self._get_page,
            "update_page": self._update_page,
            "query_database": self._query_database,
            "create_database": self._create_database,
            "search": self._search,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Integration Token de Notion este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Notion."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_page(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una pagina en Notion.

        Args:
            params: Debe contener 'parent' (dict con database_id o page_id) y 'properties'
        """
        parent = params.get("parent", {})
        properties = params.get("properties", {})
        children = params.get("children", [])
        if not parent or not properties:
            return {"success": False, "error": "Parametros requeridos: parent, properties"}
        self._log_operation("create_page", f"parent={parent}")

        try:
            body: dict[str, Any] = {
                "parent": parent,
                "properties": properties,
            }
            if children:
                body["children"] = children
            icon = params.get("icon")
            if icon:
                body["icon"] = icon
            cover = params.get("cover")
            if cover:
                body["cover"] = cover

            response = self._http.post("/pages", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("id", ""),
                "object": data.get("object", "page"),
                "archived": data.get("archived", False),
                "url": data.get("url", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _get_page(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene una pagina por su ID.

        Args:
            params: Debe contener 'page_id'
        """
        page_id = params.get("page_id", "")
        if not page_id:
            return {"success": False, "error": "Parametro requerido: page_id"}
        self._log_operation("get_page", f"id={page_id}")

        try:
            response = self._http.get(f"/pages/{page_id}")
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("id", page_id),
                "object": data.get("object", "page"),
                "archived": data.get("archived", False),
                "properties": data.get("properties", {}),
                "url": data.get("url", ""),
                "created_time": data.get("created_time", ""),
                "last_edited_time": data.get("last_edited_time", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _update_page(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza las propiedades de una pagina en Notion.

        Args:
            params: Debe contener 'page_id' y 'properties'
        """
        page_id = params.get("page_id", "")
        properties = params.get("properties", {})
        if not page_id or not properties:
            return {"success": False, "error": "Parametros requeridos: page_id, properties"}
        self._log_operation("update_page", f"id={page_id}")

        try:
            body: dict[str, Any] = {"properties": properties}
            if params.get("archived") is not None:
                body["archived"] = params["archived"]
            if params.get("icon"):
                body["icon"] = params["icon"]
            if params.get("cover"):
                body["cover"] = params["cover"]

            response = self._http.patch(f"/pages/{page_id}", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("id", page_id),
                "object": data.get("object", "page"),
                "archived": data.get("archived", False),
                "url": data.get("url", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _query_database(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta una base de datos de Notion con filtros.

        Args:
            params: Debe contener 'database_id' y opcionalmente 'filter', 'sorts'
        """
        database_id = params.get("database_id", "")
        if not database_id:
            return {"success": False, "error": "Parametro requerido: database_id"}
        self._log_operation("query_database", f"db={database_id}")

        try:
            body: dict[str, Any] = {}
            if params.get("filter"):
                body["filter"] = params["filter"]
            if params.get("sorts"):
                body["sorts"] = params["sorts"]
            if params.get("start_cursor"):
                body["start_cursor"] = params["start_cursor"]
            if params.get("page_size"):
                body["page_size"] = params["page_size"]

            response = self._http.post(f"/databases/{database_id}/query", json=body if body else None)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "results": data.get("results", []),
                "has_more": data.get("has_more", False),
                "object": data.get("object", "list"),
                "next_cursor": data.get("next_cursor", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _create_database(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una base de datos en Notion.

        Args:
            params: Debe contener 'parent' (page_id), 'title' y 'properties' (schema)
        """
        parent = params.get("parent", {})
        title = params.get("title", "")
        properties = params.get("properties", {})
        if not parent or not title:
            return {"success": False, "error": "Parametros requeridos: parent, title"}
        self._log_operation("create_database", f"title={title}")

        try:
            # Build Notion title format
            title_rich_text = title if isinstance(title, list) else [{"type": "text", "text": {"content": title}}]

            body: dict[str, Any] = {
                "parent": parent,
                "title": title_rich_text,
                "properties": properties if properties else {"Name": {"title": {}}},
            }

            response = self._http.post("/databases", json=body)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "id": data.get("id", ""),
                "object": data.get("object", "database"),
                "title": data.get("title", title_rich_text),
                "url": data.get("url", ""),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Busca en el workspace de Notion.

        Args:
            params: Opcionalmente 'query', 'filter', 'sort'
        """
        query = params.get("query", "")
        self._log_operation("search", f"query={query}")

        try:
            body: dict[str, Any] = {}
            if query:
                body["query"] = query
            if params.get("filter"):
                body["filter"] = params["filter"]
            if params.get("sort"):
                body["sort"] = params["sort"]
            if params.get("start_cursor"):
                body["start_cursor"] = params["start_cursor"]
            if params.get("page_size"):
                body["page_size"] = params["page_size"]

            response = self._http.post("/search", json=body if body else None)
            if not response.ok:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.body}"}
            data = response.json()
            return {
                "success": True,
                "results": data.get("results", []),
                "has_more": data.get("has_more", False),
                "object": data.get("object", "list"),
                "next_cursor": data.get("next_cursor", None),
            }
        except HTTPClientError as e:
            return {"success": False, "error": str(e)}


NOTION_SCHEMA = ConnectorSchema(
    name="notion",
    version="1.0.0",
    description="Gestiona paginas, bases de datos y bloques en Notion",
    category="project_management",
    icon="book-open",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_page", description="Crea una pagina", category="write"),
        ActionDefinition(name="get_page", description="Obtiene una pagina", category="read"),
        ActionDefinition(name="update_page", description="Actualiza una pagina", category="write"),
        ActionDefinition(name="query_database", description="Consulta una base de datos", category="read"),
        ActionDefinition(name="create_database", description="Crea una base de datos", category="write"),
        ActionDefinition(name="search", description="Busca en el workspace", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["integration_token"], description="Notion Integration Token")
    ],
)
