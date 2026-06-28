"""
Workflow Determinista — LicenseValidator (Ed25519)
Valida License Keys firmadas con Ed25519 y gestiona período de prueba (trial) de 30 días.

La firma completa (base64url) se almacena en la columna signature_b64 de la tabla license
durante activate_key(). validate() la recupera y verifica con la clave pública Ed25519.

Bug LIC-01 (CRÍTICO): el validador debe re-verificar la firma criptográficamente
con la clave pública Ed25519 en CADA invocación de validate(), sin confiar en
que la firma almacenada en DB sea legítima. Si la DB se compromete y un atacante
inserta una fila con signature_b64 arbitraria, la verificación criptográfica
fallará (porque el atacante no tiene la clave privada) y validate() retornará
invalid. Defensa en profundidad: verificar longitud de firma (64 bytes para
Ed25519) y usar datetimes timezone-aware para evitar skew.
"""

import base64
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Any

from cryptography.exceptions import InvalidSignature

from src.core.config import TRIAL_DAYS
from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.license.keys import load_public_key

# Caracteres permitidos en License Keys (sin vocales para evitar palabras)
LICENSE_CHARSET = "BCDFGHJKLMNPQRSTVWXYZ23456789"

# Longitud esperada de una firma Ed25519 en bytes (defensa en profundidad).
ED25519_SIGNATURE_LEN = 64

logger = setup_logging(__name__)

# ── Foso 3: License tier gating ──────────────────────────────────────

TIER_FEATURES: dict[str, dict[str, int | bool]] = {
    "trial": {
        "max_leads": 10,
        "max_invoices_per_month": 5,
        "max_products": 20,
        # BUG-4 fix: WhatsApp ahora habilitado en trial con cuota baja para que
        # los usuarios puedan probar el canal principal desde el día 1.
        # Cuota: 10 mensajes/mes (suficiente para probar notificaciones).
        "whatsapp_enabled": True,
        "whatsapp_monthly_quota": 10,
        "pdf_invoices": False,
        "fiscal_electronic": False,
    },
    "individual": {
        "max_leads": 1000,
        "max_invoices_per_month": 100,
        "max_products": 500,
        "whatsapp_enabled": True,
        "pdf_invoices": True,
        "fiscal_electronic": False,
    },
    "reseller": {
        "max_leads": 10000,
        "max_invoices_per_month": 1000,
        "max_products": 5000,
        "whatsapp_enabled": True,
        "pdf_invoices": True,
        "fiscal_electronic": True,
    },
    "enterprise": {
        "max_leads": -1,
        "max_invoices_per_month": -1,
        "max_products": -1,
        "whatsapp_enabled": True,
        "pdf_invoices": True,
        "fiscal_electronic": True,
    },
}


def get_tier_features(license_type: str) -> dict[str, Any]:
    """Devuelve las features del tier de licencia."""
    return TIER_FEATURES.get(license_type, TIER_FEATURES["trial"])


def check_feature(license_type: str, feature: str) -> bool:
    """Verifica si una feature booleana está habilitada para el tier."""
    feats = get_tier_features(license_type)
    return bool(feats.get(feature, False))


def check_quota(license_type: str, resource: str, current_count: int) -> bool:
    """Verifica si el count actual está dentro del quota del tier.

    Args:
        license_type: trial | individual | reseller | enterprise
        resource: leads | invoices_per_month | products
        current_count: cantidad actual usada

    Returns:
        True si está dentro del quota, False si excedido.
    """
    feats = get_tier_features(license_type)
    max_val = feats.get(f"max_{resource}", 0)
    if max_val == -1:
        return True  # ilimitado
    return current_count < max_val


