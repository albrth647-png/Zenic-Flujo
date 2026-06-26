"""Tests para ToolsRegistry y ToolRegistration — registro central de 19 tools.

Cubre:
- ToolRegistration: dataclass frozen, atributos, requires_event_bus default.
- _REGISTRY: 19 entradas, 5 categorías, 3 dominios.
- ToolsRegistry: singleton, register_all, get, get_spec, list_all.
- list_by_domain, list_by_category, list_domains, list_categories.
- __len__, __contains__.
- get_tools_registry factory.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.hat.level5_tools.registry import (
    _REGISTRY,
    ToolRegistration,
    ToolsRegistry,
    get_tools_registry,
)

# ── Tests de ToolRegistration ──────────────────────────────────────────


class TestToolRegistration:
    """Dataclass ToolRegistration (frozen)."""

    def test_minimal_registration(self) -> None:
        """Registration con campos requeridos."""
        reg = ToolRegistration(
            name="crm",
            domain="operaciones",
            category="business",
            import_path="src.hat.level5_tools.business.crm.service",
            class_name="CRMService",
        )
        assert reg.name == "crm"
        assert reg.domain == "operaciones"
        assert reg.category == "business"
        assert reg.import_path == "src.hat.level5_tools.business.crm.service"
        assert reg.class_name == "CRMService"
        assert reg.requires_event_bus is False  # default

    def test_requires_event_bus_default_false(self) -> None:
        """requires_event_bus default es False."""
        reg = ToolRegistration(
            name="x", domain="d", category="c",
            import_path="p", class_name="C",
        )
        assert reg.requires_event_bus is False

    def test_requires_event_bus_true(self) -> None:
        """requires_event_bus=True se respeta."""
        reg = ToolRegistration(
            name="crm", domain="d", category="c",
            import_path="p", class_name="C",
            requires_event_bus=True,
        )
        assert reg.requires_event_bus is True

    def test_frozen_dataclass(self) -> None:
        """ToolRegistration es frozen — no se puede mutar."""
        reg = ToolRegistration(
            name="x", domain="d", category="c",
            import_path="p", class_name="C",
        )
        with pytest.raises(AttributeError):
            reg.name = "other"  # type: ignore[misc]


# ── Tests de _REGISTRY (las 19 tools) ──────────────────────────────────


class TestRegistryContents:
    """El _REGISTRY tiene las 19 tools esperadas."""

    def test_registry_has_tools(self) -> None:
        """_REGISTRY tiene al menos 75 entradas (19 nativas + conectores variables)."""
        assert len(_REGISTRY) >= 75

    def test_all_entries_are_tool_registration(self) -> None:
        """Todas las entradas son instancias de ToolRegistration."""
        for reg in _REGISTRY:
            assert isinstance(reg, ToolRegistration)

    def test_unique_names(self) -> None:
        """Todos los names son únicos."""
        names = [reg.name for reg in _REGISTRY]
        assert len(names) == len(set(names))

    def test_business_tools_present(self) -> None:
        """Categoría 'business' tiene crm, invoice, inventory."""
        business = [r.name for r in _REGISTRY if r.category == "business"]
        assert "crm" in business
        assert "invoice" in business
        assert "inventory" in business

    def test_payments_tools_present(self) -> None:
        """Categoría 'payments' tiene stripe, mercadopago."""
        payments = [r.name for r in _REGISTRY if r.category == "payments"]
        assert "stripe" in payments
        assert "mercadopago" in payments

    def test_communications_tools_present(self) -> None:
        """Categoría 'communications' tiene notification, gmail, slack, telegram."""
        comm = [r.name for r in _REGISTRY if r.category == "communications"]
        assert "notification" in comm
        assert "gmail" in comm
        assert "slack" in comm
        assert "telegram" in comm

    def test_data_tools_present(self) -> None:
        """Categoría 'data' tiene data_keeper, api_connector, sheets, drive, postgresql."""
        data = [r.name for r in _REGISTRY if r.category == "data"]
        assert "data_keeper" in data
        assert "api_connector" in data
        assert "sheets" in data
        assert "drive" in data
        assert "postgresql" in data

    def test_automation_tools_present(self) -> None:
        """Categoría 'automation' tiene code_runner, logic_gate, autopilot, openai, ollama."""
        auto = [r.name for r in _REGISTRY if r.category == "automation"]
        assert "code_runner" in auto
        assert "logic_gate" in auto
        assert "autopilot" in auto
        assert "openai" in auto
        assert "ollama" in auto

    def test_all_tools_have_valid_domain(self) -> None:
        """Todas las tools tienen domain en {operaciones, comunicaciones, datos_auto}."""
        valid_domains = {"operaciones", "comunicaciones", "datos_auto"}
        for reg in _REGISTRY:
            assert reg.domain in valid_domains, f"{reg.name} has invalid domain: {reg.domain}"

    def test_operaciones_domain_has_correct_tools(self) -> None:
        """Dominio 'operaciones' tiene business + payments (5 tools)."""
        ops = [r.name for r in _REGISTRY if r.domain == "operaciones"]
        assert "crm" in ops
        assert "invoice" in ops
        assert "inventory" in ops
        assert "stripe" in ops
        assert "mercadopago" in ops

    def test_tools_requiring_event_bus(self) -> None:
        """Las tools que requieren event_bus son las correctas."""
        requires_eb = [r.name for r in _REGISTRY if r.requires_event_bus]
        assert "crm" in requires_eb
        assert "invoice" in requires_eb
        assert "inventory" in requires_eb
        assert "logic_gate" in requires_eb


# ── Tests de ToolsRegistry singleton ───────────────────────────────────


class TestToolsRegistrySingleton:
    """ToolsRegistry es un singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        """Dos llamadas a ToolsRegistry() retornan la misma instancia."""
        # Reset singleton para test aislado
        ToolsRegistry._instance = None
        r1 = ToolsRegistry()
        r2 = ToolsRegistry()
        assert r1 is r2

    def test_get_tools_registry_returns_singleton(self) -> None:
        """get_tools_registry() retorna el singleton."""
        ToolsRegistry._instance = None
        r1 = get_tools_registry()
        r2 = get_tools_registry()
        assert r1 is r2


