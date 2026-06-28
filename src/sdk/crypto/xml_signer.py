"""XMLDSig wrapper para firma XML de facturación electrónica LATAM.

Usa signxml (LGPL) que internamente usa xmlsec + lxml.
Soporta firma XMLDSig enveloped sobre nodos específicos.

Uso:
    from src.sdk.crypto.xml_signer import sign_xml, verify_signature
    signed_xml = sign_xml(xml_bytes, key_pem, cert_pem, reference_uri="#NFe")
    assert verify_signature(signed_xml, cert_pem)
"""
from __future__ import annotations

import logging

from lxml import etree

logger = logging.getLogger(__name__)


def sign_xml(
    xml_bytes: bytes,
    private_key_pem: bytes,
    cert_pem: bytes,
    reference_uri: str | None = None,
) -> bytes:
    """Firma XML con XMLDSig enveloped.

    Usa signxml si está disponible. Si no, usa lxml + cryptography directo.
    """
    from lxml import etree

    root = etree.fromstring(xml_bytes)

    try:
        from signxml import XMLSigner, methods

        signer = XMLSigner(method=methods.enveloped, signature_algorithm="rsa-sha256",
                           digest_algorithm="sha256")
        signer.namespaces = dict(root.nsmap)

        if reference_uri:
            signed_root = signer.sign(root, key=private_key_pem, cert=cert_pem,
                                      reference_uri=reference_uri)
        else:
            signed_root = signer.sign(root, key=private_key_pem, cert=cert_pem)

        result = etree.tostring(signed_root, xml_declaration=True, encoding="UTF-8")
        logger.debug("XML firmado con signxml (%d bytes)", len(result))
        return result

    except (ImportError, Exception) as e:
        logger.warning("signxml falló (%s), usando firma manual con cryptography", e)
        return _sign_xml_manual(root, private_key_pem, cert_pem, reference_uri)


def _sign_xml_manual(
    root: etree._Element,
    private_key_pem: bytes,
    cert_pem: bytes,
    reference_uri: str | None,
) -> bytes:
    """Firma XML manualmente con cryptography (fallback si signxml no disponible)."""
    import base64

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    # Canonicalizar el documento
    canon = etree.tostring(root, method="c14n", exclusive=False, with_comments=False)

    # Firmar con RSA-SHA256
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = private_key.sign(canon, padding.PKCS1v15(), hashes.SHA256())

    # Calcular digest del documento
    digest = hashes.HashData(canon, hashes.SHA256()) if hasattr(hashes, 'HashData') else None
    if digest is None:
        import hashlib
        digest = hashlib.sha256(canon).digest()

    # Extraer certificado base64
    cert_b64 = base64.b64encode(cert_pem).decode()

    # Construir Signature element
    ns = "http://www.w3.org/2000/09/xmldsig#"
    sig = etree.SubElement(root, f"{{{ns}}}Signature")
    sig.set("Id", "Signature")

    signed_info = etree.SubElement(sig, f"{{{ns}}}SignedInfo")
    etree.SubElement(signed_info, f"{{{ns}}}CanonicalizationMethod",
                     Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
    etree.SubElement(signed_info, f"{{{ns}}}SignatureMethod",
                     Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")
    ref = etree.SubElement(signed_info, f"{{{ns}}}Reference")
    if reference_uri:
        ref.set("URI", reference_uri)
    transforms = etree.SubElement(ref, f"{{{ns}}}Transforms")
    etree.SubElement(transforms, f"{{{ns}}}Transform",
                     Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    etree.SubElement(ref, f"{{{ns}}}DigestMethod",
                     Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
    etree.SubElement(ref, f"{{{ns}}}DigestValue",
                     text=base64.b64encode(digest).decode())

    etree.SubElement(sig, f"{{{ns}}}SignatureValue",
                     text=base64.b64encode(signature).decode())

    key_info = etree.SubElement(sig, f"{{{ns}}}KeyInfo")
    x509_data = etree.SubElement(key_info, f"{{{ns}}}X509Data")
    etree.SubElement(x509_data, f"{{{ns}}}X509Certificate",
                     text=cert_b64.replace("-----BEGIN CERTIFICATE-----", "")
                              .replace("-----END CERTIFICATE-----", "")
                              .replace("\n", ""))

    result = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
    logger.debug("XML firmado manualmente (%d bytes)", len(result))
    return result


def verify_signature(
    xml_bytes: bytes,
    cert_pem: bytes | None = None,
) -> bool:
    """Verifica firma XMLDSig.

    Args:
        xml_bytes: XML firmado (bytes).
        cert_pem: Certificado X.509 PEM para verificar (opcional).

    Returns:
        True si la firma es válida, False en caso contrario.
    """
    try:
        from signxml import XMLVerifier
    except (ImportError, Exception):
        logger.warning("signxml no disponible — no se puede verificar firma XML")
        return False

    try:
        from lxml import etree
        root = etree.fromstring(xml_bytes)
        # Si no hay nodo Signature, devolver False
        ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
        sig = root.find(".//ds:Signature", namespaces=ns)
        if sig is None:
            return False
        XMLVerifier().verify(root, x509_cert=cert_pem)
        return True
    except Exception as e:
        logger.warning("Verificación de firma falló: %s", e)
        return False
