"""
Workflow Determinista — MFA TOTP (Phase 0)

Sistema de autenticación multi-factor basado en TOTP (Time-based One-Time Password).
Compatible con apps autenticadoras: Google Authenticator, Authy, Microsoft Authenticator, etc.

Funcionalidades:
- Generar secreto TOTP por usuario
- Generar URI de aprovisionamiento (otpauth://) para QR codes
- Verificar códigos TOTP de 6 dígitos
- Códigos de recuperación (10 códigos de un solo uso, hasheados con bcrypt)
- Confiar en dispositivo ("Recordarme" por 30 días, token firmado)
- Habilitar/deshabilitar MFA por usuario
"""

import hashlib
import hmac
import json
import secrets
import struct
import time

from src.data.database_manager import DatabaseManager
from src.utils.logger import setup_logging
from typing import Any

logger = setup_logging(__name__)

# ── Constantes TOTP ──────────────────────────────────────────

TOTP_PERIOD: int = 30  # segundos por paso
TOTP_DIGITS: int = 6
TOTP_ALGORITHM: str = "SHA1"
RECOVERY_CODE_COUNT: int = 10
TRUSTED_DEVICE_DAYS: int = 30
ISSUER_NAME: str = "Zenic-Flijo"


def _hotp(secret: bytes, counter: int, digits: int = TOTP_DIGITS) -> str:
    """
    Genera un código HOTP (HMAC-based One-Time Password).

    Implementación RFC 4226 sin dependencia externa.

    Args:
        secret: Clave secreta en bytes
        counter: Contador (para TOTP = floor(time / period))
        digits: Número de dígitos del código

    Returns:
        Código OTP como string de 6 dígitos
    """
    # Codificar counter como big-endian 8 bytes
    counter_bytes = struct.pack(">Q", counter)
    # HMAC-SHA1
    hmac_hash = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    # Dynamic truncation (RFC 4226)
    offset = hmac_hash[-1] & 0x0F
    code = struct.unpack(">I", hmac_hash[offset : offset + 4])[0]
    code &= 0x7FFFFFFF  # Mask para 31 bits
    code %= 10**digits
    return str(code).zfill(digits)


def _generate_totp(secret: bytes, timestamp: int | None = None, period: int = TOTP_PERIOD) -> str:
    """
    Genera un código TOTP (Time-based One-Time Password).

    Implementación RFC 6238 sin dependencia externa.

    Args:
        secret: Clave secreta en bytes
        timestamp: Timestamp Unix (default: ahora)
        period: Período en segundos

    Returns:
        Código TOTP como string de 6 dígitos
    """
    if timestamp is None:
        timestamp = int(time.time())
    counter = timestamp // period
    return _hotp(secret, counter)


def _base32_encode(data: bytes) -> str:
    """Codifica bytes a Base32 sin padding (formato estándar para TOTP)."""
    import base64

    return base64.b32encode(data).decode("ascii").rstrip("=")


def _generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """
    Genera códigos de recuperación de un solo uso.

    Formato: XXXX-XXXX (8 caracteres alfanuméricos, separados por guion).

    Args:
        count: Número de códigos a generar

    Returns:
        Lista de códigos de recuperación
    """
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()  # 8 hex chars
        code = f"{raw[:4]}-{raw[4:]}"
        codes.append(code)
    return codes


