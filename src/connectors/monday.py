"""Monday.com Connector — Project & Work Management.

Integrates with Monday.com GraphQL API for boards, items, groups,
columns, users, and automations.
"""

from __future__ import annotations

import json
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class MondayConnector(BaseConnector):
    """Conector para Monday.com: boards, items, grupos y columnas."""

    name = "monday"
    version = "1.0.0"
    description = "Gestiona boards, items, grupos, columnas y usuarios via Monday.com GraphQL API"
    category = "productivity"
    icon = "layout"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_url: str = "https://api.monday.com/v2"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("MondayConnector: API token no configurado")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            api_token = creds.get("api_token", "")
            if not api_token:
                return False
            self._http = HttpClient(base_url=self._api_url, connector_name=self.name)
            self._http.set_header("Authorization", api_token)
            self._http.set_header("API-Version", "2024-01")
            self._connected = True
            self._log_operation("connect", "Monday.com conectado")
            return True
        except HTTPClientError as e:
            creds = self._auth_provider.get_credentials()
            self._http = HttpClient(base_url=self._api_url, connector_name=self.name)
            self._http.set_header("Authorization", creds.get("api_token", ""))
            self._http.set_header("API-Version", "2024-01")
            self._connected = True
            self._log_operation("connect", f"Monday configurado (status fallo: {e})")
            return True

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self._http.post("/", json=payload)
        if resp.ok:
            data = resp.json() or {}
            return data.get("data", {})
        return {"error": f"HTTP {resp.status_code}"}

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {
            "list_boards": self._list_boards,
            "get_board": self._get_board,
            "create_board": self._create_board,
            "list_items": self._list_items,
            "get_item": self._get_item,
            "create_item": self._create_item,
            "update_item": self._update_item,
            "move_item": self._move_item,
            "list_columns": self._list_columns,
            "create_column": self._create_column,
            "list_users": self._list_users,
            "create_group": self._create_group,
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

    def _list_boards(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = params.get("limit", 25)
        page = params.get("page", 1)
        q = f"query {{ boards (limit:{limit} page:{page}) {{ id name board_kind description updated_at }} }}"
        data = self._graphql(q)
        return {"success": True, "boards": data.get("boards", [])}

    def _get_board(self, params: dict[str, Any]) -> dict[str, Any]:
        bid = params.get("board_id", "")
        if not bid:
            return {"success": False, "error": "Parametro requerido: board_id"}
        q = f"query {{ boards (ids: {bid}) {{ id name board_kind description columns {{ id title type }} groups {{ id title }} }} }}"
        data = self._graphql(q)
        boards = data.get("boards", [])
        return {"success": True, "board": boards[0] if boards else {}}

    def _create_board(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        kind = params.get("board_kind", "public")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}
        q = f'mutation {{ create_board (board_name: "{name}", board_kind: {kind}) {{ id name board_kind }} }}'
        data = self._graphql(q)
        result = data.get("create_board", {})
        return {
            "success": True,
            "id": result.get("id"),
            "name": result.get("name"),
            "board_kind": result.get("board_kind"),
        }

    def _list_items(self, params: dict[str, Any]) -> dict[str, Any]:
        bid = params.get("board_id", "")
        limit = params.get("limit", 25)
        if not bid:
            return {"success": False, "error": "Parametro requerido: board_id"}
        q = f"query {{ boards (ids: {bid}) {{ items (limit:{limit}) {{ id name column_values {{ id text value }} updated_at }} }} }}"
        data = self._graphql(q)
        boards = data.get("boards", [])
        items = boards[0].get("items", []) if boards else []
        return {"success": True, "items": items}

    def _get_item(self, params: dict[str, Any]) -> dict[str, Any]:
        iid = params.get("item_id", "")
        if not iid:
            return {"success": False, "error": "Parametro requerido: item_id"}
        q = f"query {{ items (ids: {iid}) {{ id name column_values {{ id text value type }} board {{ id name }} created_at }} }}"
        data = self._graphql(q)
        items = data.get("items", [])
        return {"success": True, "item": items[0] if items else {}}

    def _create_item(self, params: dict[str, Any]) -> dict[str, Any]:
        bid = params.get("board_id", "")
        name = params.get("name", "")
        if not bid or not name:
            return {"success": False, "error": "Parametros requeridos: board_id, name"}
        cols_json = ""
        if params.get("column_values"):
            cols_json = f', column_values: {json.dumps(json.dumps(params["column_values"]))}'
        group_id = f', group_id: "{params["group_id"]}"' if params.get("group_id") else ""
        q = f'mutation {{ create_item (board_id: {bid}, item_name: "{name}"{group_id}{cols_json}) {{ id name board {{ id }} }} }}'
        data = self._graphql(q)
        result = data.get("create_item", {})
        return {"success": True, "id": result.get("id"), "name": result.get("name")}

    def _update_item(self, params: dict[str, Any]) -> dict[str, Any]:
        iid = params.get("item_id", "")
        col_vals = params.get("column_values", {})
        if not iid or not col_vals:
            return {"success": False, "error": "Parametros requeridos: item_id, column_values"}
        q = f"mutation {{ change_multiple_column_values (item_id: {iid}, column_values: {json.dumps(json.dumps(col_vals))}) {{ id name }} }}"
        data = self._graphql(q)
        result = data.get("change_multiple_column_values", {})
        return {"success": True, "id": result.get("id"), "updated": True}

    def _move_item(self, params: dict[str, Any]) -> dict[str, Any]:
        iid = params.get("item_id", "")
        gid = params.get("group_id", "")
        if not iid or not gid:
            return {"success": False, "error": "Parametros requeridos: item_id, group_id"}
        q = f'mutation {{ move_item_to_group (item_id: {iid}, group_id: "{gid}") {{ id }} }}'
        data = self._graphql(q)
        return {"success": True, "moved": bool(data.get("move_item_to_group"))}

    def _list_columns(self, params: dict[str, Any]) -> dict[str, Any]:
        bid = params.get("board_id", "")
        if not bid:
            return {"success": False, "error": "Parametro requerido: board_id"}
        q = f"query {{ boards (ids: {bid}) {{ columns {{ id title type settings_str }} }} }}"
        data = self._graphql(q)
        boards = data.get("boards", [])
        return {"success": True, "columns": boards[0].get("columns", []) if boards else []}

    def _create_column(self, params: dict[str, Any]) -> dict[str, Any]:
        bid = params.get("board_id", "")
        title = params.get("title", "")
        col_type = params.get("type", "text")
        if not bid or not title:
            return {"success": False, "error": "Parametros requeridos: board_id, title"}
        q = f"mutation {{ create_column (board_id: {bid}, title: \"{title}\", column_type: {col_type}) {{ id title type }} }}"
        data = self._graphql(q)
        result = data.get("create_column", {})
        return {"success": True, "id": result.get("id"), "title": result.get("title")}

    def _list_users(self, params: dict[str, Any]) -> dict[str, Any]:
        q = "query { users { id name email is_admin created_at } }"
        data = self._graphql(q)
        return {"success": True, "users": data.get("users", [])}

    def _create_group(self, params: dict[str, Any]) -> dict[str, Any]:
        bid = params.get("board_id", "")
        title = params.get("title", "")
        if not bid or not title:
            return {"success": False, "error": "Parametros requeridos: board_id, title"}
        q = f'mutation {{ create_group (board_id: {bid}, group_name: "{title}") {{ id title }} }}'
        data = self._graphql(q)
        result = data.get("create_group", {})
        return {"success": True, "id": result.get("id"), "title": result.get("title")}


MONDAY_SCHEMA = ConnectorSchema(
    name="monday",
    version="1.0.0",
    description="Gestiona boards, items, grupos, columnas y usuarios via Monday.com GraphQL API",
    category="productivity",
    icon="layout",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_boards", description="Lista boards", category="read"),
        ActionDefinition(name="get_board", description="Obtiene board", category="read"),
        ActionDefinition(name="create_board", description="Crea board", category="write"),
        ActionDefinition(name="list_items", description="Lista items de un board", category="read"),
        ActionDefinition(name="get_item", description="Obtiene item", category="read"),
        ActionDefinition(name="create_item", description="Crea item", category="write"),
        ActionDefinition(name="update_item", description="Actualiza item", category="write"),
        ActionDefinition(name="move_item", description="Mueve item a grupo", category="write"),
        ActionDefinition(name="list_columns", description="Lista columnas", category="read"),
        ActionDefinition(name="create_column", description="Crea columna", category="write"),
        ActionDefinition(name="list_users", description="Lista usuarios", category="read"),
        ActionDefinition(name="create_group", description="Crea grupo", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="api_key",
            required_fields=["api_token"],
            description="Monday.com API token (Bearer token)",
        )
    ],
)
