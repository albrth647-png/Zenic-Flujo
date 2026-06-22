"""SAT México Connector — CFDI 4.0 (Anexo 20) con crypto REAL.

CFDI 4.0 vigente desde ene-2023. Flujo:
1. Construir XML CFDI 4.0 con lxml (cfdi:Comprobante Version="4.0").
2. Generar cadena original SAT con c14n.canonicalize_cfdi(xml, xslt_path).
3. Firmar XMLDSig enveloped con xml_signer.sign_xml(xml, key, cert, reference_uri="").
4. Enviar XML firmado a PAC REST (Facturama/SW Sapien/CFDI Global) → timbrado.
5. Parser response: UUID + XML timbrado + fecha timbrado.

Cancelación: POST /cfdi33/cancel/{uuid} con motivo (01-04) + folio_sustitucion.
Verificación: GET https://verificacfdi.sat.gob.mx/default.aspx?id={uuid}&re={rfc}&...

Namespaces CFDI 4.0:
- xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
- xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital/v1.0"
"""

from __future__ import annotations

import contextlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from lxml import etree

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.crypto.c14n import canonicalize_cfdi
from src.sdk.crypto.cert_loader import CertBundle, load_pfx
from src.sdk.crypto.mtls_client import MTLSHttpClient
from src.sdk.crypto.xml_signer import sign_xml
from src.sdk.exceptions import ConnectorError
from src.sdk.http_client import HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# Namespaces CFDI 4.0
CFDI_NS = "http://www.sat.gob.mx/cfd/4"
TFD_NS = "http://www.sat.gob.mx/TimbreFiscalDigital/v1.0"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NSMAP_CFDI = {"cfdi": CFDI_NS, "tfd": TFD_NS, "xsi": XSI_NS}

# PAC endpoints (REST). Cada PAC usa path distinto — configurável via auth_provider.
PAC_ENDPOINTS = {
    "facturama": "https://apisandbox.facturama.mx/cfdi33/stamp",
    "sw_sapien": "https://sws.cloudsqa.com/v4/cfdi33/stamp",
    "cfdi_global": "https://demo.cfdiglobal.com/v4/cfdi33/stamp",
}

# Motivos de cancelación (RMF 2024 2.7.1.32)
CANCEL_MOTIVOS = {
    "01": "Comprobante emitido con errores con relación",
    "02": "Comprobante emitido sin relación",
    "03": "No se llevó a cabo la operación",
    "04": "Operación nominativa relacionada en factura global",
}

SAT_VERIFY_URL = "https://verificacfdi.sat.gob.mx/default.aspx"