def _hash_recovery_code(code: str) -> str:
    """
    Hashea un código de recuperación con bcrypt.

    Args:
        code: Código en texto plano

    Returns:
        Hash bcrypt del código
    """
    import bcrypt

    return bcrypt.hashpw(code.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_recovery_hash(code: str, hash_value: str) -> bool:
    """
    Verifica un código de recuperación contra su hash bcrypt.

    Args:
        code: Código en texto plano
        hash_value: Hash bcrypt almacenado

    Returns:
        True si el código coincide
    """
    import bcrypt

    try:
        return bcrypt.checkpw(code.encode(), hash_value.encode())
    except (ValueError, TypeError):
        return False


class MFAService:
    """Servicio de autenticación multi-factor (TOTP)."""

    def __init__(self) -> None:
        self._db = DatabaseManager()
        self._ensure_columns()

    # ── Inicialización ────────────────────────────────────

    def _ensure_columns(self) -> None:
        """Agrega columnas MFA a la tabla users si no existen (migración)."""
        conn = self._db.get_connection()
        cursor = conn.cursor()

        # Migración: users.mfa_secret
        try:
            cursor.execute("SELECT mfa_secret FROM users LIMIT 1")
        except Exception:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_secret TEXT")
            conn.commit()
            logger.info("Migración: users.mfa_secret agregada")

        # Migración: users.mfa_enabled
        try:
            cursor.execute("SELECT mfa_enabled FROM users LIMIT 1")
        except Exception:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER DEFAULT 0")
            conn.commit()
            logger.info("Migración: users.mfa_enabled agregada")

        # Migración: users.mfa_recovery_codes
        try:
            cursor.execute("SELECT mfa_recovery_codes FROM users LIMIT 1")
        except Exception:
            cursor.execute("ALTER TABLE users ADD COLUMN mfa_recovery_codes TEXT")
            conn.commit()
            logger.info("Migración: users.mfa_recovery_codes agregada")

    # ── Generación de secreto ─────────────────────────────

    def generate_secret(self, user_id: int) -> dict[str, Any]:
        """
        Genera un secreto TOTP para un usuario y lo almacena.

        El secreto NO activa MFA automáticamente; se debe llamar a enable_mfa()
        después de verificar que el usuario puede generar códigos válidos.

        Args:
            user_id: ID del usuario

        Returns:
            dict con: status, secret, provisioning_uri
        """
        user = self._db.fetchone(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        )
        if not user:
            return {"status": "error", "message": f"Usuario {user_id} no encontrado"}

        # Generar secreto aleatorio de 20 bytes (160 bits, estándar TOTP)
        secret_bytes = secrets.token_bytes(20)
        secret_b32 = _base32_encode(secret_bytes)

        # Almacenar secreto (no habilita MFA todavía)
        self._db.execute(
            "UPDATE users SET mfa_secret = ? WHERE id = ?",
            (secret_b32, user_id),
        )
        self._db.commit()

        # Generar URI de aprovisionamiento
        username = user.get("username", f"user_{user_id}")
        uri = self.get_provisioning_uri(user_id, username)

        logger.info(f"MFA: Secreto generado para usuario {user_id}")
        return {
            "status": "ok",
            "secret": secret_b32,
            "provisioning_uri": uri,
        }

    def get_provisioning_uri(self, user_id: int, username: str) -> str:
        """
        Genera la URI otpauth:// para escanear con una app autenticadora.

        Formato: otpauth://totp/Zenic-Flijo:username?secret=XXX&issuer=Zenic-Flijo

        Args:
            user_id: ID del usuario
            username: Nombre de usuario (para la etiqueta)

        Returns:
            URI otpauth:// como string
        """
        user = self._db.fetchone("SELECT mfa_secret FROM users WHERE id = ?", (user_id,))
        if not user or not user.get("mfa_secret"):
            return ""

        secret = user["mfa_secret"]
        # Formato estándar otpauth://
        label = f"{ISSUER_NAME}:{username}"
        uri = (
            f"otpauth://totp/{label}"
            f"?secret={secret}"
            f"&issuer={ISSUER_NAME}"
            f"&algorithm={TOTP_ALGORITHM}"
            f"&digits={TOTP_DIGITS}"
            f"&period={TOTP_PERIOD}"
        )
        return uri

    # ── Verificación de código ────────────────────────────

    def verify_code(self, user_id: int, code: str) -> dict[str, Any]:
        """
        Verifica un código TOTP de 6 dígitos.

        Acepta el código del período actual y el anterior (tolerancia de 1 paso
        = 30 segundos) para compensar desync de reloj.

        Args:
            user_id: ID del usuario
            code: Código TOTP de 6 dígitos

        Returns:
            dict con: valid (bool), message
        """
        user = self._db.fetchone("SELECT mfa_secret, mfa_enabled FROM users WHERE id = ?", (user_id,))
        if not user:
            return {"valid": False, "message": "Usuario no encontrado"}

        if not user.get("mfa_secret"):
            return {"valid": False, "message": "MFA no configurado para este usuario"}

        secret_b32 = user["mfa_secret"]

        # Decodificar secreto Base32 a bytes
        import base64

        # Agregar padding si es necesario
        padding = 8 - len(secret_b32) % 8
        secret_b32_padded = secret_b32 + "=" * padding if padding != 8 else secret_b32

        try:
            secret_bytes = base64.b32decode(secret_b32_padded)
        except Exception:
            return {"valid": False, "message": "Secreto TOTP inválido"}

        # Verificar código actual y ±1 ventana (3 códigos: anterior, actual, siguiente)
        now = int(time.time())
        valid = False
        for offset in range(-1, 2):
            expected = _generate_totp(secret_bytes, now + offset * TOTP_PERIOD)
            if hmac.compare_digest(code, expected):
                valid = True
                break

        if valid:
            return {"valid": True, "message": "Código TOTP verificado"}
        else:
            return {"valid": False, "message": "Código TOTP inválido"}

    # ── Códigos de recuperación ───────────────────────────

    def generate_recovery_codes(self, user_id: int) -> dict[str, Any]:
        """
        Genera códigos de recuperación para un usuario.

        Los códigos se almacenan hasheados con bcrypt. Solo se muestran una vez
        en la respuesta; después solo se pueden verificar, no recuperar.

        Args:
            user_id: ID del usuario

        Returns:
            dict con: status, recovery_codes (texto plano, solo esta vez)
        """
        user = self._db.fetchone("SELECT id, mfa_secret FROM users WHERE id = ?", (user_id,))
        if not user:
            return {"status": "error", "message": f"Usuario {user_id} no encontrado"}

        if not user.get("mfa_secret"):
            return {"status": "error", "message": "Debe configurar MFA primero"}

        # Generar códigos y hashearlos
        plain_codes = _generate_recovery_codes(RECOVERY_CODE_COUNT)
        hashed_codes = [_hash_recovery_code(c) for c in plain_codes]

        self._db.execute(
            "UPDATE users SET mfa_recovery_codes = ? WHERE id = ?",
            (json.dumps(hashed_codes), user_id),
        )
        self._db.commit()

        logger.info(f"MFA: {RECOVERY_CODE_COUNT} códigos de recuperación generados para usuario {user_id}")
        return {
            "status": "ok",
            "recovery_codes": plain_codes,
            "message": "Guarda estos códigos en un lugar seguro. No se volverán a mostrar.",
        }

    def verify_recovery_code(self, user_id: int, code: str) -> dict[str, Any]:
        """
        Verifica y consume un código de recuperación.

        Una vez verificado, el código se elimina de la lista y no puede
        volver a usarse.

        Args:
            user_id: ID del usuario
            code: Código de recuperación (formato: XXXX-XXXX)

        Returns:
            dict con: valid (bool), message, remaining_codes
        """
        user = self._db.fetchone("SELECT mfa_recovery_codes FROM users WHERE id = ?", (user_id,))
        if not user:
            return {"valid": False, "message": "Usuario no encontrado"}

        raw_codes = user.get("mfa_recovery_codes")
        if not raw_codes:
            return {"valid": False, "message": "No hay códigos de recuperación configurados"}

        hashed_codes: list[str] = json.loads(raw_codes)

        # Buscar y verificar el código
        found_index = -1
        for i, hashed in enumerate(hashed_codes):
            if _verify_recovery_hash(code, hashed):
                found_index = i
                break

        if found_index == -1:
            return {"valid": False, "message": "Código de recuperación inválido"}

        # Consumir el código (remover de la lista)
        hashed_codes.pop(found_index)
        self._db.execute(
            "UPDATE users SET mfa_recovery_codes = ? WHERE id = ?",
            (json.dumps(hashed_codes), user_id),
        )
        self._db.commit()

        remaining = len(hashed_codes)
        logger.info(f"MFA: Código de recuperación usado por usuario {user_id}. Quedan {remaining}")

        if remaining < 3:
            return {
                "valid": True,
                "message": f"Código verificado. ADVERTENCIA: solo quedan {remaining} códigos.",
                "remaining_codes": remaining,
            }

        return {
            "valid": True,
            "message": "Código de recuperación verificado",
            "remaining_codes": remaining,
        }

    # ── Habilitar/deshabilitar MFA ────────────────────────

    def enable_mfa(self, user_id: int) -> dict[str, Any]:
        """
        Habilita MFA para un usuario.

        Requiere que el secreto TOTP ya haya sido generado.

        Args:
            user_id: ID del usuario

        Returns:
            dict con: status, message
        """
        user = self._db.fetchone("SELECT mfa_secret, mfa_enabled FROM users WHERE id = ?", (user_id,))
        if not user:
            return {"status": "error", "message": f"Usuario {user_id} no encontrado"}

        if not user.get("mfa_secret"):
            return {"status": "error", "message": "Debe generar el secreto TOTP primero"}

        if user.get("mfa_enabled"):
            return {"status": "ok", "message": "MFA ya estaba habilitado"}

        self._db.execute("UPDATE users SET mfa_enabled = 1 WHERE id = ?", (user_id,))
        self._db.commit()

        # Generar códigos de recuperación automáticamente
        recovery = self.generate_recovery_codes(user_id)

        self._db.audit("mfa.enabled", f"MFA habilitado para usuario {user_id}", user_id=user_id)
        logger.info(f"MFA: Habilitado para usuario {user_id}")

        return {
            "status": "ok",
            "message": "MFA habilitado exitosamente",
            "recovery_codes": recovery.get("recovery_codes", []),
        }

    def disable_mfa(self, user_id: int) -> dict[str, Any]:
        """
        Deshabilita MFA para un usuario.

        Args:
            user_id: ID del usuario

        Returns:
            dict con: status, message
        """
        user = self._db.fetchone("SELECT mfa_enabled FROM users WHERE id = ?", (user_id,))
        if not user:
            return {"status": "error", "message": f"Usuario {user_id} no encontrado"}

        self._db.execute(
            "UPDATE users SET mfa_enabled = 0, mfa_secret = NULL, mfa_recovery_codes = NULL WHERE id = ?",
            (user_id,),
        )
        self._db.commit()

        self._db.audit("mfa.disabled", f"MFA deshabilitado para usuario {user_id}", user_id=user_id)
        logger.info(f"MFA: Deshabilitado para usuario {user_id}")
        return {"status": "ok", "message": "MFA deshabilitado"}

    def is_mfa_enabled(self, user_id: int) -> dict[str, Any]:
        """
        Verifica si MFA está habilitado para un usuario.

        Args:
            user_id: ID del usuario

        Returns:
            dict con: enabled (bool), has_secret (bool)
        """
        user = self._db.fetchone("SELECT mfa_enabled, mfa_secret FROM users WHERE id = ?", (user_id,))
        if not user:
            return {"enabled": False, "has_secret": False}

        return {
            "enabled": bool(user.get("mfa_enabled")),
            "has_secret": bool(user.get("mfa_secret")),
        }

    # ── Confiar en dispositivo ────────────────────────────

    def trust_device(self, user_id: int, days: int = TRUSTED_DEVICE_DAYS) -> dict[str, Any]:
        """
        Genera un token de dispositivo confiable.

        El token se almacena como cookie firmada en el navegador del usuario.
        Mientras el token sea válido, no se solicitará MFA en ese dispositivo.

        Args:
            user_id: ID del usuario
            days: Días de validez del token

        Returns:
            dict con: status, token, expires_at
        """
        import base64

        from src.config import SESSION_SECRET

        # Generar token aleatorio
        token_raw = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + days * 86400

        # Crear payload: user_id:token:expires
        payload = f"{user_id}:{token_raw}:{expires_at}"

        # Firmar con HMAC-SHA256 usando SESSION_SECRET
        signature = hmac.new(
            SESSION_SECRET.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Token final: base64(payload:signature)
        token_data = f"{payload}:{signature}"
        token = base64.urlsafe_b64encode(token_data.encode()).decode()

        # Almacenar hash del token en DB para revocación
        token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
        self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (f"trusted_device:{user_id}:{token_hash}", str(expires_at)),
        )
        self._db.commit()

        logger.info(f"MFA: Dispositivo confiable registrado para usuario {user_id} ({days} días)")
        return {
            "status": "ok",
            "token": token,
            "expires_at": expires_at,
        }

    def verify_trusted_device(self, token: str) -> dict[str, Any]:
        """
        Verifica un token de dispositivo confiable.

        Args:
            token: Token de dispositivo (generado por trust_device)

        Returns:
            dict con: valid (bool), user_id (si válido), message
        """
        import base64

        from src.config import SESSION_SECRET

        try:
            # Decodificar token
            token_data = base64.urlsafe_b64decode(token.encode()).decode()
            parts = token_data.split(":")
            if len(parts) != 4:
                return {"valid": False, "message": "Token malformado"}

            user_id_str, token_raw, expires_str, signature = parts
            user_id = int(user_id_str)
            expires_at = int(expires_str)

            # Verificar expiración
            if time.time() > expires_at:
                return {"valid": False, "message": "Token expirado"}

            # Verificar firma
            payload = f"{user_id_str}:{token_raw}:{expires_str}"
            expected_sig = hmac.new(
                SESSION_SECRET.encode(),
                payload.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return {"valid": False, "message": "Firma inválida"}

            # Verificar que el token no fue revocado
            token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
            stored = self._db.get_setting(f"trusted_device:{user_id}:{token_hash}")
            if not stored:
                return {"valid": False, "message": "Token revocado"}

            return {
                "valid": True,
                "user_id": user_id,
                "message": "Dispositivo confiable verificado",
            }

        except Exception as e:
            logger.error(f"MFA: Error verificando dispositivo confiable: {e}")
            return {"valid": False, "message": "Token inválido"}

    def revoke_trusted_devices(self, user_id: int) -> dict[str, Any]:
        """
        Revoca todos los dispositivos confiables de un usuario.

        Args:
            user_id: ID del usuario

        Returns:
            dict con: status, revoked_count
        """
        all_settings = self._db.fetchall(
            "SELECT key FROM settings WHERE key LIKE ?",
            (f"trusted_device:{user_id}:%",),
        )
        revoked = 0
        for row in all_settings:
            self._db.execute("DELETE FROM settings WHERE key = ?", (row["key"],))
            revoked += 1
        self._db.commit()

        logger.info(f"MFA: {revoked} dispositivo(s) confiable(s) revocados para usuario {user_id}")
        return {"status": "ok", "revoked_count": revoked}
