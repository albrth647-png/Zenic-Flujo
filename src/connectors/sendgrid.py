"""
Conector SendGrid — Email via SendGrid API
============================================

Permite enviar correos electronicos, gestionar listas de
contactos, crear plantillas y trackear eventos de email
usando la API de SendGrid.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class SendGridConnector(BaseConnector):
    """Conector para SendGrid: envio de emails y gestion de contactos."""

    name = "sendgrid"
    version = "1.0.0"
    description = "Envia emails, gestiona contactos y plantillas via SendGrid"
    category = "communication"
    icon = "mail"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._api_key: str = ""
        self._base_url: str = "https://api.sendgrid.com/v3"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de SendGrid."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("SendGridConnector: API key no configurada")
            return False

        self._api_key = getattr(self._auth_provider, "_api_key", "")

        if not self._api_key:
            logger.error("SendGridConnector: API key es requerida")
            return False

        # Set up HttpClient with Bearer auth (SendGrid uses Bearer token)
        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=self._api_key)

        self._connected = True
        self._log_operation("connect", "API key configurada")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector SendGrid.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "send_email": self._send_email,
            "send_template_email": self._send_template_email,
            "add_contact": self._add_contact,
            "list_contacts": self._list_contacts,
            "create_template": self._create_template,
            "get_email_stats": self._get_email_stats,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que la API key de SendGrid este configurada."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con SendGrid."""
        self._connected = False
        self._api_key = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    def _send_email(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un email via SendGrid.

        Args:
            params: Debe contener 'to', 'from', 'subject' y 'content'
        """
        to = params.get("to", "")
        from_email = params.get("from", "")
        subject = params.get("subject", "")
        content = params.get("content", "")
        content_type = params.get("content_type", "text/plain")

        if not to or not from_email or not subject:
            return {"success": False, "error": "Parametros requeridos: to, from, subject"}

        self._log_operation("send_email", f"to={to}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload: dict[str, Any] = {
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": from_email},
                "subject": subject,
            }

            if content:
                payload["content"] = [{"type": content_type, "value": content}]

            # Add optional fields
            if params.get("cc"):
                payload["personalizations"][0]["cc"] = [{"email": e} for e in params["cc"]]
            if params.get("bcc"):
                payload["personalizations"][0]["bcc"] = [{"email": e} for e in params["bcc"]]
            if params.get("reply_to"):
                payload["reply_to"] = {"email": params["reply_to"]}

            response = self._http.post("/mail/send", json=payload)

            # SendGrid returns 202 Accepted on success with no body
            if response.ok or response.status_code == 202:
                # Extract message ID from headers if available
                message_id = response.headers.get("X-Message-Id", "")
                return {
                    "success": True,
                    "message_id": message_id,
                    "status": "accepted",
                    "to": to,
                    "from": from_email,
                    "subject": subject,
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _send_template_email(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un email usando una plantilla de SendGrid.

        Args:
            params: Debe contener 'to', 'from', 'template_id' y 'dynamic_data'
        """
        to = params.get("to", "")
        from_email = params.get("from", "")
        template_id = params.get("template_id", "")
        dynamic_data = params.get("dynamic_data", {})

        if not to or not from_email or not template_id:
            return {"success": False, "error": "Parametros requeridos: to, from, template_id"}

        self._log_operation("send_template_email", f"template={template_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload: dict[str, Any] = {
                "personalizations": [
                    {
                        "to": [{"email": to}],
                        "dynamic_template_data": dynamic_data,
                    }
                ],
                "from": {"email": from_email},
                "template_id": template_id,
            }

            response = self._http.post("/mail/send", json=payload)

            if response.ok or response.status_code == 202:
                message_id = response.headers.get("X-Message-Id", "")
                return {
                    "success": True,
                    "message_id": message_id,
                    "status": "accepted",
                    "to": to,
                    "template_id": template_id,
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _add_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        """Anade un contacto a una lista de SendGrid.

        Args:
            params: Debe contener 'email' y opcionalmente 'first_name', 'last_name', 'list_ids'
        """
        email = params.get("email", "")
        if not email:
            return {"success": False, "error": "Parametro requerido: email"}

        self._log_operation("add_contact", f"email={email}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            contacts = [{"email": email}]
            if params.get("first_name"):
                contacts[0]["first_name"] = params["first_name"]
            if params.get("last_name"):
                contacts[0]["last_name"] = params["last_name"]
            if params.get("custom_fields"):
                contacts[0]["custom_fields"] = params["custom_fields"]

            payload: dict[str, Any] = {"contacts": contacts}
            if params.get("list_ids"):
                payload["list_ids"] = params["list_ids"]

            response = self._http.put("/marketing/contacts", json=payload)

            if response.ok or response.status_code == 202:
                data = response.json() or {}
                return {
                    "success": True,
                    "job_id": data.get("job_id", ""),
                    "email": email,
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_contacts(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista contactos de SendGrid.

        Args:
            params: Opcionalmente 'limit' y 'page'
        """
        limit = params.get("limit", 20)
        self._log_operation("list_contacts", f"limit={limit}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            query_params: dict[str, Any] = {"page_size": limit, "page_token": params.get("page_token", "")}

            response = self._http.get("/marketing/contacts", params=query_params)

            if response.ok:
                data = response.json() or {}
                contacts = data.get("result", [])
                return {
                    "success": True,
                    "contacts": [
                        {
                            "id": c.get("id", ""),
                            "email": c.get("email", ""),
                            "first_name": c.get("first_name", ""),
                            "last_name": c.get("last_name", ""),
                            "created_at": c.get("created_at", ""),
                            "updated_at": c.get("updated_at", ""),
                        }
                        for c in contacts
                    ],
                    "total": len(contacts),
                    "contact_count": data.get("contact_count", 0),
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _create_template(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una plantilla de email en SendGrid.

        Args:
            params: Debe contener 'name' y 'html_content'
        """
        name = params.get("name", "")
        if not name:
            return {"success": False, "error": "Parametro requerido: name"}

        self._log_operation("create_template", f"name={name}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            # Step 1: Create the template
            payload: dict[str, Any] = {"name": name, "generation": "dynamic"}

            response = self._http.post("/templates", json=payload)

            if response.ok:
                data = response.json() or {}
                template_id = data.get("id", "")

                # Step 2: Add a version to the template if html_content provided
                if params.get("html_content") and template_id:
                    version_payload: dict[str, Any] = {
                        "name": f"{name} - Version 1",
                        "html_content": params["html_content"],
                        "plain_content": params.get("plain_content", ""),
                        "subject": params.get("subject", name),
                        "active": 1,
                    }
                    version_response = self._http.post(
                        f"/templates/{template_id}/versions",
                        json=version_payload,
                    )
                    if not version_response.ok:
                        logger.warning(
                            f"SendGridConnector: template created but version failed: {version_response.status_code}"
                        )

                return {
                    "success": True,
                    "template_id": template_id,
                    "name": name,
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _get_email_stats(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene estadisticas de envio de emails.

        Args:
            params: Opcionalmente 'start_date' y 'end_date'
        """
        self._log_operation("get_email_stats")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            query_params: dict[str, Any] = {}
            if params.get("start_date"):
                query_params["start_date"] = params["start_date"]
            if params.get("end_date"):
                query_params["end_date"] = params["end_date"]
            if params.get("aggregated_by"):
                query_params["aggregated_by"] = params["aggregated_by"]

            response = self._http.get("/stats", params=query_params)

            if response.ok:
                data = response.json() or []
                stats_list = []
                for entry in data:
                    stats_item = {
                        "date": entry.get("date", ""),
                    }
                    for stat in entry.get("stats", []):
                        metrics = stat.get("metrics", {})
                        stats_item.update({
                            "delivered": metrics.get("delivered", 0),
                            "opens": metrics.get("opens", 0),
                            "clicks": metrics.get("clicks", 0),
                            "bounces": metrics.get("bounces", 0),
                            "spam_reports": metrics.get("spam_reports", 0),
                            "blocks": metrics.get("blocks", 0),
                            "requests": metrics.get("requests", 0),
                        })
                    stats_list.append(stats_item)

                return {
                    "success": True,
                    "stats": stats_list,
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}


SENDGRID_SCHEMA = ConnectorSchema(
    name="sendgrid",
    version="1.0.0",
    description="Envia emails, gestiona contactos y plantillas via SendGrid",
    category="communication",
    icon="mail",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="send_email", description="Envia un email", category="write"),
        ActionDefinition(name="send_template_email", description="Envia un email con plantilla", category="write"),
        ActionDefinition(name="add_contact", description="Anade un contacto", category="write"),
        ActionDefinition(name="list_contacts", description="Lista contactos", category="read"),
        ActionDefinition(name="create_template", description="Crea una plantilla de email", category="write"),
        ActionDefinition(name="get_email_stats", description="Obtiene estadisticas de email", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_key"], description="API Key de SendGrid")
    ],
)
