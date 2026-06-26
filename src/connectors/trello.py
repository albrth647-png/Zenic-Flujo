"""Conector Trello — Project Management API."""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TrelloConnector(BaseConnector):
    name = "trello"
    version = "1.0.0"
    description = "Gestiona tableros, listas y tarjetas en Trello"
    category = "project_management"
    icon = "columns"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""; self._token: str = ""; self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._api_key = c.get("api_key", ""); self._token = c.get("token", "")
        if not self._api_key or not self._token: logger.error("Trello: api_key y token requeridos"); return False
        self._http = HttpClient(base_url="https://api.trello.com/1", connector_name=self.name)
        self._connected = True; self._log_operation("connect"); return True

    def _get_auth_params(self, **extra: Any) -> dict: return {"key": self._api_key, "token": self._token, **extra}

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"get_boards": self._get_boards, "get_board": self._get_board, "get_lists": self._get_lists,
                       "get_cards": self._get_cards, "get_card": self._get_card, "create_card": self._create_card,
                       "update_card": self._update_card, "add_comment": self._add_comment}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool: return bool(self._auth_provider and self._auth_provider.validate())
    def disconnect(self) -> bool: self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    def _api(self, method: str, path: str, **kw: Any) -> dict:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            kw.setdefault("params", {}).update(self._get_auth_params())
            resp = getattr(self._http, method)(path, **kw)
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d}
            return {"success": False, "error": d.get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_boards(self, p: dict) -> dict: return self._api("get", "/members/me/boards", params=p)
    def _get_board(self, p: dict) -> dict: return self._api("get", f"/boards/{p.get('board_id', '')}", params=p)
    def _get_lists(self, p: dict) -> dict: return self._api("get", f"/boards/{p.get('board_id', '')}/lists")
    def _get_cards(self, p: dict) -> dict:
        lid = p.get("list_id", ""); return self._api("get", f"/lists/{lid}/cards", params=p) if lid else self._api("get", "/members/me/cards", params=p)
    def _get_card(self, p: dict) -> dict: return self._api("get", f"/cards/{p.get('card_id', '')}", params=p)
    def _create_card(self, p: dict) -> dict:
        return self._api("post", "/cards", params=self._get_auth_params(**{k: p[k] for k in ("idList", "name", "desc", "due") if k in p}))
    def _update_card(self, p: dict) -> dict:
        cid = p.pop("card_id", ""); return self._api("put", f"/cards/{cid}", params=self._get_auth_params(**p))
    def _add_comment(self, p: dict) -> dict:
        return self._api("post", f"/cards/{p.get('card_id', '')}/actions/comments", params=self._get_auth_params(text=p.get("text", "")))


TRELLO_SCHEMA = ConnectorSchema(name="trello", version="1.0.0", description="Gestiona tableros y tarjetas en Trello",
    category="project_management", icon="columns", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_boards", description="Lista tableros del usuario", category="read"),
    ActionDefinition(name="get_board", description="Obtiene un tablero por ID", category="read"),
    ActionDefinition(name="get_lists", description="Lista listas de un tablero", category="read"),
    ActionDefinition(name="get_cards", description="Lista tarjetas de una lista", category="read"),
    ActionDefinition(name="get_card", description="Obtiene una tarjeta por ID", category="read"),
    ActionDefinition(name="create_card", description="Crea una nueva tarjeta", category="write"),
    ActionDefinition(name="update_card", description="Actualiza una tarjeta", category="write"),
    ActionDefinition(name="add_comment", description="Agrega comentario a tarjeta", category="write"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["api_key", "token"])])
