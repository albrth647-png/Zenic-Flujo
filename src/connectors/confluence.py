"""Conector Confluence — Documentación y Wiki API."""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class ConfluenceConnector(BaseConnector):
    name = "confluence"
    version = "1.0.0"
    description = "Gestiona paginas, espacios y contenido en Confluence"
    category = "documentation"
    icon = "file-text"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""; self._username: str = ""; self._api_token: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._base_url = c.get("base_url", "").rstrip("/")
            self._username = c.get("username", ""); self._api_token = c.get("api_token", "")
        if not self._base_url or not self._username or not self._api_token:
            logger.error("Confluence: base_url, username y api_token requeridos"); return False
        self._http = HttpClient(base_url=f"{self._base_url}/rest/api", connector_name=self.name)
        self._http.set_auth("Basic", username=self._username, password=self._api_token)
        self._connected = True; self._log_operation("connect", f"url={self._base_url}"); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"get_page": self._get_page, "create_page": self._create_page, "update_page": self._update_page,
                       "delete_page": self._delete_page, "search_content": self._search_content, "get_spaces": self._get_spaces}
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
            if resp.ok: return {"success": True, "data": d.get("results", d)}
            return {"success": False, "error": d.get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _get_page(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/content/{p.get('page_id', '')}", params=p.get("params"))
    def _create_page(self, p: dict[str, Any]) -> dict[str, Any]:
        return self._api("post", "/content", json={"type": "page", "title": p.get("title", ""),
            "space": {"key": p.get("space_key", "")}, "body": {"storage": {"value": p.get("body", ""), "representation": "storage"}}})
    def _update_page(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("put", f"/content/{p.get('page_id', '')}", json=p.get("data", {}))
    def _delete_page(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("delete", f"/content/{p.get('page_id', '')}")
    def _search_content(self, p: dict[str, Any]) -> dict[str, Any]:
        return self._api("get", "/search", params={"cql": p.get("cql", ""), "limit": p.get("limit", 25)})
    def _get_spaces(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", "/space", params=p)


CONFLUENCE_SCHEMA = ConnectorSchema(name="confluence", version="1.0.0", description="Gestiona paginas y contenido en Confluence",
    category="documentation", icon="file-text", author="Zenic-Flijo", actions=[
    ActionDefinition(name="get_page", description="Obtiene una pagina por ID", category="read"),
    ActionDefinition(name="create_page", description="Crea una nueva pagina", category="write"),
    ActionDefinition(name="update_page", description="Actualiza una pagina", category="write"),
    ActionDefinition(name="delete_page", description="Elimina una pagina", category="write"),
    ActionDefinition(name="search_content", description="Busca contenido con CQL", category="read"),
    ActionDefinition(name="get_spaces", description="Lista espacios disponibles", category="read"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["base_url", "username", "api_token"])])
