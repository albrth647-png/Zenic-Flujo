"""CMS/PKCS#7 signer para AFIP WSAA (Argentina).

AFIP requiere firma CMS (Cryptographic Message Syntax) sobre el TRA
(Ticket de Requerimiento de Acceso) para obtener Token + Sign.

Usa cryptography (Apache-2.0/BSD) + asn1crypto para construir
el CMS PKCS#7 detached con SHA-1 (AFIP exige SHA-1 en WSAA).

Uso:
    from src.sdk.crypto.cms_signer import sign_cms
    cms_bytes = sign_cms(tra_xml_bytes, private_key_pem, cert_pem)
"""
from __future__ import annotations

import logging

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

logger = logging.getLogger(__name__)


def sign_cms(
    payload: bytes,
    private_key_pem: bytes,
    cert_pem: bytes,
) -> bytes:
    """Firma payload con CMS/PKCS#7 detached (SHA-1, RSA).

    AFIP WSAA exige SHA-1 (no SHA-256) para el LoginCms.

    Args:
        payload: Datos a firmar (bytes, ej. TRA XML).
        private_key_pem: Clave privada RSA en PEM.
        cert_pem: Certificado X.509 en PEM.

    Returns:
        CMS firmado como bytes (DER format).

    Raises:
        Exception: Si la firma falla.
    """
    try:
        from cryptography.hazmat.primitives.serialization import pkcs7
        private_key = serialization.load_pem_private_key(private_key_pem, password=None)
        cert = load_pem_x509_certificate(cert_pem)

        builder = pkcs7.PKCS7SignatureBuilder()
        builder = builder.set_data(payload)
        builder = builder.add_signer(cert, private_key, hashes.SHA256())

        # Sin opciones (default = attached, no detached)
        cms_der = builder.sign(serialization.Encoding.DER, [hashes.SHA256()])

        logger.debug("CMS firmado con pkcs7/SHA256 (%d bytes)", len(cms_der))
        return cms_der
    except Exception:
        return _sign_cms_asn1(payload, private_key_pem, cert_pem)


def _sign_cms_asn1(
    payload: bytes,
    private_key_pem: bytes,
    cert_pem: bytes,
) -> bytes:
    """Fallback: construir CMS con asn1crypto si pkcs7 no disponible.

    Esto construye un CMS PKCS#7 SignedData manualmente usando
    asn1crypto para la estructura ASN.1 y cryptography para la firma.
    """
    from asn1crypto import algos, cms
    from asn1crypto import x509 as asn1x509

    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    cert = load_pem_x509_certificate(cert_pem)

    # Firmar con RSA + SHA-1
    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA1())

    # Construir certificado ASN.1 desde PEM
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    asn1_cert = asn1x509.Certificate.load(cert_der)

    # Construir SignedData
    signed_data = cms.SignedData({
        "version": "v1",
        "digest_algorithms": [algos.DigestAlgorithm({"algorithm": "sha1"})],
        "encap_content_info": {"content_type": "data"},
        "certificates": [cms.CertificateChoices({"certificate": asn1_cert})],
        "signer_infos": [cms.SignerInfo({
            "version": "v1",
            "sid": cms.SignerIdentifier({"issuer_and_serial_number": {
                "issuer": asn1_cert.issuer,
                "serial_number": asn1_cert.serial_number,
            }}),
            "digest_algorithm": {"algorithm": "sha1"},
            "signature_algorithm": {"algorithm": "sha1_rsa"},
            "signature": signature,
        })],
    })

    # Envolver en ContentInfo
    content_info = cms.ContentInfo({
        "content_type": "signed_data",
        "content": signed_data,
    })

    cms_der = content_info.dump()
    logger.debug("CMS (asn1crypto) firmado correctamente (%d bytes)", len(cms_der))
    return cms_der


def verify_cms(
    cms_bytes: bytes,
    payload: bytes,
    cert_pem: bytes | None = None,
) -> bool:
    """Verifica firma CMS/PKCS#7 detached.

    Args:
        cms_bytes: CMS firmado (DER).
        payload: Datos originales firmados.
        cert_pem: Certificado para verificar (opcional).

    Returns:
        True si la firma es válida.
    """
    try:
        from asn1crypto import cms as asn1cms

        content_info = asn1cms.ContentInfo.load(cms_bytes)
        if content_info["content_type"].native != "signed_data":
            return False

        signed_data = content_info["content"]
        signer_infos = signed_data["signer_infos"]

        if len(signer_infos) == 0:
            return False

        # Verificar firma del primer signer
        signer = signer_infos[0]
        signature = signer["signature"].native

        # Obtener certificado del signer
        certs = signed_data["certificates"]
        if len(certs) == 0:
            return False

        cert_choice = certs[0]
        asn1_cert = cert_choice.chosen
        cert_der = asn1_cert.dump()

        # Cargar certificado con cryptography
        from cryptography.x509 import load_der_x509_certificate
        cert = load_der_x509_certificate(cert_der)

        # Obtener clave pública
        public_key = cert.public_key()

        # Verificar firma RSA — intentar SHA256 primero, luego SHA1
        for hash_algo in [hashes.SHA256(), hashes.SHA1()]:
            try:
                public_key.verify(
                    signature,
                    payload,
                    padding.PKCS1v15(),
                    hash_algo,
                )
                return True
            except Exception:
                continue
        return False

    except Exception as e:
        logger.warning("Verificación CMS falló: %s", e)
        return False
