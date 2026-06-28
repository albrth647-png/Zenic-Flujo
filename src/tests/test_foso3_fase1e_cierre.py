"""Tests Fase 1E — Cierre Foso 3 + Foso 2 al 100%.

Cubre:
- SF1: Pix Brazil host correcto (homo + prod)
- SF3/SF4: i18n EN + PT_BR con claves crm/invoice/inventory/minegocio
- SF7: Totvs write actions (create_product, update_product, etc.)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmpdir = tempfile.mkdtemp(prefix="fase1e_test_")
os.environ["HOME"] = _tmpdir
os.environ["WFD_PRODUCTION"] = "false"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


# ── SF1: Pix Brazil host ────────────────────────────────────────────────


class TestPixBrazilHost:
    """Fix Foso 2 SF1 — host BCB Pix correcto (homo + prod)."""

    def test_pix_brazil_homo_host_is_bcb_official(self):
        """El host de homologação debe ser api.hm-pix.bcb.gov.br (no api.pix.gov.br)."""
        from src.connectors.pix_brazil import PixBrazilConnector

        conn = PixBrazilConnector(environment="homo")
        assert conn._base_url == "https://api.hm-pix.bcb.gov.br/v2", (
            f"Host homo erróneo: {conn._base_url}"
        )

    def test_pix_brazil_prod_host_is_bcb_official(self):
        """El host de producción debe ser api-pix.bcb.gov.br."""
        from src.connectors.pix_brazil import PixBrazilConnector

        conn = PixBrazilConnector(environment="prod")
        assert conn._base_url == "https://api-pix.bcb.gov.br/v2", (
            f"Host prod erróneo: {conn._base_url}"
        )

    def test_pix_brazil_default_is_homo(self):
        """Sin environment explícito, default = homo (más seguro)."""
        from src.connectors.pix_brazil import PixBrazilConnector

        conn = PixBrazilConnector()
        assert conn._environment == "homo"
        assert "hm-pix" in conn._base_url

    def test_pix_brazil_invalid_environment_falls_back_to_homo(self):
        """Environment inválido → fallback a homo (no crashea)."""
        from src.connectors.pix_brazil import PixBrazilConnector

        conn = PixBrazilConnector(environment="staging")
        assert conn._environment == "homo"

    def test_pix_brazil_old_host_not_used(self):
        """El host viejo (api.pix.gov.br) NO debe aparecer en ningún lugar."""
        from src.connectors.pix_brazil import PixBrazilConnector

        conn_homo = PixBrazilConnector(environment="homo")
        conn_prod = PixBrazilConnector(environment="prod")
        for conn in (conn_homo, conn_prod):
            assert "api.pix.gov.br" not in conn._base_url, (
                "Host viejo api.pix.gov.br sigue presente — fix incompleto"
            )


# ── SF3 + SF4: i18n EN + PT_BR con claves crm/invoice/inventory ────────


class TestI18nCompleteness:
    """i18n EN y PT_BR deben tener las 76 claves crm/invoice/inventory/minegocio."""

    @pytest.fixture(scope="class")
    def es_keys(self):
        from src.core.i18n.locales import es

        return set(es.MESSAGES.keys())

    @pytest.fixture(scope="class")
    def en_keys(self):
        from src.core.i18n.locales import en

        return set(en.MESSAGES.keys())

    @pytest.fixture(scope="class")
    def pt_br_keys(self):
        from src.core.i18n.locales import pt_br

        return set(pt_br.MESSAGES.keys())

    def test_en_has_all_business_keys(self, es_keys, en_keys):
        """EN debe tener todas las claves crm.*/invoice.*/inventory.*/minegocio.* que ES."""
        business_keys = {
            k for k in es_keys
            if k.startswith(("crm.", "invoice.", "inventory.", "minegocio."))
        }
        missing = business_keys - en_keys
        assert not missing, f"EN falta {len(missing)} claves: {sorted(missing)[:10]}"

    def test_pt_br_has_all_business_keys(self, es_keys, pt_br_keys):
        """PT_BR debe tener todas las claves crm.*/invoice.*/inventory.*/minegocio.* que ES."""
        business_keys = {
            k for k in es_keys
            if k.startswith(("crm.", "invoice.", "inventory.", "minegocio."))
        }
        missing = business_keys - pt_br_keys
        assert not missing, f"PT_BR falta {len(missing)} claves: {sorted(missing)[:10]}"

    @pytest.mark.parametrize("key", [
        "crm.title", "crm.leads", "crm.clients", "crm.deals",
        "crm.stage_closed_won", "crm.convert_to_invoice",
        "invoice.title", "invoice.mark_paid", "invoice.overdue",
        "inventory.title", "inventory.stock_low", "inventory.stock_out_alert",
        "minegocio.title", "minegocio.critical_stock", "minegocio.sales_pipeline",
    ])
    def test_key_translated_in_en(self, en_keys, key):
        """Cada clave crítica existe en EN."""
        assert key in en_keys, f"Clave {key} no existe en EN"

    @pytest.mark.parametrize("key", [
        "crm.title", "crm.leads", "crm.clients", "crm.deals",
        "crm.stage_closed_won", "crm.convert_to_invoice",
        "invoice.title", "invoice.mark_paid", "invoice.overdue",
        "inventory.title", "inventory.stock_low", "inventory.stock_out_alert",
        "minegocio.title", "minegocio.critical_stock", "minegocio.sales_pipeline",
    ])
    def test_key_translated_in_pt_br(self, pt_br_keys, key):
        """Cada clave crítica existe en PT_BR."""
        assert key in pt_br_keys, f"Clave {key} no existe en PT_BR"

    def test_en_values_are_english(self):
        """Las traducciones EN no deben contener texto en español obvio."""
        from src.core.i18n.locales import en

        # Spot-check de claves que eran strings hardcoded en MiNegocioPage
        assert en.MESSAGES["minegocio.title"] == "My Business"
        assert en.MESSAGES["minegocio.critical_stock"] == "Critical Stock"
        assert en.MESSAGES["minegocio.sales_pipeline"] == "Sales Pipeline"
        assert en.MESSAGES["invoice.mark_paid"] == "Mark Paid"

    def test_pt_br_values_are_portuguese(self):
        """Las traducciones PT_BR deben ser portugués brasileño correcto."""
        from src.core.i18n.locales import pt_br

        assert pt_br.MESSAGES["minegocio.title"] == "Meu Negócio"
        assert pt_br.MESSAGES["minegocio.critical_stock"] == "Estoque Crítico"
        assert pt_br.MESSAGES["minegocio.sales_pipeline"] == "Pipeline de Vendas"
        assert pt_br.MESSAGES["invoice.mark_paid"] == "Marcar Paga"
        assert pt_br.MESSAGES["inventory.stock_low"] == "Estoque Baixo"


# ── SF7: Totvs write actions ───────────────────────────────────────────


class TestTotvsWriteActions:
    """SF7 — Totvs soporta write actions (no solo read)."""

    def test_totvs_schema_has_write_actions(self):
        """El schema debe listar al menos 7 acciones write."""
        from src.connectors.totvs import TOTVS_SCHEMA

        write_actions = [a for a in TOTVS_SCHEMA.actions if a.category == "write"]
        assert len(write_actions) >= 7, (
            f"Solo {len(write_actions)} write actions, esperadas >= 7"
        )

    @pytest.mark.parametrize("action_name", [
        "create_product", "update_product",
        "create_customer", "update_customer",
        "create_invoice", "create_sales_order",
        "post_financial_entry",
    ])
    def test_totvs_schema_lists_action(self, action_name):
        from src.connectors.totvs import TOTVS_SCHEMA

        names = {a.name for a in TOTVS_SCHEMA.actions}
        assert action_name in names, f"Action {action_name} no está en el schema"

    def test_totvs_connector_dispatches_write_actions(self):
        """execute() despacha write actions correctamente."""
        from src.connectors.totvs import TotvsConnector

        conn = TotvsConnector()
        # Sin connect(), _api retorna error controlado — suficiente para verificar dispatch
        result = conn.execute("create_product", {"name": "Test", "sku": "T001"})
        # No debe decir "accion no soportada"
        assert "no soportada" not in str(result.get("error", "")), (
            f"create_product no despachado: {result}"
        )

    def test_totvs_update_requires_id(self):
        """update_product sin product_id debe fallar con error explícito."""
        from src.connectors.totvs import TotvsConnector

        conn = TotvsConnector()
        result = conn.execute("update_product", {"name": "Test"})
        assert result["success"] is False
        assert "product_id" in result["error"]

    def test_totvs_financial_entry_routes_receivable_vs_payable(self, monkeypatch):
        """post_financial_entry enruta a /receivables o /payables según entry_type."""
        from src.connectors.totvs import TotvsConnector

        conn = TotvsConnector()
        # Mock _api para capturar el endpoint sin hacer HTTP real
        captured: list[str] = []

        def mock_api(method: str, path: str, **kw):
            captured.append((method, path))
            return {"success": True, "data": {}}

        monkeypatch.setattr(conn, "_api", mock_api)

        conn.execute("post_financial_entry", {"entry_type": "receivable", "amount": 100})
        conn.execute("post_financial_entry", {"entry_type": "payable", "amount": 50})

        assert ("post", "/financial/receivables") in captured
        assert ("post", "/financial/payables") in captured

    def test_totvs_version_bumped_to_1_1(self):
        """Versión bumpada a 1.1.0 (write actions añadidos)."""
        from src.connectors.totvs import TotvsConnector

        assert TotvsConnector.version == "1.1.0"
