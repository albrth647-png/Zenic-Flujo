"""SUNAT Peru Connector — Facturación Electrónica con crypto REAL.

Implementa la facturación electrónica de Perú según:
- RS SUNAT 097-2012/SUNAT (SEE — Sistema de Emisión Electrónica)
- RS SUNAT 318-2019/SUNAT (OSE — Operador de Servicios Electrónicos)
- RS SUNAT 300-2014/SUNAT (envío de resúmenes)
- DL 1333/2017 (factura electrónica obligatoria)
- TUO Ley IGV DS 055-99-EF (IGV 18% = 16% IGV + 2% IPM)
- ETSI TS 101 903 v1.4.1 (XAdES-BES)

Flujo:
1. Construir XML UBL 2.1 (Invoice para tipo 01/03; CreditNote/DebitNote para 07/08)
2. Firmar XAdES-BES sobre UBLExtensions/ExtensionContent/Signature
3. ZIP + base64 del XML firmado
4. SOAP sendBill (síncrono, factura/boleta individual) o sendSummary (asíncrono, lotes)
5. Recibir ApplicationResponse (CDR) con ResponseCode (0=aceptado, >0=rechazo)

Tipos soportados:
- 01 = Factura (serie F001)
- 03 = Boleta   (serie B001)
- 07 = Nota crédito (serie FC01/BC01)
- 08 = Nota débito  (serie FD01/BD01)

Códigos SUNAT → ZF-FISCAL-VAL-601-<code>.

Crypto REAL: signxml (XMLDSig enveloped) + lxml (XAdES QualifyingProperties)
+ cryptography (carga de PEM) + requests (mTLS).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from typing import Any

from lxml import etree

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.crypto.cert_loader import CertBundle, load_pem, load_pfx
from src.sdk.crypto.mtls_client import MTLSHttpClient
from src.sdk.crypto.xml_signer import sign_xml, verify_signature
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# Endpoints SUNAT SEE (SOAP + mTLS) y OSE configurable
SUNAT_ENDPOINTS: dict[str, str] = {
    "see_beta": "https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/betaService",
    "see_produccion": "https://www.sunat.gob.pe/ol-ti-itcpfegem/billService",
}

# Pesos módulo 11 SUNAT para DV de RUC — izquierda a derecha sobre 10 dígitos
SUNAT_RUC_WEIGHTS: tuple[int, ...] = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

# Tipos de comprobante SUNAT
SUNAT_DOC_TYPES: dict[str, str] = {
    "01": "Factura",
    "03": "Boleta de Venta",
    "07": "Nota de Crédito",
    "08": "Nota de Débito",
}

# Series válidas por tipo
SUNAT_SERIES_BY_TYPE: dict[str, tuple[str, ...]] = {
    "01": ("F",),
    "03": ("B",),
    "07": ("FC", "BC"),
    "08": ("FD", "BD"),
}

# IGV 18% = 16% IGV + 2% IPM (NO se desglosa en el XML)
SUNAT_IGV_RATE = 0.18

# Namespaces UBL 2.1 (Perú usa UBL 2.1 con extensión PE)
NSMAP_PE: dict[str, str] = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "CreditNote": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "DebitNote": "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sac": "urn:sunat:names:specification:ubl:peru:schema:xsd:SunatAggregateComponents-1",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xades": "http://uri.etsi.org/01903/v1.4.1#",
}


def _compute_ruc_dv(ruc_10: str) -> str:
    """Calcula el dígito de verificación (DV) de un RUC peruano.

    Algoritmo SUNAT: pesos [5,4,3,2,7,6,5,4,3,2] de izquierda a derecha
    sobre los primeros 10 dígitos del RUC, módulo 11.
    DV = 11 - (sum % 11). Si DV == 10 → 0; si DV == 11 → 1.
    """
    digits = [int(c) for c in ruc_10 if c.isdigit()][:10]
    if len(digits) < 10:
        return "0"
    weights = SUNAT_RUC_WEIGHTS
    total = sum(d * w for d, w in zip(digits, weights, strict=False))
    remainder = total % 11
    dv = 11 - remainder
    if dv == 10:
        return "0"
    if dv == 11:
        return "1"
    return str(dv)


def _xades_sunat_bes(signed_xml: bytes, cert_pem: bytes, signing_time: str) -> bytes:
    """Inyecta QualifyingProperties XAdES-BES en el nodo <ds:Signature>."""
    root = etree.fromstring(signed_xml)
    ns_ds = NSMAP_PE["ds"]
    ns_xades = NSMAP_PE["xades"]

    sig = root.find(f".//{{{ns_ds}}}Signature")
    if sig is None:
        return signed_xml

    cert_digest = base64.b64encode(hashlib.sha256(cert_pem).digest()).decode()

    obj = etree.SubElement(sig, f"{{{ns_ds}}}Object")
    qp = etree.SubElement(
        obj,
        f"{{{ns_xades}}}QualifyingProperties",
        Target="#" + (sig.get("Id") or "SignatureSUNAT"),
    )
    signed_props = etree.SubElement(qp, f"{{{ns_xades}}}SignedProperties")
    sig_sig_props = etree.SubElement(signed_props, f"{{{ns_xades}}}SignedSignatureProperties")
    etree.SubElement(sig_sig_props, f"{{{ns_xades}}}SigningTime").text = signing_time

    sig_cert = etree.SubElement(sig_sig_props, f"{{{ns_xades}}}SigningCertificate")
    cert_el = etree.SubElement(sig_cert, f"{{{ns_xades}}}Cert")
    cert_digest_el = etree.SubElement(cert_el, f"{{{ns_xades}}}CertDigest")
    etree.SubElement(
        cert_digest_el,
        f"{{{ns_ds}}}DigestMethod",
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256",
    )
    etree.SubElement(cert_digest_el, f"{{{ns_ds}}}DigestValue").text = cert_digest
    etree.SubElement(cert_el, f"{{{ns_xades}}}IssuerSerial")

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _zip_xml(xml_bytes: bytes, filename: str) -> bytes:
    """Comprime el XML en un ZIP en memoria (SUNAT exige ZIP del XML)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, xml_bytes)
    return buf.getvalue()


