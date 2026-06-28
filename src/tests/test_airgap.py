"""Air-Gapped Deployment — Tests for airgap config, offline license, and connector filtering."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.airgap import (
    CLOUD_CONNECTORS,
    AirGapConfig,
    get_connector_filter,
    is_connector_allowed,
)


@pytest.fixture
def airgap_config():
    """AirGapConfig with patched environment for testing."""
    old_mode = os.environ.get("WFD_AIRGAP_MODE", "")
    old_ai = os.environ.get("WFD_AIRGAP_ALLOW_LOCAL_AI", "")
    old_registry = os.environ.get("WFD_AIRGAP_REGISTRY_MIRROR", "")
    old_license = os.environ.get("WFD_AIRGAP_LICENSE_FILE", "")

    os.environ["WFD_AIRGAP_MODE"] = "true"
    os.environ["WFD_AIRGAP_ALLOW_LOCAL_AI"] = "false"

    config = AirGapConfig()

    yield config

    # Restore env
    if old_mode:
        os.environ["WFD_AIRGAP_MODE"] = old_mode
    else:
        os.environ.pop("WFD_AIRGAP_MODE", None)
    if old_ai:
        os.environ["WFD_AIRGAP_ALLOW_LOCAL_AI"] = old_ai
    else:
        os.environ.pop("WFD_AIRGAP_ALLOW_LOCAL_AI", None)
    if old_registry:
        os.environ["WFD_AIRGAP_REGISTRY_MIRROR"] = old_registry
    else:
        os.environ.pop("WFD_AIRGAP_REGISTRY_MIRROR", None)
    if old_license:
        os.environ["WFD_AIRGAP_LICENSE_FILE"] = old_license
    else:
        os.environ.pop("WFD_AIRGAP_LICENSE_FILE", None)


class TestAirGapConfig:
    """Tests for AirGapConfig initialization and basic properties."""

    def test_init_disabled_by_default(self):
        os.environ.pop("WFD_AIRGAP_MODE", None)
        config = AirGapConfig()
        assert config.enabled is False

    def test_init_enabled(self, airgap_config):
        assert airgap_config.enabled is True

    def test_get_disabled_connectors(self, airgap_config):
        disabled = airgap_config.get_disabled_connectors()
        assert "openai_v2" in disabled
        assert "anthropic" in disabled
        assert "sendgrid" in disabled
        assert "github" in disabled
        assert "totvs" not in disabled  # TOTVS is local ERP
        assert len(disabled) == len(set(disabled))  # No duplicates

    def test_get_local_connectors(self, airgap_config):
        locals_ = airgap_config.get_local_connectors()
        assert "ruv" not in locals_  # RuvConnector removido en Fase 2B
        assert "totvs" in locals_
        assert "vault" in locals_
        assert "sat_mexico" in locals_
        assert "pix_brazil" in locals_

    def test_is_connector_allowed(self, airgap_config):
        assert airgap_config.is_connector_allowed("openai_v2") is False
        assert airgap_config.is_connector_allowed("anthropic") is False
        assert airgap_config.is_connector_allowed("totvs") is True
        assert airgap_config.is_connector_allowed("vault") is True

    def test_is_connector_allowed_case_insensitive(self, airgap_config):
        assert airgap_config.is_connector_allowed("OpenAI_V2") is False
        assert airgap_config.is_connector_allowed("TOTVS") is True

    def test_disabled_when_not_airgap(self):
        os.environ.pop("WFD_AIRGAP_MODE", None)
        config = AirGapConfig()
        assert config.is_connector_allowed("openai_v2") is True  # Not filtered in online mode
        assert config.get_disabled_connectors() == []

    def test_global_duplicates(self):
        """Verify no duplicate entries in CLOUD_CONNECTORS."""
        assert len(CLOUD_CONNECTORS) == len(set(CLOUD_CONNECTORS))


class TestAirGapValidation:
    """Tests for air-gapped readiness validation."""

    def test_validate_disabled(self):
        os.environ.pop("WFD_AIRGAP_MODE", None)
        config = AirGapConfig()
        result = config.validate()
        assert result["airgap_enabled"] is False

    def test_validate_returns_checks(self, airgap_config):
        result = airgap_config.validate()
        assert result["airgap_enabled"] is True
        assert "checks" in result
        assert "all_passed" in result

    def test_internet_check_not_critical(self, airgap_config):
        """Internet check may or may not pass depending on environment."""
        result = airgap_config.validate()
        checks = result["checks"]
        assert "no_internet_access" in checks


class TestOfflineLicense:
    """Tests for offline license creation and verification."""

    def test_create_license(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config.LICENSE_SECRET_KEY", "test-secret-key-for-testing-only")
        license_path = str(tmp_path / "license.json")

        config = AirGapConfig()
        result = config.create_airgap_license(
            customer_name="Test Corp",
            license_key="TST-1234-5678",
            expiry_days=365,
            output_path=license_path,
        )

        assert result["payload"]["customer"] == "Test Corp"
        assert result["payload"]["airgap"] is True
        assert "signature" in result

        # Verify file was created
        assert Path(license_path).exists()

    def test_verify_valid_license(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config.LICENSE_SECRET_KEY", "test-secret-key-for-testing-only")
        license_path = str(tmp_path / "license.json")

        config = AirGapConfig()
        config.create_airgap_license("Test Corp", "TST-1234-5678", output_path=license_path)

        # Create a new config pointing to this license
        config2 = AirGapConfig()
        config2.license_file = license_path
        result = config2.verify_airgap_license()

        assert result["valid"] is True
        assert result["customer"] == "Test Corp"

    def test_verify_missing_license(self, tmp_path):
        config = AirGapConfig()
        config.license_file = str(tmp_path / "nonexistent.json")
        result = config.verify_airgap_license()
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_verify_tampered_license(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config.LICENSE_SECRET_KEY", "test-secret-key-for-testing-only")
        license_path = str(tmp_path / "license.json")

        config = AirGapConfig()
        config.create_airgap_license("Test Corp", "TST-1234-5678", output_path=license_path)

        # Tamper with the license
        data = json.loads(Path(license_path).read_text())
        data["payload"]["customer"] = "Evil Corp"
        Path(license_path).write_text(json.dumps(data))

        result = config.verify_airgap_license(license_path)
        assert result["valid"] is False

    def test_create_and_verify_cycle(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config.LICENSE_SECRET_KEY", "a" * 64)
        license_path = str(tmp_path / "license.json")

        config = AirGapConfig()
        config.create_airgap_license("Valid Customer", "KEY-1234", output_path=license_path)

        result = config.verify_airgap_license(license_path)
        assert result["valid"] is True
        assert result["customer"] == "Valid Customer"
        assert result["days_remaining"] > 0


class TestConnectorFilter:
    """Tests for connector filter convenience functions."""

    def test_is_connector_allowed_global(self, monkeypatch):
        monkeypatch.setenv("WFD_AIRGAP_MODE", "true")
        # Reset singleton to pick up new env
        import src.airgap as airgap_module
        airgap_module._instance = None

        assert is_connector_allowed("openai_v2") is False
        assert is_connector_allowed("totvs") is True

        airgap_module._instance = None

    def test_get_connector_filter(self, monkeypatch):
        monkeypatch.setenv("WFD_AIRGAP_MODE", "true")
        import src.airgap as airgap_module
        airgap_module._instance = None

        filter_ = get_connector_filter()
        assert "disabled" in filter_
        assert "local_only" in filter_
        assert len(filter_["disabled"]) > 0

        airgap_module._instance = None


class TestAirGapStatus:
    """Tests for air-gapped status summary."""

    def test_status_online(self):
        os.environ.pop("WFD_AIRGAP_MODE", None)
        config = AirGapConfig()
        status = config.get_status_summary()
        assert status["mode"] == "online"

    def test_status_airgapped(self, airgap_config):
        status = airgap_config.get_status_summary()
        assert status["mode"] == "airgapped"
        assert status["enabled"] is True