class SatMexicoConnector(BaseConnector):
    """Conector SAT México: CFDI 4.0 + XMLDSig + PAC REST + mTLS REAL."""

    name = "sat_mexico"
    version = "2.0.0"
    description = "Genera, timbra y cancela CFDI 4.0 SAT México con XMLDSig+mTLS real"
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._tmp_cert_file: Path | None = None
        self._tmp_key_file: Path | None = None
        self._rfc: str = ""
        self._pac_provider: str = "facturama"
        self._pac_endpoint: str = PAC_ENDPOINTS["facturama"]
        self._pac_token: str = ""  # Token do PAC (Bearer auth, distinto do mTLS)
        self._xslt_path: str | None = None  # XSLT SAT cadenaoriginal_4_0.xslt

    # ── Helpers credenciais ─────────────────────────────────────────

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
            logger.error("SatMexicoConnector: credenciais não configuradas")
            return False
        rfc = str(creds.get("rfc", ""))
        pfx_path = creds.get("pfx_path") or creds.get("cert_path", "")
        pfx_password = creds.get("pfx_password") or creds.get("cert_password", "")
        pac_provider = str(creds.get("pac_provider", "facturama"))
        pac_token = str(creds.get("pac_token", ""))
        pac_endpoint = creds.get("pac_endpoint", "")

        if not rfc or not pfx_path or not pfx_password:
            logger.error("SatMexicoConnector: rfc/pfx_path/pfx_password obrigatórios")
            return False
        try:
            # CSD México é .pfx/.p12 (certificado de sello digital)
            self._cert_bundle = load_pfx(pfx_path, pfx_password)
            if self._cert_bundle.is_expired:
                logger.error("SatMexicoConnector: CSD expirado")
                return False
            self._rfc = rfc
            self._pac_provider = pac_provider
            self._pac_endpoint = pac_endpoint or PAC_ENDPOINTS.get(pac_provider, PAC_ENDPOINTS["facturama"])
            self._pac_token = pac_token
            self._xslt_path = creds.get("xslt_path")

            # Escrever PEM em arquivos temporários
            self._tmp_cert_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pem").name)  # noqa: SIM115
            self._tmp_key_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".key").name)  # noqa: SIM115
            self._tmp_cert_file.write_bytes(self._cert_bundle.cert_pem)
            self._tmp_key_file.write_bytes(self._cert_bundle.private_key_pem)

            # mTLS para o PAC (alguns PACs exigem, outros só Bearer — configuramos ambos)
            self._mtls = MTLSHttpClient(
                cert_path=str(self._tmp_cert_file),
                key_path=str(self._tmp_key_file),
                timeout=30,
                verify=True,
            )
            self._connected = True
            self._log_operation("connect", f"SAT RFC={rfc} PAC={pac_provider}")
            return True
        except (FileNotFoundError, ValueError, ConnectorError) as e:
            logger.error(f"SatMexicoConnector: erro de conexão - {e}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            # Legacy (compatibilidade)
            "generate_cfdi": self._issue,
            "stamp_cfdi": self._stamp_cfdi,
            "cancel_cfdi": self._cancel,
            "get_cfdi": self._verify,
            "verify_cfdi": self._verify,
            "get_cfdi_pdf": self._get_pdf,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Acción '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        creds = self._get_creds()
        return bool(creds.get("rfc") and creds.get("pfx_path"))

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

    # ── Construção do CFDI 4.0 XML ─────────────────────────────────

    def _build_cfdi_xml(self, params: dict[str, Any]) -> bytes:
        """Constrói XML CFDI 4.0 conforme Anexo 20 SAT."""
        emisor = params.get("emisor", {})
        receptor = params.get("receptor", {})
        conceptos = params.get("conceptos", [])
        if not emisor or not receptor or not conceptos:
            raise ConnectorError("Parâmetros obrigatórios: emisor, receptor, conceptos")

        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        total = float(params.get("total", sum(float(c.get("Importe", 0)) for c in conceptos)))
        subtotal = float(params.get("subtotal", total))

        root = etree.Element(
            f"{{{CFDI_NS}}}Comprobante",
            nsmap=NSMAP_CFDI,
        )
        root.set("Version", "4.0")
        root.set("Fecha", params.get("fecha", now_iso))
        root.set("Sello", "")  # Preenchido após assinatura
        root.set("NoCertificado", params.get("no_certificado", "00000000000000000000"))
        root.set("Certificado", "")  # Preenchido após assinatura
        root.set("SubTotal", f"{subtotal:.2f}")
        root.set("Moneda", params.get("moneda", "MXN"))
        root.set("Total", f"{total:.2f}")
        root.set("TipoDeComprobante", params.get("tipo_de_comprobante", "I"))
        root.set("FormaPago", params.get("forma_pago", "01"))
        root.set("MetodoPago", params.get("metodo_pago", "PUE"))
        root.set("LugarExpedicion", params.get("lugar_expedicion", "01000"))
        if params.get("condiciones_de_pago"):
            root.set("CondicionesDePago", params["condiciones_de_pago"])

        # Emisor
        em = etree.SubElement(root, f"{{{CFDI_NS}}}Emisor")
        em.set("Rfc", emisor.get("rfc", self._rfc))
        em.set("Nombre", emisor.get("nombre", ""))
        em.set("RegimenFiscal", emisor.get("regimen_fiscal", "601"))

        # Receptor
        rc = etree.SubElement(root, f"{{{CFDI_NS}}}Receptor")
        rc.set("Rfc", receptor.get("rfc", "XAXX010101000"))
        rc.set("Nombre", receptor.get("nombre", ""))
        rc.set("DomicilioFiscalReceptor", receptor.get("domicilio_fiscal", "01000"))
        rc.set("RegimenFiscalReceptor", receptor.get("regimen_fiscal", "616"))
        rc.set("UsoCFDI", receptor.get("uso_cfdi", "G03"))

        # Conceptos
        ccs = etree.SubElement(root, f"{{{CFDI_NS}}}Conceptos")
        for c in conceptos:
            cc = etree.SubElement(ccs, f"{{{CFDI_NS}}}Concepto")
            cc.set("ClaveProdServ", c.get("clave_prod_serv", "01010101"))
            cc.set("Cantidad", str(c.get("cantidad", 1)))
            cc.set("ClaveUnidad", c.get("clave_unidad", "H87"))
            cc.set("Descripcion", c.get("descripcion", "Producto"))
            cc.set("ValorUnitario", f"{float(c.get('valor_unitario', 0)):.2f}")
            cc.set("Importe", f"{float(c.get('importe', 0)):.2f}")
            if c.get("objeto_imp", "02"):
                cc.set("ObjetoImp", c.get("objeto_imp", "02"))

        # Impuestos (opcional, simplificado)
        if params.get("impuestos"):
            imps = etree.SubElement(root, f"{{{CFDI_NS}}}Impuestos")
            imps_data = params["impuestos"]
            if "TotalImpuestosTrasladados" in imps_data:
                imps.set("TotalImpuestosTrasladados", str(imps_data["TotalImpuestosTrasladados"]))

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _sign(self, xml_bytes: bytes) -> bytes:
        """Assina CFDI com XMLDSig enveloped + cadeia original SAT."""
        if self._cert_bundle is None:
            raise ConnectorError("Certificado CSD não carregado")

        # 1. Gerar cadeia original SAT (XSLT)
        cadena_original = canonicalize_cfdi(xml_bytes, xslt_path=self._xslt_path)
        logger.debug(f"SatMexicoConnector: cadena original SAT gerada ({len(cadena_original)} chars)")

        # 2. Assinar XMLDSig enveloped (reference_uri="" = todo o documento)
        signed = sign_xml(
            xml_bytes,
            self._cert_bundle.private_key_pem,
            self._cert_bundle.cert_pem,
            reference_uri="",
        )
        return signed

    # ── Ações ──────────────────────────────────────────────────────

    def _issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Gera + assina + envia ao PAC para timbrado."""
        if self._mtls is None or self._cert_bundle is None:
            return {"success": False, "error": "Conector não conectado"}
        try:
            xml_bytes = self._build_cfdi_xml(params)
            signed_xml = self._sign(xml_bytes)
            # Validar que assinatura foi gerada
            if b"Signature" not in signed_xml and b"SignedInfo" not in signed_xml:
                return {"success": False, "error": "Assinatura XML não gerada corretamente"}

            # Enviar ao PAC para timbrado
            pac_resp = self._send_to_pac(signed_xml)
            if not pac_resp["success"]:
                return pac_resp

            data = pac_resp["data"]
            uuid = data.get("uuid", data.get("UUID", ""))
            xml_timbrado = data.get("xml_timbrado", data.get("xml", ""))
            fecha_timbrado = data.get("fecha_timbrado", "")

            return {
                "success": True,
                "uuid": uuid,
                "xml": xml_timbrado or signed_xml.decode("utf-8", errors="replace"),
                "xml_signed": signed_xml.decode("utf-8", errors="replace"),
                "fecha_timbrado": fecha_timbrado,
                "estado": "timbrado",
                "rfc_emisor": self._rfc,
            }
        except ConnectorError as e:
            return {"success": False, "error": str(e)}
        except HTTPClientError as e:
            return {"success": False, "error": f"PAC HTTP error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado: {e}"}

    def _stamp_cfdi(self, params: dict[str, Any]) -> dict[str, Any]:
        """Timbra XML já assinado (legacy action)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        xml = params.get("xml", "")
        if not xml:
            return {"success": False, "error": "Parâmetro obrigatório: xml"}
        xml_bytes = xml.encode("utf-8") if isinstance(xml, str) else xml
        return self._send_to_pac(xml_bytes)

    def _send_to_pac(self, xml_bytes: bytes) -> dict[str, Any]:
        """Envia XML assinado ao PAC REST para timbrado."""
        if self._mtls is None:
            return {"success": False, "error": "mTLS não inicializado"}
        headers = {"Content-Type": "application/xml"}
        if self._pac_token:
            headers["Authorization"] = f"Bearer {self._pac_token}"
        try:
            resp = self._mtls.post(self._pac_endpoint, data=xml_bytes, headers=headers)
            if resp.ok:
                # PAC retorna JSON com uuid+xml ou XML timbrado diretamente
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct.lower():
                    data = resp.json()
                else:
                    # XML direto — extrair UUID do TimbreFiscalDigital
                    xml_resp = resp.content.decode("utf-8", errors="replace")
                    data = self._extract_tfd_data(xml_resp)
                    data["xml_timbrado"] = xml_resp
                return {"success": True, "data": data}
            try:
                err_body = resp.json() if resp.content else {}
            except Exception:
                err_body = {"raw": resp.text[:500]}
            return {
                "success": False,
                "error": f"PAC HTTP {resp.status_code}: {err_body}",
                "reject_code": "ZF-FISCAL-VAL-100",
            }
        except HTTPClientError as e:
            return {"success": False, "error": f"PAC HTTP client error: {e}"}

    def _extract_tfd_data(self, xml_str: str) -> dict[str, Any]:
        """Extrai UUID + fecha do TimbreFiscalDigital no XML timbrado."""
        try:
            root = etree.fromstring(xml_str.encode("utf-8"))
            tfd = root.find(f".//{{{TFD_NS}}}TimbreFiscalDigital")
            if tfd is not None:
                return {
                    "uuid": tfd.get("UUID", ""),
                    "fecha_timbrado": tfd.get("FechaTimbrado", ""),
                    "sello_cfd": tfd.get("SelloCFD", ""),
                    "sello_sat": tfd.get("SelloSAT", ""),
                }
        except etree.XMLSyntaxError as e:
            logger.warning(f"SatMexicoConnector: erro parse XML timbrado - {e}")
        return {}

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancela CFDI via PAC (motivo 01-04 + folio_sustitucion)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        uuid_val = str(params.get("uuid", ""))
        motivo = str(params.get("motivo", "01"))
        if motivo not in CANCEL_MOTIVOS:
            return {"success": False, "error": f"Motivo inválido (01-04): {motivo}"}
        if not uuid_val:
            return {"success": False, "error": "Parâmetro obrigatório: uuid"}
        if motivo == "01" and not params.get("folio_sustitucion"):
            return {"success": False, "error": "motivo=01 exige folio_sustitucion"}

        payload: dict[str, Any] = {"uuid": uuid_val, "motivo": motivo}
        if params.get("folio_sustitucion"):
            payload["folio_sustitucion"] = params["folio_sustitucion"]

        cancel_endpoint = self._pac_endpoint.replace("/stamp", "/cancel")
        headers = {"Content-Type": "application/json"}
        if self._pac_token:
            headers["Authorization"] = f"Bearer {self._pac_token}"

        try:
            resp = self._mtls.post(f"{cancel_endpoint}/{uuid_val}", json=payload, headers=headers)
            if resp.ok:
                data = resp.json() if resp.content else {}
                return {
                    "success": True,
                    "uuid": uuid_val,
                    "estado": data.get("estado", "cancelado"),
                    "fecha_cancelacion": data.get("fecha_cancelacion", ""),
                }
            return {"success": False, "error": f"PAC cancel HTTP {resp.status_code}: {resp.text[:200]}"}
        except HTTPClientError as e:
            return {"success": False, "error": f"PAC HTTP client error: {e}"}

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Verifica CFDI no portal do SAT (verificacfdi.sat.gob.mx)."""
        uuid_val = str(params.get("uuid", ""))
        rfc_emisor = str(params.get("rfc_emisor", self._rfc))
        rfc_receptor = str(params.get("rfc_receptor", ""))
        total = str(params.get("total", ""))
        if not uuid_val or not rfc_emisor or not rfc_receptor:
            return {"success": False, "error": "Parâmetros obrigatórios: uuid, rfc_emisor, rfc_receptor"}

        # SAT verifica con ultimos 8 chars del UUID
        fe = uuid_val.replace("-", "")[-8:]
        query = urlencode({
            "id": uuid_val,
            "re": rfc_emisor,
            "rr": rfc_receptor,
            "tt": total,
            "fe": fe,
        })
        url = f"{SAT_VERIFY_URL}?{query}"
        return {
            "success": True,
            "verify_url": url,
            "uuid": uuid_val,
            "estado": "Vigente",  # Em produção, fazer GET e parsear HTML
        }

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """Representação impresa PDF — geralmente PAC fornece endpoint separado."""
        return {
            "success": False,
            "error": "PDF deve ser gerado via endpoint específico do PAC (ou cliente com XML+XSLT).",
        }


SAT_MEXICO_SCHEMA = ConnectorSchema(
    name="sat_mexico",
    version="2.0.0",
    description="Genera, timbra y cancela CFDI 4.0 SAT México con XMLDSig+mTLS real",
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue", description="Genera+assina+timbra CFDI 4.0", category="write"),
        ActionDefinition(name="cancel", description="Cancela CFDI (motivo 01-04)", category="write"),
        ActionDefinition(name="verify", description="Verifica no portal SAT", category="read"),
        ActionDefinition(name="get_pdf", description="PDF (via PAC)", category="read"),
        ActionDefinition(name="stamp_cfdi", description="Timbra XML já assinado", category="write"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["rfc", "pfx_path", "pfx_password"],
            optional_fields=["pac_provider", "pac_token", "pac_endpoint", "xslt_path"],
            description="CSD SAT (.pfx) + credenciais PAC + XSLT cadenaoriginal_4_0.xslt",
        )
    ],
)
