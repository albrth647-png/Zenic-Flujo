"""
Workflow Determinista — LicenseGenerator (Ed25519)
Genera License Keys firmadas con Ed25519.
"""

import base64
import random
from datetime import datetime, timedelta

from src.license.keys import load_private_key
from src.license.validator import LICENSE_CHARSET

CHARSET = LICENSE_CHARSET


class LicenseGenerator:
    """
    Genera License Keys firmadas con Ed25519.

    Almacena la firma completa (base64url) internamente para que
    LicenseValidator pueda acceder a ella durante activate_key().
    """

    def __init__(self):
        self._last_signature_b64: str = ""
        self._last_payload: str = ""

    @property
    def last_signature_b64(self) -> str:
        """Retorna la última firma completa en base64url (sin padding)."""
        return self._last_signature_b64

    @property
    def last_payload(self) -> str:
        """Retorna el último payload firmado."""
        return self._last_payload

    def generate(
        self,
        admin_password: str,
        license_type: str = "individual",
        client_name: str = "",
        days_valid: int = 365,
    ) -> str:
        if not load_private_key(admin_password):
            raise ValueError("Clave privada no disponible o contraseña incorrecta")

        private_key = load_private_key(admin_password)
        expiry = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d")
        payload = f"{license_type}|{client_name}|{expiry}"
        self._last_payload = payload

        signature = private_key.sign(payload.encode())
        sig_b64url = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        self._last_signature_b64 = sig_b64url

        # Tomar primeros 12 chars de la firma base64url y reemplazar chars que
        # puedan romper el split por "-" (base64url usa "-" y "_")
        sig_fragment = sig_b64url[:12].replace("-", "Z").replace("_", "X")

        blocks = [
            sig_fragment[0:4],
            sig_fragment[4:8],
            sig_fragment[8:12],
            "".join(random.choice(CHARSET) for _ in range(4)),
        ]
        return f"WFD-{blocks[0]}-{blocks[1]}-{blocks[2]}-{blocks[3]}"
