"""Tests Fase 2C — Connectors LATAM nuevos con crypto REAL (sin MOCKs).

Tests para:
- DIAN Colombia: UBL 2.1 + CUFE SHA-256 + XAdES-EPES + WSDIAN SendBillAsync + eventos 1-7
- SUNAT Perú: UBL 2.1 + XAdES-BES + sendBill/sendSummary + CDR ResponseCode + RUC DV mod-11
- SRI Ecuador: XML SRI 1.1.0 + clave acceso 49 díg + DV mod-11 + XAdES-EPES + IVA 15% post-reforma 2024

Todos los tests usan cert autofirmado RSA 2048 generado en runtime (cryptography).
Sin MOCKs en el código de producción — solo se mockea MTLSHttpClient para evitar
llamadas reales a WSDIAN/SEE-SUNAT/SRI en tests.
"""
from __future__ import annotations

import base64
import io
import os
import re
import sys
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_tmpdir = tempfile.mkdtemp(prefix="fase2c_test_")
os.environ["HOME"] = _tmpdir

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ── Helpers ────────────────────────────────────────────────────────


def _generate_test_cert(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Genera certificado autofirmado RSA 2048 para tests (PEM + PFX)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(key_size=2048, public_exponent=65537)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CO"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Test LATAM Fase2C Cert"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )

    key_path = tmp_path / "test_key.pem"
    cert_path = tmp_path / "test_cert.pem"
    pfx_path = tmp_path / "test_cert.pfx"

    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    pfx_data = pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None,
        serialization.BestAvailableEncryption(b"testpass"),
    )
    pfx_path.write_bytes(pfx_data)
    return key_path, cert_path, pfx_path


class _StubAuthProvider:
    """Stub de AuthProvider con get_credentials() (patrón usado por los connectors).

    AuthProvider base no define get_credentials() — connectors usan getattr,
    pero en producción algunos auth_providers concretos exponen este método.
    """

    def __init__(self, creds: dict[str, Any]) -> None:
        self._creds = creds

    def get_credentials(self) -> dict[str, Any]:
        return dict(self._creds)

    def validate(self) -> bool:
        return bool(self._creds)

    def is_expired(self) -> bool:
        return False

    def refresh(self) -> bool:
        return True

    def get_auth_type(self) -> str:
        return "mtls"

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        return request

    def to_dict(self) -> dict[str, Any]:
        return {"auth_type": "mtls"}


