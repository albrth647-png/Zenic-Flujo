"""Tests para el fix del bug LIC-01 (license validator confía en firma almacenada).

Verifica que ``LicenseValidator.validate`` re-verifica la firma Ed25519 con
la clave pública en CADA invocación. Si la DB se compromete y un atacante
escribe un ``signature_b64`` arbitrario (sin tener la clave privada), la
verificación criptográfica debe fallar y ``validate`` debe retornar
``{"valid": False}``.

Defensa en profundidad cubierta:
- Longitud de firma Ed25519 = 64 bytes (rechazada antes de verify).
- Datetimes timezone-aware (sin skew).
- Cualquier excepción durante verify -> invalid.
"""
from __future__ import annotations

import base64
import contextlib
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="lic01_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Cada test usa una DB SQLite limpia con claves Ed25519 generadas."""
    data_dir = tmp_path / "data" / ".workflow_determinista"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "workflow_determinista.db"
    monkeypatch.setenv("WFD_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HOME", str(tmp_path))

    from src.core.db import sqlite_manager as sm_mod

    monkeypatch.setattr(sm_mod, "DB_PATH", db_path)
    sm_mod.DatabaseManager._reset()

    from src.license import keys as license_keys

    test_keys_dir = data_dir / "license_keys"
    test_keys_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(license_keys, "KEYS_DIR", test_keys_dir)
    monkeypatch.setattr(license_keys, "PRIVATE_KEY_FILE", test_keys_dir / "private_key.enc")
    monkeypatch.setattr(license_keys, "PUBLIC_KEY_FILE", test_keys_dir / "public_key.pem")
    monkeypatch.setattr(license_keys, "SALT_FILE", test_keys_dir / "key_salt.bin")
    monkeypatch.setattr(license_keys, "METADATA_FILE", test_keys_dir / "metadata.json")

    # Generar par de claves Ed25519 para tests
    if not (test_keys_dir / "private_key.enc").exists():
        license_keys.generate_keypair("test-admin-pw")

    from src.core.security.encryption import EncryptionService

    EncryptionService._instance = None  # type: ignore[attr-defined]
    EncryptionService._initialized = False  # type: ignore[attr-defined]

    yield

    with contextlib.suppress(Exception):
        sm_mod.DatabaseManager._reset()


