"""
Workflow Determinista — LicenseValidator
Valida License Keys y gestiona período de prueba (trial) de 30 días.
"""
import hmac
import hashlib
from datetime import datetime, timedelta

from src.data.database_manager import DatabaseManager
from src.config import LICENSE_SECRET_KEY, TRIAL_DAYS

# Caracteres permitidos en License Keys (sin vocales para evitar palabras)
LICENSE_CHARSET = "BCDFGHJKLMNPQRSTVWXYZ23456789"
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class LicenseValidator:
    LICENSE_TYPES = {"individual": 1, "reseller": 10, "enterprise": -1}

    def __init__(self):
        self._db = DatabaseManager()

    def validate(self, key: str) -> dict:
        """Valida una License Key: formato, firma HMAC, expiración."""
        key = key.strip().upper()
        parts = key.split("-")
        if len(parts) != 5 or parts[0] != "WFD":
            return {"valid": False, "reason": "Formato inválido"}
        # Verificar caracteres: first 3 blocks are HMAC hex, last block uses LICENSE_CHARSET
        sig_body = "".join(parts[1:4])
        if not all(c in "0123456789ABCDEF" for c in sig_body):
            return {"valid": False, "reason": "Firma HMAC con caracteres inválidos"}
        if not all(c in LICENSE_CHARSET for c in parts[4]):
            return {"valid": False, "reason": "Caracteres inválidos en la key"}
        stored = self._db.fetchone("SELECT * FROM license WHERE key = ?", (key,))
        if not stored:
            return {"valid": False, "reason": "License Key no encontrada"}
        if stored["expires_at"]:
            try:
                expiry = datetime.strptime(stored["expires_at"], "%Y-%m-%d")
                if expiry < datetime.now():
                    return {"valid": False, "reason": "Licencia expirada"}
            except ValueError:
                return {"valid": False, "reason": "Fecha de expiración inválida"}
        # Verificar firma HMAC
        payload = f"{stored['type']}|{stored['client_name'] or ''}|{stored['expires_at'] or ''}"
        expected_sig = hmac.new(
            LICENSE_SECRET_KEY.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()[:12].upper()
        stored_sig = "".join(parts[1:4])
        if not hmac.compare_digest(expected_sig, stored_sig):
            return {"valid": False, "reason": "Firma HMAC inválida — la key ha sido alterada"}
        return {
            "valid": True,
            "type": stored["type"],
            "client_name": stored["client_name"],
            "expires_at": stored["expires_at"],
        }

    def get_trial_status(self) -> dict:
        trial = self._db.fetchone(
            "SELECT * FROM license WHERE is_trial = 1 ORDER BY trial_started_at DESC LIMIT 1"
        )
        if not trial:
            self._start_trial()
            return {"status": "active", "days_left": TRIAL_DAYS, "is_trial": True}
        started = datetime.strptime(trial["trial_started_at"], "%Y-%m-%dT%H:%M:%S.%f")
        elapsed = (datetime.now() - started).days
        if elapsed >= TRIAL_DAYS:
            return {"status": "expired", "days_left": 0, "is_trial": True}
        return {"status": "active", "days_left": TRIAL_DAYS - elapsed, "is_trial": True}

    def _start_trial(self):
        from datetime import datetime as dt
        now = dt.now().isoformat()
        self._db.execute(
            "INSERT INTO license (key, type, is_trial, trial_started_at) VALUES (?, 'trial', 1, ?)",
            ("TRIAL", now),
        )
        self._db.commit()

    def get_license_info(self) -> dict:
        trial = self.get_trial_status()
        if trial["status"] == "active" and trial["is_trial"]:
            return {"type": "free", "is_trial": True, "days_left": trial["days_left"]}
        key_row = self._db.fetchone(
            "SELECT * FROM license WHERE is_trial = 0 ORDER BY issued_at DESC LIMIT 1"
        )
        if key_row:
            return {
                "type": key_row["type"],
                "client_name": key_row["client_name"],
                "expires_at": key_row["expires_at"],
                "is_trial": False,
            }
        return {"type": "free", "is_trial": True, "days_left": TRIAL_DAYS}

    def activate_key(self, key: str, license_type: str = "individual",
                     client_name: str = "", days_valid: int = 365) -> dict:
        expiry = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d") if days_valid else None
        self._db.execute(
            "INSERT OR REPLACE INTO license (key, type, client_name, expires_at) VALUES (?, ?, ?, ?)",
            (key, license_type, client_name, expiry),
        )
        self._db.commit()
        logger.info(f"Licencia activada: {key} ({license_type})")
        return {"valid": True, "type": license_type, "expires_at": expiry}
