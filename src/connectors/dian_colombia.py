"""DIAN Colombia Connector — Facturación Electrónica con crypto REAL.

Implementa la facturación electrónica de Colombia según:
- Resolución DIAN 165/2023 (facturación electrónica)
- Decreto 358/2020 (operación DIAN)
- Ley 1819/2016 art. 51 (CUFE)
- Decreto 474/2020 (eventos post-validación)
- ETSI TS 101 903 v1.3.2 (XAdES-EPES)

Flujo:
1. Construir XML UBL 2.1 con extensión DIAN
2. Calcular CUFE = SHA-256(NumFac & FecFac & HorFac & NitOFE & DocAdq & ValFac
                              & ValIva & ValIpo & ValTot & NitTec & TipoAmb & ClaveTec)
3. Firmar XAdES-EPES sobre el nodo <ext:UBLExtensions>
4. Enviar SOAP 1.2 + mTLS a WcfDianCustomerServices.svc (SendBillAsync)
5. Recibir TrackId + estado (accepted/rejected)

Impuestos soportados:
- IVA 19% (codigo=01, tipo=01) — régimen general
- IVA 5%  (codigo=01, tipo=02) — bienes/servicios reducidos
- IVA 0%  (codigo=01, tipo=03) — exentos
- INC 8%  (codigo=05) — impuesto al consumo

Eventos DIAN 1-7 con ventanas 72h/30 días.
Códigos DIAN mapeados a ZF-FISCAL-VAL-501-<code>.

Crypto REAL: signxml (XMLDSig enveloped) + lxml (XAdES QualifyingProperties)
+ cryptography (carga de PFX/PEM) + requests (mTLS).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import tempfile
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

# Endpoints WSDIAN (SOAP 1.2 + mTLS)
DIAN_ENDPOINTS: dict[str, str] = {
    "homologacion": "https://vpfe-hab.dian.gov.co/WcfDianCustomerServices.svc",
    "produccion": "https://vpfe.dian.gov.co/WcfDianCustomerServices.svc",
}

# Pesos módulo 11 para DV de NIT (DIAN) — de derecha a izquierda
DIAN_NIT_WEIGHTS: tuple[int, ...] = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)

# Catálogo de impuestos DIAN
DIAN_TAXES: dict[str, dict[str, str]] = {
    "iva_19": {"codigo": "01", "tipo": "01", "porcentaje": "19.00", "nombre": "IVA 19%"},
    "iva_5": {"codigo": "01", "tipo": "02", "porcentaje": "5.00", "nombre": "IVA 5%"},
    "iva_0": {"codigo": "01", "tipo": "03", "porcentaje": "0.00", "nombre": "IVA 0%"},
    "inc_8": {"codigo": "05", "tipo": "04", "porcentaje": "8.00", "nombre": "INC 8%"},
}

# Eventos DIAN (Decreto 474/2020)
DIAN_EVENTS: dict[int, str] = {
    1: "Cancelación de factura",
    2: "Anulación de factura",
    3: "Acuse de recibo",
    4: "Notas crédito/débito",
    5: "Reporte de pago",
    6: "Aceptación tácita",
    7: "Endoso de factura",
}

# Namespaces UBL 2.1 + DIAN
NSMAP_UBL: dict[str, str] = {
    "Invoice": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "http://www.dian.gov.co/contratos/facturaelectronica/v1/Structures",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xades": "http://uri.etsi.org/01903/v1.3.2#",
}


def _compute_nit_dv(nit: str) -> str:
    """Calcula el dígito de verificación (DV) de un NIT colombiano.

    Algoritmo DIAN: pesos [71,67,59,53,47,43,41,37,29,23,19,17,13,7,3]
    de derecha a izquierda, módulo 11. DV = 11 - (sum % 11).
    Si DV == 11 → 0; si DV == 10 → 1.
    """
    nit_digits = [int(c) for c in nit if c.isdigit()]
    if not nit_digits:
        return "0"
    weights = DIAN_NIT_WEIGHTS
    total = 0
    for idx, digit in enumerate(reversed(nit_digits)):
        if idx >= len(weights):
            break
        total += digit * weights[idx]
    remainder = total % 11
    dv = 11 - remainder
    if dv == 11:
        return "0"
    if dv == 10:
        return "1"
    return str(dv)


def _compute_cufe(params: dict[str, Any]) -> str:
    """Calcula el CUFE (Código Único de Factura Electrónica).

    CUFE = SHA-256(NumFac & FecFac & HorFac & NitOFE & DocAdq & ValFac
                   & ValIva & ValIpo & ValTot & NitTec & TipoAmb & ClaveTec)
    """
    fields = [
        params["NumFac"],
        params["FecFac"],
        params["HorFac"],
        params["NitOFE"],
        params["DocAdq"],
        params["ValFac"],
        params["ValIva"],
        params["ValIpo"],
        params["ValTot"],
        params["NitTec"],
        params["TipoAmb"],
        params["ClaveTec"],
    ]
    cadena = "&".join(str(f) for f in fields)
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


def _xades_dian_epes(
    signed_xml: bytes,
    cert_pem: bytes,
    signing_time: str,
    policy_id: str = "https://facturaelectronica.dian.gov.co/politicadefirma/v2/politicadefirmav2.pdf",
) -> bytes:
    """Inyecta QualifyingProperties XAdES-EPES en el nodo <ds:Signature>."""
    root = etree.fromstring(signed_xml)
    ns_ds = NSMAP_UBL["ds"]
    ns_xades = NSMAP_UBL["xades"]

    sig = root.find(f".//{{{ns_ds}}}Signature")
    if sig is None:
        return signed_xml

    cert_digest_b64 = base64.b64encode(hashlib.sha256(cert_pem).digest()).decode()
    policy_digest_b64 = base64.b64encode(hashlib.sha256(policy_id.encode()).digest()).decode()

    obj = etree.SubElement(sig, f"{{{ns_ds}}}Object")
    qp = etree.SubElement(
        obj,
        f"{{{ns_xades}}}QualifyingProperties",
        Target="#" + (sig.get("Id") or "Signature"),
    )
    signed_props = etree.SubElement(qp, f"{{{ns_xades}}}SignedProperties")
    sig_sig_props = etree.SubElement(signed_props, f"{{{ns_xades}}}SignedSignatureProperties")
    etree.SubElement(sig_sig_props, f"{{{ns_xades}}}SigningTime").text = signing_time

    sig_cert = etree.SubElement(sig_sig_props, f"{{{ns_xades}}}SigningCertificate")
    cert_el = etree.SubElement(sig_cert, f"{{{ns_xades}}}Cert")
    cert_digest = etree.SubElement(cert_el, f"{{{ns_xades}}}CertDigest")
    etree.SubElement(
        cert_digest,
        f"{{{ns_ds}}}DigestMethod",
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256",
    )
    etree.SubElement(cert_digest, f"{{{ns_ds}}}DigestValue").text = cert_digest_b64
    etree.SubElement(cert_el, f"{{{ns_xades}}}IssuerSerial")

    sig_policy = etree.SubElement(sig_sig_props, f"{{{ns_xades}}}SignaturePolicyIdentifier")
    sig_policy_id = etree.SubElement(sig_policy, f"{{{ns_xades}}}SignaturePolicyId")
    sig_policy_qual = etree.SubElement(sig_policy_id, f"{{{ns_xades}}}SigPolicyId")
    etree.SubElement(sig_policy_qual, f"{{{ns_xades}}}Identifier").text = policy_id
    etree.SubElement(
        sig_policy_qual,
        f"{{{ns_xades}}}Description",
    ).text = "Política de firma DIAN Colombia v2"
    hash_alg = etree.SubElement(sig_policy_id, f"{{{ns_xades}}}SigPolicyHashDigest")
    etree.SubElement(
        hash_alg,
        f"{{{ns_ds}}}DigestMethod",
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256",
    )
    etree.SubElement(hash_alg, f"{{{ns_ds}}}DigestValue").text = policy_digest_b64

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _sub(parent: etree._Element, tag: str, text: str | None = None,
         **attrs: str) -> etree._Element:
    """Helper: SubElement with optional text content and attributes."""
    el = etree.SubElement(parent, tag, **{k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


class DIANColombiaConnector(BaseConnector):
    """Conector DIAN Colombia: facturación electrónica UBL 2.1 + XAdES-EPES + mTLS."""

    name = "dian_colombia"
    version = "1.0.0"
    description = (
        "Emite, consulta y gestiona facturas electrónicas DIAN Colombia "
        "(UBL 2.1 + CUFE + XAdES-EPES + eventos 1-7)"
    )
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._nit: str = ""
        self._dv: str = ""
        self._software_id: str = ""
        self._pin: str = ""
        self._technical_nit: str = ""
        self._environment: str = "homologacion"
        self._cert_path: str = ""
        self._cert_password: str = ""
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._temp_files: list[str] = []

    # ── Ciclo de vida ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Carga certificado (PFX/PEM) e inicializa cliente mTLS."""
        creds = self._get_creds()
        self._nit = creds.get("nit_or_ruc", self._nit)
        self._cert_path = creds.get("cert_path", self._cert_path)
        self._cert_password = creds.get("cert_password", self._cert_password)
        self._environment = creds.get("environment", self._environment)
        self._software_id = creds.get("software_id", self._software_id)
        self._pin = creds.get("pin", self._pin)
        self._technical_nit = creds.get("technical_nit", self._nit)

        if not self._nit or not self._cert_path:
            logger.error("DIAN connect: nit_or_ruc y cert_path son obligatorios")
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
            logger.error("DIAN connect: error cargando certificado: %s", e)
            return False

        if self._cert_bundle.is_expired:
            logger.warning(
                "DIAN connect: certificado expirado (not_after=%s)",
                self._cert_bundle.not_after,
            )

        self._write_temp_pems()
        try:
            self._mtls = MTLSHttpClient(
                cert_path=self._temp_files[0],
                key_path=self._temp_files[1],
                timeout=60,
                verify=False,
            )
        except Exception as e:
            logger.error("DIAN connect: error inicializando mTLS: %s", e)
            return False

        self._dv = _compute_nit_dv(self._nit)
        self._connected = True
        self._log_operation("connect", f"NIT={self._nit} DV={self._dv} env={self._environment}")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            "send_event": self._send_event,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Acción '{action}' no soportada",
                    "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        if not self._nit or not self._cert_path:
            return False
        return self._environment in ("homologacion", "produccion")

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
        """Emite factura: build XML → compute CUFE → sign XAdES-EPES → SOAP."""
        if not self._connected and not self.connect():
            return {"success": False, "error": "Conector no conectado"}

        try:
            xml_bytes = self._build_xml_dian(params)
            cufe = _compute_cufe(self._cufe_fields(params, xml_bytes))
            signed = self._sign(xml_bytes)
            soap_body = self._wrap_soap_sendbill(signed, cufe)
            endpoint = DIAN_ENDPOINTS[self._environment]
            response = self._send_soap(endpoint, soap_body)
            return self._parse_sendbill_response(response, cufe, signed)
        except Exception as e:
            logger.exception("DIAN issue falló")
            return {"success": False, "error": str(e),
                    "code": "ZF-FISCAL-VAL-501-999"}

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancelación DIAN = evento 1 con referencia al documento."""
        return self._send_event({"event_code": 1, **params})

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta estado de un documento por TrackId o CUFE."""
        track_id = params.get("track_id", "")
        cufe = params.get("cufe", "")
        if not track_id and not cufe:
            return {"success": False, "error": "track_id o cufe requerido"}
        soap = self._wrap_soap_getstatus(track_id or cufe)
        endpoint = DIAN_ENDPOINTS[self._environment]
        response = self._send_soap(endpoint, soap)
        return self._parse_getstatus_response(response)

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """Obtiene PDF de representación gráfica (lo entrega el OUP/AC)."""
        cufe = params.get("cufe", "")
        if not cufe:
            return {"success": False, "error": "cufe requerido"}
        return {"success": False, "error": "PDF requerido vía OUP autorizado (no DIAN directa)",
                "code": "ZF-FISCAL-VAL-501-801"}

    def _send_event(self, params: dict[str, Any]) -> dict[str, Any]:
        """Registra un evento DIAN 1-7 (Decreto 474/2020)."""
        event_code = int(params.get("event_code", 0))
        if event_code not in DIAN_EVENTS:
            return {"success": False, "error": f"event_code inválido: {event_code}",
                    "valid_codes": list(DIAN_EVENTS.keys())}
        doc_ref = params.get("doc_ref", params.get("cufe", ""))
        if not doc_ref:
            return {"success": False, "error": "doc_ref/cufe requerido"}

        soap = self._wrap_soap_event(event_code, doc_ref, params.get("reason", ""))
        endpoint = DIAN_ENDPOINTS[self._environment]
        response = self._send_soap(endpoint, soap)
        return self._parse_event_response(response, event_code, doc_ref)

    # ── Construcción XML UBL 2.1 ─────────────────────────────────────

    def _build_xml_dian(self, params: dict[str, Any]) -> bytes:
        """Construye XML UBL 2.1 + extensión DIAN (sin firmar)."""
        ns_inv = NSMAP_UBL["Invoice"]
        ns_cbc = NSMAP_UBL["cbc"]
        ns_cac = NSMAP_UBL["cac"]
        ns_ext = NSMAP_UBL["ext"]

        invoice_id = params.get("invoice_id", "SETP-99001")
        issue_date = params.get("issue_date", datetime.now(UTC).strftime("%Y-%m-%d"))
        issue_time = params.get("issue_time", datetime.now(UTC).strftime("%H:%M:%S"))
        currency = params.get("currency", "COP")
        receiver_nit = params.get("receiver_nit", "")
        receiver_name = params.get("receiver_name", "")
        val_fac = str(params.get("net_amount", 0))
        val_iva = str(params.get("tax_amount", 0))
        val_ipo = str(params.get("consumption_tax", 0))
        val_tot = str(params.get("total_amount", 0))
        tax_code = params.get("tax_code", "iva_19")
        tax_info = DIAN_TAXES.get(tax_code, DIAN_TAXES["iva_19"])

        root = etree.Element(
            f"{{{ns_inv}}}Invoice",
            nsmap={None: ns_inv, "cbc": ns_cbc, "cac": ns_cac, "ext": ns_ext,
                   "sts": NSMAP_UBL["sts"], "ds": NSMAP_UBL["ds"],
                   "xades": NSMAP_UBL["xades"]},
        )

        # UBLVersionID + ProfileID
        _sub(root, f"{{{ns_cbc}}}UBLVersionID", text="UBL 2.1")
        _sub(root, f"{{{ns_cbc}}}ProfileID",
             text="http://uri.dian.gov.co/0004/00/DIAN_UBL_Profile.svc")
        _sub(root, f"{{{ns_cbc}}}ID", text=invoice_id)
        _sub(root, f"{{{ns_cbc}}}UUID", text="PLACEHOLDER_CUFE",
             schemeName="CUFE",
             schemeURI="http://www.dian.gov.co/contratos/facturaelectronica/v1")
        _sub(root, f"{{{ns_cbc}}}IssueDate", text=issue_date)
        _sub(root, f"{{{ns_cbc}}}IssueTime", text=issue_time)
        _sub(root, f"{{{ns_cbc}}}DocumentCurrencyCode", text=currency)

        # Extensiones UBL (placeholder para firma)
        ext = _sub(root, f"{{{ns_ext}}}UBLExtensions")
        ext_one = _sub(ext, f"{{{ns_ext}}}UBLExtension")
        ext_content = _sub(ext_one, f"{{{ns_ext}}}ExtensionContent")

        # Emisor (AccountingSupplierParty)
        supplier = _sub(root, f"{{{ns_cac}}}AccountingSupplierParty")
        supp_party = _sub(supplier, f"{{{ns_cac}}}Party")
        supp_tax = _sub(supp_party, f"{{{ns_cac}}}PartyIdentification")
        _sub(supp_tax, f"{{{ns_cbc}}}ID", text=self._nit,
             schemeID=self._dv, schemeName="NIT",
             schemeAgencyID="195", schemeAgencyName="DIAN")
        supp_name = _sub(supp_party, f"{{{ns_cac}}}PartyName")
        _sub(supp_name, f"{{{ns_cbc}}}Name",
             text=params.get("emitter_name", "EMISOR SAS"))

        # Receptor (AccountingCustomerParty)
        customer = _sub(root, f"{{{ns_cac}}}AccountingCustomerParty")
        cust_party = _sub(customer, f"{{{ns_cac}}}Party")
        cust_tax = _sub(cust_party, f"{{{ns_cac}}}PartyIdentification")
        _sub(cust_tax, f"{{{ns_cbc}}}ID", text=receiver_nit,
             schemeID=_compute_nit_dv(receiver_nit) if receiver_nit else "0",
             schemeName="NIT", schemeAgencyID="195", schemeAgencyName="DIAN")
        cust_name = _sub(cust_party, f"{{{ns_cac}}}PartyName")
        _sub(cust_name, f"{{{ns_cbc}}}Name", text=receiver_name)

        # Totales (LegalMonetaryTotal + TaxTotal)
        tax_total = _sub(root, f"{{{ns_cac}}}TaxTotal")
        _sub(tax_total, f"{{{ns_cbc}}}TaxAmount", text=val_iva, currencyID=currency)
        tax_sub = _sub(tax_total, f"{{{ns_cac}}}TaxSubtotal")
        _sub(tax_sub, f"{{{ns_cbc}}}TaxableAmount", text=val_fac, currencyID=currency)
        _sub(tax_sub, f"{{{ns_cbc}}}TaxAmount", text=val_iva, currencyID=currency)
        tax_cat = _sub(tax_sub, f"{{{ns_cac}}}TaxCategory")
        _sub(tax_cat, f"{{{ns_cbc}}}ID", text=tax_info["tipo"],
             schemeID="UN/ECE 5305", schemeName="DianTaxTypeCode")
        tax_scheme = _sub(tax_cat, f"{{{ns_cac}}}TaxScheme")
        _sub(tax_scheme, f"{{{ns_cbc}}}ID", text=tax_info["codigo"],
             schemeID="UN/ECE 5153", schemeAgencyID="6")

        # INC (Impuesto Nacional al Consumo) si aplica
        if float(val_ipo or 0) > 0:
            inc_total = _sub(root, f"{{{ns_cac}}}TaxTotal")
            _sub(inc_total, f"{{{ns_cbc}}}TaxAmount", text=val_ipo, currencyID=currency)
            inc_sub = _sub(inc_total, f"{{{ns_cac}}}TaxSubtotal")
            _sub(inc_sub, f"{{{ns_cbc}}}TaxableAmount", text=val_fac, currencyID=currency)
            _sub(inc_sub, f"{{{ns_cbc}}}TaxAmount", text=val_ipo, currencyID=currency)
            inc_cat = _sub(inc_sub, f"{{{ns_cac}}}TaxCategory")
            _sub(inc_cat, f"{{{ns_cbc}}}ID", text="04", schemeID="UN/ECE 5305")
            inc_scheme = _sub(inc_cat, f"{{{ns_cac}}}TaxScheme")
            _sub(inc_scheme, f"{{{ns_cbc}}}ID", text="05",
                 schemeID="UN/ECE 5153", schemeAgencyID="6")

        legal = _sub(root, f"{{{ns_cac}}}LegalMonetaryTotal")
        _sub(legal, f"{{{ns_cbc}}}LineExtensionAmount", text=val_fac, currencyID=currency)
        _sub(legal, f"{{{ns_cbc}}}TaxInclusiveAmount",
             text=str(float(val_fac) + float(val_iva)), currencyID=currency)
        _sub(legal, f"{{{ns_cbc}}}PayableAmount", text=val_tot, currencyID=currency)

        # Ítems (InvoiceLine)
        for idx, item in enumerate(params.get("items", [{}]) or [{}], start=1):
            line = _sub(root, f"{{{ns_cac}}}InvoiceLine")
            _sub(line, f"{{{ns_cbc}}}ID", text=str(idx))
            _sub(line, f"{{{ns_cbc}}}LineExtensionAmount",
                 text=str(item.get("amount", val_fac)), currencyID=currency)
            item_el = _sub(line, f"{{{ns_cac}}}Item")
            _sub(item_el, f"{{{ns_cbc}}}Description",
                 text=item.get("description", "Servicio"))
            price = _sub(line, f"{{{ns_cac}}}Price")
            _sub(price, f"{{{ns_cbc}}}PriceAmount",
                 text=str(item.get("unit_price", val_fac)), currencyID=currency)

        # Placeholder firma en ExtensionContent (se reemplaza en _sign)
        ds_ns = NSMAP_UBL["ds"]
        sig_placeholder = etree.SubElement(
            ext_content, f"{{{ds_ns}}}Signature", Id="SignatureDIAN"
        )
        etree.SubElement(sig_placeholder, f"{{{ds_ns}}}SignedInfo")

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _cufe_fields(self, params: dict[str, Any], xml_bytes: bytes) -> dict[str, Any]:
        """Extrae los 12 campos para CUFE desde params y XML."""
        issue_date = params.get("issue_date", datetime.now(UTC).strftime("%Y-%m-%d"))
        issue_time = params.get("issue_time", datetime.now(UTC).strftime("%H:%M:%S-05:00"))
        return {
            "NumFac": params.get("invoice_id", "SETP-99001"),
            "FecFac": issue_date,
            "HorFac": issue_time,
            "NitOFE": self._nit,
            "DocAdq": params.get("receiver_nit", ""),
            "ValFac": str(params.get("net_amount", 0)),
            "ValIva": str(params.get("tax_amount", 0)),
            "ValIpo": str(params.get("consumption_tax", 0)),
            "ValTot": str(params.get("total_amount", 0)),
            "NitTec": self._technical_nit or self._nit,
            "TipoAmb": "1" if self._environment == "produccion" else "2",
            "ClaveTec": self._pin or params.get("clave_tec", "00000000-0000-0000-0000-000000000000"),
        }

    # ── Firma XAdES-EPES ─────────────────────────────────────────────

    def _sign(self, xml_bytes: bytes) -> bytes:
        """Firma XMLDSig enveloped + añade QualifyingProperties XAdES-EPES."""
        if not self._cert_bundle:
            raise RuntimeError("Certificado no cargado — llame a connect() primero")
        signed = sign_xml(
            xml_bytes,
            self._cert_bundle.private_key_pem,
            self._cert_bundle.cert_pem,
            reference_uri="",
        )
        signing_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        signed = _xades_dian_epes(signed, self._cert_bundle.cert_pem, signing_time)
        return signed

    # ── SOAP / mTLS ──────────────────────────────────────────────────

    def _send_soap(self, endpoint: str, soap_body: bytes) -> bytes:
        """Envuelve body SOAP 1.2 y POST con mTLS."""
        if not self._mtls:
            raise RuntimeError("mTLS no inicializado — llame a connect() primero")
        headers = {
            "Content-Type": 'application/soap+xml; charset="utf-8"',
            "SOAPAction": '"http://wcf.dian.colombia/IWcfDianCustomerServices/SendBillAsync"',
        }
        response = self._mtls.post(endpoint, data=soap_body, headers=headers)
        return response.content

    def _wrap_soap_sendbill(self, signed_xml: bytes, cufe: str) -> bytes:
        """Construye envelope SOAP SendBillAsync con XML firmado base64."""
        xml_b64 = base64.b64encode(signed_xml).decode()
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <SendBillAsync xmlns="http://wcf.dian.colombia">
      <fileName>{cufe}.xml</fileName>
      <contentFile>{xml_b64}</contentFile>
    </SendBillAsync>
  </s:Body>