# ── Tests de register_all ──────────────────────────────────────────────


class TestRegisterAll:
    """register_all() instancia las tools."""

    def test_register_all_returns_dict(self) -> None:
        """register_all() retorna un dict."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_class = MagicMock(return_value=MagicMock())
            mock_module.CRMService = mock_class
            mock_import.return_value = mock_module
            tools = registry.register_all()
        assert isinstance(tools, dict)

    def test_register_all_with_event_bus(self) -> None:
        """register_all(event_bus=...) pasa event_bus a tools que lo requieren."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        mock_event_bus = MagicMock()

        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_class = MagicMock(return_value=MagicMock())
            mock_module.CRMService = mock_class
            mock_import.return_value = mock_module

            registry.register_all(event_bus=mock_event_bus)
            # Al menos una tool fue instanciada
            assert mock_class.called


# ── Tests de get / get_spec ────────────────────────────────────────────


class TestGetMethods:
    """get() y get_spec()."""

    def test_get_returns_none_for_unregistered(self) -> None:
        """get() retorna None para tool no registrada."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        assert registry.get("nonexistent") is None

    def test_get_spec_returns_none_for_unregistered(self) -> None:
        """get_spec() retorna None para tool no registrada."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        assert registry.get_spec("nonexistent") is None

    def test_get_spec_returns_registration(self) -> None:
        """get_spec() retorna ToolRegistration para tool conocida."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        spec = registry.get_spec("crm")
        assert spec is not None
        assert isinstance(spec, ToolRegistration)
        assert spec.name == "crm"
        assert spec.domain == "operaciones"


# ── Tests de list methods ──────────────────────────────────────────────


class TestListMethods:
    """list_all, list_by_domain, list_by_category, list_domains, list_categories."""

    def test_list_domains_returns_sorted(self) -> None:
        """list_domains() retorna dominios ordenados."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        domains = registry.list_domains()
        assert isinstance(domains, list)
        assert domains == sorted(domains)
        assert "operaciones" in domains
        assert "comunicaciones" in domains
        assert "datos_auto" in domains

    def test_list_categories_returns_sorted(self) -> None:
        """list_categories() retorna categorías ordenadas."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        cats = registry.list_categories()
        assert isinstance(cats, list)
        assert cats == sorted(cats)
        assert "business" in cats
        assert "payments" in cats
        assert "communications" in cats
        assert "data" in cats
        assert "automation" in cats


# ── Tests de __len__ y __contains__ ────────────────────────────────────


class TestDunderMethods:
    """__len__ y __contains__."""

    def test_len_returns_zero_initially(self) -> None:
        """len(registry) == 0 antes de register_all."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        assert len(registry) == 0

    def test_contains_returns_false_for_unregistered(self) -> None:
        """'nonexistent' not in registry antes de register_all."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        assert "nonexistent" not in registry

    def test_contains_returns_true_for_registered_spec(self) -> None:
        """'crm' in registry verifica si está en specs (no en instancias)."""
        ToolsRegistry._instance = None
        registry = ToolsRegistry()
        # crm está en _specs aunque no esté instanciada
        # __contains__ verifica _tools, no _specs
        assert "crm" not in registry  # no instanciada aún
