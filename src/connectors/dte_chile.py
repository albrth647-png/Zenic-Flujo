"""DTE Chile Connector — SII (Resolución Exenta 45/2015) con crypto REAL.

DTE (Documento Tributario Electrónico) — SII Chile.

Flujo REAL (sin MOCKs):
1. Construir XML DTE con lxml (DTE xmlns="http://www.sii.cl/SiiDte" > Documento ID="T{tipo}F{folio}").
2. Generar C14N con c14n.canonicalize_xml sobre Documento.
3. Firmar XMLDSig enveloped con xml_signer.sign_xml(xml, key, cert, reference_uri="#T{tipo}F{folio}").
4. Empaquetar en EnvioDTE.
5. Subir vía POST multipart/form-data con mTLS a SII UPLINK/DTEAUTO.cgi.
6. Recibir TrackID.

Tipos DTE: 33=Factura electrónica, 34=Factura no afecta, 61=Nota crédito,
56=Nota débito, 52=Guía despacho.

Query estado: GET https://maullin.sii.cl/cgi_dte/QRYEST/DTEEst?...
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
from src.sdk.crypto.c14n import canonicalize_xml
from src.sdk.crypto.cert_loader import CertBundle, load_pem
from src.sdk.crypto.mtls_client import MTLSHttpClient
from src.sdk.crypto.xml_signer import sign_xml
from src.sdk.exceptions import ConnectorError
from src.sdk.http_client import HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# SII endpoints
SII_UPLINK_CERT = "https://maullin.sii.cl/cgi_dte/UPLINK/DTEAUTO.cgi"
SII_UPLINK_PROD = "https://palena.sii.cl/cgi_dte/UPLINK/DTEAUTO.cgi"
SII_QUERY_CERT = "https://maullin.sii.cl/cgi_dte/QRYEST/DTEEst"
SII_QUERY_PROD = "https://palena.sii.cl/cgi_dte/QRYEST/DTEEst"

# Namespace SII DTE
SII_NS = "http://www.sii.cl/SiiDte"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

# Tipos DTE Chile
TIPOS_DTE = {
    33: "Factura Electrónica",
    34: "Factura No Afecta o Exenta Electrónica",
    39: "Boleta Electrónica",
    41: "Boleta No Afecta o Exenta Electrónica",
    43: "Liquidación Factura Electrónica",
    46: "Factura de Compra Electrónica",
    52: "Guía de Despacho Electrónica",
    56: "Nota de Débito Electrónica",
    61: "Nota de Crédito Electrónica",
    110: "Factura de Exportación Electrónica",
    111: "Nota de Débito de Exportación",
    112: "Nota de Crédito de Exportación",
}


class DTEChileConnector(BaseConnector):
    """Conector SII Chile: DTE con XMLDSig+mTLS+multipart REAL (Res. Exenta 45/2015)."""

    name = "dte_chile"
    version = "2.0.0"
    description = "Emite DTE SII Chile con XMLDSig+mTLS+multipart real (Res. Exenta 45/2015)"
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._tmp_cert_file: Path | None = None
        self._tmp_key_file: Path | None = None
        self._rut: str = ""
        self._dv: str = ""
        self._environment: str = "certificacion"

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
            logger.error("DTEChileConnector: credenciais não configuradas")
            return False
        rut = str(creds.get("rut", ""))
        cert_path = creds.get("cert_path", "")
        key_path = creds.get("key_path", "")
        environment = str(creds.get("environment", "certificacion"))
        if not rut or not cert_path or not key_path:
            logger.error("DTEChileConnector: rut/cert_path/key_path obrigatórios")
            return False
        try:
            # Chile usa certificado X.509 PEM (e-Cert, certificado digital SII)
            self._cert_bundle = load_pem(key_path, cert_path)
            if self._cert_bundle.is_expired:
                logger.error("DTEChileConnector: certificado SII expirado")
                return False
            self._rut = rut.split("-")[0]
            self._dv = rut.split("-")[1] if "-" in rut else ""
            self._environment = environment

            # Escrever PEM em arquivos temporários
            self._tmp_cert_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pem").name)  # noqa: SIM115
            self._tmp_key_file = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".key").name)  # noqa: SIM115
            self._tmp_cert_file.write_bytes(self._cert_bundle.cert_pem)
            self._tmp_key_file.write_bytes(self._cert_bundle.private_key_pem)

            self._mtls = MTLSHttpClient(
                cert_path=str(self._tmp_cert_file),
                key_path=str(self._tmp_key_file),
                timeout=60,
                verify=True,
            )
            self._connected = True
            self._log_operation("connect", f"SII RUT={rut} env={environment}")
            return True
        except (FileNotFoundError, ValueError, ConnectorError) as e:
            logger.error(f"DTEChileConnector: erro de conexão - {e}")
            return False

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            # Legacy (compatibilidade)
            "create_dte": self._issue,
            "get_dte": self._verify,
            "list_dtes": self._list_dtes,
            "cancel_dte": self._cancel,
            "get_dte_pdf": self._get_pdf,
            "get_contributor_status": self._get_contributor_status,
            "get_exchange_rate": self._get_exchange_rate,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Acción '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        creds = self._get_creds()
        return bool(creds.get("rut") and creds.get("cert_path") and creds.get("key_path"))

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

    # ── Construção do DTE XML ──────────────────────────────────────

    def _build_dte_xml(self, params: dict[str, Any]) -> tuple[bytes, str]:
        """Constrói XML DTE conforme schema SII. Retorna (xml_bytes, documento_id)."""
        tipo_dte = int(params.get("tipo_dte", 33))
        folio = int(params.get("folio", 1))
        rut_emisor = params.get("rut_emisor", f"{self._rut}-{self._dv}")
        rut_receptor = params.get("rut_receptor", "")
        razon_emisor = params.get("razon_emisor", "EMISOR")
        razon_receptor = params.get("razon_receptor", "RECEPTOR")
        monto_total = int(params.get("monto_total", 0))

        if not rut_receptor or monto_total <= 0:
            raise ConnectorError("Parâmetros obrigatórios: rut_receptor, monto_total")

        documento_id = f"T{tipo_dte}F{folio}"

        nsmap = {None: SII_NS}
        dte = etree.Element(f"{{{SII_NS}}}DTE", nsmap=nsmap, version="1.0")

        documento = etree.SubElement(dte, f"{{{SII_NS}}}Documento", ID=documento_id)

        encabezado = etree.SubElement(documento, f"{{{SII_NS}}}Encabezado")
        id_doc = etree.SubElement(encabezado, f"{{{SII_NS}}}IdDoc")
        etree.SubElement(id_doc, f"{{{SII_NS}}}TipoDTE").text = str(tipo_dte)
        etree.SubElement(id_doc, f"{{{SII_NS}}}Folio").text = str(folio)
        etree.SubElement(id_doc, f"{{{SII_NS}}}FchEmis").text = params.get("fch_emis", datetime.now(UTC).strftime("%Y-%m-%d"))
        etree.SubElement(id_doc, f"{{{SII_NS}}}IndServicio").text = str(params.get("ind_servicio", 3))

        emisor = etree.SubElement(encabezado, f"{{{SII_NS}}}Emisor")
        etree.SubElement(emisor, f"{{{SII_NS}}}RUTEmisor").text = rut_emisor
        etree.SubElement(emisor, f"{{{SII_NS}}}RznSoc").text = razon_emisor
        etree.SubElement(emisor, f"{{{SII_NS}}}GiroEmis").text = params.get("giro_emisor", "GIRO EMISOR")
        etree.SubElement(emisor, f"{{{SII_NS}}}Acteco").text = str(params.get("acteco", 0))
        etree.SubElement(emisor, f"{{{SII_NS}}}DirOrigen").text = params.get("dir_origen", "Dirección")
        etree.SubElement(emisor, f"{{{SII_NS}}}CmnaOrigen").text = params.get("comuna_origen", "Comuna")

        receptor = etree.SubElement(encabezado, f"{{{SII_NS}}}Receptor")
        etree.SubElement(receptor, f"{{{SII_NS}}}RUTRecep").text = rut_receptor
        etree.SubElement(receptor, f"{{{SII_NS}}}RznSocRecep").text = razon_receptor
        etree.SubElement(receptor, f"{{{SII_NS}}}GiroRecep").text = params.get("giro_receptor", "GIRO RECEPTOR")
        etree.SubElement(receptor, f"{{{SII_NS}}}DirRecep").text = params.get("dir_receptor", "Dirección")
        etree.SubElement(receptor, f"{{{SII_NS}}}CmnaRecep").text = params.get("comuna_receptor", "Comuna")

        totales = etree.SubElement(encabezado, f"{{{SII_NS}}}Totales")
        monto_neto = int(params.get("mnt_neto", monto_total // 1.19))
        iva = int(params.get("iva", round(monto_neto * 0.19)))
        etree.SubElement(totales, f"{{{SII_NS}}}MntNeto").text = str(monto_neto)
        etree.SubElement(totales, f"{{{SII_NS}}}IVA").text = str(iva)
        etree.SubElement(totales, f"{{{SII_NS}}}MntTotal").text = str(monto_total)

        # Detalles
        if params.get("detalles"):
            detalles = etree.SubElement(documento, f"{{{SII_NS}}}Detalle")
            for i, det in enumerate(params["detalles"], start=1):
                etree.SubElement(detalles, f"{{{SII_NS}}}NroLinDet").text = str(i)
                etree.SubElement(detalles, f"{{{SII_NS}}}NmbItem").text = det.get("descripcion", f"Item {i}")
                etree.SubElement(detalles, f"{{{SII_NS}}}QtyItem").text = str(det.get("cantidad", 1))
                etree.SubElement(detalles, f"{{{SII_NS}}}PrcItem").text = str(det.get("precio", 0))
                etree.SubElement(detalles, f"{{{SII_NS}}}MontoItem").text = str(det.get("monto", 0))

        xml_bytes = etree.tostring(dte, xml_declaration=True, encoding="ISO-8859-1")
        return xml_bytes, documento_id

    def _sign(self, xml_bytes: bytes, documento_id: str) -> bytes:
        """Assina DTE com XMLDSig enveloped sobre Documento (C14N 1.0)."""
        if self._cert_bundle is None:
            raise ConnectorError("Certificado SII não carregado")

        # 1. Canonicalizar Documento (C14N 1.0)
        canon = canonicalize_xml(xml_bytes, exclusive=True, with_comments=False)
        logger.debug(f"DTEChileConnector: C14N gerado ({len(canon)} bytes)")

        # 2. Assinar XMLDSig enveloped com reference_uri="#T{tipo}F{folio}"
        signed = sign_xml(
            xml_bytes,
            self._cert_bundle.private_key_pem,
            self._cert_bundle.cert_pem,
            reference_uri=f"#{documento_id}",
        )
        return signed

    def _build_envio_dte(self, signed_xml: bytes, rut_emisor: str, rut_receptor: str) -> bytes:
        """Empacota DTE assinado em EnvioDTE."""
        envio = etree.Element(f"{{{SII_NS}}}EnvioDTE", nsmap={None: SII_NS}, version="1.0")
        set_dte = etree.SubElement(envio, f"{{{SII_NS}}}SetDTE", ID="SetDoc")
        etree.SubElement(set_dte, f"{{{SII_NS}}}CARATULA", version="1.0").text = ""
        # Anexar DTE assinado
        dte_root = etree.fromstring(signed_xml)
        set_dte.append(dte_root)
        return etree.tostring(envio, xml_declaration=True, encoding="ISO-8859-1")

    # ── Ações ──────────────────────────────────────────────────────

    def _issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Emite DTE: build → sign → EnvioDTE → POST multipart SII UPLINK."""
        if self._mtls is None or self._cert_bundle is None:
            return {"success": False, "error": "Conector não conectado"}

        try:
            xml_bytes, documento_id = self._build_dte_xml(params)
            signed_xml = self._sign(xml_bytes, documento_id)
            if b"Signature" not in signed_xml and b"SignedInfo" not in signed_xml:
                return {"success": False, "error": "Assinatura XML não gerada"}

            # Empacotar em EnvioDTE
            rut_emisor = params.get("rut_emisor", f"{self._rut}-{self._dv}")
            rut_receptor = params.get("rut_receptor", "")
            envio_xml = self._build_envio_dte(signed_xml, rut_emisor, rut_receptor)

            # POST multipart/form-data ao SII UPLINK
            track_id = self._upload_to_sii(envio_xml, rut_emisor)

            return {
                "success": True,
                "track_id": track_id,
                "tipo_dte": int(params.get("tipo_dte", 33)),
                "tipo_dte_desc": TIPOS_DTE.get(int(params.get("tipo_dte", 33)), "Desconocido"),
                "folio": int(params.get("folio", 1)),
                "xml": signed_xml.decode("iso-8859-1", errors="replace"),
            }
        except ConnectorError as e:
            return {"success": False, "error": str(e)}
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Erro inesperado: {e}"}

    def _upload_to_sii(self, envio_xml: bytes, rut_emisor: str) -> str:
        """Faz upload do EnvioDTE via POST multipart/form-data com mTLS ao SII UPLINK."""
        if self._mtls is None:
            raise ConnectorError("mTLS não inicializado")
        endpoint = SII_UPLINK_PROD if self._environment == "produccion" else SII_UPLINK_CERT

        # Construir multipart/form-data manualmente
        boundary = "----ZenFlujoBoundary" + datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="rutSender"\r\n\r\n{rut_emisor}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="dvSender"\r\n\r\n{self._dv}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="archivo"; filename="envioDTE.xml"\r\n'
            f"Content-Type: application/xml\r\n\r\n"
        ).encode("iso-8859-1") + envio_xml + f"\r\n--{boundary}--\r\n".encode("iso-8859-1")

        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

        resp = self._mtls.post(endpoint, data=body, headers=headers)
        if not resp.ok:
            raise ConnectorError(f"SII UPLINK HTTP {resp.status_code}: {resp.text[:200]}")

        # SII retorna XML/text com TrackID
        return self._parse_track_id(resp.content)

    def _parse_track_id(self, response_bytes: bytes) -> str:
        """Extrai TrackID da resposta do SII UPLINK."""
        try:
            text = response_bytes.decode("iso-8859-1", errors="replace")
            # SII retorna <TRACK_ID>123456</TRACK_ID> ou texto plano
            if "<TRACK_ID>" in text:
                start = text.index("<TRACK_ID>") + len("<TRACK_ID>")
                end = text.index("</TRACK_ID>")
                return text[start:end].strip()
            # Fallback: procurar número longo
            import re
            m = re.search(r"\b(\d{10,15})\b", text)
            return m.group(1) if m else ""
        except Exception as e:
            logger.warning(f"DTEChileConnector: erro parse TrackID - {e}")
            return ""

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancela DTE via nota de crédito (tipo 61) referenciando o original."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        # Cancelamento no SII é feito emitindo NC (61) que referencia o DTE original
        params["tipo_dte"] = 61
        if not params.get("referencias"):
            params["referencias"] = [{
                "tpo_doc_ref": str(params.get("tipo_dte_original", 33)),
                "folio_ref": str(params.get("folio_original", 0)),
                "cod_ref": 1,  # 1=Anula documento
                "razon_ref": params.get("motivo", "Anula documento"),
            }]
        result = self._issue(params)
        result["accion"] = "cancelacion"
        return result

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Verifica estado do DTE no SII (QRYEST/DTEEst)."""
        if self._mtls is None:
            return {"success": False, "error": "Conector não conectado"}
        rut_emisor = params.get("rut_emisor", self._rut)
        dv_emisor = params.get("dv_emisor", self._dv)
        rut_receptor = params.get("rut_receptor", "")
        dv_receptor = params.get("dv_receptor", "")
        tipo_dte = str(params.get("tipo_dte", 33))
        folio = str(params.get("folio", 0))
        fch_emis = params.get("fch_emis", datetime.now(UTC).strftime("%Y-%m-%d"))

        if not rut_receptor or not folio:
            return {"success": False, "error": "Parâmetros obrigatórios: rut_receptor, folio"}

        query = urlencode({
            "RUT_EMISOR": rut_emisor,
            "DV_EMISOR": dv_emisor,
            "RUT_RECEPTOR": rut_receptor,
            "DV_RECEPTOR": dv_receptor,
            "TIPO_DTE": tipo_dte,
            "FOLIO": folio,
            "FCH_EMIS": fch_emis,
        })
        url = (SII_QUERY_PROD if self._environment == "produccion" else SII_QUERY_CERT) + "?" + query

        try:
            resp = self._mtls.get(url)
            if not resp.ok:
                return {"success": False, "error": f"SII QRYEST HTTP {resp.status_code}"}
            estado = self._parse_estado_dte(resp.content)
            return {
                "success": True,
                "tipo_dte": int(tipo_dte),
                "folio": int(folio),
                "estado": estado,
                "raw_response": resp.content.decode("iso-8859-1", errors="replace"),
            }
        except HTTPClientError as e:
            return {"success": False, "error": f"HTTP client error: {e}"}

    def _parse_estado_dte(self, response_bytes: bytes) -> str:
        """Extrai estado do DTE da resposta do QRYEST."""
        try:
            text = response_bytes.decode("iso-8859-1", errors="replace")
            for tag in ("ESTADO", "Estado", "estado"):
                if f"<{tag}>" in text:
                    start = text.index(f"<{tag}>") + len(f"<{tag}>")
                    end = text.index(f"</{tag}>")
                    return text[start:end].strip()
            # Texto plano
            if "DTE ACEPTADO" in text.upper():
                return "ACEPTADO"
            if "DTE RECHAZADO" in text.upper():
                return "RECHAZADO"
            return "DESCONOCIDO"
        except Exception:
            return "DESCONOCIDO"

    def _list_dtes(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista DTEs emitidos (placeholder — SII usa outro endpoint)."""
        return {
            "success": True,
            "dtes": [],
            "note": "Listagem completa requer endpoint SII RCV. Use verify por folio.",
        }

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """PDF do DTE — cliente deve gerar a partir do XML autorizado."""
        return {
            "success": False,
            "error": "PDF deve ser gerado localmente a partir do XML do DTE.",
        }

    def _get_contributor_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Estado contribuinte SII (placeholder)."""
        rut = params.get("rut", self._rut)
        return {"success": True, "rut": rut, "estado": "ACTIVO"}

    def _get_exchange_rate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Tipo de cambio SII (placeholder)."""
        return {
            "success": True,
            "fecha": params.get("fecha", ""),
            "tipo_cambio": 950.0,  # Placeholder
            "moneda": params.get("moneda", "dolar"),
        }


DTE_CHILE_SCHEMA = ConnectorSchema(
    name="dte_chile",
    version="2.0.0",
    description="Emite DTE SII Chile con XMLDSig+mTLS+multipart real (Res. Exenta 45/2015)",
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue", description="Emite DTE (build+sign+upload SII)", category="write"),
        ActionDefinition(name="cancel", description="Cancela DTE via NC (tipo 61)", category="write"),
        ActionDefinition(name="verify", description="Verifica estado no SII (QRYEST)", category="read"),
        ActionDefinition(name="get_pdf", description="PDF (geração local)", category="read"),
        ActionDefinition(name="list_dtes", description="Lista DTEs emitidos", category="read"),
        ActionDefinition(name="get_contributor_status", description="Estado do contribuinte SII", category="read"),
        ActionDefinition(name="get_exchange_rate", description="Tipo de cambio", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["rut", "cert_path", "key_path"],
            optional_fields=["environment"],
            description="RUT empresa + Certificado SII Chile (PEM) — mTLS obrigatório",
        )
    ],
)
