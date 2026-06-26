"""Conector Mailgun — Email API Service."""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class MailgunConnector(BaseConnector):
    name = "mailgun"
    version = "1.0.0"
    description = "Envia emails transaccionales via Mailgun API"
    category = "communication"
    icon = "mail"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""; self._domain: str = ""; self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate(): return False
        if hasattr(self._auth_provider, "_credentials"):
            c = self._auth_provider._credentials; self._api_key = c.get("api_key", ""); self._domain = c.get("domain", "")
        if not self._api_key or not self._domain:
            logger.error("Mailgun: api_key y domain requeridos"); return False
        self._base_url = f"https://api.mailgun.net/v3/{self._domain}"
        self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
        self._http.set_auth("Basic", username="api", password=self._api_key)
        self._connected = True; self._log_operation("connect", f"domain={self._domain}"); return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map = {"send_email": self._send_email, "get_domains": self._get_domains, "get_events": self._get_events,
                       "create_domain": self._create_domain, "verify_domain": self._verify_domain}
        handler = action_map.get(action)
        return handler(params) if handler else {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}

    def validate(self) -> bool: return bool(self._auth_provider and self._auth_provider.validate())
    def disconnect(self) -> bool: self._connected = False; self._http = None; self._log_operation("disconnect"); return True

    def _api(self, method: str, path: str, **kw: Any) -> dict:
        if not self._http: return {"success": False, "error": "Not connected"}
        try:
            resp = getattr(self._http, method)(path, **kw)
            if resp.ok:
                d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
                return {"success": True, "data": d}
            else:
                d = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
                return {"success": False, "error": d.get("message", d.get("error", f"HTTP {resp.status_code}"))}
        except HTTPClientError as e: return {"success": False, "error": str(e)}
        except Exception as e: return {"success": False, "error": str(e)}

    def _send_email(self, p: dict) -> dict:
        to = p.get("to", ""); subject = p.get("subject", ""); text = p.get("text", "")
        html = p.get("html", ""); from_addr = p.get("from", f"noreply@{self._domain}")
        if not to or not subject: return {"success": False, "error": "to y subject requeridos"}
        data = {"from": from_addr, "to": to, "subject": subject}
        if text: data["text"] = text
        if html: data["html"] = html
        if p.get("cc"): data["cc"] = p["cc"]
        if p.get("bcc"): data["bcc"] = p["bcc"]
        return self._api("post", "/messages", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})

    def _get_domains(self, p: dict) -> dict: return self._api("get", "/domains", params=p)
    def _get_events(self, p: dict) -> dict: return self._api("get", "/events", params=p)
    def _create_domain(self, p: dict) -> dict:
        return self._api("post", "/domains", data={"name": p.get("name", ""), "smtp_password": p.get("smtp_password", "")},
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
    def _verify_domain(self, p: dict) -> dict: return self._api("get", f"/domains/{p.get('domain', self._domain)}/verify")


MAILGUN_SCHEMA = ConnectorSchema(name="mailgun", version="1.0.0", description="Envia emails transaccionales via Mailgun",
    category="communication", icon="mail", author="Zenic-Flijo", actions=[
    ActionDefinition(name="send_email", description="Envia un email transaccional", category="write"),
    ActionDefinition(name="get_domains", description="Lista dominios configurados", category="read"),
    ActionDefinition(name="get_events", description="Obtiene eventos de envio", category="read"),
    ActionDefinition(name="create_domain", description="Registra un nuevo dominio", category="write"),
    ActionDefinition(name="verify_domain", description="Verifica un dominio", category="read"),
], auth_requirements=[AuthRequirement(auth_type="api_key", required_fields=["api_key", "domain"])])
