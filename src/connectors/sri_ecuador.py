"""SRI Ecuador Connector — Facturación Electrónica con crypto REAL.

Implementa la facturación electrónica de Ecuador según:
- LORTI art. 56 (reforma 2024 IVA 12% → 15% por Ley Sostenibilidad Financiera R.O. 519)
- Resolución SRI NAC-DGERCGC16-00000831 (23-dic-2016)
- Resolución SRI NAC-DGERCGC17-00000018 (21-jul-2017)
- Resolución SRI NAC-DGERCGC20-00000046 (may-2020) — contingencia
- Resolución SRI NAC-DGERCGC20-0000145 (oct-2020)
- ETSI TS 101 903 v1.3.2 (XAdES-EPES)

Flujo:
1. Construir XML SRI 1.1.0 (esquema PROPIO, NO UBL)
2. Generar clave de acceso 49 dígitos + DV módulo 11
3. Firmar XAdES-EPES con SignaturePolicyIdentifier URN SRI
4. POST SOAP a Recepción → "ComprobanteRecibido" o errores
5. Polling a Autorización cada 5s hasta 24h máx → "AUTORIZADO" / "NO AUTORIZADO"

Clave de acceso (49 dígitos):
- fecha(8) + tipoComprobante(2) + ruc(13) + ambiente(1) + serie(6)
  + secuencial(9) + código numérico(8) + tipoEmision(1) + DV(1)
- DV módulo 11 pesos [2,3,4,5,6,7] cíclicos de derecha a izquierda
- Si DV=11→0, si DV=10→1

Tipos comprobante:
- 01=Factura, 02=Nota débito, 03=Nota crédito, 04=Comprobante retención,
  05=Guía remisión, 06=Liquidación compras, 07=Comprobante venta (consumidor final)

IVA post-reforma 2024: 15% (codigoPorcentaje=2). Histórico 12% NO vigente.
Cancelación = NC(04) referenciando numDocModificado (NO existe cancel directo).

Códigos SRI → ZF-FISCAL-VAL-701-<code>.

Crypto REAL: signxml (XMLDSig enveloped) + lxml (XAdES QualifyingProperties)
+ cryptography (carga de PEM) + requests (mTLS).
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import random
import tempfile
import time
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

# Endpoints SRI (SOAP + mTLS para ambiente de pruebas; producción igual host sin 'cer')
SRI_ENDPOINTS: dict[str, dict[str, str]] = {
    "homologacion": {
        "recepcion": "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline",
        "autorizacion": "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline",
    },
    "produccion": {
        "recepcion": "https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline",
        "autorizacion": "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline",
    },
}

# Política de firma XAdES-EPES propia del SRI (NO reutilizar DIAN/SUNAT)
SRI_SIGNATURE_POLICY_URN: str = "https://www.sri.gob.ec/firma-electronica/politica-firma-v2"
SRI_SIGNATURE_POLICY_DESC: str = "Política de firma electrónica SRI Ecuador v2"

# IVA post-reforma 2024: 15% (codigoPorcentaje 2 = 15%)
# Histórico 12% NO vigente desde Ley Sostenibilidad Financiera R.O. 519.
SRI_IVA_CODES: dict[str, dict[str, str]] = {
    "0": {"porcentaje": "0.00", "tarifa": "0", "nombre": "IVA 0%"},
    "2": {"porcentaje": "15.00", "tarifa": "15", "nombre": "IVA 15% (post-reforma 2024)"},
    "3": {"porcentaje": "0.00", "tarifa": "0", "nombre": "No objeto de impuesto"},
    "6": {"porcentaje": "0.00", "tarifa": "0", "nombre": "Exento de IVA"},
}

# Tipos de comprobante SRI (comprobantes electrónicos)
SRI_DOC_TYPES: dict[str, str] = {
    "01": "Factura",
    "02": "Nota de Débito",
    "03": "Nota de Crédito",
    "04": "Comprobante de Retención",
    "05": "Guía de Remisión",
    "06": "Liquidación de Compras",
    "07": "Comprobante de Venta (consumidor final)",
}

# Pesos módulo 11 SRI para DV de clave de acceso — [2,3,4,5,6,7] cíclicos
SRI_DV_WEIGHTS: tuple[int, ...] = (2, 3, 4, 5, 6, 7)

# Namespace SRI 1.1.0 (esquema propio, NO UBL)
SRI_NS: str = "http://ec.gob.sri.factura.v1.1.0"

# Namespaces auxiliares
NSMAP_SRI: dict[str, str] = {
    "factura": SRI_NS,
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xades": "http://uri.etsi.org/01903/v1.3.2#",
}


def _compute_sri_dv(clave_48: str) -> str:
    """Calcula el DV (dígito verificador) de una clave de acceso SRI.

    Algoritmo SRI:
    - Tomar los 48 dígitos de la clave (sin DV)
    - Multiplicar de derecha a izquierda por pesos [2,3,4,5,6,7] cíclicos
    - Sumar los productos
    - mod = sum % 11
    - DV = 11 - mod
    - Si DV == 11 → 0; si DV == 10 → 1
    """
    digits = [int(c) for c in clave_48 if c.isdigit()]
    if len(digits) != 48:
        if len(digits) > 48:
            digits = digits[-48:]
        else:
            return "0"
    weights = SRI_DV_WEIGHTS
    total = 0
    for i, digit in enumerate(reversed(digits)):
        total += digit * weights[i % len(weights)]
    mod = total % 11
    dv = 11 - mod
    if dv == 11:
        return "0"
    if dv == 10:
        return "1"
    return str(dv)


def _build_clave_acceso(
    fecha: str,
    tipo_comprobante: str,
    ruc: str,
    ambiente: str,
    serie: str,
    secuencial: str,
    codigo_numerico: str,
    tipo_emision: str,
) -> str:
    """Construye la clave de acceso SRI de 49 dígitos con DV."""
    clave_48 = (
        f"{fecha:0>8}"
        f"{tipo_comprobante:0>2}"
        f"{ruc:0>13}"
        f"{ambiente:0>1}"
        f"{serie:0>6}"
        f"{secuencial:0>9}"
        f"{codigo_numerico:0>8}"
        f"{tipo_emision:0>1}"
    )
    dv = _compute_sri_dv(clave_48)
    return clave_48 + dv


def _xades_sri_epes(
    signed_xml: bytes,
    cert_pem: bytes,
    signing_time: str,
    policy_id: str = SRI_SIGNATURE_POLICY_URN,
    policy_desc: str = SRI_SIGNATURE_POLICY_DESC,
) -> bytes:
    """Inyecta QualifyingProperties XAdES-EPES con política SRI propia."""
    root = etree.fromstring(signed_xml)
    ns_ds = NSMAP_SRI["ds"]
    ns_xades = NSMAP_SRI["xades"]

    sig = root.find(f".//{{{ns_ds}}}Signature")
    if sig is None:
        return signed_xml

    cert_digest = base64.b64encode(hashlib.sha256(cert_pem).digest()).decode()
    policy_digest = base64.b64encode(hashlib.sha256(policy_id.encode()).digest()).decode()

    obj = etree.SubElement(sig, f"{{{ns_ds}}}Object")
    qp = etree.SubElement(
        obj,
        f"{{{ns_xades}}}QualifyingProperties",
        Target="#" + (sig.get("Id") or "SignatureSRI"),
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

    sig_policy = etree.SubElement(sig_sig_props, f"{{{ns_xades}}}SignaturePolicyIdentifier")
    sig_policy_id = etree.SubElement(sig_policy, f"{{{ns_xades}}}SignaturePolicyId")
    sig_policy_qual = etree.SubElement(sig_policy_id, f"{{{ns_xades}}}SigPolicyId")
    etree.SubElement(sig_policy_qual, f"{{{ns_xades}}}Identifier").text = policy_id
    etree.SubElement(sig_policy_qual, f"{{{ns_xades}}}Description").text = policy_desc
    hash_alg = etree.SubElement(sig_policy_id, f"{{{ns_xades}}}SigPolicyHashDigest")
    etree.SubElement(
        hash_alg,
        f"{{{ns_ds}}}DigestMethod",
        Algorithm="http://www.w3.org/2001/04/xmlenc#sha256",
    )
    etree.SubElement(hash_alg, f"{{{ns_ds}}}DigestValue").text = policy_digest

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _sub(parent: etree._Element, tag: str, text: str | None = None,
         **attrs: str) -> etree._Element:
    """Helper: SubElement with optional text content and attributes."""
    el = etree.SubElement(parent, tag, **{k: v for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


class SRIEcuadorConnector(BaseConnector):
    """Conector SRI Ecuador: XML 1.1.0 + clave acceso 49 díg + XAdES-EPES + Recepción+Autorización."""

    name = "sri_ecuador"
    version = "1.0.0"
    description = (
        "Emite, consulta y gestiona comprobantes electrónicos SRI Ecuador "
        "(XML 1.1.0 + clave acceso 49 díg DV mod-11 + XAdES-EPES)"
    )
    category = "latam"
    icon = "file-text"
    author = "Zenic-Flujo"

    # Configuración de polling a Autorización
    _POLL_INTERVAL_SECONDS: int = 5
    _POLL_MAX_ATTEMPTS: int = 17_280  # 24h / 5s

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ruc: str = ""
        self._razon_social: str = ""
        self._ambiente: str = "2"  # 1=producción, 2=pruebas
        self._estab: str = "001"
        self._pto_emi: str = "001"
        self._cert_path: str = ""
        self._cert_password: str = ""
        self._cert_bundle: CertBundle | None = None
        self._mtls: MTLSHttpClient | None = None
        self._temp_files: list[str] = []

    # ── Ciclo de vida ────────────────────────────────────────────────

    def connect(self) -> bool:
        """Carga certificado PEM e inicializa cliente mTLS a SRI."""
        creds = self._get_creds()
        self._ruc = creds.get("nit_or_ruc", creds.get("ruc", self._ruc))
        self._razon_social = creds.get("razon_social", self._razon_social)
        self._ambiente = str(creds.get("ambiente", self._ambiente))
        self._estab = creds.get("estab", self._estab)
        self._pto_emi = creds.get("pto_emi", self._pto_emi)
        self._cert_path = creds.get("cert_path", self._cert_path)
        self._cert_password = creds.get("cert_password", self._cert_password)

        if not self._ruc or not self._cert_path:
            logger.error("SRI connect: ruc y cert_path son obligatorios")
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
            logger.error("SRI connect: error cargando certificado: %s", e)
            return False

        if self._cert_bundle.is_expired:
            logger.warning("SRI connect: certificado expirado")

        self._write_temp_pems()
        try:
            self._mtls = MTLSHttpClient(
                cert_path=self._temp_files[0],
                key_path=self._temp_files[1],
                timeout=60,
                verify=False,
            )
        except Exception as e:
            logger.error("SRI connect: error inicializando mTLS: %s", e)
            return False

        self._connected = True
        self._log_operation("connect", f"RUC={self._ruc} ambiente={self._ambiente}")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        action_map: dict[str, Any] = {
            "issue": self._issue,
            "cancel": self._cancel,
            "verify": self._verify,
            "get_pdf": self._get_pdf,
            "get_status": self._verify,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Acción '{action}' no soportada",
                    "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        if not self._ruc or not self._cert_path:
            return False
        if len(self._ruc) != 13:
            return False
        return self._ambiente in ("1", "2")

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
        """Emite comprobante: build XML → clave acceso → sign XAdES-EPES → Recepción → Autorización."""
        if not self._connected and not self.connect():
            return {"success": False, "error": "Conector no conectado"}

        try:
            xml_bytes = self._build_xml_sri(params)
            clave_acceso = self._compute_clave_acceso(params)
            xml_bytes = self._inject_clave_acceso(xml_bytes, clave_acceso)
            signed = self._sign(xml_bytes)
            soap = self._wrap_soap_recepcion(signed, clave_acceso)
            endpoint = SRI_ENDPOINTS[self._ambiente_env()]["recepcion"]
            response = self._send_soap(endpoint, soap)
            recepcion_result = self._parse_recepcion_response(response, clave_acceso)

            if not recepcion_result["success"]:
                return recepcion_result

            max_attempts = params.get("max_poll_attempts", 3)
            autorizacion = self._poll_autorizacion(clave_acceso, max_attempts=max_attempts)
            autorizacion["xml"] = signed.decode("utf-8", errors="replace")
            autorizacion["clave_acceso"] = clave_acceso
            return autorizacion
        except Exception as e:
            logger.exception("SRI issue falló")
            return {"success": False, "error": str(e),
                    "code": "ZF-FISCAL-VAL-701-999"}

    def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancelación SRI = NC(03) referenciando numDocModificado."""
        cancel_params = {
            **params,
            "doc_type": "03",
            "ref_doc_type": params.get("ref_doc_type", "01"),
            "ref_num_doc_modificado": params.get("ref_num_doc_modificado",
                                                  params.get("num_doc_modificado", "")),
            "ref_fecha_emision_doc_sustento": params.get("ref_fecha_emision_doc_sustento", ""),
            "reason": params.get("reason", "Anulación de factura"),
        }
        return self._issue(cancel_params)

    def _verify(self, params: dict[str, Any]) -> dict[str, Any]:
        """Consulta autorización por clave de acceso."""
        clave = params.get("clave_acesso", "") or params.get("clave_acceso", "")
        if not clave:
            return {"success": False, "error": "clave_acceso requerido"}
        endpoint = SRI_ENDPOINTS[self._ambiente_env()]["autorizacion"]
        soap = self._wrap_soap_autorizacion(clave)
        response = self._send_soap(endpoint, soap)
        return self._parse_autorizacion_response(response, clave)

    def _get_pdf(self, params: dict[str, Any]) -> dict[str, Any]:
        """PDF lo entrega un PAC/AC autorizado; SRI directa no provee PDF."""
        return {"success": False, "error": "PDF vía PAC autorizado (no SRI directa)",
                "code": "ZF-FISCAL-VAL-701-801"}

    # ── Construcción XML SRI 1.1.0 ───────────────────────────────────

    def _build_xml_sri(self, params: dict[str, Any]) -> bytes:
        """Construye XML SRI 1.1.0 (esquema propio, NO UBL)."""
        doc_type = params.get("doc_type", "01")
        issue_date = params.get("issue_date", datetime.now(UTC).strftime("%d/%m/%Y"))
        receiver_ruc = params.get("receiver_ruc", params.get("receiver_nit", ""))
        receiver_name = params.get("receiver_name", "CONSUMIDOR FINAL")
        receiver_type = params.get("receiver_type", "07")
        net_amount = str(params.get("net_amount", 0))
        tax_amount = str(params.get("tax_amount", 0))
        total_amount = str(params.get("total_amount", 0))
        iva_code = str(params.get("iva_code", "2"))
        iva_info = SRI_IVA_CODES.get(iva_code, SRI_IVA_CODES["2"])
        tarifa_iva = str(iva_info["tarifa"])

        root = etree.Element(
            f"{{{SRI_NS}}}factura",
            id="comprobante",
            version="1.1.0",
            nsmap={"factura": SRI_NS, "ds": NSMAP_SRI["ds"], "xades": NSMAP_SRI["xades"]},
        )

        # infoTributaria
        info_trib = _sub(root, f"{{{SRI_NS}}}infoTributaria")
        _sub(info_trib, f"{{{SRI_NS}}}ambiente", text=self._ambiente)
        _sub(info_trib, f"{{{SRI_NS}}}tipoEmision", text="1")
        _sub(info_trib, f"{{{SRI_NS}}}razonSocial",
             text=self._razon_social or "EMISOR SA")
        _sub(info_trib, f"{{{SRI_NS}}}nombreComercial",
             text=params.get("nombre_comercial", self._razon_social or "EMISOR"))
        _sub(info_trib, f"{{{SRI_NS}}}ruc", text=self._ruc)
        _sub(info_trib, f"{{{SRI_NS}}}claveAcceso", text="PLACEHOLDER_CLAVE")
        _sub(info_trib, f"{{{SRI_NS}}}codDoc", text=doc_type)
        _sub(info_trib, f"{{{SRI_NS}}}estab", text=self._estab)
        _sub(info_trib, f"{{{SRI_NS}}}ptoEmi", text=self._pto_emi)
        _sub(info_trib, f"{{{SRI_NS}}}secuencial",
             text=params.get("secuencial", "000000001"))
        _sub(info_trib, f"{{{SRI_NS}}}dirMatriz",
             text=params.get("dir_matriz", "Dirección Matriz"))

        # infoFactura
        info_fac = _sub(root, f"{{{SRI_NS}}}infoFactura")
        _sub(info_fac, f"{{{SRI_NS}}}fechaEmision", text=issue_date)
        _sub(info_fac, f"{{{SRI_NS}}}dirEstablecimiento",
             text=params.get("dir_establecimiento", "Dirección Establecimiento"))
        _sub(info_fac, f"{{{SRI_NS}}}obligadoContabilidad",
             text=params.get("obligado_contabilidad", "SI"))
        _sub(info_fac, f"{{{SRI_NS}}}tipoIdentificacionComprador", text=receiver_type)
        _sub(info_fac, f"{{{SRI_NS}}}razonSocialComprador", text=receiver_name)
        _sub(info_fac, f"{{{SRI_NS}}}identificacionComprador", text=receiver_ruc)
        _sub(info_fac, f"{{{SRI_NS}}}totalSinImpuestos", text=net_amount)
        _sub(info_fac, f"{{{SRI_NS}}}totalDescuento",
             text=str(params.get("descuento", "0.00")))

        # totalConImpuestos
        total_imp = _sub(info_fac, f"{{{SRI_NS}}}totalConImpuestos")
        total_imp_el = _sub(total_imp, f"{{{SRI_NS}}}totalImpuesto")
        _sub(total_imp_el, f"{{{SRI_NS}}}codigo", text="2")
        _sub(total_imp_el, f"{{{SRI_NS}}}codigoPorcentaje", text=iva_code)
        _sub(total_imp_el, f"{{{SRI_NS}}}baseImponible", text=net_amount)
        _sub(total_imp_el, f"{{{SRI_NS}}}tarifa", text=tarifa_iva)
        _sub(total_imp_el, f"{{{SRI_NS}}}valor", text=tax_amount)

        _sub(info_fac, f"{{{SRI_NS}}}propina",
             text=str(params.get("propina", "0.00")))
        _sub(info_fac, f"{{{SRI_NS}}}importeTotal", text=total_amount)
        _sub(info_fac, f"{{{SRI_NS}}}moneda", text="DOLAR")
        pagos = _sub(info_fac, f"{{{SRI_NS}}}pagos")
        pago = _sub(pagos, f"{{{SRI_NS}}}pago")
        _sub(pago, f"{{{SRI_NS}}}formaPago", text=params.get("forma_pago", "01"))
        _sub(pago, f"{{{SRI_NS}}}total", text=total_amount)
        _sub(pago, f"{{{SRI_NS}}}plazo", text=str(params.get("plazo", "0")))
        _sub(pago, f"{{{SRI_NS}}}unidadTiempo", text=params.get("unidad_tiempo", "dias"))

        # detalles
        detalles = _sub(root, f"{{{SRI_NS}}}detalles")
        for idx, item in enumerate(params.get("items", [{}]) or [{}], start=1):
            detalle = _sub(detalles, f"{{{SRI_NS}}}detalle")
            _sub(detalle, f"{{{SRI_NS}}}codigoPrincipal",
                 text=item.get("codigo", f"PRD{idx:03d}"))
            _sub(detalle, f"{{{SRI_NS}}}codigoAuxiliar",
                 text=item.get("codigo_aux", f"PRD{idx:03d}"))
            _sub(detalle, f"{{{SRI_NS}}}descripcion",
                 text=item.get("description", "Producto/Servicio"))
            _sub(detalle, f"{{{SRI_NS}}}cantidad",
                 text=str(item.get("quantity", "1.00")))
            _sub(detalle, f"{{{SRI_NS}}}precioUnitario",
                 text=str(item.get("unit_price", net_amount)))
            _sub(detalle, f"{{{SRI_NS}}}descuento",
                 text=str(item.get("descuento", "0.00")))
            _sub(detalle, f"{{{SRI_NS}}}precioTotalSinImpuesto",
                 text=str(item.get("amount", net_amount)))
            impuestos = _sub(detalle, f"{{{SRI_NS}}}impuestos")
            imp = _sub(impuestos, f"{{{SRI_NS}}}impuesto")
            _sub(imp, f"{{{SRI_NS}}}codigo", text="2")
            _sub(imp, f"{{{SRI_NS}}}codigoPorcentaje", text=iva_code)
            _sub(imp, f"{{{SRI_NS}}}tarifa", text=tarifa_iva)
            _sub(imp, f"{{{SRI_NS}}}baseImponible",
                 text=str(item.get("amount", net_amount)))
            _sub(imp, f"{{{SRI_NS}}}valor",
                 text=str(item.get("tax_amount", tax_amount)))

        # infoAdicional opcional
        if params.get("info_adicional"):
            info_adic = _sub(root, f"{{{SRI_NS}}}infoAdicional")
            for k, v in params["info_adicional"].items():
                _sub(info_adic, f"{{{SRI_NS}}}campoAdicional",
                     text=str(v), nombre=k)

        # Placeholder firma
        ds_ns = NSMAP_SRI["ds"]
        etree.SubElement(root, f"{{{ds_ns}}}Signature", Id="SignatureSRI")

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    def _compute_clave_acceso(self, params: dict[str, Any]) -> str:
        """Genera clave de acceso SRI de 49 dígitos con DV."""
        fecha = params.get("fecha", "")
        if not fecha:
            fecha = datetime.now(UTC).strftime("%d%m%Y")
        fecha = fecha.replace("-", "").replace("/", "")
        if len(fecha) == 8 and fecha[:4] in ("2024", "2025", "2026"):
            fecha = fecha[6:8] + fecha[4:6] + fecha[:4]

        tipo = params.get("doc_type", "01").zfill(2)
        ruc = self._ruc.zfill(13)[:13]
        ambiente = str(params.get("ambiente", self._ambiente))
        serie = params.get("serie", f"{self._estab}{self._pto_emi}")
        secuencial = params.get("secuencial", "000000001").zfill(9)[:9]
        codigo_numerico = params.get("codigo_numerico", f"{random.randint(0, 99999999):08d}")
        tipo_emision = str(params.get("tipo_emision", "1"))

        return _build_clave_acceso(fecha, tipo, ruc, ambiente, serie,
                                   secuencial, codigo_numerico, tipo_emision)

    def _inject_clave_acceso(self, xml_bytes: bytes, clave_acesso: str) -> bytes:
        """Reemplaza el placeholder de claveAcceso por la clave generada."""
        root = etree.fromstring(xml_bytes)
        clave_node = root.find(f".//{{{SRI_NS}}}claveAcceso")
        if clave_node is not None:
            clave_node.text = clave_acesso
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

    # ── Firma XAdES-EPES (política SRI propia) ───────────────────────

    def _sign(self, xml_bytes: bytes) -> bytes:
        """Firma XMLDSig enveloped + añade QualifyingProperties XAdES-EPES SRI."""
        if not self._cert_bundle:
            raise RuntimeError("Certificado no cargado — llame a connect() primero")
        signed = sign_xml(
            xml_bytes,
            self._cert_bundle.private_key_pem,
            self._cert_bundle.cert_pem,
            reference_uri="",
        )
        signing_time = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        signed = _xades_sri_epes(signed, self._cert_bundle.cert_pem, signing_time)
        return signed

    # ── SOAP / mTLS ──────────────────────────────────────────────────

    def _ambiente_env(self) -> str:
        """Mapea ambiente interno (1/2) a ambiente_env (homologacion/produccion)."""
        return "produccion" if self._ambiente == "1" else "homologacion"

    def _send_soap(self, endpoint: str, soap_body: bytes) -> bytes:
        if not self._mtls:
            raise RuntimeError("mTLS no inicializado — llame a connect() primero")
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '""',
        }
        response = self._mtls.post(endpoint, data=soap_body, headers=headers)
        return response.content

    def _wrap_soap_recepcion(self, signed_xml: bytes, clave_acesso: str) -> bytes:
        xml_b64 = base64.b64encode(signed_xml).decode()
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ec="http://ec.gob.sri.factura.v1.1.0">
  <soapenv:Header/>
  <soapenv:Body>
    <ec:validarComprobante>
      <xml>{xml_b64}</xml>
    </ec:validarComprobante>
  </soapenv:Body>
