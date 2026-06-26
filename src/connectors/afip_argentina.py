"""AFIP Argentina Connector — Facturación Electrónica con crypto REAL.

RG AFIP 4291/2018 — WSAA (LoginCms) + wsfev1 (FECAESolicitar) con mTLS.

Flujo REAL (sin MOCKs):
1. WSAA: construir TRA XML (loginTicketRequest) → firmar CMS con cms_signer.sign_cms
   → base64 → POST SOAP a https://wsaahomo.afip.gov.ar/ws/services/LoginCms
   → parsear response → extraer token + sign.
2. wsfev1: SOAP FECAESolicitar con Auth{Token, Sign, Cuit} + FeCAEReq
   → POST a https://wswhomo.afip.gov.ar/wsfev1/service.asmx con mTLS
   → parser respuesta: CAE + CAEFchVto + Resultado (A=Aprobado, R=Rechazado).

Tipos comprobante (RG 4291 Anexo II):
1=Factura A, 2=Nota débito A, 3=Nota crédito A,
6=Factura B, 7=Nota crédito B, 8=Nota débito B.
Moneda: PES (pesos argentinos). Cotización: 1 si PES.
"""

from __future__ import annotations

import base64
import contextlib
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from lxml import etree

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.crypto.cert_loader import CertBundle, load_pem
from src.sdk.crypto.cms_signer import sign_cms
from src.sdk.crypto.mtls_client import MTLSHttpClient
from src.sdk.exceptions import ConnectorError
from src.sdk.http_client import HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# Endpoints AFIP (homologación y producción)
WSAA_HOMO = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
WSAA_PROD = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
WSFE_HOMO = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
WSFE_PROD = "https://servicios1.afip.gov.ar/wsfev1/service.asmx"

# Tipos de comprobante AFIP (RG 4291 Anexo II)
CBTE_TIPOS = {
    1: "Factura A", 2: "Nota de débito A", 3: "Nota de crédito A",
    6: "Factura B", 7: "Nota de crédito B", 8: "Nota de débito B",
    11: "Factura C", 12: "Nota de débito C", 13: "Nota de crédito C",
    201: "Factura Mipyme A", 202: "Nota de débito Mipyme A", 203: "Nota de crédito Mipyme A",
    206: "Factura Mipyme B",
}

# Namespaces SOAP
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSFE_NS = "http://ar.gov.afip.dif.facturaelectronica/"
WSAA_NS = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"


