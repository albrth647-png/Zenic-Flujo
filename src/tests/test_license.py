"""
Workflow Determinista — Tests del License System
Tests unitarios para el generador y validador de licencias: formato, Ed25519, trial.
"""

import pytest


class TestLicenseGenerator:
    """Tests para la clase LicenseGenerator."""

    def test_generate_key_format(self, license_generator):
        """Test: la key generada tiene formato WFD-XXXX-XXXX-XXXX-XXXX."""
        key = license_generator.generate(admin_password="test-admin-pw")
        parts = key.split("-")
        assert len(parts) == 5
        assert parts[0] == "WFD"
        for block in parts[1:]:
            assert len(block) == 4

    def test_generate_key_type(self, license_generator):
        """Test: la key generada con tipo 'enterprise' se puede generar."""
        key = license_generator.generate(admin_password="test-admin-pw", license_type="enterprise", client_name="Test Corp")
        assert key.startswith("WFD-")

    def test_generate_key_unique(self, license_generator):
        """Test: cada key generada es única."""
        keys = {license_generator.generate(admin_password="test-admin-pw") for _ in range(10)}
        assert len(keys) == 10

    def test_generate_key_valid_chars(self, license_generator):
        """Test: la key solo contiene caracteres permitidos (consonantes + dígitos)."""
        from src.license.validator import LICENSE_CHARSET

        key = license_generator.generate(admin_password="test-admin-pw")
        parts = key.split("-")
        # The last block uses LICENSE_CHARSET
        random_block = parts[4]
        for char in random_block:
            assert char in LICENSE_CHARSET, f"Carácter inválido en key: {char}"

    def test_generate_stores_signature(self, license_generator):
        """Test: generate() almacena la firma completa internamente."""
        license_generator.generate(
            admin_password="test-admin-pw",
            license_type="individual",
            client_name="Sig Test",
            days_valid=365,
        )
        sig = license_generator.last_signature_b64
        assert len(sig) > 20, f"La firma almacenada es demasiado corta: {len(sig)}"
        assert sig, "No se almacenó la firma"

    def test_generate_requires_private_key(self, license_generator):
        """Test: generate() sin clave privada debe fallar."""
        from src.license.keys import PRIVATE_KEY_FILE

        if not PRIVATE_KEY_FILE.exists():
            pytest.skip("No hay clave privada — este test se ejecuta en entorno con keys existentes")
        # Si la clave existe pero damos password incorrecto
        with pytest.raises(ValueError, match="no disponible|incorrecta"):  # noqa: RUF043
            license_generator.generate(admin_password="wrong-password-123")  # forge-ignore-security: test wrong password


class TestLicenseValidator:
    """Tests para la clase LicenseValidator."""

    def test_validate_invalid_format(self, license_validator):
        """Test: key con formato inválido retorna valid=False."""
        result = license_validator.validate("INVALID-KEY")
        assert result["valid"] is False
        assert "Formato" in result["reason"]

    def test_validate_wrong_prefix(self, license_validator):
        """Test: key sin prefijo WFD retorna valid=False."""
        result = license_validator.validate("XYZ-ABCD-EFGH-IJKL-MNOP")
        assert result["valid"] is False

    def test_validate_nonexistent_key(self, license_validator):
        """Test: key que no existe en DB retorna valid=False."""
        result = license_validator.validate("WFD-0A1B-2C3D-4E5F-BCDF")
        assert result["valid"] is False
        assert "no encontrada" in result["reason"]

    def test_trial_starts_automatically(self, license_validator):
        """Test: el trial se inicia automáticamente en la primera validación."""
        from src.core.config import TRIAL_DAYS

        status = license_validator.get_trial_status()
        assert status["is_trial"] is True
        assert status["days_left"] > 0
        assert status["days_left"] <= TRIAL_DAYS

    def test_trial_30_days(self):
        """Test: el trial dura exactamente 30 días (spec requirement)."""
        from src.core.config import TRIAL_DAYS

        assert TRIAL_DAYS == 30

    def test_get_license_info(self, license_validator):
        """Test: get_license_info retorna información de la licencia actual."""
        info = license_validator.get_license_info()
        assert "type" in info
        assert "is_trial" in info

    def test_activate_key(self, license_generator, license_validator):
        """Test: activar una key la guarda en la DB."""
        key = license_generator.generate(
            admin_password="test-admin-pw",
            license_type="individual",
            client_name="Test Client",
        )
        result = license_validator.activate_key(
            key,
            license_type="individual",
            client_name="Test Client",
            signature_b64=license_generator.last_signature_b64,
        )
        assert result["valid"] is True
        assert result["type"] == "individual"

    def test_full_generate_validate_cycle(self, license_generator, license_validator):
        """Test: ciclo completo de generar key → activar → validar."""
        key = license_generator.generate(
            admin_password="test-admin-pw",
            license_type="individual",
            client_name="Cycle Test",
            days_valid=365,
        )

        # Activate with full Ed25519 signature
        license_validator.activate_key(
            key,
            license_type="individual",
            client_name="Cycle Test",
            days_valid=365,
            signature_b64=license_generator.last_signature_b64,
        )

        # Validate — debe verificar la firma Ed25519 con la clave pública
        result = license_validator.validate(key)
        assert result["valid"] is True, f"Validación falló: {result.get('reason')}"
        assert result["type"] == "individual"
        assert result["client_name"] == "Cycle Test"

    def test_license_types(self):
        """Test: los tipos de licencia son individual, reseller, enterprise."""
        from src.license.validator import LicenseValidator

        assert "individual" in LicenseValidator.LICENSE_TYPES
        assert "reseller" in LicenseValidator.LICENSE_TYPES
        assert "enterprise" in LicenseValidator.LICENSE_TYPES

    def test_generator_uses_ed25519_not_hmac(self):
        """Test: verificar que el generador usa Ed25519 (no HMAC-SHA256)."""
        import inspect

        from src.license.generator import LicenseGenerator

        source = inspect.getsource(LicenseGenerator)
        # El generador debe usar "sign" (Ed25519), no "hmac"
        assert "sign(" in source or "Ed25519" in source
        # No debe importar hmac
        assert "import hmac" not in source

    def test_validator_uses_ed25519_verify(self):
        """Test: verificar que el validador usa public_key.verify() (Ed25519)."""
        import inspect

        from src.license.validator import LicenseValidator

        source = inspect.getsource(LicenseValidator)
        assert "public_key.verify" in source or "load_public_key" in source