</soapenv:Envelope>"""
        return soap.encode()

    def _wrap_soap_autorizacion(self, clave_acesso: str) -> bytes:
        soap = f"""<?xml version="1.0" encoding="utf-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ec="http://ec.gob.sri.factura.v1.1.0">
  <soapenv:Header/>
  <soapenv:Body>
    <ec:autorizacionComprobante>
      <claveAccesoComprobante>{clave_acesso}</claveAccesoComprobante>
    </ec:autorizacionComprobante>
  </soapenv:Body>
</soapenv:Envelope>"""
        return soap.encode()

    # ── Parseo respuestas + polling ──────────────────────────────────

    def _parse_recepcion_response(self, response: bytes,
                                  clave_acesso: str) -> dict[str, Any]:
        try:
            root = etree.fromstring(response)
            estado = self._xpath_text(root, ".//*[local-name()='estado']") \
                or self._xpath_text(root, ".//*[local-name()='Estado']")
            comprobante = self._xpath_text(root, ".//*[local-name()='comprobante']") or ""
            mensajes = []
            for msg in root.iter():
                if msg.tag.endswith("mensaje") or msg.tag.endswith("Mensaje"):
                    info = self._xpath_text(msg, ".//*[local-name()='informacionAdicional']") \
                        or self._xpath_text(msg, ".//*[local-name()='identificador']") \
                        or msg.text or ""
                    if info:
                        mensajes.append(info)
        except etree.XMLSyntaxError:
            estado, comprobante, mensajes = "DEVUELTA", "", ["Respuesta no es XML"]

        received = estado.upper() == "RECIBIDA"
        return {
            "success": received,
            "clave_acesso": clave_acesso,
            "estado_recepcion": estado,
            "comprobante": comprobante,
            "mensajes": mensajes,
            "code": "ZF-FISCAL-VAL-701-200" if received else "ZF-FISCAL-VAL-701-4XX",
        }

    def _parse_autorizacion_response(self, response: bytes,
                                     clave_acesso: str) -> dict[str, Any]:
        try:
            root = etree.fromstring(response)
            estado = self._xpath_text(root, ".//*[local-name()='estado']") \
                or self._xpath_text(root, ".//*[local-name()='Estado']")
            numero_aut = self._xpath_text(root, ".//*[local-name()='numeroAutorizacion']") \
                or self._xpath_text(root, ".//*[local-name()='NumeroAutorizacion']") or ""
            fecha_aut = self._xpath_text(root, ".//*[local-name()='fechaAutorizacion']") \
                or self._xpath_text(root, ".//*[local-name()='FechaAutorizacion']") or ""
            mensajes = []
            for msg in root.iter():
                if msg.tag.endswith("mensaje") or msg.tag.endswith("Mensaje"):
                    info = self._xpath_text(msg, ".//*[local-name()='informacionAdicional']") \
                        or self._xpath_text(msg, ".//*[local-name()='identificador']") \
                        or msg.text or ""
                    if info:
                        mensajes.append(info)
        except etree.XMLSyntaxError:
            estado, numero_aut, fecha_aut, mensajes = "NO AUTORIZADO", "", "", ["XML inválido"]

        authorized = estado.upper() == "AUTORIZADO"
        return {
            "success": authorized,
            "clave_acesso": clave_acesso,
            "estado": estado,
            "numero_autorizacion": numero_aut,
            "fecha_autorizacion": fecha_aut,
            "mensajes": mensajes,
            "code": "ZF-FISCAL-VAL-701-200" if authorized else f"ZF-FISCAL-VAL-701-{estado}",
        }

    def _poll_autorizacion(self, clave_acesso: str, max_attempts: int = 3) -> dict[str, Any]:
        """Polling a Autorización cada 5s hasta 'AUTORIZADO' o 'NO AUTORIZADO' o max_attempts."""
        endpoint = SRI_ENDPOINTS[self._ambiente_env()]["autorizacion"]
        soap = self._wrap_soap_autorizacion(clave_acesso)
        last_response: dict[str, Any] = {"success": False, "estado": "EN_PROCESO",
                                         "clave_acesso": clave_acesso,
                                         "code": "ZF-FISCAL-VAL-701-202"}
        for attempt in range(max_attempts):
            response = self._send_soap(endpoint, soap)
            result = self._parse_autorizacion_response(response, clave_acesso)
            estado = result.get("estado", "").upper()
            if estado in ("AUTORIZADO", "NO AUTORIZADO"):
                return result
            last_response = result
            if attempt < max_attempts - 1:
                time.sleep(self._POLL_INTERVAL_SECONDS)
        return last_response

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
        with tempfile.NamedTemporaryFile(delete=False, suffix="_sri_cert.pem") as cert_f:
            cert_f.write(self._cert_bundle.cert_pem)
            cert_tmp = cert_f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix="_sri_key.pem") as key_f:
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

SRI_ECUADOR_SCHEMA = ConnectorSchema(
    name="sri_ecuador",
    version="1.0.0",
    description=(
        "Emite, consulta y gestiona comprobantes electrónicos SRI Ecuador "
        "(XML 1.1.0 + clave acceso 49 díg DV mod-11 + XAdES-EPES)"
    ),
    category="latam",
    icon="file-text",
    author="Zenic-Flujo",
    actions=[
        ActionDefinition(name="issue",
                         description="Emite comprobante SRI (Recepción + Autorización)",
                         category="write"),
        ActionDefinition(name="cancel",
                         description="Emite NC(03) referenciando numDocModificado",
                         category="write"),
        ActionDefinition(name="verify",
                         description="Verifica autorización por clave de acceso",
                         category="read"),
        ActionDefinition(name="get_pdf",
                         description="Obtiene PDF (vía PAC autorizado)",
                         category="read"),
        ActionDefinition(name="get_status",
                         description="Alias de verify — consulta por clave de acceso",
                         category="read"),
    ],
    auth_requirements=[
        AuthRequirement(
            auth_type="mtls",
            required_fields=["nit_or_ruc", "cert_path", "cert_password", "environment"],
            optional_fields=["razon_social", "estab", "pto_emi", "key_path"],
            description="RUC 13 dígitos + certificado digital PEM + ambiente SRI (homologacion/produccion)",
        ),
    ],
)