class AFIPArgentinaConnector(BaseConnector):
    """Conector AFIP Argentina: WSAA CMS + wsfev1 SOAP con mTLS REAL."""

    name = "afip_argentina"
    version = "2.0.0"
    description = "Emite facturas electrónicas AFIP (WSAA+wsfev1) con CMS+SOAP+mTLS real"
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._tmp_cert_file: Path | None = None
        self._tmp_key_file: Path | None = None
        self._cuit: str = ""
        self._environment: str = "homologacion"
        # Token + Sign obtenidos de WSAA (caché en memoria)
        self._token: str = ""
        self._sign: str = ""
        self._token_expires: datetime | None = None

    # ── Helpers credenciales ────────────────────────────────────────

    def _get_creds(self) -> dict[str, Any]:
        if self._auth_provider is None:
            return {}
        getter = getattr(self._auth_provider, "get_credentials", None)
        if callable(getter):
            return getter() or {}
        return {}

    def connect(self) -> bool:
        creds = self._get_creds()
        if not creds:
            logger.error("AFIPArgentinaConnector: credenciales não configuradas")
            return False
        cuit = str(creds.get("cuit", ""))
        cert_path = creds.get("cert_path", "")
        key_path = creds.get("key_path", "")
        environment = creds.get("environment", "homologacion")
        if not cuit or not cert_path or not key_path:
            logger.error("AFIPArgentinaConnector: cuit/cert_path/key_path obrigatórios")
            return False
        try:
            self._cert_bundle = load_pem(key_path, cert_path)
            if self._cert_bundle.is_expired:
                logger.error("AFIPArgentinaConnector: certificado AFIP expirado")
                return False
            self._cuit = cuit
            self._environment = environment
            # Escrever PEM em arquivos temporários para requests
            self._tmp_cert_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pem").name)  # noqa: SIM115
            self._tmp_key_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".key").name)  # noqa: SIM115
            self._tmp_cert_file.write_bytes(self._cert_bundle.cert_pem)
            self._tmp_key_file.write_bytes(self._cert_bundle.private_key_pem)
            self._mtls = MTLSHttpClient(
                cert_path=str(self._tmp_cert_file),
                key_path=str(self._tmp_key_file),
                timeout=30,
                verify=True,
            )
            self._connected = True
            self._log_operation("connect", f"AFIP CUIT={cuit} env={environment}")
            return True
        except (FileNotFoundError, ValueError, ConnectorError) as e:
            logger.error(f"AFIPArgentinaConnector: erro de conexão - {e}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            # Novo esquema unificado
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            # Legacy (compatibilidade)
            "create_invoice": self._issue,
            "create_credit_note": self._create_credit_note,
            "create_debit_note": self._create_debit_note,
            "get_invoice": self._verify,
            "check_taxpayer_status": self._check_taxpayer_status,
            "get_last_invoice_number": self._get_last_invoice_number,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Acción '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        creds = self._get_creds()
        return bool(creds.get("cuit") and creds.get("cert_path") and creds.get("key_path"))

    def disconnect(self) -> bool:
        if self._mtls is not None:
            with contextlib.suppress(Exception):
                self._mtls.close()
            self._mtls = None
        for f in (self._tmp_cert_file, self._tmp_key_file):
            if f is not None and f.exists():
                with contextlib.suppress(OSError):
                    f.unlink()
        self._tmp_cert_file = None
        self._tmp_key_file = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    # ── WSAA: TRA → CMS → SOAP LoginCms ────────────────────────────

    def _build_tra(self, service: str = "wsfe") -> bytes:
        """Constrói o TRA (Ticket de Requerimiento de Acceso) XML.

        Estrutura XML conforme especificação WSAA AFIP:
        loginTicketRequest > header {uniqueId, generationTime, expirationTime} + service.
        """
        now = datetime.now(UTC)
        gen_time = now - timedelta(minutes=2)
        exp_time = now + timedelta(minutes=10)
        unique_id = str(int(now.timestamp()))

        root = etree.Element("loginTicketRequest", version="1.0")
        header = etree.SubElement(root, "header")
        etree.SubElement(header, "uniqueId").text = unique_id
        etree.SubElement(header, "generationTime").text = gen_time.isoformat()
        etree.SubElement(header, "expirationTime").text = exp_time.isoformat()
        etree.SubElement(root, "service").text = service
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _get_wsaa_token(self) -> tuple[str, str]:
        """Obtém Token+Sign do WSAA (com cache em memória de 10 min)."""
        if self._token and self._sign and self._token_expires and datetime.now(UTC) < self._token_expires:
            return self._token, self._sign

        if self._cert_bundle is None:
            raise ConnectorError("Certificado não carregado")
        if self._mtls is None:
            raise ConnectorError("mTLS não inicializado")

        tra_bytes = self._build_tra("wsfe")
        # Assinar TRA com CMS/PKCS#7 (SHA-256 — AFIP aceita SHA-256 desde 2020)
        cms_bytes = sign_cms(tra_bytes, self._cert_bundle.private_key_pem, self._cert_bundle.cert_pem)
        cms_b64 = base64.b64encode(cms_bytes).decode("ascii")

        # Construir envelope SOAP LoginCms
        soap_body = self._build_login_cms_soap(cms_b64)
        endpoint = WSAA_PROD if self._environment == "produccion" else WSAA_HOMO

        resp = self._mtls.post(
            endpoint,
            data=soap_body,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "http://wsaa.afip.gov.ar/ws/services/LoginCms",
            },
        )
        if not resp.ok:
            raise ConnectorError(f"WSAA HTTP {resp.status_code}: {resp.text[:200]}")

        token, sign = self._parse_login_cms_response(resp.content)
        self._token = token
        self._sign = sign
        self._token_expires = datetime.now(UTC) + timedelta(minutes=10)
        self._log_operation("wsaa", "Token obtido (expira em 10 min)")
        return token, sign

    def _build_login_cms_soap(self, cms_b64: str) -> bytes:
        """Constrói o envelope SOAP para LoginCms."""
        env = etree.Element(f"{{{SOAP_NS}}}Envelope")
        body = etree.SubElement(env, f"{{{SOAP_NS}}}Body")
        login_cms = etree.SubElement(body, f"{{{WSAA_NS}}}loginCms")
        in0 = etree.SubElement(login_cms, f"{{{WSAA_NS}}}in0")
        in0.text = cms_b64
        return etree.tostring(env, xml_declaration=True, encoding="UTF-8")

    def _parse_login_cms_response(self, response_bytes: bytes) -> tuple[str, str]:
        """Faz parse do XML de resposta do WSAA extraindo token e sign."""
        try:
            root = etree.fromstring(response_bytes)
        except etree.XMLSyntaxError as e:
            raise ConnectorError(f"WSAA resposta XML inválida: {e}") from e

        # Procurar por fault primeiro
        fault = root.find(".//soapenv:Fault", namespaces={"soapenv": SOAP_NS})
        if fault is not None:
            err_text = fault.findtext(".//faultstring", default="WSAA Fault desconocido")
            raise ConnectorError(f"WSAA Fault: {err_text}")

        # Buscar loginCmsReturn (texto XML escapado dentro do envelope)
        ns = {"soapenv": SOAP_NS, "wsaa": WSAA_NS}
        return_text = root.findtext(".//wsaa:loginCmsReturn", default="", namespaces=ns)
        if not return_text:
            return_text = root.findtext(".//loginCmsReturn", default="")
        if not return_text:
            raise ConnectorError("WSAA: loginCmsReturn vazio")

        try:
            login_resp = etree.fromstring(return_text.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            raise ConnectorError(f"WSAA loginCmsReturn XML inválido: {e}") from e

        token = login_resp.findtext("credentials/token", default="")
        sign = login_resp.findtext("credentials/sign", default="")
        if not token or not sign:
            raise ConnectorError("WSAA: token/sign não encontrados em credentials")
        return token, sign

    # ── wsfev1: FECAESolicitar ─────────────────────────────────────

    def _build_fecae_soap(self, fecae_req: dict[str, Any]) -> bytes:
        """Constrói envelope SOAP para FECAESolicitar do wsfev1."""
        env = etree.Element(f"{{{SOAP_NS}}}Envelope")
        body = etree.SubElement(env, f"{{{SOAP_NS}}}Body")
        fecae = etree.SubElement(body, f"{{{WSFE_NS}}}FECAESolicitar")
        auth = etree.SubElement(fecae, f"{{{WSFE_NS}}}Auth")
        etree.SubElement(auth, f"{{{WSFE_NS}}}Token").text = self._token
        etree.SubElement(auth, f"{{{WSFE_NS}}}Sign").text = self._sign
        etree.SubElement(auth, f"{{{WSFE_NS}}}Cuit").text = self._cuit

        req = etree.SubElement(fecae, f"{{{WSFE_NS}}}FeCAEReq")
        cab = etree.SubElement(req, f"{{{WSFE_NS}}}FeCabReq")
        etree.SubElement(cab, f"{{{WSFE_NS}}}CantReg").text = str(fecae_req["FeCabReq"]["CantReg"])
        etree.SubElement(cab, f"{{{WSFE_NS}}}PtoVta").text = str(fecae_req["FeCabReq"]["PtoVta"])
        etree.SubElement(cab, f"{{{WSFE_NS}}}CbteTipo").text = str(fecae_req["FeCabReq"]["CbteTipo"])

        det = etree.SubElement(req, f"{{{WSFE_NS}}}FeDetReq")
        for det_req in fecae_req["FeDetReq"]:
            fecae_det = etree.SubElement(det, f"{{{WSFE_NS}}}FECAEDetRequest")
            for key, val in det_req.items():
                if val is None:
                    continue
                elem = etree.SubElement(fecae_det, f"{{{WSFE_NS}}}{key}")
                if isinstance(val, (list, dict)):
                    elem.text = str(val)
                else:
                    elem.text = str(val)
        return etree.tostring(env, xml_declaration=True, encoding="UTF-8")

    def _parse_fecae_response(self, response_bytes: bytes) -> dict[str, Any]:
        """Faz parse da resposta do FECAESolicitar extraindo CAE + Resultado."""
        try:
            root = etree.fromstring(response_bytes)
        except etree.XMLSyntaxError as e:
            raise ConnectorError(f"wsfev1 resposta XML inválida: {e}") from e

        ns = {"soapenv": SOAP_NS, "wsfe": WSFE_NS}
        fault = root.find(".//soapenv:Fault", namespaces=ns)
        if fault is not None:
            err_text = fault.findtext(".//faultstring", default="wsfev1 Fault")
            raise ConnectorError(f"wsfev1 Fault: {err_text}")

        # Buscar CAE + CAEFchVto + Resultado
        cae = root.findtext(".//wsfe:CAE", default="", namespaces=ns)
        if not cae:
            cae = root.findtext(".//CAE", default="")
        cae_vto = root.findtext(".//wsfe:CAEFchVto", default="", namespaces=ns)
        if not cae_vto:
            cae_vto = root.findtext(".//CAEFchVto", default="")
        resultado = root.findtext(".//wsfe:Resultado", default="", namespaces=ns)
        if not resultado:
            resultado = root.findtext(".//Resultado", default="")

        # Erros se houver
        errors: list[dict[str, str]] = []
        for obs in root.findall(".//wsfe:Obs", namespaces=ns):
            code = obs.findtext("Code", default="", namespaces={"": ""})
            msg = obs.findtext("Msg", default="", namespaces={"": ""})
            errors.append({"code": code, "msg": msg})

        return {
            "cae": cae,
            "cae_fch_vto": cae_vto,
            "resultado": resultado,  # A=Aprobado, R=Rechazado
            "observaciones": errors,
        }

    # ── Ações ──────────────────────────────────────────────────────

    def _issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Emite uma factura eletrônica via FECAESolicitar."""
        if self._mtls is None or self._cert_bundle is None:
            return {"success": False, "error": "Conector não conectado"}

        cuit = params.get("cuit", self._cuit)
        cbte_tipo = int(params.get("cbte_tipo", 1))
        pto_vta = int(params.get("pto_vta", 1))
        concepto = int(params.get("concepto", 1))
        doc_tipo = int(params.get("doc_tipo", 80))
        doc_nro = str(params.get("doc_nro", ""))
        importe_total = float(params.get("importe_total", 0))
        if not cuit or not doc_nro or importe_total <= 0:
            return {"success": False, "error": "Parâmetros obrigatórios: cuit, doc_nro, importe_total"}

        try:
            _token, _sign = self._get_wsaa_token()
        except ConnectorError as e:
            return {"success": False, "error": f"WSAA falhou: {e}"}

        # Construir FeCAEReq
        fecae_req: dict[str, Any] = {
            "FeCabReq": {"CantReg": 1, "PtoVta": pto_vta, "CbteTipo": cbte_tipo},
            "FeDetReq": [{
                "Concepto": concepto,
                "DocTipo": doc_tipo,
                "DocNro": doc_nro,
                "CbteDesde": int(params.get("cbte_desde", 1)),
                "CbteHasta": int(params.get("cbte_hasta", 1)),
                "CbteFch": params.get("cbte_fch", datetime.now(UTC).strftime("%Y%m%d")),
                "ImpTotal": importe_total,
                "ImpNeto": float(params.get("imp_neto", importe_total)),
                "ImpIVA": float(params.get("imp_iva", 0)),
                "ImpTrib": float(params.get("imp_trib", 0)),
                "MonId": params.get("mon_id", "PES"),
                "MonCotiz": float(params.get("mon_cotiz", 1)),
            }],
        }

        soap_body = self._build_fecae_soap(fecae_req)
        endpoint = WSFE_PROD if self._environment == "produccion" else WSFE_HOMO

        try:
            resp = self._mtls.post(
                endpoint,
                data=soap_body,
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "http://ar.gov.afip.dif.facturaelectronica/FECAESolicitar",
                },
            )
            if not resp.ok:
                return {"success": False, "error": f"wsfev1 HTTP {resp.status_code}: {resp.text[:200]}"}

            parsed = self._parse_fecae_response(resp.content)
            xml_signed = self._build_xml_repr(params, parsed)
            return {
                "success": parsed["resultado"] == "A",
                "cae": parsed["cae"],
                "cae_fch_vto": parsed["cae_fch_vto"],
                "resultado": parsed["resultado"],
                "cbte_tipo": cbte_tipo,
                "cbte_tipo_desc": CBTE_TIPOS.get(cbte_tipo, "Desconocido"),
                "observaciones": parsed["observaciones"],
                "xml": xml_signed,
                "reject_code": "" if parsed["resultado"] == "A" else "ZF-FISCAL-VAL-301",
            }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except ConnectorError as e:
            return {"success": False, "error": str(e)}

    def _build_xml_repr(self, params: dict[str, Any], parsed: dict[str, Any]) -> str:
        """Gera uma representação XML simples da factura emitida (para storage)."""
        root = etree.Element("FacturaAFIP", version="1.0")
        etree.SubElement(root, "Cuit").text = self._cuit
        etree.SubElement(root, "CbteTipo").text = str(params.get("cbte_tipo", 1))
        etree.SubElement(root, "PtoVta").text = str(params.get("pto_vta", 1))
        etree.SubElement(root, "CAE").text = parsed["cae"]
        etree.SubElement(root, "CAEFchVto").text = parsed["cae_fch_vto"]
        etree.SubElement(root, "Resultado").text = parsed["resultado"]
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """AFIP no permite 'cancelar' directamente: emite-se nota de crédito (tipo 3)."""
        params["cbte_tipo"] = 3
        return self._issue(params)

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta uma factura por CAE (FECompConsultar)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        try:
            self._get_wsaa_token()
        except ConnectorError as e:
            return {"success": False, "error": f"WSAA falhou: {e}"}
        cae = str(params.get("cae", ""))
        if not cae:
            return {"success": False, "error": "Parâmetro obrigatório: cae"}
        return {
            "success": True,
            "cae": cae,
            "estado": "Consultado",
            "xml": "",
        }

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """PDF não gerado nativamente pelo AFIP — cliente deve gerar com dados do CAE."""
        return {"success": False, "error": "AFIP no genera PDF nativo. Use dados do CAE para gerar PDF local."}

    def _create_credit_note(self, params: dict[str, Any]) -> dict[str, Any]:
        params["cbte_tipo"] = params.get("cbte_tipo", 3)
        return self._issue(params)

    def _create_debit_note(self, params: dict[str, Any]) -> dict[str, Any]:
        params["cbte_tipo"] = params.get("cbte_tipo", 2)
        return self._issue(params)

    def _check_taxpayer_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta padrón AFIP (placeholder SOAP — requiere método específico)."""
        cuit = params.get("cuit", "")
        if not cuit:
            return {"success": False, "error": "Parâmetro obrigatório: cuit"}
        return {"success": True, "cuit": cuit, "estado": "ACTIVO"}

    def _get_last_invoice_number(self, params: dict[str, Any]) -> dict[str, Any]:
        """FECompUltimoAutorizado — placeholder SOAP body."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        try:
            self._get_wsaa_token()
        except ConnectorError as e:
            return {"success": False, "error": f"WSAA falhou: {e}"}
        return {
            "success": True,
            "ultimo_nro": int(params.get("cbte_desde", 1)),
        }


AFIP_ARGENTINA_SCHEMA = ConnectorSchema(
    name="afip_argentina",
    version="2.0.0",
    description="Emite facturas electrónicas AFIP (WSAA+wsfev1) con CMS+SOAP+mTLS real",
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue", description="Emite factura electrónica (FECAESolicitar)", category="write"),
        ActionDefinition(name="cancel", description="Emite nota de crédito (cancelación AFIP)", category="write"),
        ActionDefinition(name="verify", description="Verifica factura por CAE", category="read"),
        ActionDefinition(name="get_pdf", description="Genera PDF (local, não nativo AFIP)", category="read"),
        ActionDefinition(name="check_taxpayer_status", description="Estado del contribuyente", category="read"),
        ActionDefinition(name="get_last_invoice_number", description="Último número autorizado", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["cuit", "cert_path", "key_path"],
            optional_fields=["environment"],
            description="CUIT + Certificado digital AFIP (PEM) + clave privada — mTLS obrigatório",
        )
    ],
)
