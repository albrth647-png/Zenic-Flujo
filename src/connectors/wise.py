"""
Conector Wise — Transferencias Internacionales via Wise API
==============================================================

Permite crear cotizaciones, transferencias y gestionar
cuentas y balances via la API de Wise (TransferWise).
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class WiseConnector(BaseConnector):
    """Conector para Wise: transferencias internacionales y cotizaciones."""

    name = "wise"
    version = "1.0.0"
    description = "Crea transferencias internacionales y cotizaciones via Wise"
    category = "finance_payments"
    icon = "globe"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.transferwise.com"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Wise."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("WiseConnector: API Token no configurado")
            return False
        try:
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            # Wise uses Bearer token (api_token)
            creds = self._auth_provider.get_credentials()
            api_token = creds.get("api_token", "")
            if api_token:
                self._http.set_auth("Bearer", token=api_token)

            # Validate by fetching user profiles
            resp = self._http.get("/v1/profiles")
            if resp.ok:
                self._connected = True
                self._log_operation("connect", "API Token configurado y validado")
                return True
            else:
                # Still connect even if profiles call fails
                self._connected = True
                self._log_operation("connect", f"API Token configurado (validacion fallo: HTTP {resp.status_code})")
                return True
        except HTTPClientError as e:
            logger.warning(f"WiseConnector: error durante conexion - {e}")
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            creds = self._auth_provider.get_credentials()
            api_token = creds.get("api_token", "")
            if api_token:
                self._http.set_auth("Bearer", token=api_token)
            self._connected = True
            self._log_operation("connect", f"API Token configurado (validacion fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Wise.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_quote": self._create_quote,
            "create_transfer": self._create_transfer,
            "list_transfers": self._list_transfers,
            "get_balance": self._get_balance,
            "list_recipients": self._list_recipients,
            "get_exchange_rate": self._get_exchange_rate,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el API Token de Wise este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Wise."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_quote(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una cotizacion de tipo de cambio en Wise.

        Args:
            params: Debe contener 'source_currency', 'target_currency' y 'amount'
                    Opcionalmente 'profile_id', 'rate_type'
        """
        source = params.get("source_currency", "")
        target = params.get("target_currency", "")
        amount = params.get("amount", 0)
        if not source or not target or not amount:
            return {"success": False, "error": "Parametros requeridos: source_currency, target_currency, amount"}
        self._log_operation("create_quote", f"{source}->{target} amount={amount}")

        payload: dict[str, Any] = {
            "sourceCurrency": source,
            "targetCurrency": target,
            "amount": str(amount),
            "type": params.get("rate_type", "REGULAR"),
        }
        if params.get("profile_id"):
            payload["profile"] = params["profile_id"]

        try:
            resp = self._http.post("/v3/profiles/{profile_id}/quotes".format(
                profile_id=params.get("profile_id", 0)
            ), json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "quote_id": data.get("id", ""),
                    "source": data.get("sourceCurrency", source),
                    "target": data.get("targetCurrency", target),
                    "rate": data.get("rate", 0.0),
                    "fee": data.get("fee", 0.0),
                    "data": data,
                }
            else:
                # Fallback to v1 quotes endpoint
                resp_v1 = self._http.post("/v1/quotes", json=payload)
                if resp_v1.ok:
                    data = resp_v1.json() or {}
                    return {
                        "success": True,
                        "quote_id": data.get("id", ""),
                        "source": data.get("sourceCurrency", source),
                        "target": data.get("targetCurrency", target),
                        "rate": data.get("rate", 0.0),
                        "fee": data.get("fee", 0.0),
                        "data": data,
                    }
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('errors', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_transfer(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea una transferencia en Wise.

        Args:
            params: Debe contener 'quote_id', 'recipient_id' y 'reference'
        """
        quote_id = params.get("quote_id", "")
        recipient_id = params.get("recipient_id", "")
        if not quote_id or not recipient_id:
            return {"success": False, "error": "Parametros requeridos: quote_id, recipient_id"}
        self._log_operation("create_transfer", f"quote={quote_id}")

        payload: dict[str, Any] = {
            "quoteId": str(quote_id),
            "recipientId": str(recipient_id),
            "reference": params.get("reference", ""),
            "details": {
                "reference": params.get("reference", ""),
            },
        }
        if params.get("source_account_id"):
            payload["sourceAccount"] = params["source_account_id"]

        try:
            resp = self._http.post("/v1/transfers", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "transfer_id": data.get("id", ""),
                    "status": data.get("status", "incoming_payment_waiting"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                errors = error_body.get("errors", [])
                error_msg = errors[0].get("message", str(resp.body)) if errors else str(resp.body)
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_msg}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_transfers(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista transferencias de Wise.

        Args:
            params: Opcionalmente 'limit', 'offset', 'status', 'profile_id'
        """
        limit = params.get("limit", 20)
        self._log_operation("list_transfers", f"limit={limit}")

        query_params: dict[str, Any] = {
            "limit": limit,
        }
        if params.get("offset"):
            query_params["offset"] = params["offset"]
        if params.get("status"):
            query_params["status"] = params["status"]
        if params.get("profile_id"):
            query_params["profileId"] = params["profile_id"]

        try:
            resp = self._http.get("/v1/transfers", params=query_params)
            if resp.ok:
                data = resp.json() or {}
                transfers = data if isinstance(data, list) else data.get("transfers", [])
                return {
                    "success": True,
                    "transfers": transfers,
                    "total": len(transfers) if isinstance(transfers, list) else 0,
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_balance(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene los balances de la cuenta de Wise.

        Args:
            params: Opcionalmente 'profile_id'
        """
        self._log_operation("get_balance")

        profile_id = params.get("profile_id", "")
        if not profile_id:
            # Try to get profiles first to find the default profile
            try:
                profiles_resp = self._http.get("/v1/profiles")
                if profiles_resp.ok:
                    profiles_data = profiles_resp.json() or {}
                    if isinstance(profiles_data, list) and profiles_data:
                        profile_id = str(profiles_data[0].get("id", ""))
                    elif isinstance(profiles_data, dict) and profiles_data.get("id"):
                        profile_id = str(profiles_data["id"])
            except HTTPClientError:
                pass

        if not profile_id:
            return {"success": False, "error": "Parametro requerido: profile_id (no se pudo obtener automaticamente)"}

        try:
            resp = self._http.get(f"/v4/profiles/{profile_id}/balances")
            if resp.ok:
                data = resp.json() or {}
                balances = data if isinstance(data, list) else data.get("balances", [])
                return {
                    "success": True,
                    "balances": balances,
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _list_recipients(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los destinatarios configurados en Wise.

        Args:
            params: Opcionalmente 'profile_id', 'limit', 'offset'
        """
        self._log_operation("list_recipients")

        query_params: dict[str, Any] = {}
        if params.get("profile_id"):
            query_params["profileId"] = params["profile_id"]
        if params.get("limit"):
            query_params["limit"] = params["limit"]
        if params.get("offset"):
            query_params["offset"] = params["offset"]
        if params.get("currency"):
            query_params["currency"] = params["currency"]

        try:
            resp = self._http.get("/v1/accounts", params=query_params if query_params else None)
            if resp.ok:
                data = resp.json() or {}
                recipients = data if isinstance(data, list) else data.get("accounts", [])
                return {
                    "success": True,
                    "recipients": recipients,
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_exchange_rate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene el tipo de cambio actual entre dos monedas.

        Args:
            params: Debe contener 'source' y 'target' (codigos de moneda)
        """
        source = params.get("source", "")
        target = params.get("target", "")
        if not source or not target:
            return {"success": False, "error": "Parametros requeridos: source, target"}
        self._log_operation("get_exchange_rate", f"{source}->{target}")

        try:
            resp = self._http.get("/v1/rates", params={"source": source, "target": target})
            if resp.ok:
                data = resp.json() or {}
                rate = data.get("rate", 0.0) if isinstance(data, dict) else 0.0
                return {
                    "success": True,
                    "source": source,
                    "target": target,
                    "rate": rate,
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', resp.body)}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


WISE_SCHEMA = ConnectorSchema(
    name="wise",
    version="1.0.0",
    description="Crea transferencias internacionales y cotizaciones via Wise",
    category="finance_payments",
    icon="globe",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_quote", description="Crea una cotizacion", category="write"),
        ActionDefinition(name="create_transfer", description="Crea una transferencia", category="write"),
        ActionDefinition(name="list_transfers", description="Lista transferencias", category="read"),
        ActionDefinition(name="get_balance", description="Obtiene balances", category="read"),
        ActionDefinition(name="list_recipients", description="Lista destinatarios", category="read"),
        ActionDefinition(name="get_exchange_rate", description="Obtiene tipo de cambio", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_token"], description="Wise API Token")
    ],
)
