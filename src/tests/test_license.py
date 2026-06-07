"""
Workflow Determinista — Tests del License System
Tests unitarios para el generador y validador de licencias: formato, HMAC, trial.
"""
import pytest


class TestLicenseGenerator:
    """Tests para la clase LicenseGenerator."""

    def test_generate_key_format(self, license_generator):
        """Test: la key generada tiene formato WFD-XXXX-XXXX-XXXX-XXXX."""
        key = license_generator.generate()
        parts = key.split("-")
        assert len(parts) == 5
        assert parts[0] == "WFD"
        for block in parts[1:]:
            assert len(block) == 4

    def test_generate_key_type(self, license_generator):
        """Test: la key generada con tipo 'enterprise' se puede generar."""
        key = license_generator.generate(license_type="enterprise", client_name="Test Corp")
        assert key.startswith("WFD-")

    def test_generate_key_unique(self, license_generator):
        """Test: cada key generada es única."""
        keys = {license_generator.generate() for _ in range(10)}
        assert len(keys) == 10

    def test_generate_key_valid_chars(self, license_generator):
        """Test: la key solo contiene caracteres permitidos (consonantes + dígitos)."""
        from src.license.validator import LICENSE_CHARSET
        key = license_generator.generate()
        parts = key.split("-")
        # Only the last block uses LICENSE_CHARSET; the first 3 blocks are HMAC hex
        random_block = parts[4]
        for char in random_block:
            assert char in LICENSE_CHARSET, f"Carácter inválido en key: {char}"


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
        # Use a key with valid HMAC hex chars (0-9, A-F) in first 3 blocks
        # and valid LICENSE_CHARSET chars in the last block, but not stored in DB.
        result = license_validator.validate("WFD-0A1B-2C3D-4E5F-BCDF")
        assert result["valid"] is False
        assert "no encontrada" in result["reason"]

    def test_trial_starts_automatically(self, license_validator):
        """Test: el trial se inicia automáticamente en la primera validación."""
        from src.config import TRIAL_DAYS
        status = license_validator.get_trial_status()
        assert status["is_trial"] is True
        assert status["days_left"] > 0
        assert status["days_left"] <= TRIAL_DAYS

    def test_trial_30_days(self):
        """Test: el trial dura exactamente 30 días (spec requirement)."""
        from src.config import TRIAL_DAYS
        assert TRIAL_DAYS == 30

    def test_get_license_info(self, license_validator):
        """Test: get_license_info retorna información de la licencia actual."""
        info = license_validator.get_license_info()
        assert "type" in info
        assert "is_trial" in info

    def test_activate_key(self, license_validator, license_generator):
        """Test: activar una key la guarda en la DB."""
        key = license_generator.generate(license_type="individual", client_name="Test Client")
        result = license_validator.activate_key(key, license_type="individual", client_name="Test Client")
        assert result["valid"] is True
        assert result["type"] == "individual"

    def test_full_generate_validate_cycle(self, license_generator, license_validator):
        """Test: ciclo completo de generar key → activar → validar."""
        key = license_generator.generate(
            license_type="individual",
            client_name="Cycle Test",
            days_valid=365,
        )

        # Activate
        license_validator.activate_key(
            key,
            license_type="individual",
            client_name="Cycle Test",
            days_valid=365,
        )

        # Validate
        result = license_validator.validate(key)
        # The key should be valid (format + stored + HMAC match)
        assert result["valid"] is True
        assert result["type"] == "individual"
        assert result["client_name"] == "Cycle Test"

    def test_license_types(self):
        """Test: los tipos de licencia son individual, reseller, enterprise."""
        from src.license.validator import LicenseValidator
        assert "individual" in LicenseValidator.LICENSE_TYPES
        assert "reseller" in LicenseValidator.LICENSE_TYPES
        assert "enterprise" in LicenseValidator.LICENSE_TYPES

    def test_hmac_used_not_plain_hash(self):
        """Test: verificar que el generador usa HMAC-SHA256 (no SHA-256 simple)."""
        import inspect
        from src.license.generator import LicenseGenerator

        source = inspect.getsource(LicenseGenerator)
        assert "hmac" in source
        assert "sha256" in source

    def test_validator_uses_compare_digest(self):
        """Test: verificar que el validador usa hmac.compare_digest (timing-safe)."""
        import inspect
        from src.license.validator import LicenseValidator

        source = inspect.getsource(LicenseValidator)
        assert "compare_digest" in source
