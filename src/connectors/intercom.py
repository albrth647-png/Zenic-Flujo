"""
Conector Intercom — Mensajeria de Atencion al Cliente
=======================================================

Permite enviar mensajes a usuarios, gestionar conversaciones,
crear contactos y administrar tickets via la API de Intercom.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class IntercomConnector(BaseConnector):
    """Conector para Intercom: mensajeria y atencion al cliente."""

    name = "intercom"
    version = "1.0.0"
    description = "Gestiona conversaciones, contactos y tickets via Intercom"
    category = "communication"
    icon = "headphones"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.intercom.io"
        self._access_token: str = ""
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Intercom."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("IntercomConnector: Access Token no configurado")
            return False

        self._access_token = getattr(self._auth_provider, "_api_key", "")

        # Try to get from credentials dict if available
        if not self._access_token and hasattr(self._auth_provider, "_credentials"):
            self._access_token = self._auth_provider._credentials.get("access_token", "")

        if not self._access_token:
            logger.error("IntercomConnector: access_token es requerido")
            return False

        # Set up HttpClient with Bearer auth (Intercom uses Bearer token)
        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=self._access_token)
        # Intercom requires Intercom-Version header
        self._http.set_header("Intercom-Version", "2.11")
        # Override Accept header for Intercom
        self._http.set_header("Accept", "application/json")

        self._connected = True
        self._log_operation("connect", "Access Token configurado")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Intercom.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "send_message": self._send_message,
            "list_conversations": self._list_conversations,
            "get_conversation": self._get_conversation,
            "create_contact": self._create_contact,
            "list_contacts": self._list_contacts,
            "create_ticket": self._create_ticket,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el Access Token de Intercom este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Intercom."""
        self._connected = False
        self._access_token = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un mensaje a un usuario o conversacion de Intercom.

        Args:
            params: Debe contener 'conversation_id' o 'user_id', y 'body'
        """
        conversation_id = params.get("conversation_id", "")
        user_id = params.get("user_id", "")
        body = params.get("body", "")
        message_type = params.get("message_type", "comment")

        if not body or (not conversation_id and not user_id):
            return {"success": False, "error": "Requiere conversation_id o user_id, y body"}

        self._log_operation("send_message", f"conversation={conversation_id or user_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            if conversation_id:
                # Reply to existing conversation
                payload: dict[str, Any] = {
                    "message_type": message_type,
                    "body": body,
                    "type": "admin",
                }
                if params.get("admin_id"):
                    payload["admin_id"] = params["admin_id"]

                response = self._http.post(
                    f"/conversations/{conversation_id}/reply",
                    json=payload,
                )
            else:
                # Start a new conversation with a user
                payload = {
                    "from": {"type": "admin", "id": params.get("admin_id", "")},
                    "to": {"type": "user", "id": user_id},
                    "body": body,
                    "message_type": "inapp",
                }
                if params.get("subject"):
                    payload["subject"] = params["subject"]

                response = self._http.post(
                    "/messages",
                    json=payload,
                )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "message_id": data.get("id", ""),
                    "conversation_id": data.get("conversation_id", conversation_id),
                    "body": data.get("body", body),
                    "type": data.get("type", ""),
                    "created_at": data.get("created_at", ""),
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "error_code": errors[0].get("code", "") if errors else "",
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_conversations(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista conversaciones de Intercom.

        Args:
            params: Opcionalmente 'limit', 'status' y 'assignee_id'
        """
        limit = params.get("limit", 20)
        self._log_operation("list_conversations", f"limit={limit}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            query_params: dict[str, Any] = {"per_page": min(limit, 60)}
            if params.get("status"):
                query_params["status"] = params["status"]
            if params.get("assignee_id"):
                query_params["assignee_id"] = params["assignee_id"]
            if params.get("start_after"):
                query_params["starting_after"] = params["start_after"]
            if params.get("created_after"):
                query_params["created_at_after"] = params["created_after"]

            response = self._http.get("/conversations", params=query_params)

            if response.ok:
                data = response.json() or {}
                conversations = data.get("conversations", [])
                return {
                    "success": True,
                    "conversations": [
                        {
                            "id": conv.get("id", ""),
                            "created_at": conv.get("created_at", ""),
                            "updated_at": conv.get("updated_at", ""),
                            "state": conv.get("state", ""),
                            "open": conv.get("open", False),
                            "read": conv.get("read", False),
                            "priority": conv.get("priority", ""),
                            "subject": conv.get("title", ""),
                            "source": conv.get("source", {}),
                            "assignee": conv.get("assignee", {}),
                            "contacts": conv.get("contacts", {}),
                        }
                        for conv in conversations
                    ],
                    "total": len(conversations),
                    "pages": data.get("pages", {}),
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

    def _get_conversation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene los detalles de una conversacion.

        Args:
            params: Debe contener 'conversation_id'
        """
        conversation_id = params.get("conversation_id", "")
        if not conversation_id:
            return {"success": False, "error": "Parametro requerido: conversation_id"}

        self._log_operation("get_conversation", f"id={conversation_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            response = self._http.get(f"/conversations/{conversation_id}")

            if response.ok:
                data = response.json() or {}
                conversation_parts = data.get("conversation_parts", {}).get("conversation_parts", [])
                return {
                    "success": True,
                    "conversation_id": data.get("id", conversation_id),
                    "state": data.get("state", ""),
                    "open": data.get("open", False),
                    "read": data.get("read", False),
                    "subject": data.get("title", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "source": data.get("source", {}),
                    "contacts": data.get("contacts", {}),
                    "assignee": data.get("assignee", {}),
                    "tags": data.get("tags", {}),
                    "messages": [
                        {
                            "id": part.get("id", ""),
                            "part_type": part.get("part_type", ""),
                            "body": part.get("body", ""),
                            "created_at": part.get("created_at", ""),
                            "author": part.get("author", {}),
                        }
                        for part in conversation_parts
                    ],
                    "total_parts": len(conversation_parts),
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

    def _create_contact(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un contacto en Intercom.

        Args:
            params: Debe contener 'email' y opcionalmente 'name', 'phone'
        """
        email = params.get("email", "")
        if not email:
            return {"success": False, "error": "Parametro requerido: email"}

        self._log_operation("create_contact", f"email={email}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload: dict[str, Any] = {"email": email}
            if params.get("name"):
                payload["name"] = params["name"]
            if params.get("phone"):
                payload["phone"] = params["phone"]
            if params.get("custom_attributes"):
                payload["custom_attributes"] = params["custom_attributes"]
            if params.get("role"):
                payload["role"] = params["role"]

            response = self._http.post("/contacts", json=payload)

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "contact_id": data.get("id", ""),
                    "email": data.get("email", email),
                    "name": data.get("name", ""),
                    "phone": data.get("phone", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "external_id": data.get("external_id", ""),
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "error_code": errors[0].get("code", "") if errors else "",
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_contacts(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista contactos de Intercom.

        Args:
            params: Opcionalmente 'limit' y 'created_after'
        """
        limit = params.get("limit", 20)
        self._log_operation("list_contacts", f"limit={limit}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            query_params: dict[str, Any] = {"per_page": min(limit, 60)}
            if params.get("created_after"):
                query_params["created_at_after"] = params["created_after"]
            if params.get("email"):
                query_params["email"] = params["email"]
            if params.get("start_after"):
                query_params["starting_after"] = params["start_after"]

            response = self._http.get("/contacts", params=query_params)

            if response.ok:
                data = response.json() or {}
                contacts = data.get("contacts", data.get("data", []))
                return {
                    "success": True,
                    "contacts": [
                        {
                            "id": c.get("id", ""),
                            "email": c.get("email", ""),
                            "name": c.get("name", ""),
                            "phone": c.get("phone", ""),
                            "created_at": c.get("created_at", ""),
                            "updated_at": c.get("updated_at", ""),
                            "last_seen_at": c.get("last_seen_at", ""),
                            "signed_up_at": c.get("signed_up_at", ""),
                        }
                        for c in contacts
                    ],
                    "total": len(contacts),
                    "pages": data.get("pages", {}),
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

    def _create_ticket(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un ticket en Intercom.

        Args:
            params: Debe contener 'contact_id', 'subject' y 'body'
        """
        contact_id = params.get("contact_id", "")
        subject = params.get("subject", "")
        body = params.get("body", "")
        if not contact_id or not subject:
            return {"success": False, "error": "Parametros requeridos: contact_id, subject"}

        self._log_operation("create_ticket", f"contact={contact_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            payload: dict[str, Any] = {
                "contacts": {"id": contact_id},
                "ticket_attributes": {
                    "_default_title_": subject,
                },
            }
            if body:
                payload["ticket_attributes"]["_default_description_"] = body
            if params.get("ticket_type_id"):
                payload["ticket_type_id"] = params["ticket_type_id"]
            if params.get("custom_attributes"):
                payload["ticket_attributes"].update(params["custom_attributes"])
            if params.get("assignee_id"):
                payload["assignee_id"] = params["assignee_id"]

            response = self._http.post("/tickets", json=payload)

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "ticket_id": data.get("id", ""),
                    "subject": subject,
                    "state": data.get("state", "submitted"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "contacts": data.get("contacts", {}),
                    "assignee": data.get("assignee", {}),
                }
            else:
                error_data = response.json() or {}
                errors = error_data.get("errors", [])
                error_msg = errors[0].get("message", f"HTTP {response.status_code}") if errors else f"HTTP {response.status_code}"
                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "error_code": errors[0].get("code", "") if errors else "",
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}


INTERCOM_SCHEMA = ConnectorSchema(
    name="intercom",
    version="1.0.0",
    description="Gestiona conversaciones, contactos y tickets via Intercom",
    category="communication",
    icon="headphones",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="send_message", description="Envia un mensaje", category="write"),
        ActionDefinition(name="list_conversations", description="Lista conversaciones", category="read"),
        ActionDefinition(name="get_conversation", description="Obtiene detalles de conversacion", category="read"),
        ActionDefinition(name="create_contact", description="Crea un contacto", category="write"),
        ActionDefinition(name="list_contacts", description="Lista contactos", category="read"),
        ActionDefinition(name="create_ticket", description="Crea un ticket", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["access_token"], description="Intercom Access Token")
    ],
)
