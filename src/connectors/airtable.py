"""Conector Airtable — Bases de datos sin codigo API."""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class AirtableConnector(BaseConnector):
    name = "airtable"
    version = "1.0.0"
    description = "Lee y escribe registros en bases de Airtable"
    category = "database"
    icon = "grid"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""; self._base_id: str = ""; self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._api_key = c.get("api_key", ""); self._base_id = c.get("base_id", "")
        if not self._api_key or not self._base_id:
            logger.error("Airtable: api_key y base_id requeridos"); return False
        self._http = HttpClient(base_url=f"https://api.airtable.com/v0/{self._base_id}", connector_name=self.name)
        self._http.set_header("Authorization", f"Bearer {self._api_key}")
        self._connected = True; self._log_operation("connect", f"base={self._base_id[:6]}..."); return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"list_records": self._list_records, "get_record": self._get_record, "create_record": self._create_record,
                       "update_record": self._update_record, "delete_record": self._delete_record}
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
            if resp.ok: return {"success": True, "data": d.get("records", d)}
            return {"success": False, "error": d.get("error", {}).get("message", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _list_records(self, p: dict[str, Any]) -> dict[str, Any]:
        table = p.pop("table", ""); return self._api("get", f"/{table}", params=p) if table else {"success": False, "error": "table requerido"}
    def _get_record(self, p: dict[str, Any]) -> dict[str, Any]:
        table = p.get("table", ""); rec_id = p.get("record_id", "")
        return self._api("get", f"/{table}/{rec_id}") if table and rec_id else {"success": False, "error": "table y record_id requeridos"}
    def _create_record(self, p: dict[str, Any]) -> dict[str, Any]:
        table = p.pop("table", ""); return self._api("post", f"/{table}", json={"fields": p}) if table else {"success": False, "error": "table requerido"}
    def _update_record(self, p: dict[str, Any]) -> dict[str, Any]:
        table = p.pop("table", ""); rec_id = p.pop("record_id", "")
        return self._api("patch", f"/{table}/{rec_id}", json={"fields": p}) if table and rec_id else {"success": False, "error": "table y record_id requeridos"}
    def _delete_record(self, p: dict[str, Any]) -> dict[str, Any]:
        table = p.get("table", ""); rec_id = p.get("record_id", "")
        return self._api("delete", f"/{table}/{rec_id}") if table and rec_id else {"success": False, "error": "table y record_id requeridos"}


AIRTABLE_SCHEMA = ConnectorSchema(name="airtable", version="1.0.0", description="Lee y escribe registros en Airtable",
    category="database", icon="grid", author="Zenic-Flijo", actions=[
    ActionDefinition(name="list_records", description="Lista registros de una tabla", category="read"),
    ActionDefinition(name="get_record", description="Obtiene un registro por ID", category="read"),
    ActionDefinition(name="create_record", description="Crea un nuevo registro", category="write"),
    ActionDefinition(name="update_record", description="Actualiza un registro existente", category="write"),
    ActionDefinition(name="delete_record", description="Elimina un registro", category="write"),
], auth_requirements=[AuthRequirement(auth_type="bearer_token", required_fields=["api_key", "base_id"])])