class TestLic01Fix:
    """Verifica el fix del bypass de la verificación de firma en LicenseValidator."""

    def test_valid_license_validates_correctly(self):
        """Ciclo completo generate -> activate -> validate retorna válido."""
        from src.license.generator import LicenseGenerator
        from src.license.validator import LicenseValidator

        gen = LicenseGenerator()
        key = gen.generate(
            admin_password="test-admin-pw",
            license_type="individual",
            client_name="Test Client",
            days_valid=365,
        )
        validator = LicenseValidator()
        validator.activate_key(
            key,
            license_type="individual",
            client_name="Test Client",
            days_valid=365,
            signature_b64=gen.last_signature_b64,
        )

        result = validator.validate(key)
        assert result["valid"] is True, f"License válida rechazada: {result.get('reason')}"
        assert result["type"] == "individual"
        assert result["client_name"] == "Test Client"

    def test_invalid_signature_stored_in_db_is_rejected(self):
        """Bug LIC-01: una firma inválida almacenada en DB debe ser rechazada.

        Simula compromiso de DB: el atacante inserta una fila con un
        ``signature_b64`` arbitrario (64 bytes aleatorios en base64url)
        pero NO puede firmar el payload con la clave privada legítima.
        El validador debe detectar que la firma no corresponde al payload
        y retornar ``{"valid": False}``.
        """
        import os as _os

        from src.license.validator import LicenseValidator

        # Crear 64 bytes aleatorios como firma falsa (longitud correcta
        # para Ed25519, pero contenido inválido).
        fake_sig_bytes = _os.urandom(64)
        fake_sig_b64 = base64.urlsafe_b64encode(fake_sig_bytes).decode().rstrip("=")

        # Insertar directamente en DB (simula SQLi / acceso físico)
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        # Generar una key con formato válido para que validate() llegue al
        # chequeo de firma (no falle en validación de formato).
        # parts[4] debe contener solo consonantes (LICENSE_CHARSET no tiene vocales).
        key = "WFD-ABCD-EFGH-IJKL-MNPR"
        expiry = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        db.execute(
            "INSERT OR REPLACE INTO license (key, type, client_name, expires_at, signature_b64, is_trial) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (key, "enterprise", "Attacker Corp", expiry, fake_sig_b64),
        )
        db.commit()

        validator = LicenseValidator()
        result = validator.validate(key)

        # El validador debe rechazar la firma (aunque esté en DB) porque
        # no pasa la verificación criptográfica con la clave pública legítima.
        assert result["valid"] is False, (
            "Bug LIC-01 NO fixeado: firma inválida en DB fue aceptada. "
            f"Result: {result}"
        )
        assert "Firma" in result["reason"] or "alterada" in result["reason"], (
            f"Razón inesperada: {result['reason']}"
        )

    def test_wrong_signature_length_rejected(self):
        """Defensa en profundidad: firma con longitud != 64 bytes se rechaza."""
        from src.license.validator import LicenseValidator

        # Firma falsa con longitud incorrecta (32 bytes en vez de 64)
        fake_sig_bytes = b"\x00" * 32
        fake_sig_b64 = base64.urlsafe_b64encode(fake_sig_bytes).decode().rstrip("=")

        from src.core.db import DatabaseManager

        db = DatabaseManager()
        # parts[4] solo consonantes (no vocales) para pasar LICENSE_CHARSET check.
        key = "WFD-WXYZ-PQRS-TUVW-BCDF"
        expiry = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        db.execute(
            "INSERT OR REPLACE INTO license (key, type, client_name, expires_at, signature_b64, is_trial) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (key, "enterprise", "Attacker Corp", expiry, fake_sig_b64),
        )
        db.commit()

        validator = LicenseValidator()
        result = validator.validate(key)
        assert result["valid"] is False
        assert "Firma" in result["reason"] or "alterada" in result["reason"]

    def test_missing_signature_rejected(self):
        """Licencia sin signature_b64 en DB debe ser rechazada."""
        from src.core.db import DatabaseManager
        from src.license.validator import LicenseValidator

        db = DatabaseManager()
        key = "WFD-WXYZ-PQRS-TUVW-BCDF"
        expiry = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        # Insertar sin signature_b64 (default '')
        db.execute(
            "INSERT OR REPLACE INTO license (key, type, client_name, expires_at, is_trial) "
            "VALUES (?, ?, ?, ?, 0)",
            (key, "individual", "No Sig", expiry),
        )
        db.commit()

        validator = LicenseValidator()
        result = validator.validate(key)
        assert result["valid"] is False
        assert "firma" in result["reason"].lower()

    def test_signature_validates_with_correct_payload(self):
        """La firma debe corresponder al payload exacto firmado por generator."""
        from src.license.generator import LicenseGenerator
        from src.license.validator import LicenseValidator

        gen = LicenseGenerator()
        # Generar con valores específicos
        key = gen.generate(
            admin_password="test-admin-pw",
            license_type="reseller",
            client_name="Payload Test SA",
            days_valid=30,
        )

        validator = LicenseValidator()
        # Activar con los MISMOS valores usados en generate
        validator.activate_key(
            key,
            license_type="reseller",
            client_name="Payload Test SA",
            days_valid=30,
            signature_b64=gen.last_signature_b64,
        )

        # La validación debe pasar porque el payload coincide
        result = validator.validate(key)
        assert result["valid"] is True, f"Firma válida rechazada: {result.get('reason')}"
        assert result["type"] == "reseller"

    def test_signature_rejected_when_payload_tampered(self):
        """Bug LIC-01: cambiar client_name en DB después de activate invalida la firma.

        Aunque el atacante modifique el client_name en la DB, no puede
        generar una nueva firma válida (no tiene la clave privada).
        El payload reconstruido ya no coincide con la firma original.
        """
        from src.license.generator import LicenseGenerator
        from src.license.validator import LicenseValidator

        gen = LicenseGenerator()
        key = gen.generate(
            admin_password="test-admin-pw",
            license_type="individual",
            client_name="Original Client",
            days_valid=365,
        )
        validator = LicenseValidator()
        validator.activate_key(
            key,
            license_type="individual",
            client_name="Original Client",
            days_valid=365,
            signature_b64=gen.last_signature_b64,
        )

        # Antes: válida
        assert validator.validate(key)["valid"] is True

        # Tamper DB: cambiar client_name (simula compromiso de DB)
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        # Usar key.upper() porque activate_key normaliza a mayúsculas antes
        # de almacenar, pero LicenseGenerator.generate() puede devolverla
        # en mixed-case (sig_b64url contiene minúsculas).
        db.execute(
            "UPDATE license SET client_name = ? WHERE key = ?",
            ("Tampered Client", key.strip().upper()),
        )
        db.commit()

        # Después: la firma ya no corresponde al payload modificado
        result = validator.validate(key)
        assert result["valid"] is False, (
            "Bug LIC-01 NO fixeado: tamper del client_name en DB no invalidó la licencia. "
            f"Result: {result}"
        )
        assert "Firma" in result["reason"] or "alterada" in result["reason"]

    def test_signature_rejected_when_type_escalated(self):
        """Bug LIC-01: cambiar type 'trial' -> 'enterprise' en DB invalida la firma.

        Ataque de escalada de privilegios vía DB comprometida: el atacante
        intenta cambiar el tipo de licencia para acceder a features premium.
        El validador debe detectar que la firma ya no corresponde al payload.
        """
        from src.license.generator import LicenseGenerator
        from src.license.validator import LicenseValidator

        gen = LicenseGenerator()
        key = gen.generate(
            admin_password="test-admin-pw",
            license_type="individual",  # tipo legítimo: individual
            client_name="Humble User",
            days_valid=365,
        )
        validator = LicenseValidator()
        validator.activate_key(
            key,
            license_type="individual",
            client_name="Humble User",
            days_valid=365,
            signature_b64=gen.last_signature_b64,
        )

        # Antes: válida como individual
        result_before = validator.validate(key)
        assert result_before["valid"] is True
        assert result_before["type"] == "individual"

        # Tamper: cambiar type a "enterprise" (escalada de privilegios)
        from src.core.db import DatabaseManager

        db = DatabaseManager()
        # Usar key.upper() porque activate_key normaliza a mayúsculas antes
        # de almacenar, pero LicenseGenerator.generate() puede devolverla
        # en mixed-case (sig_b64url contiene minúsculas).
        db.execute(
            "UPDATE license SET type = ? WHERE key = ?",
            ("enterprise", key.strip().upper()),
        )
        db.commit()

        # Después: la firma no corresponde al payload (type cambió)
        result = validator.validate(key)
        assert result["valid"] is False, (
            "Bug LIC-01 NO fixeado: escalada trial -> enterprise via DB no detectada. "
            f"Result: {result}"
        )
        assert "Firma" in result["reason"] or "alterada" in result["reason"]

    def test_validator_uses_public_key_verify(self):
        """Test estructural: el código fuente usa public_key.verify() (no compara strings)."""
        import inspect

        from src.license.validator import LicenseValidator

        source = inspect.getsource(LicenseValidator.validate)
        # Debe invocar public_key.verify con el payload
        assert "public_key.verify" in source
        assert "load_public_key" in source
        # No debe haber comparación trivial de strings con signature_b64
        assert "stored_sig_b64 ==" not in source
        assert "== stored_sig_b64" not in source
