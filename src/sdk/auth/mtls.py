"""
Connector SDK — MTLSAuth
========================

Autenticacion mTLS (Mutual TLS) con certificado de cliente.
Configura la peticion para usar un certificado de cliente
y clave privada para autenticacion mutua TLS.
"""

from __future__ import annotations

import os
from typing import Any

from src.sdk.auth.base import AuthProvider
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class MTLSAuth(AuthProvider):
    """
    Autenticacion mTLS (Mutual TLS) con certificado de cliente.

    Configura la peticion para usar un certificado de cliente
    y clave privada para autenticacion mutua TLS.

    Args:
        cert_path: Ruta al certificado de cliente (PEM)
        key_path: Ruta a la clave privada del cliente (PEM)
        ca_path: Ruta al certificado CA para verificar el servidor (PEM)
        cert_password: Password para la clave privada (opcional)
    """

    def __init__(
        self,
        cert_path: str,
        key_path: str,
        ca_path: str | None = None,
        cert_password: str | None = None,
    ) -> None:
        self._cert_path = cert_path
        self._key_path = key_path
        self._ca_path = ca_path
        self._cert_password = cert_password

    def apply_auth(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Aplica la configuracion mTLS a la peticion.

        Agrega los certificados de cliente y CA a la peticion
        para que el transporte HTTP los use durante el handshake TLS.

        Args:
            request: Peticion HTTP

        Retorna:
            Peticion con la configuracion de certificados TLS aplicada
        """
        cert_tuple: tuple[str, str] | tuple[str, str, str] = (self._cert_path, self._key_path)
        if self._cert_password:
            cert_tuple = (self._cert_path, self._key_path, self._cert_password)

        request["cert"] = cert_tuple
        if self._ca_path:
            request["verify"] = self._ca_path

        logger.debug("MTLSAuth: certificados de cliente configurados para mTLS")
        return request

    def refresh(self) -> bool:
        """Los certificados mTLS no soportan renovacion automatica."""
        return False

    def is_expired(self) -> bool:
        """
        Verifica si el certificado de cliente ha expirado.

        Lee el certificado PEM y verifica la fecha de expiracion.

        Retorna:
            True si el certificado expiro
        """
        try:
            from datetime import UTC, datetime

            from cryptography import x509

            with open(self._cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            return cert.not_valid_after_utc < datetime.now(UTC)
        except ImportError:
            logger.debug("MTLSAuth: cryptography no instalado, no se puede verificar expiracion")
            return False
        except FileNotFoundError:
            logger.warning(f"MTLSAuth: certificado no encontrado en {self._cert_path}")
            return True
        except Exception as e:
            logger.warning(f"MTLSAuth: error verificando expiracion del certificado: {e}")
            return False

    def validate(self) -> bool:
        """
        Valida que los archivos de certificado y clave existan.

        Retorna:
            True si ambos archivos existen
        """
        cert_exists = os.path.isfile(self._cert_path)
        key_exists = os.path.isfile(self._key_path)
        if not cert_exists:
            logger.warning(f"MTLSAuth: certificado no encontrado: {self._cert_path}")
        if not key_exists:
            logger.warning(f"MTLSAuth: clave privada no encontrada: {self._key_path}")
        return cert_exists and key_exists

    def to_dict(self) -> dict[str, Any]:
        """Serializa la config de mTLS (oculta el password)."""
        result = super().to_dict()
        result["cert_path"] = self._cert_path
        result["key_path"] = self._key_path
        result["ca_path"] = self._ca_path
        result["has_password"] = bool(self._cert_password)
        return result
