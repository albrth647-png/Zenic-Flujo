"""Cargador de certificados X.509 para LATAM e-invoicing.

Soporta:
- .pfx/.p12 (Brasil ICP-Brasil A1, México CSD/FIEL, Argentina e-Sign AR)
- .pem (Chile e-Cert, Peru, Colombia)
- Extracción de clave privada + cert + CA chain
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
    pkcs12,
)
from typing import Any


@dataclass
class CertBundle:
    """Bundle de certificado + clave privada + CA chain."""
    private_key_pem: bytes
    cert_pem: bytes
    ca_chain_pem: bytes | None
    subject: str
    issuer: str
    not_before: str
    not_after: str
    serial_number: str

    @property
    def is_expired(self) -> bool:
        """True si el certificado ya expiró."""
        try:
            exp = datetime.fromisoformat(self.not_after.replace("Z", "+00:00"))
            return datetime.now(UTC) > exp
        except (ValueError, AttributeError):
            return True


def load_pfx(pfx_path: str | Path, password: str | bytes) -> CertBundle:
    """Carga .pfx/.p12 (Brasil ICP-Brasil, México CSD).

    Args:
        pfx_path: Path al archivo .pfx o .p12.
        password: Contraseña del archivo (str o bytes).

    Returns:
        CertBundle con private_key_pem, cert_pem, ca_chain_pem.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si la contraseña es incorrecta o el formato es inválido.
    """
    if isinstance(password, str):
        password = password.encode()

    path = Path(pfx_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo PFX no encontrado: {pfx_path}")

    pfx_data = path.read_bytes()
    private_key, cert, additional_certs = pkcs12.load_key_and_certificates(
        pfx_data, password
    )

    if private_key is None or cert is None:
        raise ValueError("PFX no contiene clave privada o certificado")

    return _build_bundle(private_key, cert, additional_certs)


def load_pem(
    key_path: str | Path,
    cert_path: str | Path,
    ca_path: str | Path | None = None,
    password: str | bytes | None = None,
) -> CertBundle:
    """Carga .pem (Chile e-Cert, Argentina, Colombia, Peru).

    Args:
        key_path: Path al archivo .key (PEM).
        cert_path: Path al archivo .cer/.crt (PEM).
        ca_path: Path opcional al CA chain (PEM).
        password: Contraseña de la clave privada (opcional).

    Returns:
        CertBundle con private_key_pem, cert_pem, ca_chain_pem.
    """
    if isinstance(password, str):
        password = password.encode() if password else None

    key_p = Path(key_path)
    cert_p = Path(cert_path)
    if not key_p.exists():
        raise FileNotFoundError(f"Archivo key no encontrado: {key_path}")
    if not cert_p.exists():
        raise FileNotFoundError(f"Archivo cert no encontrado: {cert_path}")

    private_key = load_pem_private_key(key_p.read_bytes(), password=password)
    cert = x509.load_pem_x509_certificate(cert_p.read_bytes())

    additional = []
    if ca_path:
        ca_p = Path(ca_path)
        if ca_p.exists():
            additional = list(x509.load_pem_x509_certificates(ca_p.read_bytes()))

    return _build_bundle(private_key, cert, additional or None)


def _build_bundle(
    private_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey,
    cert: x509.Certificate,
    additional_certs: list[x509.Certificate] | None = None,
) -> CertBundle:
    """Construye CertBundle desde objetos cryptography."""
    key_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    cert_pem = cert.public_bytes(Encoding.PEM)
    ca_pem = None
    if additional_certs:
        ca_pem = b"".join(c.public_bytes(Encoding.PEM) for c in additional_certs)

    return CertBundle(
        private_key_pem=key_pem,
        cert_pem=cert_pem,
        ca_chain_pem=ca_pem,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        serial_number=hex(cert.serial_number),
    )


def get_cert_info(bundle: CertBundle) -> dict[str, Any]:
    """Devuelve información del certificado como dict."""
    return {
        "subject": bundle.subject,
        "issuer": bundle.issuer,
        "not_before": bundle.not_before,
        "not_after": bundle.not_after,
        "serial_number": bundle.serial_number,
        "is_expired": bundle.is_expired,
        "has_ca_chain": bundle.ca_chain_pem is not None,
    }
