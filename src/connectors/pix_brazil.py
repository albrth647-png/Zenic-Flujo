"""
Conector Pix Brazil — Pagos Instantaneos via Pix (BCB) con mTLS REAL.
=====================================================================

Pix exige mTLS con certificado cliente ICP-Brasil A1 (PFX).
Fix Fase 2B: validar currency BRL en create_cob / create_cobv.
Reemplaza HttpClient plano por MTLSHttpClient + cert_loader.

Funcionalidades:
- create_cob / get_cob (cobrança imediata)
- create_cobv (cobrança com vencimento)
- create_devolution / get_devolution (reembolsos)
- get_pix (consulta pagamento)

Conformidade:
- Bacen Resolução 1/2020, Manual de Padrões para Iniciação do Pix (v6.8)
- Bacen DOC 3020/2020 — mTLS obrigatório desde 14-out-2020
- DIC 01/2020 (Diretrizes), DAD 01/2020 (Padrões de Dados)
"""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.crypto.cert_loader import CertBundle, load_pem, load_pfx
from src.sdk.crypto.mtls_client import MTLSHttpClient
from src.sdk.exceptions import ConnectorError
from src.sdk.http_client import HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# Pix só suporta BRL (Real brasileiro). Resolução Bacen 1/2020 art. 9.
PIX_CURRENCY = "BRL"


