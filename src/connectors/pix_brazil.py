"""
Conector Pix Brazil — Pagos Instantaneos via Pix
====================================================

Permite crear, consultar y gestionar cobranzas y pagos
instantaneos via el sistema Pix de Brasil.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class PixBrazilConnector(BaseConnector):
    """Conector para Pix Brazil: cobranzas y pagos instantaneos."""

    name = "pix_brazil"
    version = "1.0.0"
    description = "Crea y gestiona cobranzas y pagos instantaneos via Pix de Brasil"
    category = "latam"
    icon = "zap"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.pix.gov.br/v2"
        self._http: HttpClient | None = None

    def connect(self) -> bool:
        """Establece conexion con la API de Pix (BCB)."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("PixBrazilConnector: credenciales no configuradas")
            return False
        try:
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            # Pix uses mTLS with client_id/client_secret for OAuth2
            creds = self._auth_provider.get_credentials()
            client_id = creds.get("client_id", "")
            client_secret = creds.get("client_secret", "")

            # Obtain OAuth2 access token
            if client_id and client_secret:
                token_resp = self._http.post(
                    "/oauth/token",
                    json={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                if token_resp.ok:
                    token_data = token_resp.json() or {}
                    access_token = token_data.get("access_token", "")
                    if access_token:
                        self._http.set_auth("Bearer", token=access_token)
                else:
                    logger.warning(f"PixBrazilConnector: fallo al obtener token OAuth2 - {token_resp.status_code}")
                    # Fall back to API key auth
                    if client_id:
                        self._http.set_auth("ApiKey", token=client_id)

            self._connected = True
            self._log_operation("connect", "Credenciales Pix configuradas")
            return True
        except HTTPClientError as e:
            logger.warning(f"PixBrazilConnector: error durante conexion - {e}")
            # Still set up HTTP client for later use
            self._http = HttpClient(
                base_url=self._base_url,
                connector_name=self.name,
            )
            self._connected = True
            self._log_operation("connect", f"Credenciales Pix configuradas (token request fallo: {e})")
            return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Pix Brazil.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_cob": self._create_cob,
            "get_cob": self._get_cob,
            "create_cobv": self._create_cobv,
            "create_devolution": self._create_devolution,
            "get_devolution": self._get_devolution,
            "get_pix": self._get_pix,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que las credenciales de Pix esten configuradas."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con la API de Pix."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_cob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cria uma cobranca imediata via Pix.

        Args:
            params: Debe contener 'txid' y 'valor' (dict com original, chave,
                    e solicitacaoPagador)
        """
        txid = params.get("txid", "")
        valor = params.get("valor", {})
        if not txid or not valor:
            return {"success": False, "error": "Parametros requeridos: txid, valor"}
        self._log_operation("create_cob", f"txid={txid}")

        payload: dict[str, Any] = {
            "calendario": params.get("calendario", {"expiracao": 3600}),
            "valor": valor,
            "chave": params.get("chave", ""),
        }
        if params.get("solicitacaoPagador"):
            payload["solicitacaoPagador"] = params["solicitacaoPagador"]
        if params.get("devedor"):
            payload["devedor"] = params["devedor"]
        if params.get("infoAdicionais"):
            payload["infoAdicionais"] = params["infoAdicionais"]

        try:
            resp = self._http.put(f"/cob/{txid}", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "txid": data.get("txid", txid),
                    "status": data.get("status", "ATIVA"),
                    "pix": data.get("pix", []),
                    "valor": data.get("valor", valor),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('descricao', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_cob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta uma cobranca imediata por txid.

        Args:
            params: Debe contener 'txid'
        """
        txid = params.get("txid", "")
        if not txid:
            return {"success": False, "error": "Parametro requerido: txid"}
        self._log_operation("get_cob", f"txid={txid}")

        query_params: dict[str, Any] = {}
        if params.get("revisao"):
            query_params["revisao"] = params["revisao"]

        try:
            resp = self._http.get(f"/cob/{txid}", params=query_params if query_params else None)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "txid": data.get("txid", txid),
                    "status": data.get("status", "ATIVA"),
                    "pix": data.get("pix", []),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('descricao', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_cobv(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cria uma cobranca com vencimento via Pix.

        Args:
            params: Debe contener 'txid', 'calendario', 'valor', 'chave',
                    'solicitacaoPagador', 'devedor'
        """
        txid = params.get("txid", "")
        valor = params.get("valor", {})
        if not txid or not valor:
            return {"success": False, "error": "Parametros requeridos: txid, valor"}
        self._log_operation("create_cobv", f"txid={txid}")

        payload: dict[str, Any] = {
            "calendario": params.get("calendario", {}),
            "valor": valor,
            "chave": params.get("chave", ""),
        }
        if params.get("solicitacaoPagador"):
            payload["solicitacaoPagador"] = params["solicitacaoPagador"]
        if params.get("devedor"):
            payload["devedor"] = params["devedor"]
        if params.get("recebedor"):
            payload["recebedor"] = params["recebedor"]
        if params.get("infoAdicionais"):
            payload["infoAdicionais"] = params["infoAdicionais"]

        try:
            resp = self._http.put(f"/cobv/{txid}", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "txid": data.get("txid", txid),
                    "status": data.get("status", "ATIVA"),
                    "valor": data.get("valor", valor),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('descricao', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _create_devolution(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cria uma devolucao (reembolso) de um pagamento Pix.

        Args:
            params: Debe contener 'e2eid', 'id' (id da devolucao) y 'valor'
        """
        e2eid = params.get("e2eid", "")
        dev_id = params.get("id", "")
        valor = params.get("valor", "")
        if not e2eid or not dev_id or not valor:
            return {"success": False, "error": "Parametros requeridos: e2eid, id, valor"}
        self._log_operation("create_devolution", f"e2eid={e2eid}")

        payload: dict[str, Any] = {"valor": valor}
        if params.get("descricao"):
            payload["descricao"] = params["descricao"]

        try:
            resp = self._http.put(f"/pix/{e2eid}/devolucao/{dev_id}", json=payload)
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "e2eid": e2eid,
                    "id": dev_id,
                    "status": data.get("status", "EM_PROCESSAMENTO"),
                    "valor": data.get("valor", valor),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('descricao', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_devolution(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta uma devolucao de pagamento Pix.

        Args:
            params: Debe contener 'e2eid' e 'id'
        """
        e2eid = params.get("e2eid", "")
        dev_id = params.get("id", "")
        if not e2eid or not dev_id:
            return {"success": False, "error": "Parametros requeridos: e2eid, id"}
        self._log_operation("get_devolution", f"e2eid={e2eid}")

        try:
            resp = self._http.get(f"/pix/{e2eid}/devolucao/{dev_id}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "e2eid": e2eid,
                    "id": dev_id,
                    "status": data.get("status", "DEVOLVIDA"),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('descricao', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _get_pix(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta um pagamento Pix recebido.

        Args:
            params: Debe contener 'e2eid'
        """
        e2eid = params.get("e2eid", "")
        if not e2eid:
            return {"success": False, "error": "Parametro requerido: e2eid"}
        self._log_operation("get_pix", f"e2eid={e2eid}")

        try:
            resp = self._http.get(f"/pix/{e2eid}")
            if resp.ok:
                data = resp.json() or {}
                return {
                    "success": True,
                    "e2eid": e2eid,
                    "status": data.get("status", "CONCLUIDA"),
                    "valor": data.get("valor", {}),
                    "data": data,
                }
            else:
                error_body = resp.json() if resp.is_client_error or resp.is_server_error else {}
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_body.get('message', error_body.get('descricao', resp.body))}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}


PIX_BRAZIL_SCHEMA = ConnectorSchema(
    name="pix_brazil",
    version="1.0.0",
    description="Crea y gestiona cobranzas y pagos instantaneos via Pix de Brasil",
    category="latam",
    icon="zap",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_cob", description="Cria cobranca imediata", category="write"),
        ActionDefinition(name="get_cob", description="Consulta cobranca", category="read"),
        ActionDefinition(name="create_cobv", description="Cria cobranca com vencimento", category="write"),
        ActionDefinition(name="create_devolution", description="Cria devolucao", category="write"),
        ActionDefinition(name="get_devolution", description="Consulta devolucao", category="read"),
        ActionDefinition(name="get_pix", description="Consulta pagamento Pix", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["client_id", "client_secret", "certificate"], description="Credenciais Pix BCB + Certificado mTLS")
    ],
)
