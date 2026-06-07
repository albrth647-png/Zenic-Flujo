"""
Workflow Determinista — LicenseGenerator
Genera License Keys usando HMAC-SHA256.
"""
import hmac
import hashlib
import random
from datetime import datetime, timedelta

from src.config import LICENSE_SECRET_KEY

CHARSET = "BCDFGHJKLMNPQRSTVWXYZ23456789"


class LicenseGenerator:
    def generate(self, license_type: str = "individual",
                 client_name: str = "", days_valid: int = 365) -> str:
        expiry = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d")
        payload = f"{license_type}|{client_name}|{expiry}"
        sig = hmac.new(
            LICENSE_SECRET_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:12].upper()
        blocks = [
            sig[:4], sig[4:8], sig[8:12],
            "".join(random.choice(CHARSET) for _ in range(4)),
        ]
        return f"WFD-{blocks[0]}-{blocks[1]}-{blocks[2]}-{blocks[3]}"