class _MockResponse:
    """Mock de requests.Response para MTLSHttpClient."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        json_data: Any = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._content = content
        self._json = json_data
        self.text = text or (content.decode("utf-8", errors="replace") if content else "")
        self.headers: dict[str, str] = {"Content-Type": "application/xml"}
        self.elapsed = 0.1

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def content(self) -> bytes:
        return self._content

    def json(self) -> Any:
        if self._json is not None:
            return self._json
        return None


def _install_mock_mtls(connector: Any, mock_response: _MockResponse) -> MagicMock:
    """Sustituye self._mtls por MagicMock que retorna mock_response para cualquier llamada."""
    mock_mtls = MagicMock()
    mock_mtls.post = MagicMock(return_value=mock_response)
    mock_mtls.put = MagicMock(return_value=mock_response)
    mock_mtls.get = MagicMock(return_value=mock_response)
    mock_mtls.close = MagicMock()
    connector._mtls = mock_mtls  # type: ignore[attr-defined]
    return mock_mtls


# ── DIAN Colombia ─────────────────────────────────────────────────


class TestDIANColombia:
    """Tests para DIAN Colombia (CUFE SHA-256 + UBL 2.1 + XAdES-EPES + SendBillAsync)."""

    def test_cufe_sha256_64_chars(self):
        """CUFE debe ser SHA-256 hex de 64 caracteres (32 bytes)."""
        from src.connectors.dian_colombia import _compute_cufe

        params = {
            "NumFac": "SETP-99001",
            "FecFac": "2024-12-31",
            "HorFac": "12:00:00-05:00",
            "NitOFE": "900123456",
            "DocAdq": "800987654",
            "ValFac": "1000.00",
            "ValIva": "190.00",
            "ValIpo": "0.00",
            "ValTot": "1190.00",
            "NitTec": "900123456",
            "TipoAmb": "2",
            "ClaveTec": "00000000-0000-0000-0000-000000000000",
        }
        cufe = _compute_cufe(params)
        assert len(cufe) == 64, f"CUFE debe ser 64 chars, es {len(cufe)}"
        # Hex chars únicamente
        assert all(c in "0123456789abcdef" for c in cufe), f"CUFE no es hex: {cufe}"
        # Determinismo: misma entrada → mismo CUFE
        assert cufe == _compute_cufe(params)
        # Cambiar un campo → cambia CUFE
        params2 = dict(params)
        params2["NumFac"] = "SETP-99002"
        assert _compute_cufe(params2) != cufe

    def test_nit_dv_modulo_11(self):
        """DIAN NIT DV módulo 11 con pesos [71,67,59,53,47,43,41,37,29,23,19,17,13,7,3]."""
        from src.connectors.dian_colombia import _compute_nit_dv

        # NIT 900123456 — cálculo manual:
        # digits = [9,0,0,1,2,3,4,5,6] reversed = [6,5,4,3,2,1,0,0,9]
        # weights[0..8] = [71,67,59,53,47,43,41,37,29]
        # 6*71 + 5*67 + 4*59 + 3*53 + 2*47 + 1*43 + 0*41 + 0*37 + 9*29
        # = 426 + 335 + 236 + 159 + 94 + 43 + 0 + 0 + 261 = 1554
        # 1554 % 11 = 3 (11*141 = 1551) → DV = 11 - 3 = 8
        assert _compute_nit_dv("900123456") == "8"

        # NIT vacío o no numérico → "0"
        assert _compute_nit_dv("") == "0"
        assert _compute_nit_dv("abc") == "0"

        # Determinismo
        assert _compute_nit_dv("900123456") == _compute_nit_dv("900123456")

    def test_dian_xml_has_ubl_21_namespace(self, tmp_path):
        """XML DIAN debe tener xmlns UBL 2.1 Invoice."""
        from src.connectors.dian_colombia import NSMAP_UBL, DIANColombiaConnector

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        connector = DIANColombiaConnector()
        connector._auth_provider = _StubAuthProvider({  # type: ignore[attr-defined]
            "nit_or_ruc": "900123456",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "environment": "homologacion",
        })
        assert connector.connect() is True

        xml_bytes = connector._build_xml_dian({  # type: ignore[attr-defined]
            "invoice_id": "SETP-99001",
            "net_amount": "1000.00",
            "tax_amount": "190.00",
            "total_amount": "1190.00",
        })

        # Verificar namespace UBL 2.1 Invoice
        assert b"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in xml_bytes
        assert b"Invoice" in xml_bytes

        from lxml import etree
        root = etree.fromstring(xml_bytes)
        assert root.tag == f"{{{NSMAP_UBL['Invoice']}}}Invoice"

        connector.disconnect()

    def test_dian_issue_signs_xml(self, tmp_path):
        """Test DIAN issue: build XML → CUFE → sign XAdES-EPES → SOAP SendBillAsync.

        Mock MTLSHttpClient para retornar SOAP canned response.
        Verifica que el XML enviado (base64-encoded en <contentFile>) contiene b"Signature".
        """
        from src.connectors.dian_colombia import DIANColombiaConnector

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        connector = DIANColombiaConnector()
        connector._auth_provider = _StubAuthProvider({  # type: ignore[attr-defined]
            "nit_or_ruc": "900123456",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "environment": "homologacion",
            "pin": "00000000-0000-0000-0000-000000000000",
        })
        assert connector.connect() is True

        # Mock response WSDIAN SendBillAsync — retorna TrackId + Status
        dian_response = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
            b'<s:Body>'
            b'<SendBillAsyncResponse xmlns="http://wcf.dian.colombia">'
            b'<SendBillAsyncResult>'
            b'<TrackId>1234567890</TrackId>'
            b'<Status>accepted</Status>'
            b'<StatusMessage>Procesado correctamente</StatusMessage>'
            b'</SendBillAsyncResult>'
            b'</SendBillAsyncResponse>'
            b'</s:Body></s:Envelope>'
        )
        _install_mock_mtls(connector, _MockResponse(content=dian_response))

        result = connector._issue({  # type: ignore[attr-defined]
            "invoice_id": "SETP-99001",
            "net_amount": "1000.00",
            "tax_amount": "190.00",
            "total_amount": "1190.00",
            "receiver_nit": "800987654",
        })

        assert result["success"] is True
        assert result["track_id"] == "1234567890"
        assert result["cufe"]
        assert len(result["cufe"]) == 64  # SHA-256 hex

        # Verificar que el SOAP enviado contiene SendBillAsync + XML firmado (base64)
        mock_mtls = connector._mtls  # type: ignore[attr-defined]
        assert mock_mtls.post.called
        sent_data = (
            mock_mtls.post.call_args.kwargs.get("data")
            or mock_mtls.post.call_args[1].get("data")
        )
        assert sent_data is not None
        assert b"SendBillAsync" in sent_data
        # El XML firmado va base64-encoded en <contentFile>
        m = re.search(rb"<contentFile>([^<]+)</contentFile>", sent_data)
        assert m is not None, "No se encontró <contentFile> en SOAP SendBillAsync"
        decoded = base64.b64decode(m.group(1))
        assert b"Signature" in decoded or b"SignedInfo" in decoded, \
            "XML firmado no contiene Signature/SignedInfo"

        connector.disconnect()


# ── SUNAT Perú ────────────────────────────────────────────────────


class TestSUNATPeru:
    """Tests para SUNAT Perú (RUC DV mod-11 + UBL 2.1 + XAdES-BES + sendBill + CDR)."""

    def test_ruc_dv_modulo_11(self):
        """SUNAT RUC DV módulo 11 con pesos [5,4,3,2,7,6,5,4,3,2] izquierda a derecha."""
        from src.connectors.sunat_peru import _compute_ruc_dv

        # Caso 1: RUC 2051233379 — cálculo manual:
        # digits = [2,0,5,1,2,3,3,3,7,9]
        # products = 10+0+15+2+14+18+15+12+21+18 = 125
        # 125 % 11 = 4 (11*11=121) → DV = 11 - 4 = 7
        assert _compute_ruc_dv("2051233379") == "7"

        # Caso 2: todos 1s → 1*41 = 41, 41%11 = 8 → DV = 3
        assert _compute_ruc_dv("1111111111") == "3"

        # Caso 3: DV = 10 → mapear a "0"
        # "1000100000": 1*5 + 1*7 = 12, 12%11 = 1, DV = 10 → "0"
        assert _compute_ruc_dv("1000100000") == "0"

        # Caso 4: DV = 11 → mapear a "1"
        # "1010101001": 1*5 + 1*3 + 1*7 + 1*5 + 1*2 = 22, 22%11 = 0, DV = 11 → "1"
        assert _compute_ruc_dv("1010101001") == "1"

        # Caso 5: < 10 dígitos → "0"
        assert _compute_ruc_dv("12345") == "0"
        assert _compute_ruc_dv("") == "0"

        # Determinismo
        assert _compute_ruc_dv("2051233379") == _compute_ruc_dv("2051233379")

    def test_sunat_xml_has_ubl_21_namespace(self, tmp_path):
        """XML SUNAT debe tener xmlns UBL 2.1 Invoice."""
        from src.connectors.sunat_peru import NSMAP_PE, SUNATPeruConnector

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        connector = SUNATPeruConnector()
        connector._auth_provider = _StubAuthProvider({  # type: ignore[attr-defined]
            "nit_or_ruc": "20512333791",
            "ruc": "20512333791",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "environment": "see_beta",
        })
        assert connector.connect() is True

        xml_bytes = connector._build_xml_sunat({  # type: ignore[attr-defined]
            "doc_type": "01",
            "serie": "F001",
            "doc_number": "00000001",
            "net_amount": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
        })

        assert b"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in xml_bytes
        assert b"Invoice" in xml_bytes

        from lxml import etree
        root = etree.fromstring(xml_bytes)
        assert root.tag == f"{{{NSMAP_PE['Invoice']}}}Invoice"

        connector.disconnect()

    def test_sunat_issue_returns_cdr(self, tmp_path):
        """Test SUNAT issue: build XML → sign XAdES-BES → zip → sendBill → CDR ResponseCode=0."""
        from src.connectors.sunat_peru import SUNATPeruConnector

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        connector = SUNATPeruConnector()
        connector._auth_provider = _StubAuthProvider({  # type: ignore[attr-defined]
            "nit_or_ruc": "20512333791",
            "ruc": "20512333791",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "environment": "see_beta",
        })
        assert connector.connect() is True

        # Mock CDR (zip con ApplicationResponse XML) — SUNAT devuelve CDR como ZIP base64
        cdr_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<ApplicationResponse xmlns="urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2">'
            b'<cbc:ResponseCode xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">0</cbc:ResponseCode>'
            b'<cbc:Description xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">Aceptado</cbc:Description>'
            b'</ApplicationResponse>'
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("20512333791-01-F001-00000001.xml", cdr_xml)
        cdr_zip_b64 = base64.b64encode(buf.getvalue()).decode()

        sendbill_response = (
            f'<?xml version="1.0" encoding="utf-8"?>'
            f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soapenv:Body>'
            f'<ns2:sendBillResponse xmlns:ns2="http://service.gem.sunat.gob.pe">'
            f'<applicationResponse>{cdr_zip_b64}</applicationResponse>'
            f'<responseCode>0</responseCode>'
            f'<description>Aceptado</description>'
            f'</ns2:sendBillResponse>'
            f'</soapenv:Body></soapenv:Envelope>'
        ).encode()

        _install_mock_mtls(connector, _MockResponse(content=sendbill_response))

        result = connector._issue({  # type: ignore[attr-defined]
            "doc_type": "01",
            "serie": "F001",
            "doc_number": "00000001",
            "net_amount": "1000.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
        })

        assert result["success"] is True
        assert result["response_code"] == "0"
        assert result["cdr"]  # base64 CDR no vacío
        assert "xml" in result

        # Verificar que el SOAP enviado contiene sendBill + contentFile (zip base64)
        mock_mtls = connector._mtls  # type: ignore[attr-defined]
        assert mock_mtls.post.called
        sent_data = (
            mock_mtls.post.call_args.kwargs.get("data")
            or mock_mtls.post.call_args[1].get("data")
        )
        assert sent_data is not None
        assert b"sendBill" in sent_data
        assert b"contentFile" in sent_data

        connector.disconnect()


# ── SRI Ecuador ───────────────────────────────────────────────────


class TestSRIEcuador:
    """Tests para SRI Ecuador (clave acceso 49 díg + DV mod-11 + XML 1.1.0 + IVA 15%)."""

    def test_clave_acceso_49_digits(self):
        """Clave acceso SRI debe ser 49 dígitos (48 + DV)."""
        from src.connectors.sri_ecuador import _build_clave_acceso

        clave = _build_clave_acceso(
            fecha="31122024",
            tipo_comprobante="01",
            ruc="1792146739001",
            ambiente="2",
            serie="001001",
            secuencial="000000001",
            codigo_numerico="12345678",
            tipo_emision="1",
        )
        assert len(clave) == 49, f"Clave debe ser 49 dígitos, es {len(clave)}"
        assert clave.isdigit(), f"Clave debe ser solo dígitos: {clave}"

        # Estructura: 8 + 2 + 13 + 1 + 6 + 9 + 8 + 1 + 1 (DV) = 49
        assert clave[:8] == "31122024"        # fecha DDMMAAAA
        assert clave[8:10] == "01"            # tipo comprobante
        assert clave[10:23] == "1792146739001"  # RUC 13 dígitos
        assert clave[23] == "2"               # ambiente (2=pruebas)
        assert clave[24:30] == "001001"       # serie (estab 3 + ptoEmi 3)
        assert clave[30:39] == "000000001"    # secuencial 9 dígitos
        assert clave[39:47] == "12345678"     # código numérico 8 dígitos
        assert clave[47] == "1"               # tipo emisión (1=normal)
        assert clave[48] in "0123456789"      # DV 1 dígito

    def test_sri_dv_modulo_11(self):
        """SRI DV módulo 11 con pesos [2,3,4,5,6,7] cíclicos de derecha a izquierda."""
        from src.connectors.sri_ecuador import _compute_sri_dv

        # Caso 1: 48 unos → DV = 4
        # 8 ciclos de 6 pesos (2+3+4+5+6+7=27) → 8*27 = 216
        # 216 % 11 = 7 (11*19=209) → DV = 11-7 = 4
        assert _compute_sri_dv("1" * 48) == "4"

        # Caso 2: 48 ceros → sum=0, mod=0, DV=11 → "0"
        assert _compute_sri_dv("0" * 48) == "0"

        # Caso 3: < 48 dígitos → "0"
        assert _compute_sri_dv("12345") == "0"

        # Caso 4: > 48 dígitos → usar últimos 48
        # "9" + "1"*48 → últimos 48 son "1"*48 → DV = 4
        assert _compute_sri_dv("9" + "1" * 48) == "4"

        # Caso 5: un "1" al final (derecha) → peso=2, sum=2, mod=2, DV=9
        # reversed(digits)[0] = último dígito = 1, weight[0] = 2 → sum = 2
        assert _compute_sri_dv("0" * 47 + "1") == "9"

        # Caso 6: caracteres no numéricos → se filtran (solo dígitos)
        # "1"*47 + "a" → digits = [1]*47, len=47 < 48 → "0"
        assert _compute_sri_dv("1" * 47 + "a") == "0"

        # Determinismo
        assert _compute_sri_dv("1" * 48) == _compute_sri_dv("1" * 48)

    def test_sri_xml_has_v1_1_0_namespace(self, tmp_path):
        """XML SRI debe tener xmlns='http://ec.gob.sri.factura.v1.1.0' y version='1.1.0'."""
        from src.connectors.sri_ecuador import SRI_NS, SRIEcuadorConnector

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        connector = SRIEcuadorConnector()
        connector._auth_provider = _StubAuthProvider({  # type: ignore[attr-defined]
            "nit_or_ruc": "1792146739001",
            "ruc": "1792146739001",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "ambiente": "2",
            "environment": "homologacion",
        })
        assert connector.connect() is True

        xml_bytes = connector._build_xml_sri({  # type: ignore[attr-defined]
            "doc_type": "01",
            "secuencial": "000000001",
            "net_amount": "1000.00",
            "tax_amount": "150.00",
            "total_amount": "1150.00",
        })

        assert b"http://ec.gob.sri.factura.v1.1.0" in xml_bytes
        assert b"factura" in xml_bytes
        assert b'version="1.1.0"' in xml_bytes

        from lxml import etree
        root = etree.fromstring(xml_bytes)
        assert root.tag == f"{{{SRI_NS}}}factura"
        assert root.get("version") == "1.1.0"

        connector.disconnect()

    def test_sri_iva_15_percent(self):
        """Post-reforma LORTI 2024: codigoPorcentaje=2 → IVA 15% (NO 12% histórico)."""
        from src.connectors.sri_ecuador import SRI_IVA_CODES

        # codigoPorcentaje 2 = IVA 15% (post-reforma LORTI 2024, R.O. 519)
        iva_15 = SRI_IVA_CODES["2"]
        assert iva_15["tarifa"] == "15", f"tarifa should be '15', got {iva_15['tarifa']}"
        assert iva_15["porcentaje"] == "15.00", \
            f"porcentaje should be '15.00', got {iva_15['porcentaje']}"
        assert "15" in iva_15["nombre"]
        assert "2024" in iva_15["nombre"], f"nombre should mention 2024 reform: {iva_15['nombre']}"

        # Asegurar que NO existe ningún código con tarifa 12 (histórico NO vigente)
        for code, info in SRI_IVA_CODES.items():
            assert info["tarifa"] != "12", \
                f"IVA 12% histórico (NO vigente post-2024) encontrado en código {code}"

        # Otros códigos válidos
        assert SRI_IVA_CODES["0"]["tarifa"] == "0"   # IVA 0%
        assert SRI_IVA_CODES["3"]["tarifa"] == "0"   # No objeto de impuesto
        assert SRI_IVA_CODES["6"]["tarifa"] == "0"   # Exento de IVA

    def test_sri_xml_uses_iva_15_in_details(self, tmp_path):
        """El XML generado para iva_code=2 debe incluir tarifa=15 (no 12 histórico)."""
        from src.connectors.sri_ecuador import SRIEcuadorConnector

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        connector = SRIEcuadorConnector()
        connector._auth_provider = _StubAuthProvider({  # type: ignore[attr-defined]
            "nit_or_ruc": "1792146739001",
            "ruc": "1792146739001",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "ambiente": "2",
            "environment": "homologacion",
        })
        assert connector.connect() is True

        xml_bytes = connector._build_xml_sri({  # type: ignore[attr-defined]
            "doc_type": "01",
            "iva_code": "2",  # 15% post-reforma 2024
            "net_amount": "1000.00",
            "tax_amount": "150.00",
            "total_amount": "1150.00",
            "items": [{"amount": "1000.00", "tax_amount": "150.00"}],
        })

        # Verificar que el XML incluye codigoPorcentaje=2 y tarifa=15
        # (los elementos llevan el prefijo "factura:" del namespace SRI)
        assert b"codigoPorcentaje>2</" in xml_bytes
        assert b"tarifa>15</" in xml_bytes
        # Asegurar que NO aparece tarifa 12 (histórico NO vigente post-reforma 2024)
        assert b"tarifa>12</" not in xml_bytes

        connector.disconnect()


# ── Registry ──────────────────────────────────────────────────────


class TestConnectorRegistration:
    """Verifica que los 3 nuevos connectors están en _ALL_CONNECTORS y son importables."""

    def test_dian_in_registry(self):
        """DIANColombiaConnector debe estar en _ALL_CONNECTORS y ser importable."""
        import src.connectors as pkg
        names = [c.__name__ for c in pkg._ALL_CONNECTORS]
        assert "DIANColombiaConnector" in names, \
            "DIANColombiaConnector no está en _ALL_CONNECTORS"

        from src.connectors import DIANColombiaConnector
        from src.connectors.dian_colombia import DIAN_COLOMBIA_SCHEMA

        assert DIANColombiaConnector.name == "dian_colombia"
        assert DIANColombiaConnector.category == "latam"
        assert DIANColombiaConnector.version == "1.0.0"
        # Schema con auth_type=mtls (consistencia con Fase 2B)
        assert any(a.auth_type == "mtls" for a in DIAN_COLOMBIA_SCHEMA.auth_requirements), \
            "DIAN_COLOMBIA_SCHEMA debe tener auth_type=mtls"
        # Acciones mínimas: issue, cancel, verify, get_pdf, send_event
        action_names = {a.name for a in DIAN_COLOMBIA_SCHEMA.actions}
        assert {"issue", "cancel", "verify", "get_pdf", "send_event"}.issubset(action_names), \
            f"Acciones DIAN incompletas: {action_names}"

    def test_sunat_in_registry(self):
        """SUNATPeruConnector debe estar en _ALL_CONNECTORS y ser importable."""
        import src.connectors as pkg
        names = [c.__name__ for c in pkg._ALL_CONNECTORS]
        assert "SUNATPeruConnector" in names, \
            "SUNATPeruConnector no está en _ALL_CONNECTORS"

        from src.connectors import SUNATPeruConnector
        from src.connectors.sunat_peru import SUNAT_PERU_SCHEMA

        assert SUNATPeruConnector.name == "sunat_peru"
        assert SUNATPeruConnector.category == "latam"
        assert SUNATPeruConnector.version == "1.0.0"
        assert any(a.auth_type == "mtls" for a in SUNAT_PERU_SCHEMA.auth_requirements), \
            "SUNAT_PERU_SCHEMA debe tener auth_type=mtls"
        action_names = {a.name for a in SUNAT_PERU_SCHEMA.actions}
        assert {"issue", "cancel", "verify", "get_pdf", "get_status"}.issubset(action_names), \
            f"Acciones SUNAT incompletas: {action_names}"

    def test_sri_in_registry(self):
        """SRIEcuadorConnector debe estar en _ALL_CONNECTORS y ser importable."""
        import src.connectors as pkg
        names = [c.__name__ for c in pkg._ALL_CONNECTORS]
        assert "SRIEcuadorConnector" in names, \
            "SRIEcuadorConnector no está en _ALL_CONNECTORS"

        from src.connectors import SRIEcuadorConnector
        from src.connectors.sri_ecuador import SRI_ECUADOR_SCHEMA

        assert SRIEcuadorConnector.name == "sri_ecuador"
        assert SRIEcuadorConnector.category == "latam"
        assert SRIEcuadorConnector.version == "1.0.0"
        assert any(a.auth_type == "mtls" for a in SRI_ECUADOR_SCHEMA.auth_requirements), \
            "SRI_ECUADOR_SCHEMA debe tener auth_type=mtls"
        action_names = {a.name for a in SRI_ECUADOR_SCHEMA.actions}
        assert {"issue", "cancel", "verify", "get_pdf"}.issubset(action_names), \
            f"Acciones SRI incompletas: {action_names}"

    def test_all_three_connectors_importable_from_init(self):
        """Los 3 connectors son importables vía `from src.connectors import ...`."""
        from src.connectors import (
            DIANColombiaConnector,
            SRIEcuadorConnector,
            SUNATPeruConnector,
        )
        for cls in (DIANColombiaConnector, SUNATPeruConnector, SRIEcuadorConnector):
            assert cls.name  # tiene nombre
            assert cls.description  # tiene descripción
            assert cls.author == "Zenic-Flujo"

    def test_all_schemas_have_mtls_auth_requirement(self):
        """Los 3 schemas tienen auth_type=mtls (consistencia con Fase 2B)."""
        from src.connectors.dian_colombia import DIAN_COLOMBIA_SCHEMA
        from src.connectors.sri_ecuador import SRI_ECUADOR_SCHEMA
        from src.connectors.sunat_peru import SUNAT_PERU_SCHEMA

        for schema in (DIAN_COLOMBIA_SCHEMA, SUNAT_PERU_SCHEMA, SRI_ECUADOR_SCHEMA):
            assert any(a.auth_type == "mtls" for a in schema.auth_requirements), \
                f"{schema.name} debe tener auth_type=mtls"
            # required_fields incluye los 4 campos básicos
            req_fields = set()
            for a in schema.auth_requirements:
                req_fields.update(a.required_fields)
            assert "nit_or_ruc" in req_fields
            assert "cert_path" in req_fields
            assert "cert_password" in req_fields
            assert "environment" in req_fields
