"""Conector HashiCorp Vault — Secrets Management API."""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class VaultConnector(BaseConnector):
    name = "vault"
    version = "1.0.0"
    description = "Gestiona secretos, claves y tokens en HashiCorp Vault"
    category = "security"
    icon = "lock"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._vault_url: str = ""
        self._token: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials
            self._vault_url = c.get("vault_url", "").rstrip("/")
            self._token = c.get("token", "")
        if not self._vault_url or not self._token:
            logger.error("Vault: vault_url y token requeridos"); return False
        self._http = HttpClient(base_url=self._vault_url, connector_name=self.name)
        self._http.set_header("X-Vault-Token", self._token)
        self._connected = True
        self._log_operation("connect", f"vault={self._vault_url}")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"read_secret": self._read_secret, "write_secret": self._write_secret, "delete_secret": self._delete_secret,
                       "list_secrets": self._list_secrets, "health_check": self._health_check}
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
            if resp.ok: return {"success": True, "data": d.get("data", d)}
            return {"success": False, "error": d.get("errors", [""])[0] if d.get("errors") else f"HTTP {resp.status_code}"}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _read_secret(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("get", f"/v1/secret/data/{p.get('path', '')}")
    def _write_secret(self, p: dict[str, Any]) -> dict[str, Any]:
        path = p.pop("path", "")
        return self._api("post", f"/v1/secret/data/{path}", json={"data": p}) if path else {"success": False, "error": "path requerido"}
    def _delete_secret(self, p: dict[str, Any]) -> dict[str, Any]: return self._api("delete", f"/v1/secret/metadata/{p.get('path', '')}")
    def _list_secrets(self, p: dict[str, Any]) -> dict[str, Any]:
        path = p.get('path', '')
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = self._http.get(f"/v1/secret/metadata/{path}", params={"list": "true"})
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            if resp.ok: return {"success": True, "data": d.get("data", {})}
            return {"success": False, "error": d.get("errors", [""])[0]}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}
    def _health_check(self, p: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = self._http.get("/v1/sys/health")
            d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
            return {"success": resp.ok or resp.status_code in (200, 429, 473, 503),
                    "initialized": d.get("initialized", False), "sealed": d.get("sealed", True),
                    "cluster_name": d.get("cluster_name", ""), "version": d.get("version", "")}
        except Exception as e: return {"success": False, "error": str(e)}


VAULT_SCHEMA = ConnectorSchema(name="vault", version="1.0.0", description="Gestiona secretos en HashiCorp Vault",
    category="security", icon="lock", author="Zenic-Flijo", actions=[
    ActionDefinition(name="read_secret", description="Lee un secreto por ruta", category="read"),
    ActionDefinition(name="write_secret", description="Escribe un nuevo secreto", category="write"),
    ActionDefinition(name="delete_secret", description="Elimina un secreto", category="write"),
    ActionDefinition(name="list_secrets", description="Lista secretos en una ruta", category="read"),
    ActionDefinition(name="health_check", description="Verifica salud del cluster Vault", category="read"),
], auth_requirements=[AuthRequirement(auth_type="bearer_token", required_fields=["vault_url", "token"])])
