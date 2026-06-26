"""Mailchimp Connector — Email Marketing & Automation.

Integrates with Mailchimp API v3 for campaign management, audience
management, email templates, and automation workflows.
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class MailchimpConnector(BaseConnector):
    """Conector para Mailchimp: campañas, audiencias y automatización."""

    name = "mailchimp"
    version = "1.0.0"
    description = "Gestiona campañas, audiencias y automatización de email marketing via Mailchimp API"
    category = "marketing"
    icon = "mail"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("MailchimpConnector: API key no configurada")
            return False
        try:
            creds = self._auth_provider.get_credentials()
            api_key = creds.get("api_key", "")
            if not api_key:
                return False
            dc = api_key.split("-")[-1] if "-" in api_key else "us1"
            self._base_url = f"https://{dc}.api.mailchimp.com/3.0"
            self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
            self._http.set_auth("Basic", username="anystring", password=api_key)
            resp = self._http.get("/")
            if resp.ok or resp.status_code == 200:
                self._connected = True
                self._log_operation("connect", f"Mailchimp datacenter={dc}")
                return True
            self._connected = True
            self._log_operation("connect", "Mailchimp configurado (sin verificación)")
            return True
        except HTTPClientError as e:
            self._http = HttpClient(base_url=self._base_url or "https://us1.api.mailchimp.com/3.0", connector_name=self.name)
            creds = self._auth_provider.get_credentials()
            api_key = creds.get("api_key", "")
            if api_key:
                dc = api_key.split("-")[-1] if "-" in api_key else "us1"
                self._base_url = f"https://{dc}.api.mailchimp.com/3.0"
                self._http = HttpClient(base_url=self._base_url, connector_name=self.name)
                self._http.set_auth("Basic", username="anystring", password=api_key)
            self._connected = True
            self._log_operation("connect", f"Mailchimp configurado (status check fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "add_member": self._add_member,
            "update_member": self._update_member,
            "get_member": self._get_member,
            "list_members": self._list_members,
            "create_campaign": self._create_campaign,
            "send_campaign": self._send_campaign,
            "get_campaign": self._get_campaign,
            "list_lists": self._list_lists,
            "create_list": self._create_list,
            "create_template": self._create_template,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _list_lists(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista todas las audiencias (lists) de la cuenta."""
        fields = params.get("fields", "")
        resp = self._http.get("/lists", params={"fields": fields, "count": params.get("count", 25), "offset": params.get("offset", 0)})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "lists": data.get("lists", []), "total_items": data.get("total_items", 0)}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una nueva audiencia (list)."""
        name = params.get("name", "")
        contact = params.get("contact", {})
        permission_reminder = params.get("permission_reminder", "")
        if not name or not contact:
            return {"success": False, "error": "Parametros requeridos: name, contact"}
        payload = {
            "name": name,
            "contact": contact,
            "permission_reminder": permission_reminder,
            "campaign_defaults": params.get("campaign_defaults", {"from_name": "", "from_email": "", "subject": "", "language": "en"}),
            "email_type_option": params.get("email_type_option", True),
        }
        resp = self._http.post("/lists", json=payload)
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "list_id": data.get("id", ""), "web_id": data.get("web_id", 0), "name": data.get("name", name)}
        error = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
        return {"success": False, "error": f"HTTP {resp.status_code}: {error}"}

    def _add_member(self, params: dict[str, Any]) -> dict[str, Any]:
        """Agrega un miembro a una audiencia (o lo actualiza si existe)."""
        list_id = params.get("list_id", "")
        email = params.get("email", "")
        if not list_id or not email:
            return {"success": False, "error": "Parametros requeridos: list_id, email"}
        # MD5 del email exigido por la API de Mailchimp para identificar subscribers.
        # NO es para fines de seguridad — es el contrato de la API externa.
        # Ref: https://mailchimp.com/developer/marketing/api/list-members/
        email_hash = hashlib.md5(email.lower().encode(), usedforsecurity=False).hexdigest()
        payload = {
            "email_address": email,
            "status": params.get("status", "subscribed"),
            "merge_fields": params.get("merge_fields", {}),
            "tags": params.get("tags", []),
        }
        resp = self._http.put(f"/lists/{list_id}/members/{email_hash}", json=payload)
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id", ""), "email": email, "status": data.get("status", "")}
        error = resp.json() if hasattr(resp, "json") and callable(resp.json) else {}
        return {"success": False, "error": f"HTTP {resp.status_code}: {error}"}

    def _update_member(self, params: dict[str, Any]) -> dict[str, Any]:
        """Actualiza un miembro existente en una audiencia."""
        list_id = params.get("list_id", "")
        email = params.get("email", "")
        if not list_id or not email:
            return {"success": False, "error": "Parametros requeridos: list_id, email"}
        # MD5 del email exigido por la API de Mailchimp (no criptográfico — contrato API).
        email_hash = hashlib.md5(email.lower().encode(), usedforsecurity=False).hexdigest()
        payload = {k: v for k, v in params.items() if k in ("status", "merge_fields", "tags", "email_address")}
        resp = self._http.patch(f"/lists/{list_id}/members/{email_hash}", json=payload)
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id", ""), "status": data.get("status", "")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_member(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un miembro de una audiencia por email."""
        list_id = params.get("list_id", "")
        email = params.get("email", "")
        if not list_id or not email:
            return {"success": False, "error": "Parametros requeridos: list_id, email"}
        # MD5 del email exigido por la API de Mailchimp (no criptográfico — contrato API).
        email_hash = hashlib.md5(email.lower().encode(), usedforsecurity=False).hexdigest()
        resp = self._http.get(f"/lists/{list_id}/members/{email_hash}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id", ""), "email": data.get("email_address", ""), "status": data.get("status", ""), "stats": data.get("stats", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _list_members(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista miembros de una audiencia."""
        list_id = params.get("list_id", "")
        if not list_id:
            return {"success": False, "error": "Parametro requerido: list_id"}
        resp = self._http.get(f"/lists/{list_id}/members", params={"count": params.get("count", 25), "offset": params.get("offset", 0), "status": params.get("status", "")})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "members": data.get("members", []), "total_items": data.get("total_items", 0)}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_campaign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una campaña de email."""
        list_id = params.get("list_id", "")
        subject = params.get("subject", "")
        if not list_id or not subject:
            return {"success": False, "error": "Parametros requeridos: list_id, subject"}
        payload = {
            "type": params.get("type", "regular"),
            "recipients": {"list_id": list_id, "segment_opts": params.get("segment_opts", {})},
            "settings": {
                "subject_line": subject,
                "title": params.get("title", subject),
                "from_name": params.get("from_name", ""),
                "reply_to": params.get("reply_to", ""),
                "template_id": params.get("template_id"),
            },
        }
        resp = self._http.post("/campaigns", json=payload)
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "campaign_id": data.get("id", ""), "web_id": data.get("web_id", 0), "status": data.get("status", "save")}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _send_campaign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envía una campaña de email."""
        campaign_id = params.get("campaign_id", "")
        if not campaign_id:
            return {"success": False, "error": "Parametro requerido: campaign_id"}
        resp = self._http.post(f"/campaigns/{campaign_id}/actions/send")
        if resp.ok or resp.status_code == 204:
            return {"success": True, "campaign_id": campaign_id, "status": "sent"}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _get_campaign(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene una campaña por ID."""
        campaign_id = params.get("campaign_id", "")
        if not campaign_id:
            return {"success": False, "error": "Parametro requerido: campaign_id"}
        resp = self._http.get(f"/campaigns/{campaign_id}")
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "id": data.get("id", ""), "status": data.get("status", ""), "emails_sent": data.get("emails_sent", 0), "recipients": data.get("recipients", {})}
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    def _create_template(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una plantilla de email."""
        name = params.get("name", "")
        html = params.get("html", "")
        if not name or not html:
            return {"success": False, "error": "Parametros requeridos: name, html"}
        resp = self._http.post("/templates", json={"name": name, "html": html})
        if resp.ok:
            data = resp.json() or {}
            return {"success": True, "template_id": data.get("id", ""), "name": name}
        return {"success": False, "error": f"HTTP {resp.status_code}"}


MAILCHIMP_SCHEMA = ConnectorSchema(
    name="mailchimp",
    version="1.0.0",
    description="Gestiona campañas, audiencias y automatización de email marketing via Mailchimp API",
    category="marketing",
    icon="mail",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="list_lists", description="Lista audiencias", category="read"),
        ActionDefinition(name="create_list", description="Crea audiencia", category="write"),
        ActionDefinition(name="add_member", description="Agrega/actualiza miembro", category="write"),
        ActionDefinition(name="update_member", description="Actualiza miembro", category="write"),
        ActionDefinition(name="get_member", description="Obtiene miembro", category="read"),
        ActionDefinition(name="list_members", description="Lista miembros", category="read"),
        ActionDefinition(name="create_campaign", description="Crea campaña", category="write"),
        ActionDefinition(name="send_campaign", description="Envía campaña", category="write"),
        ActionDefinition(name="get_campaign", description="Obtiene campaña", category="read"),
        ActionDefinition(name="create_template", description="Crea plantilla", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_key"], description="API Key de Mailchimp (formato: clave-datacenter)")
    ],
)
