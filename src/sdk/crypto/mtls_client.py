"""HttpClient con mTLS (mutual TLS) para webservices de gobierno LATAM.

AFIP (AR), SEFAZ (BR), SII (CL), DIAN (CO), SUNAT (PE), SRI (EC)
requieren autenticación con certificado cliente (mTLS).

Usa requests (Apache-2.0) con cert=(cert_path, key_path) + verify=ca_bundle.

Uso:
    from src.sdk.crypto.mtls_client import MTLSHttpClient
    client = MTLSHttpClient(cert_path="cert.pem", key_path="key.pem", ca_path="ca.pem")
    resp = client.post("https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
                       data=soap_body, headers={"Content-Type": "text/xml"})
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


class MTLSHttpClient:
    """Cliente HTTP con mutual TLS (certificado cliente + CA verify).

    Args:
        cert_path: Path al certificado cliente (.pem o .pfx convertido a PEM).
        key_path: Path a la clave privada (.pem).
        ca_path: Path al CA bundle para verificar el servidor (opcional).
        timeout: Timeout por defecto en segundos (default 30).
        verify: Si True, verifica certificado del servidor (default True).
    """

    def __init__(
        self,
        cert_path: str | Path | None = None,
        key_path: str | Path | None = None,
        ca_path: str | Path | None = None,
        timeout: int = 30,
        verify: bool = True,
    ) -> None:
        self._timeout = timeout
        self._verify: str | bool = verify

        # Configurar cert cliente
        if cert_path and key_path:
            cert_p = Path(cert_path)
            key_p = Path(key_path)
            if not cert_p.exists():
                raise FileNotFoundError(f"Cert no encontrado: {cert_path}")
            if not key_p.exists():
                raise FileNotFoundError(f"Key no encontrada: {key_path}")
            self._cert = (str(cert_p), str(key_p))
        elif cert_path:
            # cert_path puede ser un .pem que contiene ambos
            cert_p = Path(cert_path)
            if not cert_p.exists():
                raise FileNotFoundError(f"Cert no encontrado: {cert_path}")
            self._cert = str(cert_p)
        else:
            self._cert = None

        # Configurar CA bundle
        if ca_path:
            ca_p = Path(ca_path)
            if not ca_p.exists():
                raise FileNotFoundError(f"CA bundle no encontrado: {ca_path}")
            self._verify = str(ca_p)

        self._session = requests.Session()
        if self._cert:
            self._session.cert = self._cert
        self._session.verify = self._verify

        logger.debug("MTLSHttpClient inicializado: cert=%s verify=%s",
                      bool(self._cert), bool(self._verify))

    # legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
    def get(self, url: str, **kwargs: Any) -> requests.Response:
        """GET request con mTLS."""
        kwargs.setdefault("timeout", self._timeout)
        return self._session.get(url, **kwargs)

    # legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
    def post(self, url: str, data: Any = None, **kwargs: Any) -> requests.Response:
        """POST request con mTLS."""
        kwargs.setdefault("timeout", self._timeout)
        return self._session.post(url, data=data, **kwargs)

    # legítimo: wrapper genérico, **kwargs se pasa al SDK subyacente (skill §1.2)
    def put(self, url: str, data: Any = None, **kwargs: Any) -> requests.Response:
        """PUT request con mTLS."""
        kwargs.setdefault("timeout", self._timeout)
        return self._session.put(url, data=data, **kwargs)

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()

    def __enter__(self) -> MTLSHttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
