"""
Conector Twilio — SMS y Voice via Twilio API
==============================================

Permite enviar mensajes SMS, realizar llamadas de voz,
gestionar numeros de telefono y verificar identidades
usando la API de Twilio.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class TwilioConnector(BaseConnector):
    """Conector para Twilio: SMS, Voice y Verify."""

    name = "twilio"
    version = "1.0.0"
    description = "Envia SMS, realiza llamadas de voz y verifica identidades via Twilio"
    category = "communication"
    icon = "phone"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._account_sid: str = ""
        self._auth_token: str = ""
        self._base_url: str = "https://api.twilio.com/2010-04-01"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Twilio usando las credenciales configuradas."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("TwilioConnector: credenciales no configuradas")
            return False

        self._account_sid = getattr(self._auth_provider, "_api_key", "")
        self._auth_token = getattr(self._auth_provider, "_api_key", "")

        # Extract account_sid and auth_token from auth provider credentials
        if hasattr(self._auth_provider, "_credentials"):
            creds = self._auth_provider._credentials
            self._account_sid = creds.get("account_sid", self._account_sid)
            self._auth_token = creds.get("auth_token", "")

        if not self._account_sid:
            logger.error("TwilioConnector: account_sid es requerido")
            return False

        # Set up HttpClient with Basic Auth (Account SID:Auth Token)
        self._http = HttpClient(
            base_url=f"{self._base_url}/Accounts/{self._account_sid}",
            connector_name=self.name,
        )
        self._http.set_auth("Basic", username=self._account_sid, password=self._auth_token)

        self._connected = True
        self._log_operation("connect", f"account_sid={self._account_sid[:8]}...")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Twilio.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion

        Returns:
            Resultado de la accion ejecutada
        """
        action_map: dict[str, Any] = {
            "send_sms": self._send_sms,
            "make_call": self._make_call,
            "lookup_number": self._lookup_number,
            "list_messages": self._list_messages,
            "verify_start": self._verify_start,
            "verify_check": self._verify_check,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Twilio esten configuradas correctamente."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Twilio."""
        self._connected = False
        self._account_sid = ""
        self._auth_token = ""
        self._http = None
        self._log_operation("disconnect")
        return True

    def _send_sms(self, params: dict[str, Any]) -> dict[str, Any]:
        """Envia un mensaje SMS via Twilio.

        Args:
            params: Debe contener 'to', 'from_' y 'body'
        """
        to = params.get("to", "")
        from_ = params.get("from_", "")
        body = params.get("body", "")
        if not to or not from_ or not body:
            return {"success": False, "error": "Parametros requeridos: to, from_, body"}

        self._log_operation("send_sms", f"to={to}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            # Twilio SMS API uses form-encoded data
            response = self._http.post(
                "/Messages.json",
                data={"To": to, "From": from_, "Body": body},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "message_id": data.get("sid", ""),
                    "status": data.get("status", "queued"),
                    "to": data.get("to", to),
                    "from": data.get("from", from_),
                    "price": data.get("price"),
                    "num_segments": data.get("num_segments"),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _make_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Realiza una llamada de voz via Twilio.

        Args:
            params: Debe contener 'to', 'from_' y 'url' (Twiml URL)
        """
        to = params.get("to", "")
        from_ = params.get("from_", "")
        url = params.get("url", "")
        if not to or not from_:
            return {"success": False, "error": "Parametros requeridos: to, from_"}

        self._log_operation("make_call", f"to={to}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            call_data: dict[str, str] = {"To": to, "From": from_}
            if url:
                call_data["Url"] = url

            response = self._http.post(
                "/Calls.json",
                data=call_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "call_id": data.get("sid", ""),
                    "status": data.get("status", "ringing"),
                    "to": data.get("to", to),
                    "from": data.get("from", from_),
                    "duration": data.get("duration"),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _lookup_number(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta informacion de un numero de telefono via Twilio Lookup API.

        Args:
            params: Debe contener 'phone_number'
        """
        phone = params.get("phone_number", "")
        if not phone:
            return {"success": False, "error": "Parametro requerido: phone_number"}

        self._log_operation("lookup_number", f"phone={phone}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            # Lookup API uses a different base URL
            lookup_client = HttpClient(
                base_url="https://lookups.twilio.com/v1",
                connector_name=self.name,
            )
            lookup_client.set_auth("Basic", username=self._account_sid, password=self._auth_token)

            response = lookup_client.get(
                f"/PhoneNumbers/{phone}",
                params={"Type": "carrier"},
            )

            if response.ok:
                data = response.json() or {}
                carrier = data.get("carrier", {})
                return {
                    "success": True,
                    "phone_number": data.get("phone_number", phone),
                    "country_code": data.get("country_code", ""),
                    "national_format": data.get("national_format", ""),
                    "type": carrier.get("type", ""),
                    "carrier": carrier.get("name", ""),
                    "mobile_country_code": carrier.get("mobile_country_code", ""),
                    "mobile_network_code": carrier.get("mobile_network_code", ""),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _list_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista mensajes SMS enviados y recibidos.

        Args:
            params: Opcionalmente 'limit', 'date_sent', 'to', 'from_'
        """
        limit = params.get("limit", 20)
        self._log_operation("list_messages", f"limit={limit}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            query_params: dict[str, Any] = {"PageSize": limit}
            if params.get("date_sent"):
                query_params["DateSent"] = params["date_sent"]
            if params.get("to"):
                query_params["To"] = params["to"]
            if params.get("from_"):
                query_params["From"] = params["from_"]

            response = self._http.get("/Messages.json", params=query_params)

            if response.ok:
                data = response.json() or {}
                messages = data.get("messages", [])
                return {
                    "success": True,
                    "messages": [
                        {
                            "sid": msg.get("sid", ""),
                            "to": msg.get("to", ""),
                            "from": msg.get("from", ""),
                            "body": msg.get("body", ""),
                            "status": msg.get("status", ""),
                            "date_sent": msg.get("date_sent", ""),
                            "direction": msg.get("direction", ""),
                            "price": msg.get("price"),
                        }
                        for msg in messages
                    ],
                    "total": len(messages),
                    "num_pages": data.get("num_pages", 0),
                    "page": data.get("page", 0),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _verify_start(self, params: dict[str, Any]) -> dict[str, Any]:
        """Inicia una verificacion de identidad via SMS o call using Twilio Verify API.

        Args:
            params: Debe contener 'to', 'channel' (sms/call), and optionally 'verify_service_sid'
        """
        to = params.get("to", "")
        channel = params.get("channel", "sms")
        service_sid = params.get("verify_service_sid", "")
        if not to:
            return {"success": False, "error": "Parametro requerido: to"}
        if not service_sid:
            return {"success": False, "error": "Parametro requerido: verify_service_sid (Twilio Verify Service SID)"}

        self._log_operation("verify_start", f"to={to}, channel={channel}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            verify_client = HttpClient(
                base_url=f"https://verify.twilio.com/v2/Services/{service_sid}",
                connector_name=self.name,
            )
            verify_client.set_auth("Basic", username=self._account_sid, password=self._auth_token)

            response = verify_client.post(
                "/Verifications",
                data={"To": to, "Channel": channel},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "verification_id": data.get("sid", ""),
                    "status": data.get("status", "pending"),
                    "to": data.get("to", to),
                    "channel": data.get("channel", channel),
                    "valid": data.get("valid", False),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}

    def _verify_check(self, params: dict[str, Any]) -> dict[str, Any]:
        """Verifica un codigo de verificacion using Twilio Verify API.

        Args:
            params: Debe contener 'verification_id', 'code', and optionally 'verify_service_sid'
        """
        verification_id = params.get("verification_id", "")
        code = params.get("code", "")
        service_sid = params.get("verify_service_sid", "")
        to = params.get("to", "")
        if not verification_id or not code:
            return {"success": False, "error": "Parametros requeridos: verification_id, code"}
        if not service_sid:
            return {"success": False, "error": "Parametro requerido: verify_service_sid"}

        self._log_operation("verify_check", f"verification_id={verification_id}")

        if not self._http:
            return {"success": False, "error": "Connector not connected. Call connect() first."}

        try:
            verify_client = HttpClient(
                base_url=f"https://verify.twilio.com/v2/Services/{service_sid}",
                connector_name=self.name,
            )
            verify_client.set_auth("Basic", username=self._account_sid, password=self._auth_token)

            check_data: dict[str, str] = {"Code": code}
            if to:
                check_data["To"] = to

            response = verify_client.post(
                "/VerificationCheck",
                data=check_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.ok:
                data = response.json() or {}
                return {
                    "success": True,
                    "status": data.get("status", ""),
                    "valid": data.get("valid", False),
                    "verification_id": data.get("sid", verification_id),
                    "to": data.get("to", to),
                }
            else:
                error_data = response.json() or {}
                return {
                    "success": False,
                    "error": error_data.get("message", f"HTTP {response.status_code}"),
                    "status_code": response.status_code,
                    "error_code": error_data.get("code"),
                }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {e}"}


# Esquema del conector
TWILIO_SCHEMA = ConnectorSchema(
    name="twilio",
    version="1.0.0",
    description="Envia SMS, realiza llamadas de voz y verifica identidades via Twilio",
    category="communication",
    icon="phone",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="send_sms", description="Envia un mensaje SMS", category="write"),
        ActionDefinition(name="make_call", description="Realiza una llamada de voz", category="write"),
        ActionDefinition(name="lookup_number", description="Consulta informacion de un numero", category="read"),
        ActionDefinition(name="list_messages", description="Lista mensajes SMS", category="read"),
        ActionDefinition(name="verify_start", description="Inicia verificacion de identidad", category="write"),
        ActionDefinition(name="verify_check", description="Verifica codigo de verificacion", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="api_key",
            required_fields=["account_sid", "auth_token"],
            description="Credenciales de Twilio (Account SID + Auth Token)",
        )
    ],
)