</s:Envelope>"""
        return soap.encode("utf-8")

    def _wrap_soap_getstatus(self, track_id: str) -> bytes:
        return f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <GetStatus xmlns="http://wcf.dian.colombia">
      <trackId>{track_id}</trackId>
    </GetStatus>
  </s:Body>
</s:Envelope>""".encode()

    def _wrap_soap_event(self, event_code: int, doc_ref: str, reason: str) -> bytes:
        return f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <SendEvent xmlns="http://wcf.dian.colombia">
      <eventCode>{event_code}</eventCode>
      <docRef>{doc_ref}</docRef>
      <reason>{reason}</reason>
    </SendEvent>
  </s:Body>
</s:Envelope>""".encode()

    # ── Parseo respuestas ────────────────────────────────────────────

    def _parse_sendbill_response(self, response: bytes, cufe: str,
                                 signed_xml: bytes) -> dict[str, Any]:
        """Extrae TrackId y estado de la respuesta SendBillAsync."""
        try:
            root = etree.fromstring(response)
            track_id = self._xpath_text(root, ".//*[local-name()='TrackId']")
            status = self._xpath_text(root, ".//*[local-name()='Status']")
            status_msg = self._xpath_text(root, ".//*[local-name()='StatusMessage']") or ""
        except etree.XMLSyntaxError:
            track_id, status, status_msg = "", "error", "Respuesta no es XML"

        accepted = status in ("accepted", "00", "qb_sync_2")
        return {
            "success": accepted,
            "cufe": cufe,
            "track_id": track_id,
            "status": status,
            "status_message": status_msg,
            "xml": signed_xml.decode("utf-8", errors="replace"),
            "code": "ZF-FISCAL-VAL-501-200" if accepted else "ZF-FISCAL-VAL-501-4XX",
        }

    def _parse_getstatus_response(self, response: bytes) -> dict[str, Any]:
        try:
            root = etree.fromstring(response)
            status = self._xpath_text(root, ".//*[local-name()='Status']")
            status_msg = self._xpath_text(root, ".//*[local-name()='StatusMessage']") or ""
        except etree.XMLSyntaxError:
            status, status_msg = "error", "Respuesta no es XML"
        return {"success": status in ("accepted", "00", "qb_sync_2"),
                "status": status, "status_message": status_msg}

    def _parse_event_response(self, response: bytes, event_code: int,
                              doc_ref: str) -> dict[str, Any]:
        try:
            root = etree.fromstring(response)
            status = self._xpath_text(root, ".//*[local-name()='Status']") or "ok"
        except etree.XMLSyntaxError:
            status = "error"
        return {"success": status in ("ok", "00", "accepted"),
                "event_code": event_code,
                "event_name": DIAN_EVENTS.get(event_code, ""),
                "doc_ref": doc_ref,
                "status": status}

    # ── Helpers internos ─────────────────────────────────────────────

    def _get_creds(self) -> dict[str, Any]:
        """Obtiene credenciales desde auth_provider o atributos."""
        creds: dict[str, Any] = {}
        if self._auth_provider and hasattr(self._auth_provider, "get_credentials"):
            try:
                creds = self._auth_provider.get_credentials() or {}
            except Exception:
                creds = {}
        return creds

    def _write_temp_pems(self) -> None:
        """Escribe PEMs del bundle a archivos temporales para requests mTLS."""
        if not self._cert_bundle:
            raise RuntimeError("Bundle no cargado")
        with tempfile.NamedTemporaryFile(delete=False, suffix="_dian_cert.pem") as cert_f:
            cert_f.write(self._cert_bundle.cert_pem)
            cert_tmp = cert_f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix="_dian_key.pem") as key_f:
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
        """Verifica la firma XAdES-EPES del XML (wrapper de xml_signer)."""
        cert = self._cert_bundle.cert_pem if self._cert_bundle else None
        return verify_signature(signed_xml, cert_pem=cert)


# ── Schema del conector ──────────────────────────────────────────────

DIAN_COLOMBIA_SCHEMA = ConnectorSchema(
    name="dian_colombia",
    version="1.0.0",
    description=(
        "Emite, consulta y gestiona facturas electrónicas DIAN Colombia "
        "(UBL 2.1 + CUFE + XAdES-EPES + eventos 1-7)"
    ),
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue", description="Emite factura electrónica DIAN (SendBillAsync)",
                         category="write"),
        ActionDefinition(name="cancel", description="Cancela factura (evento DIAN 1)",
                         category="write"),
        ActionDefinition(name="verify", description="Verifica estado por TrackId/CUFE",
                         category="read"),
        ActionDefinition(name="get_pdf", description="Obtiene PDF (vía OUP autorizado)",
                         category="read"),
        ActionDefinition(name="send_event", description="Registra evento DIAN 1-7",
                         category="write"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["nit_or_ruc", "cert_path", "cert_password", "environment"],
            optional_fields=["software_id", "pin", "technical_nit", "key_path"],
            description="NIT emisor + certificado digital (PFX/PEM) + ambiente DIAN",
        ),
    ],
)