class PixBrazilConnector(BaseConnector):
    """Conector para Pix Brazil: cobranças e pagamentos instantâneos via BCB com mTLS REAL."""

    name = "pix_brazil"
    version = "2.0.0"
    description = "Cria e gestiona cobranças e pagamentos instantâneos via Pix do Brasil (mTLS ICP-Brasil)"
    category = "latam"
    icon = "zap"
    author = "Zenic-Flujo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.pix.gov.br/v2"
        self._mtls: MTLSHttpClient | None = None
        self._cert_bundle: CertBundle | None = None
        # Arquivos PEM temporários criados em connect() para passar ao MTLSHttpClient
        self._tmp_cert_file: Path | None = None
        self._tmp_key_file: Path | None = None
        self._access_token: str = ""
        self._client_id: str = ""

    # ── Helpers de credenciais ──────────────────────────────────────

    def _get_creds(self) -> dict[str, Any]:
        """Obtém credenciais do auth_provider ou kwargs (compatível mypy)."""
        if self._auth_provider is None:
            return {}
        getter = getattr(self._auth_provider, "get_credentials", None)
        if callable(getter):
            return getter() or {}
        return {}

    def connect(self) -> bool:
        """Configura mTLS com certificado ICP-Brasil A1 e obtém OAuth2 token do BCB."""
        creds = self._get_creds()
        if not creds:
            logger.error("PixBrazilConnector: credenciais não configuradas")
            return False

        client_id = creds.get("client_id", "")
        client_secret = creds.get("client_secret", "")
        cert_path = creds.get("cert_path") or creds.get("pfx_path") or ""
        key_path = creds.get("key_path", "")
        cert_password = creds.get("cert_password") or creds.get("pfx_password") or ""

        if not cert_path or not client_id:
            logger.error("PixBrazilConnector: cert_path/client_id obrigatórios")
            return False

        try:
            # Carregar certificado via cert_loader (PFX ou PEM)
            if str(cert_path).lower().endswith((".pfx", ".p12")):
                if not cert_password:
                    logger.error("PixBrazilConnector: pfx_password obrigatório para .pfx/.p12")
                    return False
                self._cert_bundle = load_pfx(cert_path, cert_password)
            else:
                if not key_path:
                    logger.error("PixBrazilConnector: key_path obrigatório para PEM")
                    return False
                self._cert_bundle = load_pem(key_path, cert_path)

            if self._cert_bundle.is_expired:
                logger.error("PixBrazilConnector: certificado ICP-Brasil expirado")
                return False

            # Escrever PEM em arquivos temporários (requests precisa de paths)
            self._tmp_cert_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pem").name)  # noqa: SIM115
            self._tmp_key_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".key").name)  # noqa: SIM115
            self._tmp_cert_file.write_bytes(self._cert_bundle.cert_pem)
            self._tmp_key_file.write_bytes(self._cert_bundle.private_key_pem)

            # Inicializar MTLSHttpClient com cert cliente
            self._mtls = MTLSHttpClient(
                cert_path=str(self._tmp_cert_file),
                key_path=str(self._tmp_key_file),
                timeout=30,
                verify=True,
            )
            self._client_id = client_id

            # Obter OAuth2 token (client_credentials) via mTLS
            token = self._fetch_oauth_token(client_id, client_secret)
            if token:
                self._access_token = token
                self._connected = True
                self._log_operation("connect", f"OAuth2 token obtido client_id={client_id}")
            else:
                # Sem token OAuth2, ainda configurado para chamadas diretas com mTLS
                self._connected = True
                self._log_operation("connect", "mTLS configurado (OAuth2 fallback)")
            return True

        except (FileNotFoundError, ValueError, ConnectorError) as e:
            logger.error(f"PixBrazilConnector: erro de conexão - {e}")
            return False

    def _fetch_oauth_token(self, client_id: str, client_secret: str) -> str:
        """Obtém access_token OAuth2 client_credentials via mTLS."""
        if self._mtls is None:
            return ""
        try:
            resp = self._mtls.post(
                f"{self._base_url}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.ok:
                data = resp.json() or {}
                return data.get("access_token", "")
            logger.warning(f"PixBrazilConnector: OAuth2 falhou HTTP {resp.status_code}")
            return ""
        except Exception as e:
            logger.warning(f"PixBrazilConnector: OAuth2 exception - {e}")
            return ""

    def _auth_headers(self) -> dict[str, str]:
        """Headers com Bearer token OAuth2."""
        if self._access_token:
            return {"Authorization": f"Bearer {self._access_token}"}
        return {}

    def execute(self, action: str, params: dict[str, Any]) -> Any:
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
            return {"error": f"Ação '{action}' não suportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        creds = self._get_creds()
        return bool(creds.get("client_id") and (creds.get("cert_path") or creds.get("pfx_path")))

    def disconnect(self) -> bool:
        if self._mtls is not None:
            with contextlib.suppress(Exception):
                self._mtls.close()
            self._mtls = None
        # Limpar arquivos PEM temporários
        for f in (self._tmp_cert_file, self._tmp_key_file):
            if f is not None and f.exists():
                with contextlib.suppress(OSError):
                    f.unlink()
        self._tmp_cert_file = None
        self._tmp_key_file = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    # ── Ações ──────────────────────────────────────────────────────

    def _validate_currency(self, params: dict[str, Any]) -> str | None:
        """Valida que a moeda é BRL. Retorna mensagem de erro ou None."""
        currency = params.get("currency", PIX_CURRENCY)
        if currency and currency.upper() != PIX_CURRENCY:
            return (
                f"Moeda '{currency}' não suportada pelo Pix. "
                f"O Pix só aceita BRL (Real brasileiro) conforme Resolução Bacen 1/2020."
            )
        return None

    def _create_cob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cria uma cobrança imediata via Pix (somente BRL)."""
        err = self._validate_currency(params)
        if err:
            return {"success": False, "error": err, "reject_code": "ZF-PIX-CUR-001"}

        txid = params.get("txid", "")
        valor = params.get("valor", {})
        if not txid or not valor:
            return {"success": False, "error": "Parâmetros obrigatórios: txid, valor"}
        self._log_operation("create_cob", f"txid={txid} currency=BRL")

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

        return self._send_request("PUT", f"/cob/{txid}", payload)

    def _get_cob(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta uma cobrança imediata por txid."""
        txid = params.get("txid", "")
        if not txid:
            return {"success": False, "error": "Parâmetro obrigatório: txid"}
        self._log_operation("get_cob", f"txid={txid}")
        query: dict[str, Any] = {}
        if params.get("revisao"):
            query["revisao"] = params["revisao"]
        return self._send_request("GET", f"/cob/{txid}", None, params=query)

    def _create_cobv(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cria uma cobrança com vencimento via Pix (somente BRL)."""
        err = self._validate_currency(params)
        if err:
            return {"success": False, "error": err, "reject_code": "ZF-PIX-CUR-001"}

        txid = params.get("txid", "")
        valor = params.get("valor", {})
        if not txid or not valor:
            return {"success": False, "error": "Parâmetros obrigatórios: txid, valor"}
        self._log_operation("create_cobv", f"txid={txid} currency=BRL")

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

        return self._send_request("PUT", f"/cobv/{txid}", payload)

    def _create_devolution(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cria uma devolução (reembolso) de um pagamento Pix."""
        e2eid = params.get("e2eid", "")
        dev_id = params.get("id", "")
        valor = params.get("valor", "")
        if not e2eid or not dev_id or not valor:
            return {"success": False, "error": "Parâmetros obrigatórios: e2eid, id, valor"}
        self._log_operation("create_devolution", f"e2eid={e2eid}")

        payload: dict[str, Any] = {"valor": valor}
        if params.get("descricao"):
            payload["descricao"] = params["descricao"]
        return self._send_request("PUT", f"/pix/{e2eid}/devolucao/{dev_id}", payload)

    def _get_devolution(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta uma devolução de pagamento Pix."""
        e2eid = params.get("e2eid", "")
        dev_id = params.get("id", "")
        if not e2eid or not dev_id:
            return {"success": False, "error": "Parâmetros obrigatórios: e2eid, id"}
        self._log_operation("get_devolution", f"e2eid={e2eid}")
        return self._send_request("GET", f"/pix/{e2eid}/devolucao/{dev_id}", None)

    def _get_pix(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta um pagamento Pix recebido por e2eid."""
        e2eid = params.get("e2eid", "")
        if not e2eid:
            return {"success": False, "error": "Parâmetro obrigatório: e2eid"}
        self._log_operation("get_pix", f"e2eid={e2eid}")
        return self._send_request("GET", f"/pix/{e2eid}", None)

    # ── HTTP helper ────────────────────────────────────────────────

    def _send_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Envia request HTTP via mTLS com Bearer token."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado (mTLS não inicializado)"}

        url = f"{self._base_url}{path}"
        headers = self._auth_headers()
        if payload is not None:
            headers["Content-Type"] = "application/json"

        try:
            if method == "GET":
                resp = self._mtls.get(url, headers=headers, params=params or {})
            elif method == "PUT":
                resp = self._mtls.put(url, data=payload, headers=headers, params=params or {})
            else:
                resp = self._mtls.post(url, data=payload, headers=headers, params=params or {})

            if resp.ok:
                data = resp.json() if resp.content else {}
                return {"success": True, "data": data}
            try:
                err_body = resp.json() if resp.content else {}
            except Exception:
                err_body = {"raw": resp.text}
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {err_body}",
                "status_code": resp.status_code,
            }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado: {e}"}


PIX_BRAZIL_SCHEMA = ConnectorSchema(
    name="pix_brazil",
    version="2.0.0",
    description="Cria e gestiona cobranças e pagamentos instantâneos via Pix do Brasil (mTLS ICP-Brasil)",
    category="latam",
    icon="zap",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="create_cob", description="Cria cobrança imediata (BRL)", category="write"),
        ActionDefinition(name="get_cob", description="Consulta cobrança", category="read"),
        ActionDefinition(name="create_cobv", description="Cria cobrança com vencimento (BRL)", category="write"),
        ActionDefinition(name="create_devolution", description="Cria devolução", category="write"),
        ActionDefinition(name="get_devolution", description="Consulta devolução", category="read"),
        ActionDefinition(name="get_pix", description="Consulta pagamento Pix", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["client_id", "client_secret", "cert_path", "key_path"],
            description="Credenciais Pix BCB + Certificado ICP-Brasil A1 (mTLS obrigatório)",
        )
    ],
)
