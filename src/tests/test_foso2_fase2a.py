"""Tests Fase 2A — Crypto shared: cert_loader, xml_signer, cms_signer, mtls_client, c14n."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="fase2a_test_")
os.environ["HOME"] = _tmpdir

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ── Helpers: generar cert autofirmado de test ──────────────────────

def _generate_test_cert(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Genera certificado autofirmado RSA 2048 para tests."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(key_size=2048, public_exponent=65537)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Test Cert"),
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

    # PFX
    from cryptography.hazmat.primitives.serialization import pkcs12
    pfx_data = pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None,
        serialization.BestAvailableEncryption(b"testpass"),
    )
    pfx_path.write_bytes(pfx_data)

    return key_path, cert_path, pfx_path


# ── cert_loader tests ────────────────────────────────────────────────

class TestCertLoader:
    """Tests para src/sdk/crypto/cert_loader.py."""

    def test_load_pem_returns_bundle(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pem
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        bundle = load_pem(str(key_path), str(cert_path))
        assert bundle.private_key_pem is not None
        assert bundle.cert_pem is not None
        assert "BEGIN PRIVATE KEY" in bundle.private_key_pem.decode()
        assert "BEGIN CERTIFICATE" in bundle.cert_pem.decode()

    def test_load_pfx_returns_bundle(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pfx
        _, _, pfx_path = _generate_test_cert(tmp_path)
        bundle = load_pfx(str(pfx_path), "testpass")
        assert bundle.private_key_pem is not None
        assert bundle.cert_pem is not None

    def test_load_pem_raises_on_missing_file(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pem
        with pytest.raises(FileNotFoundError):
            load_pem("/nonexistent/key.pem", "/nonexistent/cert.pem")

    def test_load_pfx_raises_on_missing_file(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pfx
        with pytest.raises(FileNotFoundError):
            load_pfx("/nonexistent.pfx", "password")

    def test_bundle_has_subject_and_issuer(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pem
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        bundle = load_pem(str(key_path), str(cert_path))
        assert "Test Cert" in bundle.subject
        assert "Test Cert" in bundle.issuer

    def test_bundle_is_not_expired(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pem
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        bundle = load_pem(str(key_path), str(cert_path))
        assert bundle.is_expired is False

    def test_get_cert_info_returns_dict(self, tmp_path):
        from src.sdk.crypto.cert_loader import get_cert_info, load_pem
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        bundle = load_pem(str(key_path), str(cert_path))
        info = get_cert_info(bundle)
        assert "subject" in info
        assert "issuer" in info
        assert "not_before" in info
        assert "not_after" in info
        assert "is_expired" in info
        assert info["is_expired"] is False


# ── cms_signer tests ─────────────────────────────────────────────────

class TestCMSSigner:
    """Tests para src/sdk/crypto/cms_signer.py."""

    def test_sign_cms_returns_bytes(self, tmp_path):
        from src.sdk.crypto.cms_signer import sign_cms
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        payload = b"<?xml version='1.0'?><login/>"
        cms_bytes = sign_cms(payload, key_path.read_bytes(), cert_path.read_bytes())
        assert isinstance(cms_bytes, bytes)
        assert len(cms_bytes) > 100  # CMS tiene estructura ASN.1

    def test_verify_cms_valid(self, tmp_path):
        from src.sdk.crypto.cms_signer import sign_cms, verify_cms
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        payload = b"test payload for CMS"
        cms_bytes = sign_cms(payload, key_path.read_bytes(), cert_path.read_bytes())
        assert verify_cms(cms_bytes, payload) is True

    def test_verify_cms_tampered_payload(self, tmp_path):
        from src.sdk.crypto.cms_signer import sign_cms, verify_cms
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        payload = b"original payload"
        cms_bytes = sign_cms(payload, key_path.read_bytes(), cert_path.read_bytes())
        assert verify_cms(cms_bytes, b"tampered payload") is False


# ── mtls_client tests ────────────────────────────────────────────────

class TestMTLSHttpClient:
    """Tests para src/sdk/crypto/mtls_client.py."""

    def test_init_with_pem_files(self, tmp_path):
        from src.sdk.crypto.mtls_client import MTLSHttpClient
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        client = MTLSHttpClient(cert_path=str(cert_path), key_path=str(key_path))
        assert client._cert is not None
        client.close()

    def test_init_raises_on_missing_cert(self, tmp_path):
        from src.sdk.crypto.mtls_client import MTLSHttpClient
        with pytest.raises(FileNotFoundError):
            MTLSHttpClient(cert_path="/nonexistent.pem", key_path="/nonexistent.key")

    def test_context_manager(self, tmp_path):
        from src.sdk.crypto.mtls_client import MTLSHttpClient
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        with MTLSHttpClient(cert_path=str(cert_path), key_path=str(key_path)) as client:
            assert client._cert is not None

    def test_init_without_cert(self):
        from src.sdk.crypto.mtls_client import MTLSHttpClient
        client = MTLSHttpClient()
        assert client._cert is None
        client.close()


# ── c14n tests ───────────────────────────────────────────────────────

class TestC14N:
    """Tests para src/sdk/crypto/c14n.py."""

    def test_canonicalize_xml_returns_bytes(self):
        from src.sdk.crypto.c14n import canonicalize_xml
        xml = b'<?xml version="1.0"?><root><child>text</child></root>'
        canon = canonicalize_xml(xml)
        assert isinstance(canon, bytes)
        assert b"<root>" in canon

    def test_canonicalize_xml_strips_comments(self):
        from src.sdk.crypto.c14n import canonicalize_xml
        xml = b'<?xml version="1.0"?><root><!-- comment --><child>text</child></root>'
        canon = canonicalize_xml(xml, with_comments=False)
        assert b"<!--" not in canon

    def test_canonicalize_nfe_finds_infNFe(self):
        from src.sdk.crypto.c14n import canonicalize_nfe
        xml = b'''<?xml version="1.0"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe Id="NFe12345678901234567890123456789012345678901234">
    <ide><cUF>35</cUF></ide>
  </infNFe>
</NFe>'''
        canon = canonicalize_nfe(xml, reference_id="#NFe12345678901234567890123456789012345678901234")
        assert isinstance(canon, bytes)
        assert b"infNFe" in canon

    def test_canonicalize_nfe_raises_on_missing_node(self):
        from src.sdk.crypto.c14n import canonicalize_nfe
        xml = b'<?xml version="1.0"?><root><other/></root>'
        with pytest.raises(ValueError, match="Nodo"):
            canonicalize_nfe(xml, reference_id="#NonExistent")

    def test_canonicalize_cfdi_raises_on_missing_xslt(self):
        from src.sdk.crypto.c14n import canonicalize_cfdi
        xml = b'<?xml version="1.0"?><cfdi:Comprobante/>'
        with pytest.raises(FileNotFoundError, match="XSLT"):
            canonicalize_cfdi(xml, xslt_path="/nonexistent.xslt")


# ── xml_signer tests (requiere signxml instalado) ───────────────────

class TestXMLSigner:
    """Tests para src/sdk/crypto/xml_signer.py."""

    def test_sign_xml_without_signxml_raises_importerror(self, tmp_path):
        """Si signxml no está instalado, debe dar ImportError claro."""
        from src.sdk.crypto.xml_signer import sign_xml
        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        xml = b'<root xmlns="http://test"><child>data</child></root>'
        try:
            result = sign_xml(xml, key_path.read_bytes(), cert_path.read_bytes())
            assert isinstance(result, bytes)
            assert b"Signature" in result
        except ImportError:
            pytest.skip("signxml no instalado en este entorno")

    def test_verify_signature_returns_bool(self):
        """verify_signature sin signxml devuelve False para XML sin firma."""
        from src.sdk.crypto.xml_signer import verify_signature
        xml = b'<root xmlns="http://test"><child>data</child></root>'
        result = verify_signature(xml)
        assert result is False


# ── Integration: cert → CMS → verify ────────────────────────────────

class TestIntegrationCertCMS:
    """E2E: cargar cert → firmar CMS → verificar CMS."""

    def test_end_to_end_cms_flow(self, tmp_path):
        from src.sdk.crypto.cert_loader import load_pem
        from src.sdk.crypto.cms_signer import sign_cms, verify_cms

        key_path, cert_path, _ = _generate_test_cert(tmp_path)
        bundle = load_pem(str(key_path), str(cert_path))

        payload = b'<?xml version="1.0"?><loginTicketRequest><service>wsfe</service></loginTicketRequest>'
        cms_bytes = sign_cms(payload, bundle.private_key_pem, bundle.cert_pem)

        assert verify_cms(cms_bytes, payload) is True
        assert verify_cms(cms_bytes, b"wrong") is False
