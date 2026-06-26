"""Tests Fase 1D-J — API routers + PDF + License gating + i18n + startup."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="fase1dj_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from src.core.db.sqlite_manager import DatabaseManager
    yield DatabaseManager()


# ── 1D: API v2 Routers ──────────────────────────────────────────────

class TestCRMRouter:
    """Tests para /api/v2/crm/*."""

    def test_crm_router_has_correct_prefix(self):
        from src.api_v2.routers.crm import router
        assert router.prefix == "/api/v2/crm"

    def test_crm_router_has_leads_endpoints(self):
        from src.api_v2.routers.crm import router
        paths = [r.path for r in router.routes]
        assert any("leads" in p for p in paths)

    def test_crm_router_has_clients_endpoints(self):
        from src.api_v2.routers.crm import router
        paths = [r.path for r in router.routes]
        assert any("clients" in p for p in paths)

    def test_crm_router_has_stats(self):
        from src.api_v2.routers.crm import router
        paths = [r.path for r in router.routes]
        assert any("stats" in p for p in paths)

    def test_crm_router_has_convert_to_invoice(self):
        from src.api_v2.routers.crm import router
        paths = [r.path for r in router.routes]
        assert any("convert-to-invoice" in p for p in paths)


class TestInventoryRouter:
    """Tests para /api/v2/inventory/*."""

    def test_inventory_router_has_correct_prefix(self):
        from src.api_v2.routers.inventory import router
        assert router.prefix == "/api/v2/inventory"

    def test_inventory_router_has_products(self):
        from src.api_v2.routers.inventory import router
        paths = [r.path for r in router.routes]
        assert any("products" in p for p in paths)

    def test_inventory_router_has_stock_update(self):
        from src.api_v2.routers.inventory import router
        paths = [r.path for r in router.routes]
        assert any("stock" in p for p in paths)

    def test_inventory_router_has_stats(self):
        from src.api_v2.routers.inventory import router
        paths = [r.path for r in router.routes]
        assert any("stats" in p for p in paths)


class TestInvoicesV2Router:
    """Tests para /api/v2/invoices/*."""

    def test_invoices_v2_router_has_correct_prefix(self):
        from src.api_v2.routers.invoices_v2 import router
        assert router.prefix == "/api/v2/invoices"

    def test_invoices_v2_has_create(self):
        from src.api_v2.routers.invoices_v2 import router
        paths = [r.path for r in router.routes]
        assert any("invoices" in p for p in paths)

    def test_invoices_v2_has_mark_paid(self):
        from src.api_v2.routers.invoices_v2 import router
        paths = [r.path for r in router.routes]
        assert any("mark-paid" in p for p in paths)

    def test_invoices_v2_has_stats(self):
        from src.api_v2.routers.invoices_v2 import router
        paths = [r.path for r in router.routes]
        assert any("stats" in p for p in paths)


# ── 1E: PDF Generation ──────────────────────────────────────────────

class TestPDFGeneration:
    """Tests para generate_invoice_pdf."""

    def test_pdf_module_importable(self):
        from src.hat.level5_tools.business.pyme_orchestrator.pdf import generate_invoice_pdf
        assert callable(generate_invoice_pdf)

    def test_pdf_generates_file(self, fresh_db):
        from src.hat.level5_tools.business.pyme_orchestrator.pdf import generate_invoice_pdf
        invoice = {
            "id": 123,
            "client_name": "Cliente Test",
            "items": [{"description": "Servicio", "quantity": 1, "unit_price": 100}],
            "subtotal": 100,
            "tax_rate": 0.16,
            "tax_amount": 16,
            "discount": 0,
            "total": 116,
            "currency": "MXN",
            "due_date": "2026-07-21",
        }
        path = generate_invoice_pdf(invoice)
        assert os.path.exists(path)
        assert path.endswith("factura_000123.pdf")

    def test_pdf_with_client_data(self, fresh_db):
        from src.hat.level5_tools.business.pyme_orchestrator.pdf import generate_invoice_pdf
        invoice = {
            "id": 456,
            "client_name": "Test",
            "items": [],
            "subtotal": 0,
            "tax_rate": 0,
            "tax_amount": 0,
            "discount": 0,
            "total": 0,
            "currency": "USD",
            "due_date": "",
        }
        client = {"name": "Cliente Premium", "fiscal_id": "ABC123"}
        path = generate_invoice_pdf(invoice, client=client)
        assert os.path.exists(path)


# ── 1H: License Tier Gating ─────────────────────────────────────────

class TestLicenseTierGating:
    """Tests para TIER_FEATURES + check_feature + check_quota."""

    def test_get_tier_features_trial(self):
        from src.license.validator import get_tier_features
        feats = get_tier_features("trial")
        assert feats["max_leads"] == 10
        assert feats["whatsapp_enabled"] is False

    def test_get_tier_features_individual(self):
        from src.license.validator import get_tier_features
        feats = get_tier_features("individual")
        assert feats["max_leads"] == 1000
        assert feats["whatsapp_enabled"] is True

    def test_get_tier_features_enterprise(self):
        from src.license.validator import get_tier_features
        feats = get_tier_features("enterprise")
        assert feats["max_leads"] == -1  # ilimitado

    def test_get_tier_features_unknown_falls_back_to_trial(self):
        from src.license.validator import get_tier_features
        feats = get_tier_features("unknown")
        assert feats["max_leads"] == 10

    def test_check_feature_whatsapp_trial_false(self):
        from src.license.validator import check_feature
        assert check_feature("trial", "whatsapp_enabled") is False

    def test_check_feature_whatsapp_individual_true(self):
        from src.license.validator import check_feature
        assert check_feature("individual", "whatsapp_enabled") is True

    def test_check_feature_fiscal_enterprise_true(self):
        from src.license.validator import check_feature
        assert check_feature("enterprise", "fiscal_electronic") is True

    def test_check_quota_trial_leads_under_limit(self):
        from src.license.validator import check_quota
        assert check_quota("trial", "leads", 5) is True

    def test_check_quota_trial_leads_at_limit(self):
        from src.license.validator import check_quota
        assert check_quota("trial", "leads", 10) is False

    def test_check_quota_individual_leads_under_limit(self):
        from src.license.validator import check_quota
        assert check_quota("individual", "leads", 500) is True

    def test_check_quota_enterprise_leads_unlimited(self):
        from src.license.validator import check_quota
        assert check_quota("enterprise", "leads", 999999) is True

    def test_check_quota_trial_invoices(self):
        from src.license.validator import check_quota
        assert check_quota("trial", "invoices_per_month", 3) is True
        assert check_quota("trial", "invoices_per_month", 5) is False

    def test_check_quota_trial_products(self):
        from src.license.validator import check_quota
        assert check_quota("trial", "products", 15) is True
        assert check_quota("trial", "products", 20) is False


# ── 1G: i18n ────────────────────────────────────────────────────────

class TestI18nKeys:
    """Tests para claves i18n nuevas del Foso 3."""

    def test_es_has_crm_keys(self):
        from src.core.i18n.locales.es import MESSAGES
        crm_keys = [k for k in MESSAGES if k.startswith("crm.")]
        assert len(crm_keys) >= 20, f"Expected 20+ crm keys, got {len(crm_keys)}"

    def test_es_has_invoice_keys(self):
        from src.core.i18n.locales.es import MESSAGES
        inv_keys = [k for k in MESSAGES if k.startswith("invoice.")]
        assert len(inv_keys) >= 15, f"Expected 15+ invoice keys, got {len(inv_keys)}"

    def test_es_has_inventory_keys(self):
        from src.core.i18n.locales.es import MESSAGES
        inv_keys = [k for k in MESSAGES if k.startswith("inventory.")]
        assert len(inv_keys) >= 12, f"Expected 12+ inventory keys, got {len(inv_keys)}"

    def test_es_has_mi_negocio_keys(self):
        from src.core.i18n.locales.es import MESSAGES
        mn_keys = [k for k in MESSAGES if k.startswith("mi_negocio.")]
        assert len(mn_keys) >= 4, f"Expected 4+ mi_negocio keys, got {len(mn_keys)}"

    def test_es_total_new_keys_at_least_60(self):
        from src.core.i18n.locales.es import MESSAGES
        foso3_keys = [k for k in MESSAGES if k.startswith(("crm.", "invoice.", "inventory.", "mi_negocio."))]
        assert len(foso3_keys) >= 60, f"Expected 60+ Foso 3 keys, got {len(foso3_keys)}"

    def test_specific_key_exists(self):
        from src.core.i18n.locales.es import MESSAGES
        assert MESSAGES["crm.title"] == "CRM"
        assert MESSAGES["invoice.mark_paid"] == "Marcar Pagada"
        assert MESSAGES["inventory.stock_low"] == "Stock Bajo"


# ── 1I: Startup Wiring ──────────────────────────────────────────────

class TestStartupWiring:
    """Tests para registro de subscribers en main.py."""

    def test_main_py_imports_pyme_orchestrator(self):
        """Verificar que main.py contiene el import de pyme_orchestrator."""
        source = Path("src/main.py").read_text()
        assert "pyme_orchestrator" in source
        assert "register_subscribers" in source

    def test_main_py_registers_subscribers(self):
        """Verificar que main.py llama register_subscribers(event_bus)."""
        source = Path("src/main.py").read_text()
        assert "register_subscribers(event_bus)" in source


# ── 1F: Frontend ────────────────────────────────────────────────────

class TestFrontendMiNegocio:
    """Tests para MiNegocioPage.tsx."""

    def test_minegocio_page_exists(self):
        assert Path("frontend/src/pages/MiNegocioPage.tsx").exists()

    def test_minegocio_route_registered(self):
        source = Path("frontend/src/App.tsx").read_text()
        assert "MiNegocioPage" in source
        assert "mi-negocio" in source

    def test_minegocio_page_has_dashboard_layout(self):
        """Tras SF6 (BUG-31 fix), la página usa react-i18next en vez de strings hardcoded.

        Verifica:
        - Importa useTranslation desde react-i18next
        - Llama a t('minegocio.title') para el título (no string literal "Mi Negocio")
        - Tiene las 3 cards top (Leads, Facturas Pendientes, Ingresos del Mes)
        - Tiene las 2 cards bottom (Stock Crítico, Pipeline de Ventas)
        """
        source = Path("frontend/src/pages/MiNegocioPage.tsx").read_text()
        # SF6: usa i18n en vez de strings hardcoded
        assert "useTranslation" in source, "MiNegocioPage debe importar useTranslation"
        assert "t('minegocio.title')" in source or 't("minegocio.title")' in source
        # Layout: 3 cards top + 2 cards bottom
        assert "md:grid-cols-3" in source, "Debe tener grid de 3 columnas en top row"
        assert "md:grid-cols-2" in source, "Debe tener grid de 2 columnas en bottom row"
        # Claves i18n que cubren los 5 KPI cards
        assert "crm.leads" in source
        assert "minegocio.pending_invoices" in source
        assert "minegocio.month_revenue" in source
        assert "minegocio.critical_stock" in source
        assert "minegocio.sales_pipeline" in source


# ── Integration E2E: License gating con CRM ────────────────────────

class TestIntegrationLicenseCRM:
    """E2E: verificar que el license gating funciona con CRM."""

    def test_trial_cannot_exceed_lead_quota(self, fresh_db):
        from src.hat.level5_tools.business.crm.service import CRMService
        from src.license.validator import check_quota
        crm = CRMService()

        # Crear 10 leads (límite trial)
        for i in range(10):
            crm.create_lead(name=f"Lead {i}")

        # Verificar que el quota está agotado
        stats = crm.get_stats()
        assert stats["total"] >= 10
        assert check_quota("trial", "leads", stats["total"]) is False