class LicenseValidator:
    LICENSE_TYPES: ClassVar[dict[str, int]] = {"individual": 1, "reseller": 10, "enterprise": -1}

    def __init__(self):
        self._db = DatabaseManager()

    def validate(self, key: str) -> dict[str, Any]:
        """Valida una License Key: formato, firma Ed25519, expiración.

        Bug LIC-01: la verificación criptográfica con la clave pública
        Ed25519 es la fuente de verdad. La firma almacenada en DB
        (``signature_b64``) NO se acepta por si sola: se re-verifica
        contra el payload reconstruido desde los campos visibles de la
        licencia. Si la DB se compromete y un atacante inserta una
        fila con ``signature_b64`` arbitraria, ``public_key.verify``
        fallará (porque el atacante no tiene la clave privada).

        Defensa en profundidad:
        - Longitud de firma Ed25519 = 64 bytes (rechazar antes de verify).
        - Datetimes timezone-aware para evitar skew.
        - Cualquier excepción en la verificación -> invalid.
        """
        key = key.strip().upper()
        parts = key.split("-")
        if len(parts) != 5 or parts[0] != "WFD":
            return {"valid": False, "reason": "Formato inválido"}
        # Verificar caracteres: blocks 1-3 son alfanuméricos (sin guiones para evitar ambigüedad en split)
        sig_fragment = "".join(parts[1:4])
        if not sig_fragment.isalnum():
            return {"valid": False, "reason": "Firma con caracteres inválidos"}
        if not all(c in LICENSE_CHARSET for c in parts[4]):
            return {"valid": False, "reason": "Caracteres inválidos en la key"}
        stored = self._db.fetchone("SELECT * FROM license WHERE key = ?", (key,))
        if not stored:
            return {"valid": False, "reason": "License Key no encontrada"}

        # ── Bug LIC-01: verificación criptográfica INCONDICIONAL ─────────
        # La firma almacenada en DB NO se acepta por si sola: se re-verifica
        # contra la clave pública Ed25519 cargada desde disco. Si la DB fue
        # comprometida, el atacante puede escribir cualquier signature_b64
        # pero NO puede generar una firma válida sin la clave privada.
        stored_sig_b64 = stored.get("signature_b64", "") or ""
        if not stored_sig_b64:
            return {"valid": False, "reason": "No hay firma almacenada para esta licencia"}

        public_key = load_public_key()
        if not public_key:
            return {"valid": False, "reason": "Clave pública no disponible — ejecute 'swarm tool generate_keypair'"}

        # Reconstruir el payload exacto que se firmó en generator.py:
        #   f"{license_type}|{client_name}|{expiry}"
        # Usamos los campos visibles de la DB (type/client_name/expires_at),
        # que son los mismos que se pasaron a LicenseGenerator.generate().
        payload = f"{stored['type']}|{stored['client_name'] or ''}|{stored['expires_at'] or ''}"

        try:
            # Agregar padding necesario para base64url decode
            padding = 4 - len(stored_sig_b64) % 4
            if padding != 4:
                stored_sig_b64 += "=" * padding
            signature_bytes = base64.urlsafe_b64decode(stored_sig_b64)
        except Exception as e:
            logger.warning(f"LicenseValidator: signature_b64 no es base64 válido para key {key[:20]}...: {e}")
            return {"valid": False, "reason": "Firma inválida — la key ha sido alterada"}

        # Defensa en profundidad (LIC-03): Ed25519 siempre produce 64 bytes.
        # Rechazar longitudes inesperadas antes de invocar verify para no
        # depender del comportamiento de la librería ante inputs maliciosos.
        if len(signature_bytes) != ED25519_SIGNATURE_LEN:
            logger.warning(
                f"LicenseValidator: longitud de firma inesperada ({len(signature_bytes)}) "
                f"para key {key[:20]}... — se esperaban {ED25519_SIGNATURE_LEN} bytes"
            )
            return {"valid": False, "reason": "Firma inválida — la key ha sido alterada"}

        # Verificación criptográfica con la clave pública Ed25519.
        # Si la DB fue comprometida y el atacante escribió su propia
        # signature_b64, esta verificación falla porque no tiene la
        # clave privada correspondiente a la pública embebida en el binario.
        try:
            public_key.verify(signature_bytes, payload.encode())
        except InvalidSignature as e:
            logger.warning(f"LicenseValidator: firma Ed25519 inválida para key {key[:20]}...: {e}")
            return {"valid": False, "reason": "Firma inválida — la key ha sido alterada"}
        except Exception as e:
            # Cualquier otro error durante verify() también debe invalidar.
            logger.warning(f"LicenseValidator: error verificando firma Ed25519 para key {key[:20]}...: {e}")
            return {"valid": False, "reason": "Firma inválida — la key ha sido alterada"}

        # ── Verificación de expiración (post-firma, timezone-aware) ──────
        # Bug LIC-04: comparar datetimes timezone-aware para evitar skew.
        if stored["expires_at"]:
            try:
                # La fecha se almacena como YYYY-MM-DD (ver generator.py + activate_key).
                # Interpretarla como UTC start-of-day para comparación consistente.
                expiry = datetime.strptime(stored["expires_at"], "%Y-%m-%d").replace(tzinfo=UTC)
                if expiry < datetime.now(UTC):
                    return {"valid": False, "reason": "Licencia expirada"}
            except ValueError:
                return {"valid": False, "reason": "Fecha de expiración inválida"}

        return {
            "valid": True,
            "type": stored["type"],
            "client_name": stored["client_name"],
            "expires_at": stored["expires_at"],
        }

    def get_trial_status(self) -> dict[str, Any]:
        trial = self._db.fetchone("SELECT * FROM license WHERE is_trial = 1 ORDER BY trial_started_at DESC LIMIT 1")
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

    def get_license_info(self) -> dict[str, Any]:
        # Primero buscar licencia paga activa (tiene prioridad sobre trial)
        paid = self._db.fetchone("SELECT * FROM license WHERE is_trial = 0 ORDER BY issued_at DESC LIMIT 1")
        if paid:
            # Verificar expiración
            if paid["expires_at"]:
                try:
                    expiry = datetime.strptime(paid["expires_at"], "%Y-%m-%d")
                    if expiry >= datetime.now():
                        return {
                            "type": paid["type"],
                            "client_name": paid["client_name"],
                            "expires_at": paid["expires_at"],
                            "is_trial": False,
                        }
                except ValueError:
                    pass
            else:
                # Sin expiración (licencia perpetua)
                return {
                    "type": paid["type"],
                    "client_name": paid["client_name"],
                    "expires_at": None,
                    "is_trial": False,
                }
        # Si no hay paga activa, usar trial
        trial = self.get_trial_status()
        if trial["status"] == "active" and trial["is_trial"]:
            return {"type": "free", "is_trial": True, "days_left": trial["days_left"]}
        return {"type": "free", "is_trial": True, "days_left": TRIAL_DAYS}

    def activate_key(
        self,
        key: str,
        license_type: str = "individual",
        client_name: str = "",
        days_valid: int = 365,
        signature_b64: str = "",
    ) -> dict[str, Any]:
        """Activa una License Key y almacena la firma Ed25519 completa."""
        expiry = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d") if days_valid else None
        # Normalizar a mayúsculas para consistencia con validate() que hace key.upper()
        normalized_key = key.strip().upper()
        self._db.execute(
            "INSERT OR REPLACE INTO license (key, type, client_name, expires_at, signature_b64) VALUES (?, ?, ?, ?, ?)",
            (normalized_key, license_type, client_name, expiry, signature_b64),
        )
        self._db.commit()
        logger.info(f"Licencia activada: {normalized_key} ({license_type})")
        return {"valid": True, "type": license_type, "expires_at": expiry}
