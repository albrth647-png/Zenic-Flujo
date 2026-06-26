"""Conector Typeform — Forms and Surveys API."""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class TypeformConnector(BaseConnector):
    name = "typeform"
    version = "1.0.0"
    description = "Gestiona formularios, respuestas y webhooks en Typeform"
    category = "forms"
    icon = "file-plus"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""; self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._api_key = c.get("api_key", "")
        if not self._api_key: logger.error("Typeform: api_key requerida"); return False
        self._http = HttpClient(base_url="https://api.typeform.com", connector_name=self.name)
        self._http.set_header("Authorization", f"Bearer {self._api_key}")
        self._connected = True; self._log_operation("connect"); return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"list_forms": self._list_forms, "get_form": self._get_form, "get_responses": self._get_responses,
                       "create_webhook": self._create_webhook, "delete_webhook": self._delete_webhook}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool: return bool(self._auth_provider and self._auth_provider.validate())
    def disconnect(self) -> bool: self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    def _api(self, method: str, path: str, **kw: Any) -> dict:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kw)
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d.get("items", d)}
            return {"success": False, "error": d.get("description", f"HTTP {resp.status_code}")}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _list_forms(self, p: dict) -> dict: return self._api("get", "/forms", params=p)
    def _get_form(self, p: dict) -> dict: return self._api("get", f"/forms/{p.get('form_id', '')}")
    def _get_responses(self, p: dict) -> dict: return self._api("get", f"/forms/{p.get('form_id', '')}/responses", params=p)
    def _create_webhook(self, p: dict) -> dict:
        return self._api("put", f"/forms/{p.get('form_id', '')}/webhooks/{p.get('tag', 'default')}",
                         json={"url": p.get("url", ""), "enabled": p.get("enabled", True), "secret": p.get("secret", "")})
    def _delete_webhook(self, p: dict) -> dict:
        return self._api("delete", f"/forms/{p.get('form_id', '')}/webhooks/{p.get('tag', 'default')}")


TYPEFORM_SCHEMA = ConnectorSchema(name="typeform", version="1.0.0", description="Gestiona formularios y respuestas en Typeform",
    category="forms", icon="file-plus", author="Zenic-Flijo", actions=[
    ActionDefinition(name="list_forms", description="Lista formularios", category="read"),
    ActionDefinition(name="get_form", description="Obtiene un formulario por ID", category="read"),
    ActionDefinition(name="get_responses", description="Obtiene respuestas de un formulario", category="read"),
    ActionDefinition(name="create_webhook", description="Crea webhook para formulario", category="write"),
    ActionDefinition(name="delete_webhook", description="Elimina webhook de formulario", category="write"),
], auth_requirements=[AuthRequirement(auth_type="bearer_token", required_fields=["api_key"])])