def _sub(parent: etree._Element, tag: str, text: str | None = None,
         **attrs: str) -> etree._Element:
    """Helper: SubElement with optional text content and attributes."""
    el = etree.SubElement(parent, tag, **{k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


class SUNATPeruConnector(BaseConnector):
    """Conector SUNAT Perú: UBL 2.1 + XAdES-BES + sendBill/sendSummary + CDR."""

    name = "sunat_peru"
    version = "1.0.0"
    description = (
        "Emite, consulta y gestiona comprobantes electrónicos SUNAT Perú "
        "(UBL 2.1 + XAdES-BES + sendBill/sendSummary + CDR)"
    )
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ruc: str = ""
        self._sol_user: str = ""
        self._sol_password: str = ""
        self._environment: str = "see_beta"
        self._ose_endpoint: str = ""
        self._cert_path: str = ""
        self._cert_password: str = ""
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._temp_files: list[str] = []

    # ── Ciclo de vida ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Carga certificado PEM e inicializa cliente mTLS a SUNAT/SEE/SEE-beta."""
        creds = self._get_creds()
        self._ruc = creds.get("nit_or_ruc", creds.get("ruc", self._ruc))
        self._sol_user = creds.get("sol_user", self._sol_user)
        self._sol_password = creds.get("sol_password", self._sol_password)
        self._environment = creds.get("environment", self._environment)
        self._ose_endpoint = creds.get("ose_endpoint", self._ose_endpoint)
        self._cert_path = creds.get("cert_path", self._cert_path)
        self._cert_password = creds.get("cert_password", self._cert_password)

        if not self._ruc or not self._cert_path:
            logger.error("SUNAT connect: ruc y cert_path son obligatorios")
            return False

        try:
            if self._cert_path.lower().endswith((".pfx", ".p12")):
                self._cert_bundle = load_pfx(self._cert_path, self._cert_password or "")
            else:
                key_path = creds.get("key_path", self._cert_path)
                self._cert_bundle = load_pem(
                    key_path, self._cert_path, password=self._cert_password or None
                )
        except Exception as e:
            logger.error("SUNAT connect: error cargando certificado: %s", e)
            return False

        if self._cert_bundle.is_expired:
            logger.warning("SUNAT connect: certificado expirado")

        self._write_temp_pems()
        try:
            self._mtls = MTLSHttpClient(
                cert_path=self._temp_files[0],
                key_path=self._temp_files[1],
                timeout=60,
                verify=False,
            )
        except Exception as e:
            logger.error("SUNAT connect: error inicializando mTLS: %s", e)
            return False

        self._connected = True
        self._log_operation("connect", f"RUC={self._ruc} env={self._environment}")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            "get_status": self._get_status,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Acción '{action}' no soportada",
                    "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        if not self._ruc or not self._cert_path:
            return False
        if len(self._ruc) != 11:
            return False
        return self._environment in ("see_beta", "see_produccion", "ose")

    def disconnect(self) -> bool:
        if self._mtls:
            self._mtls.close()
            self._mtls = None
        for tmp in self._temp_files:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
        self._temp_files = []
        self._cert_bundle = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    # ── Acciones ─────────────────────────────────────────────────────

    def _issue(self, params: dict[str, Any]) -> dict[str, Any]:
        """Emite comprobante: build XML → sign XAdES-BES → zip → sendBill."""
        if not self._connected and not self.connect():
            return {"success": False, "error": "Conector no conectado"}

        try:
            xml_bytes = self._build_xml_sunat(params)
            signed = self._sign(xml_bytes)
            doc_name = self._build_doc_name(params)
            zip_bytes = _zip_xml(signed, f"{doc_name}.xml")
            zip_b64 = base64.b64encode(zip_bytes).decode()
            soap_body = self._wrap_soap_sendbill(doc_name, zip_b64)
            endpoint = self._resolve_endpoint()
            response = self._send_soap(endpoint, soap_body)
            return self._parse_sendbill_response(response, signed, doc_name)
        except Exception as e:
            logger.exception("SUNAT issue falló")
            return {"success": False, "error": str(e),
                    "code": "ZF-FISCAL-VAL-601-999"}

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancelación SUNAT = nota crédito (tipo 07) que referencia la factura."""
        cancel_params = {
            **params,
            "doc_type": "07",
            "serie_prefix": params.get("cancel_serie_prefix", "FC"),
            "doc_number": params.get("cancel_doc_number", "00000001"),
            "ref_doc_type": params.get("ref_doc_type", "01"),
            "ref_serie": params.get("ref_serie", ""),
            "ref_number": params.get("ref_number", ""),
            "reason_code": params.get("reason_code", "01"),
        }
        return self._issue(cancel_params)

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta estado por ticket (sendSummary) o por documento (get_status)."""
        ticket = params.get("ticket", "")
        if ticket:
            return self._get_status({"ticket": ticket})
        doc_name = self._build_doc_name(params)
        soap = self._wrap_soap_getstatus_by_doc(doc_name)
        endpoint = self._resolve_endpoint()
        response = self._send_soap(endpoint, soap)
        return self._parse_status_response(response)

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """PDF lo entrega el OSE/AC; SUNAT directa no provee PDF."""
        return {"success": False, "error": "PDF vía OSE autorizado (no SUNAT directa)",
                "code": "ZF-FISCAL-VAL-601-801"}

    def _get_status(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta estado de un ticket sendSummary (asíncrono)."""
        ticket = params.get("ticket", "")
        if not ticket:
            return {"success": False, "error": "ticket requerido"}
        soap = self._wrap_soap_getstatus(ticket)
        endpoint = self._resolve_endpoint()
        response = self._send_soap(endpoint, soap)
        return self._parse_status_response(response)

    # ── Construcción XML UBL 2.1 ─────────────────────────────────────

    def _build_xml_sunat(self, params: dict[str, Any]) -> bytes:
        """Construye XML UBL 2.1 (Invoice/CreditNote/DebitNote) según tipo."""
        doc_type = params.get("doc_type", "01")
        serie = params.get("serie", self._default_serie(doc_type))
        doc_number = params.get("doc_number", "00000001")
        issue_date = params.get("issue_date", datetime.now(UTC).strftime("%Y-%m-%d"))
        currency = params.get("currency", "PEN")
        receiver_ruc = params.get("receiver_ruc", params.get("receiver_nit", ""))
        receiver_name = params.get("receiver_name", "")
        net_amount = str(params.get("net_amount", 0))
        tax_amount = str(params.get("tax_amount", 0))
        total_amount = str(params.get("total_amount", 0))

        ns_root_key = {
            "01": "Invoice",
            "03": "Invoice",
            "07": "CreditNote",
            "08": "DebitNote",
        }.get(doc_type, "Invoice")
        ns_root = NSMAP_PE[ns_root_key]
        ns_cbc = NSMAP_PE["cbc"]
        ns_cac = NSMAP_PE["cac"]
        ns_ext = NSMAP_PE["ext"]

        root = etree.Element(
            f"{{{ns_root}}}{ns_root_key}",
            nsmap={None: ns_root, "cbc": ns_cbc, "cac": ns_cac,
                   "ext": ns_ext, "sac": NSMAP_PE["sac"],
                   "ds": NSMAP_PE["ds"], "xades": NSMAP_PE["xades"]},
        )

        _sub(root, f"{{{ns_cbc}}}UBLVersionID", text="2.1")
        _sub(root, f"{{{ns_cbc}}}CustomizationID", text="2.0")
        _sub(root, f"{{{ns_cbc}}}ID", text=f"{serie}-{doc_number}")
        _sub(root, f"{{{ns_cbc}}}IssueDate", text=issue_date)
        _sub(root, f"{{{ns_cbc}}}DocumentCurrencyCode", text=currency)

        # UBLExtensions (placeholder firma)
        ext = _sub(root, f"{{{ns_ext}}}UBLExtensions")
        ext_one = _sub(ext, f"{{{ns_ext}}}UBLExtension")
        ext_content = _sub(ext_one, f"{{{ns_ext}}}ExtensionContent")
        ds_ns = NSMAP_PE["ds"]
        sig_placeholder = etree.SubElement(
            ext_content, f"{{{ds_ns}}}Signature", Id="SignatureSUNAT"
        )
        etree.SubElement(sig_placeholder, f"{{{ds_ns}}}SignedInfo")

        # DiscrepancyResponse para NC/ND
        if doc_type in ("07", "08"):
            disc = _sub(root, f"{{{ns_cac}}}DiscrepancyResponse")
            _sub(disc, f"{{{ns_cbc}}}ReferenceID",
                 text=f"{params.get('ref_serie', '')}-{params.get('ref_number', '')}")
            _sub(disc, f"{{{ns_cbc}}}ResponseCode", text=params.get("reason_code", "01"))
            _sub(disc, f"{{{ns_cbc}}}Description",
                 text=params.get("reason_desc", "Anulación de operación"))

        # BillingReference (NC/ND referencia documento original)
        if doc_type in ("07", "08"):
            bill_ref = _sub(root, f"{{{ns_cac}}}BillingReference")
            inv_doc_ref = _sub(bill_ref, f"{{{ns_cac}}}InvoiceDocumentReference")
            _sub(inv_doc_ref, f"{{{ns_cbc}}}ID",
                 text=f"{params.get('ref_serie', '')}-{params.get('ref_number', '')}")
            _sub(inv_doc_ref, f"{{{ns_cbc}}}DocumentTypeCode",
                 text=params.get("ref_doc_type", "01"))

        # Emisor (AccountingSupplierParty)
        supplier = _sub(root, f"{{{ns_cac}}}AccountingSupplierParty")
        supp_party = _sub(supplier, f"{{{ns_cac}}}Party")
        supp_id = _sub(supp_party, f"{{{ns_cac}}}PartyIdentification")
        _sub(supp_id, f"{{{ns_cbc}}}ID", text=self._ruc,
             schemeID="6", schemeName="RUC")
        supp_name = _sub(supp_party, f"{{{ns_cac}}}PartyName")
        _sub(supp_name, f"{{{ns_cbc}}}Name",
             text=params.get("emitter_name", "EMISOR SAC"))

        # Receptor (AccountingCustomerParty)
        customer = _sub(root, f"{{{ns_cac}}}AccountingCustomerParty")
        cust_party = _sub(customer, f"{{{ns_cac}}}Party")
        cust_id = _sub(cust_party, f"{{{ns_cac}}}PartyIdentification")
        _sub(cust_id, f"{{{ns_cbc}}}ID", text=receiver_ruc,
             schemeID="6" if len(receiver_ruc) == 11 else "1")
        cust_name = _sub(cust_party, f"{{{ns_cac}}}PartyName")
        _sub(cust_name, f"{{{ns_cbc}}}Name", text=receiver_name)

        # TaxTotal (IGV 18%)
        tax_total = _sub(root, f"{{{ns_cac}}}TaxTotal")
        _sub(tax_total, f"{{{ns_cbc}}}TaxAmount", text=tax_amount, currencyID=currency)
        tax_sub = _sub(tax_total, f"{{{ns_cac}}}TaxSubtotal")
        _sub(tax_sub, f"{{{ns_cbc}}}TaxableAmount", text=net_amount, currencyID=currency)
        _sub(tax_sub, f"{{{ns_cbc}}}TaxAmount", text=tax_amount, currencyID=currency)
        tax_cat = _sub(tax_sub, f"{{{ns_cac}}}TaxCategory")
        _sub(tax_cat, f"{{{ns_cbc}}}ID", text="S", schemeID="UN/ECE 5305")
        tax_scheme = _sub(tax_cat, f"{{{ns_cac}}}TaxScheme")
        _sub(tax_scheme, f"{{{ns_cbc}}}ID", text="1000", schemeID="UN/ECE 5153")
        _sub(tax_scheme, f"{{{ns_cbc}}}Name", text="IGV")

        # LegalMonetaryTotal
        legal = _sub(root, f"{{{ns_cac}}}LegalMonetaryTotal")
        _sub(legal, f"{{{ns_cbc}}}LineExtensionAmount", text=net_amount, currencyID=currency)
        _sub(legal, f"{{{ns_cbc}}}TaxInclusiveAmount",
             text=str(float(net_amount) + float(tax_amount)), currencyID=currency)
        _sub(legal, f"{{{ns_cbc}}}PayableAmount", text=total_amount, currencyID=currency)

        # InvoiceLine / CreditNoteLine / DebitNoteLine
        line_tag = ns_root_key.replace("Invoice", "InvoiceLine") \
                              .replace("CreditNote", "CreditNoteLine") \
                              .replace("DebitNote", "DebitNoteLine")
        for idx, item in enumerate(params.get("items", [{}]) or [{}], start=1):
            line = _sub(root, f"{{{ns_cac}}}{line_tag}")
            _sub(line, f"{{{ns_cbc}}}ID", text=str(idx))
            _sub(line, f"{{{ns_cbc}}}LineExtensionAmount",
                 text=str(item.get("amount", net_amount)), currencyID=currency)
            pricing = _sub(line, f"{{{ns_cac}}}PricingReference")
            alt_amt = _sub(pricing, f"{{{ns_cac}}}AlternativeConditionPrice")
            _sub(alt_amt, f"{{{ns_cbc}}}PriceAmount",
                 text=str(item.get("unit_price", total_amount)), currencyID=currency)
            _sub(alt_amt, f"{{{ns_cbc}}}PriceTypeCode", text="01")
            item_el = _sub(line, f"{{{ns_cac}}}Item")
            _sub(item_el, f"{{{ns_cbc}}}Description",
                 text=item.get("description", "Servicio"))
            price = _sub(line, f"{{{ns_cac}}}Price")
            _sub(price, f"{{{ns_cbc}}}PriceAmount",
                 text=str(item.get("unit_price", net_amount)), currencyID=currency)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _default_serie(self, doc_type: str) -> str:
        """Devuelve serie por defecto según tipo de documento."""
        prefixes = SUNAT_SERIES_BY_TYPE.get(doc_type, ("F",))
        return f"{prefixes[0]}001"

    def _build_doc_name(self, params: dict[str, Any]) -> str:
        """Nombre del documento: RUC-tipo-serie-numero."""
        doc_type = params.get("doc_type", "01")
        serie = params.get("serie", self._default_serie(doc_type))
        doc_number = params.get("doc_number", "00000001")
        return f"{self._ruc}-{doc_type}-{serie}-{doc_number}"

    # ── Firma XAdES-BES ──────────────────────────────────────────────

    def _sign(self, xml_bytes: bytes) -> bytes:
        """Firma XMLDSig enveloped + añade QualifyingProperties XAdES-BES."""
        if not self._cert_bundle:
            raise RuntimeError("Certificado no cargado — llame a connect() primero")
        signed = sign_xml(
            xml_bytes,
            self._cert_bundle.private_key_pem,
            self._cert_bundle.cert_pem,
            reference_uri="",
        )
        signing_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        signed = _xades_sunat_bes(signed, self._cert_bundle.cert_pem, signing_time)
        return signed

    # ── SOAP / mTLS ──────────────────────────────────────────────────

    def _resolve_endpoint(self) -> str:
        if self._environment == "ose" and self._ose_endpoint:
            return self._ose_endpoint
        return SUNAT_ENDPOINTS.get(self._environment, SUNAT_ENDPOINTS["see_beta"])

    def _send_soap(self, endpoint: str, soap_body: bytes) -> bytes:
        if not self._mtls:
            raise RuntimeError("mTLS no inicializado — llame a connect() primero")
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": "",
            "User-Agent": "Zenic-Flujo/1.0",
        }
        kwargs: dict[str, Any] = {"headers": headers}
        if self._sol_user and self._sol_password:
            sol_user = f"{self._ruc}{self._sol_user}"
            kwargs["auth"] = (sol_user, self._sol_password)
        response = self._mtls.post(endpoint, data=soap_body, **kwargs)
        return response.content

    def _wrap_soap_sendbill(self, doc_name: str, zip_b64: str) -> bytes:
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://service.gem.sunat.gob.pe">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:sendBill>
      <fileName>{doc_name}.zip</fileName>
      <contentFile>{zip_b64}</contentFile>
    </ser:sendBill>
  </soapenv:Body>
</soapenv:Envelope>"""
        return soap.encode()

    def _wrap_soap_getstatus(self, ticket: str) -> bytes:
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://service.gem.sunat.gob.pe">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:getStatus>
      <ticket>{ticket}</ticket>
    </ser:getStatus>
  </soapenv:Body>
</soapenv:Envelope>"""
        return soap.encode()

    def _wrap_soap_getstatus_by_doc(self, doc_name: str) -> bytes:
        parts = doc_name.split("-")
        doc_type = parts[1] if len(parts) > 1 else "01"
        serie = parts[2] if len(parts) > 2 else "F001"
        number = parts[3] if len(parts) > 3 else "1"
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://service.gem.sunat.gob.pe">
  <soapenv:Header/>
  <soapenv:Body>
    <ser:getStatusCdr>
      <rucComprobante>{self._ruc}</rucComprobante>
      <tipoComprobante>{doc_type}</tipoComprobante>
      <serieComprobante>{serie}</serieComprobante>
      <numeroComprobante>{number}</numeroComprobante>
    </ser:getStatusCdr>
  </soapenv:Body>
</soapenv:Envelope>"""
        return soap.encode()

    # ── Parseo respuestas ────────────────────────────────────────────

    def _parse_sendbill_response(self, response: bytes, signed_xml: bytes,
                                 doc_name: str) -> dict[str, Any]:
        """Extrae ApplicationResponse (CDR) y ResponseCode."""
        try:
            root = etree.fromstring(response)
            cdr_b64 = self._xpath_text(root, ".//*[local-name()='applicationResponse']") \
                or self._xpath_text(root, ".//*[local-name()='content']")
            code = self._xpath_text(root, ".//*[local-name()='responseCode']") \
                or self._xpath_text(root, ".//*[local-name()='ResponseCode']")
            desc = self._xpath_text(root, ".//*[local-name()='description']") \
                or self._xpath_text(root, ".//*[local-name()='StatusMessage']") or ""
        except etree.XMLSyntaxError:
            cdr_b64, code, desc = "", "9999", "Respuesta no es XML"

        accepted = code == "0"
        cdr_bytes = b""
        if cdr_b64:
            with contextlib.suppress(Exception):
                cdr_bytes = base64.b64decode(cdr_b64)

        return {
            "success": accepted,
            "cdr": base64.b64encode(cdr_bytes).decode() if cdr_bytes else "",
            "response_code": code,
            "description": desc,
            "doc_name": doc_name,
            "xml": signed_xml.decode("utf-8", errors="replace"),
            "code": "ZF-FISCAL-VAL-601-200" if accepted else f"ZF-FISCAL-VAL-601-{code}",
        }

    def _parse_status_response(self, response: bytes) -> dict[str, Any]:
        try:
            root = etree.fromstring(response)
            status = self._xpath_text(root, ".//*[local-name()='statusCode']") \
                or self._xpath_text(root, ".//*[local-name()='Status']") or ""
            msg = self._xpath_text(root, ".//*[local-name()='content']") or ""
            cdr_b64 = self._xpath_text(root, ".//*[local-name()='cdr']") or ""
        except etree.XMLSyntaxError:
            status, msg, cdr_b64 = "9999", "Respuesta no es XML", ""

        accepted = status == "0"
        return {
            "success": accepted,
            "status": status,
            "message": msg,
            "cdr": cdr_b64,
            "code": "ZF-FISCAL-VAL-601-200" if accepted else f"ZF-FISCAL-VAL-601-{status}",
        }

    # ── Helpers internos ─────────────────────────────────────────────

    def _get_creds(self) -> dict[str, Any]:
        creds: dict[str, Any] = {}
        if self._auth_provider and hasattr(self._auth_provider, "get_credentials"):
            try:
                creds = self._auth_provider.get_credentials() or {}
            except Exception:
                creds = {}
        return creds

    def _write_temp_pems(self) -> None:
        if not self._cert_bundle:
            raise RuntimeError("Bundle no cargado")
        with tempfile.NamedTemporaryFile(delete=False, suffix="_sunat_cert.pem") as cert_f:
            cert_f.write(self._cert_bundle.cert_pem)
            cert_tmp = cert_f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix="_sunat_key.pem") as key_f:
            key_f.write(self._cert_bundle.private_key_pem)
            key_tmp = key_f.name
        self._temp_files = [cert_tmp, key_tmp]

    @staticmethod
    def _xpath_text(root: etree._Element, path: str) -> str:
        """Busca texto via XPath (soporta local-name() y otros predicados)."""
        nodes = root.xpath(path)
        if not nodes:
            return ""
        node = nodes[0]
        if hasattr(node, "text"):
            return (node.text or "").strip()
        return str(node).strip()

    def _verify_signature(self, signed_xml: bytes) -> bool:
        cert = self._cert_bundle.cert_pem if self._cert_bundle else None
        return verify_signature(signed_xml, cert_pem=cert)


# ── Schema del conector ──────────────────────────────────────────────

SUNAT_PERU_SCHEMA = ConnectorSchema(
    name="sunat_peru",
    version="1.0.0",
    description=(
        "Emite, consulta y gestiona comprobantes electrónicos SUNAT Perú "
        "(UBL 2.1 + XAdES-BES + sendBill/sendSummary + CDR)"
    ),
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue", description="Emite comprobante SUNAT (sendBill)",
                         category="write"),
        ActionDefinition(name="cancel", description="Emite nota crédito (tipo 07)",
                         category="write"),
        ActionDefinition(name="verify", description="Verifica estado por ticket/doc",
                         category="read"),
        ActionDefinition(name="get_pdf", description="Obtiene PDF (vía OSE)",
                         category="read"),
        ActionDefinition(name="get_status", description="Consulta ticket sendSummary",
                         category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["nit_or_ruc", "cert_path", "cert_password", "environment"],
            optional_fields=["sol_user", "sol_password", "ose_endpoint", "key_path"],
            description="RUC + certificado digital PEM + ambiente SUNAT (see_beta/see_produccion/ose)",
        ),
    ],
)
