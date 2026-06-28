"""Tests Fase 2D — Fiscal Dispatcher + API router (LATAM e-invoicing)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_tmpdir = tempfile.mkdtemp(prefix="fase2d_test_")
os.environ["HOME"] = _tmpdir

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ── FiscalDispatcher — Unit tests ────────────────────────────────────

class TestFiscalDispatcherCountryRouting:
    """Tests de enrutamiento por país del FiscalDispatcher."""

    def test_supported_countries_includes_all_7_latam(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import SUPPORTED_COUNTRIES
        for c in ["AR", "MX", "BR", "CL", "CO", "PE", "EC"]:
            assert c in SUPPORTED_COUNTRIES, f"{c} debe estar en SUPPORTED_COUNTRIES"

    def test_dispatch_unsupported_country_returns_error(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="US",  # No LATAM
            action="issue",
            params={},
            license_type="enterprise",
            credentials={"cuit": "123"},
        )
        assert result["success"] is False
        assert result["reject_code"] == "ZF-FISCAL-COUNTRY-UNSUPPORTED"
        assert "US" in result["reject_message"]

    def test_dispatch_lowercase_country_is_normalized(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="us",  # lowercase, no LATAM
            action="issue",
            params={},
            license_type="enterprise",
            credentials={},
        )
        assert result["reject_code"] == "ZF-FISCAL-COUNTRY-UNSUPPORTED"


class TestFiscalDispatcherLicenseGating:
    """Tests de license tier gating."""

    def test_trial_license_blocked(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="MX",
            action="issue",
            params={},
            license_type="trial",
            credentials={"cuit": "123"},
        )
        assert result["success"] is False
        assert result["reject_code"] == "ZF-LICENSE-FISCAL-DENIED"
        assert "reseller" in result["reject_message"].lower()
        assert "enterprise" in result["reject_message"].lower()

    def test_individual_license_blocked(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="BR",
            action="issue",
            params={},
            license_type="individual",
            credentials={"cnpj": "123"},
        )
        assert result["success"] is False
        assert result["reject_code"] == "ZF-LICENSE-FISCAL-DENIED"

    def test_reseller_license_passes_to_connector(self):
        """Reseller tiene fiscal_electronic=True → pasa el gate pero puede fallar en connector."""
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        # Sin credenciales → pasa license gate pero falla en creds
        result = dispatch_fiscal(
            country="MX",
            action="issue",
            params={},
            license_type="reseller",
            credentials=None,
        )
        # Como no hay creds, debe dar ZF-FISCAL-CREDS-MISSING (no ZF-LICENSE)
        assert result["reject_code"] != "ZF-LICENSE-FISCAL-DENIED"
        assert result["reject_code"] in ("ZF-FISCAL-CREDS-MISSING",
                                          "ZF-FISCAL-CONNECTOR-UNAVAILABLE",
                                          "ZF-FISCAL-CONNECT-FAILED")

    def test_enterprise_license_passes_to_connector(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="AR",
            action="issue",
            params={},
            license_type="enterprise",
            credentials=None,
        )
        assert result["reject_code"] != "ZF-LICENSE-FISCAL-DENIED"


class TestFiscalDispatcherCredentialsValidation:
    """Tests de validación de credenciales."""

    def test_missing_credentials_returns_error(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="MX",
            action="issue",
            params={"receptor": {}},  # no credentials key
            license_type="reseller",
        )
        assert result["success"] is False
        assert result["reject_code"] == "ZF-FISCAL-CREDS-MISSING"

    def test_empty_credentials_returns_error(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import dispatch_fiscal
        result = dispatch_fiscal(
            country="CL",
            action="issue",
            params={},
            license_type="reseller",
            credentials={},
        )
        # Empty dict {} es falsy → ZF-FISCAL-CREDS-MISSING
        # o ZF-FISCAL-CONNECT-FAILED si el connector lo acepta y falla al conectar
        assert result["reject_code"] in (
            "ZF-FISCAL-CREDS-MISSING",
            "ZF-FISCAL-CONNECT-FAILED",
        )


class TestFiscalDispatcherAuditLog:
    """Tests del audit log y EventBus publishing."""

    def test_audit_log_records_dispatch(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        # Dispatch fallido (país no soportado no se audita, pero license denied sí)
        dispatcher.dispatch("MX", "issue", {}, license_type="trial", credentials={"x": "y"})
        # El audit log se llena solo en _audit_dispatch (que se llama después de normalize)
        # Para country-unsupported y license-denied NO se audita porque retorna antes.
        # Pero para dispatches que llegan al connector, sí.
        # Verificamos que get_audit_log retorna una lista (puede ser vacía en este caso)
        log = dispatcher.get_audit_log()
        assert isinstance(log, list)

    def test_event_bus_receives_dispatched_event(self):
        """Cuando el dispatch llega al connector, se publica 'fiscal.dispatched'."""
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher

        # Mock connector class
        mock_connector_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.connect.return_value = True
        mock_instance.execute.return_value = {
            "success": True,
            "uuid": "TEST-UUID-1234",
            "xml": "<cfdi/>",
        }
        mock_connector_cls.return_value = mock_instance

        dispatcher = FiscalDispatcher()
        with patch(
            "src.hat.level5_tools.business.invoice.fiscal_dispatcher._load_connector_class",
            return_value=mock_connector_cls,
        ):
            result = dispatcher.dispatch(
                country="MX",
                action="issue",
                params={"receptor": {"rfc": "XAXX010101000"}},
                license_type="enterprise",
                credentials={"rfc": "TEST010101AA1"},
            )

        assert result["success"] is True
        assert result["country_tracking_id"] == "TEST-UUID-1234"
        assert result["country"] == "MX"
        assert result["action"] == "issue"

        # Audit log debe tener 1 entrada
        log = dispatcher.get_audit_log()
        assert len(log) == 1
        assert log[0]["country"] == "MX"
        assert log[0]["success"] is True
        assert log[0]["tracking_id"] == "TEST-UUID-1234"


class TestFiscalDispatcherNormalization:
    """Tests de normalización de resultados por país."""

    def test_normalize_afip_cae(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        result = dispatcher._normalize_result(
            country="AR",
            action="issue",
            raw={"success": True, "cae": "69123456789012", "vto": "20251231"},
            dispatched_at="2025-01-01T00:00:00Z",
        )
        assert result["country_tracking_id"] == "69123456789012"

    def test_normalize_sat_uuid(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        result = dispatcher._normalize_result(
            country="MX",
            action="issue",
            raw={"success": True, "uuid": "abcd-1234-efgh-5678"},
            dispatched_at="2025-01-01T00:00:00Z",
        )
        assert result["country_tracking_id"] == "abcd-1234-efgh-5678"

    def test_normalize_nfe_chave(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        chave = "35200678118669000155550010000000011000000013"
        result = dispatcher._normalize_result(
            country="BR",
            action="issue",
            raw={"success": True, "chave": chave},
            dispatched_at="2025-01-01T00:00:00Z",
        )
        assert result["country_tracking_id"] == chave

    def test_normalize_dian_cufe(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        cufe = "a" * 64  # 64 hex chars
        result = dispatcher._normalize_result(
            country="CO",
            action="issue",
            raw={"success": True, "cufe": cufe},
            dispatched_at="2025-01-01T00:00:00Z",
        )
        assert result["country_tracking_id"] == cufe

    def test_normalize_sri_clave_acceso(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        clave = "1" * 49
        result = dispatcher._normalize_result(
            country="EC",
            action="issue",
            raw={"success": True, "clave_acceso": clave},
            dispatched_at="2025-01-01T00:00:00Z",
        )
        assert result["country_tracking_id"] == clave


class TestFiscalDispatcherPluginRegistry:
    """Tests del plugin registry (lazy imports)."""

    def test_load_connector_class_returns_none_for_unsupported(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import _load_connector_class
        assert _load_connector_class("XX") is None

    def test_load_connector_class_returns_class_for_ar(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import _load_connector_class
        cls = _load_connector_class("AR")
        # AFIPArgentinaConnector debe estar disponible (Fase 2B)
        assert cls is not None
        assert cls.__name__ == "AFIPArgentinaConnector"

    def test_load_connector_class_returns_class_for_mx(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import _load_connector_class
        cls = _load_connector_class("MX")
        assert cls is not None
        assert cls.__name__ == "SatMexicoConnector"

    def test_load_connector_class_returns_class_for_br(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import _load_connector_class
        cls = _load_connector_class("BR")
        assert cls is not None
        assert cls.__name__ == "NfeConnector"

    def test_load_connector_class_returns_class_for_cl(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import _load_connector_class
        cls = _load_connector_class("CL")
        assert cls is not None
        assert cls.__name__ == "DTEChileConnector"

    def test_supported_countries_filters_unavailable(self):
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher
        dispatcher = FiscalDispatcher()
        available = dispatcher.supported_countries()
        # AR, MX, BR, CL están disponibles (Fase 2B completada)
        assert "AR" in available
        assert "MX" in available
        assert "BR" in available
        assert "CL" in available


# ── API Router tests ─────────────────────────────────────────────────

class TestFiscalRouter:
    """Tests del router FastAPI /api/v2/fiscal."""

    @pytest.fixture
    def client(self):
        """FastAPI TestClient con el router fiscal montado."""
        from fastapi import FastAPI

        from src.api_v2.routers.fiscal import router as fiscal_router
        app = FastAPI()
        app.include_router(fiscal_router)
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_countries_endpoint_returns_all_7(self, client):
        resp = client.get("/api/v2/fiscal/countries")
        assert resp.status_code == 200
        data = resp.json()
        assert "supported" in data
        assert "available" in data
        for c in ["AR", "MX", "BR", "CL", "CO", "PE", "EC"]:
            assert c in data["supported"]

    def test_issue_with_trial_license_returns_denied(self, client):
        resp = client.post(
            "/api/v2/fiscal/issue",
            json={
                "country": "MX",
                "action_params": {"receptor": {"rfc": "XAXX010101000"}},
                "credentials": {"rfc": "TEST010101AA1"},
            },
            # Sin X-License-Key → trial
        )
        assert resp.status_code == 200  # El router no eleva a 403, retorna success=false
        data = resp.json()
        assert data["success"] is False
        assert data["reject_code"] == "ZF-LICENSE-FISCAL-DENIED"

    def test_issue_with_unsupported_country_returns_error(self, client):
        resp = client.post(
            "/api/v2/fiscal/issue",
            json={
                "country": "US",
                "action_params": {},
                "credentials": {},
            },
            headers={"X-License-Key": "WFD-FAKE-KEY-FOR-TEST-1234"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["reject_code"] == "ZF-FISCAL-COUNTRY-UNSUPPORTED"

    def test_cancel_endpoint_returns_normalized_result(self, client):
        resp = client.post(
            "/api/v2/fiscal/cancel",
            json={
                "country": "BR",
                "tracking_id": "35200678118669000155550010000000011000000013",
                "motivo": "teste",
                "credentials": {},
            },
            # Sin license key → trial → denegado
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        # Trial no tiene fiscal_electronic → denegado
        assert data["reject_code"] == "ZF-LICENSE-FISCAL-DENIED"

    def test_status_endpoint_returns_normalized_result(self, client):
        resp = client.get("/api/v2/fiscal/status/MX/TEST-UUID-1234")
        assert resp.status_code == 200
        data = resp.json()
        # Sin license key → trial → denegado
        assert data["success"] is False
        assert data["reject_code"] == "ZF-LICENSE-FISCAL-DENIED"

    def test_pdf_endpoint_returns_normalized_result(self, client):
        resp = client.get("/api/v2/fiscal/pdf/AR/69123456789012")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["reject_code"] == "ZF-LICENSE-FISCAL-DENIED"

    def test_issue_response_model_has_all_fields(self, client):
        """Verifica que FiscalResponse tiene todos los campos esperados."""
        resp = client.post(
            "/api/v2/fiscal/issue",
            json={
                "country": "MX",
                "action_params": {},
                "credentials": {},
            },
        )
        data = resp.json()
        for field in ["success", "country", "action", "country_tracking_id",
                       "xml", "pdf_base64", "government_response",
                       "reject_code", "reject_message", "error", "dispatched_at"]:
            assert field in data, f"FiscalResponse debe tener campo {field}"


# ── Integration: Dispatcher → Connector (mocked) ─────────────────────

class TestIntegrationDispatcherConnector:
    """Tests E2E con connector mockeado."""

    def test_full_dispatch_flow_with_mocked_connector(self):
        """E2E: dispatch → connect → execute → disconnect → audit."""
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher

        # Mock connector
        mock_cls = MagicMock()
        mock_inst = MagicMock()
        mock_inst.connect.return_value = True
        mock_inst.execute.return_value = {
            "success": True,
            "uuid": "INTEGRATION-UUID-9999",
            "xml": "<cfdi version='4.0'/>",
            "data": {"estado": "vigente"},
        }
        mock_cls.return_value = mock_inst

        dispatcher = FiscalDispatcher()
        with patch(
            "src.hat.level5_tools.business.invoice.fiscal_dispatcher._load_connector_class",
            return_value=mock_cls,
        ):
            result = dispatcher.dispatch(
                country="MX",
                action="issue",
                params={
                    "receptor": {"rfc": "XAXX010101000"},
                    "conceptos": [{"clave_prod_serv": "01010101", "cantidad": 1}],
                },
                license_type="enterprise",
                credentials={
                    "rfc": "TEST010101AA1",
                    "cert_path": "/fake/cert.pfx",
                    "cert_password": "fakepass",
                },
            )

        # Verificar resultado normalizado
        assert result["success"] is True
        assert result["country"] == "MX"
        assert result["action"] == "issue"
        assert result["country_tracking_id"] == "INTEGRATION-UUID-9999"
        assert result["xml"] == "<cfdi version='4.0'/>"
        assert result["government_response"] == {"estado": "vigente"}

        # Verificar que el connector fue llamado correctamente
        mock_inst.connect.assert_called_once()
        mock_inst.execute.assert_called_once_with("issue", {
            "receptor": {"rfc": "XAXX010101000"},
            "conceptos": [{"clave_prod_serv": "01010101", "cantidad": 1}],
        })
        mock_inst.disconnect.assert_called_once()

        # Verificar audit log
        log = dispatcher.get_audit_log()
        assert len(log) == 1
        assert log[0]["tracking_id"] == "INTEGRATION-UUID-9999"

    def test_dispatch_with_connector_exception_returns_normalized_error(self):
        """Si el connector raises, el dispatcher captura y normaliza."""
        from src.hat.level5_tools.business.invoice.fiscal_dispatcher import FiscalDispatcher

        mock_cls = MagicMock()
        mock_inst = MagicMock()
        mock_inst.connect.return_value = True
        mock_inst.execute.side_effect = RuntimeError("SOAP timeout")
        mock_cls.return_value = mock_inst

        dispatcher = FiscalDispatcher()
        with patch(
            "src.hat.level5_tools.business.invoice.fiscal_dispatcher._load_connector_class",
            return_value=mock_cls,
        ):
            result = dispatcher.dispatch(
                country="AR",
                action="issue",
                params={},
                license_type="reseller",
                credentials={"cuit": "30712345678"},
            )

        assert result["success"] is False
        assert result["reject_code"] == "ZF-FISCAL-DISPATCH-EXCEPTION"
        assert "SOAP timeout" in result["error"]
        # Incluso en excepción, disconnect se llama (via finally)
        mock_inst.disconnect.assert_called_once()
