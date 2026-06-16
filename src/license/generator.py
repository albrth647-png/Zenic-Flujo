"""
Workflow Determinista — LicenseGenerator (Ed25519)
Genera License Keys firmadas con Ed25519.
"""

import base64
import random
from datetime import datetime, timedelta

from src.config import LICENSE_SECRET_KEY
from src.license.keys import load_private_key
from src.license.validator import LICENSE_CHARSET

CHARSET = LICENSE_CHARSET


class LicenseGenerator:
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

        signature = private_key.sign(payload.encode())
        sig_b64url = base64.urlsafe_b64encode(signature).decode().rstrip("=")

        blocks = [
            sig_b64url[0:4],
            sig_b64url[4:8],
            sig_b64url[8:12],
            "".join(random.choice(CHARSET) for _ in range(4)),
        ]
        return f"WFD-{blocks[0]}-{blocks[1]}-{blocks[2]}-{blocks[3]}"