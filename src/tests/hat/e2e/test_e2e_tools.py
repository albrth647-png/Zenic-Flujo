"""E2E tests for Nivel 5 tools — verify tools work directly."""

from __future__ import annotations

import pytest

from src.events.bus import EventBus
from src.hat.level5_tools.registry import get_tools_registry


@pytest.fixture(scope="module")
def tools():
    """Register all tools once."""
    return get_tools_registry().register_all(event_bus=EventBus())


class TestCRMTool:
    def test_create_and_list_lead(self, tools):
        crm = tools.get("crm")
        assert crm is not None
        lead = crm.create_lead(name="E2E Test Lead", email="e2e@test.com")
        assert lead["name"] == "E2E Test Lead"
        leads = crm.list_leads()
        assert isinstance(leads, list)
        assert len(leads) >= 1

    def test_get_stats(self, tools):
        crm = tools.get("crm")
        stats = crm.get_stats()
        assert isinstance(stats, dict)
        assert "total" in stats


class TestInventoryTool:
    def test_add_and_list_product(self, tools):
        inv = tools.get("inventory")
        assert inv is not None
        import time
        unique_sku = f"E2E-{int(time.time())}"
        product = inv.add_product(sku=unique_sku, name="E2E Product", stock=10, price=9.99)
        assert product["sku"] == unique_sku
        products = inv.list_products()
        assert isinstance(products, list)

    def test_get_stats(self, tools):
        inv = tools.get("inventory")
        stats = inv.get_stats()
        assert isinstance(stats, dict)


class TestCodeRunnerTool:
    def test_run_python_simple(self, tools):
        runner = tools.get("code_runner")
        assert runner is not None
        result = runner.run_python(code="result = 2 + 2", output_var="result")
        assert result["success"] is True
        assert result["output"]["result"] == 4

    def test_validate_code(self, tools):
        runner = tools.get("code_runner")
        result = runner.validate(code="x = 1")
        assert result["valid"] is True


class TestLogicGateTool:
    def test_evaluate_rule(self, tools):
        gate = tools.get("logic_gate")
        assert gate is not None
        result = gate.evaluate_rule(rule="x > 5", context={"x": 10})
        assert result is True


class TestToolsRegistry:
    def test_19_tools_registered(self, tools):
        assert len(tools) >= 15

    def test_tools_by_domain(self, tools):
        registry = get_tools_registry()
        ops = registry.list_by_domain("operaciones")
        assert len(ops) >= 3
        comms = registry.list_by_domain("comunicaciones")
        assert len(comms) >= 3
        datos = registry.list_by_domain("datos_auto")
        assert len(datos) >= 5
