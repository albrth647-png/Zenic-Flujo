"""
HAT NIVEL 5 — Tools Registry Central
=====================================

Registro central de tools ZF. Punto ÚNICO de extensión:
añadir tool nueva = 1 entrada en _REGISTRY.

Al iniciar el servidor, `register_all()` instancia todas las tools
y las registra tanto en el WorkflowEngine (para workflows multi-step)
como en el SpecialistsRegistry (para que HAT las descubra).

Categorías:
- business: crm, invoice, inventory
- payments: stripe, mercadopago
- communications: notification, gmail, slack, telegram
- data: data_keeper, api_connector, sheets, drive, postgresql
- automation: code_runner, logic_gate, autopilot, openai, ollama
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from src.events.bus import EventBus
from src.core.logging import get_logger

logger = get_logger("hat.level5.registry")


@dataclass(frozen=True)
class ToolRegistration:
    """Registro de una tool ZF en el sistema HAT."""

    name: str                       # "crm", "invoice", "gmail"
    domain: str                     # "operaciones", "comunicaciones", "datos_auto"
    category: str                   # "business", "communications", ...
    import_path: str                # "src.hat.level5_tools.business.crm.service"
    class_name: str                 # "CRMService"
    requires_event_bus: bool = False  # True si la tool acepta event_bus en __init__


# Mapeo tool_name → metadatos
# EXTENSIÓN: añadir tool nueva = añadir 1 entrada aquí
_REGISTRY: list[ToolRegistration] = [
    # === BUSINESS (operaciones) ===
    ToolRegistration(
        name="crm",
        domain="operaciones",
        category="business",
        import_path="src.hat.level5_tools.business.crm.service",
        class_name="CRMService",
        requires_event_bus=True,
    ),
    ToolRegistration(
        name="invoice",
        domain="operaciones",
        category="business",
        import_path="src.hat.level5_tools.business.invoice.service",
        class_name="InvoiceService",
        requires_event_bus=True,
    ),
    ToolRegistration(
        name="inventory",
        domain="operaciones",
        category="business",
        import_path="src.hat.level5_tools.business.inventory.service",
        class_name="InventoryService",
        requires_event_bus=True,
    ),
    # === PAYMENTS (operaciones) ===
    ToolRegistration(
        name="stripe",
        domain="operaciones",
        category="payments",
        import_path="src.hat.level5_tools.payments.stripe_service",
        class_name="StripeService",
    ),
    ToolRegistration(
        name="mercadopago",
        domain="operaciones",
        category="payments",
        import_path="src.hat.level5_tools.payments.mercadopago_service",
        class_name="MercadoPagoService",
    ),
    # === COMMUNICATIONS (comunicaciones) ===
    ToolRegistration(
        name="notification",
        domain="comunicaciones",
        category="communications",
        import_path="src.hat.level5_tools.communications.notification.service",
        class_name="NotificationService",
    ),
    ToolRegistration(
        name="gmail",
        domain="comunicaciones",
        category="communications",
        import_path="src.hat.level5_tools.communications.gmail_service",
        class_name="GmailService",
    ),
    ToolRegistration(
        name="slack",
        domain="comunicaciones",
        category="communications",
        import_path="src.hat.level5_tools.communications.slack_service",
        class_name="SlackService",
    ),
    ToolRegistration(
        name="telegram",
        domain="comunicaciones",
        category="communications",
        import_path="src.hat.level5_tools.communications.telegram_service",
        class_name="TelegramService",
    ),
    # === DATA (datos_auto) ===
    ToolRegistration(
        name="data_keeper",
        domain="datos_auto",
        category="data",
        import_path="src.hat.level5_tools.data.data_keeper.service",
        class_name="DataKeeperService",
    ),
    ToolRegistration(
        name="api_connector",
        domain="datos_auto",
        category="data",
        import_path="src.hat.level5_tools.data.api_connector.service",
        class_name="APIConnectorService",
    ),
    ToolRegistration(
        name="sheets",
        domain="datos_auto",
        category="data",
        import_path="src.hat.level5_tools.data.sheets_service",
        class_name="SheetsService",
    ),
    ToolRegistration(
        name="drive",
        domain="datos_auto",
        category="data",
        import_path="src.hat.level5_tools.data.drive_service",
        class_name="DriveService",
    ),
    ToolRegistration(
        name="postgresql",
        domain="datos_auto",
        category="data",
        import_path="src.hat.level5_tools.data.postgresql_service",
        class_name="PostgreSQLService",
    ),
    # === AUTOMATION (datos_auto) ===
    ToolRegistration(
        name="code_runner",
        domain="datos_auto",
        category="automation",
        import_path="src.hat.level5_tools.automation.code_runner.service",
        class_name="CodeRunnerTool",
    ),
    ToolRegistration(
        name="logic_gate",
        domain="datos_auto",
        category="automation",
        import_path="src.hat.level5_tools.automation.logic_gate.service",
        class_name="LogicGateService",
        requires_event_bus=True,
    ),
    ToolRegistration(
        name="autopilot",
        domain="datos_auto",
        category="automation",
        import_path="src.hat.level5_tools.automation.autopilot.service",
        class_name="AutoPilotService",
    ),
    ToolRegistration(
        name="openai",
        domain="datos_auto",
        category="automation",
        import_path="src.hat.level5_tools.automation.openai_service",
        class_name="OpenAIService",
    ),
    ToolRegistration(
        name="ollama",
        domain="datos_auto",
        category="automation",
        import_path="src.hat.level5_tools.automation.ollama_service",
        class_name="OllamaService",
    ),

    # === CONECTORES EXTERNOS (Phase 4) ===
    # 61 conectores de src/connectors/ registrados como tools de HAT.
    # Ver src/hat/level5_tools/connectors_registry.py para el catálogo completo.
    # Categorías: business, payments, communications, data, automation
]

# Phase 4: Añadir conectores externos al _REGISTRY dinámicamente.
# Esto expande HAT de 19 tools nativas a 80 tools total (19 + 61 conectores).
try:
    from src.hat.level5_tools.connectors_registry import CONNECTORS_REGISTRY
    for _name, _domain, _category, _import_path, _class_name, _ebus in CONNECTORS_REGISTRY:
        _REGISTRY.append(ToolRegistration(
            name=_name,
            domain=_domain,
            category=_category,
            import_path=_import_path,
            class_name=_class_name,
            requires_event_bus=_ebus,
        ))
except ImportError:
    pass  # connectors_registry no disponible (ej: tests aislados)


class ToolsRegistry:
    """Registry central de tools activas.

    Mantiene instancias singleton de cada tool registrada.
    Tanto el WorkflowEngine como el SpecialistsRegistry consultan este registry.
    """

    _instance: ToolsRegistry | None = None
    _tools: dict[str, Any]
    _specs: dict[str, ToolRegistration]

    def __new__(cls) -> ToolsRegistry:
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._tools = {}
            instance._specs = {
                reg.name: reg for reg in _REGISTRY
            }
            cls._instance = instance
        return cls._instance

    def register_all(self, event_bus: EventBus | None = None) -> dict[str, Any]:
        """Instancia todas las tools registradas y las guarda como singletons.

        Args:
            event_bus: EventBus opcional para tools que lo requieren (CRM, Invoice, etc.)

        Returns:
            Dict {tool_name: tool_instance}
        """
        for name, spec in self._specs.items():
            if name in self._tools:
                continue  # ya instanciada
            try:
                module = importlib.import_module(spec.import_path)
                cls = getattr(module, spec.class_name)

                # Algunas tools aceptan event_bus en __init__
                if spec.requires_event_bus and event_bus is not None:
                    try:
                        instance = cls(event_bus=event_bus)
                    except TypeError:
                        # Fallback: la tool no acepta event_bus aunque lo marcamos
                        instance = cls()
                else:
                    instance = cls()

                self._tools[name] = instance
                logger.info("Tool registrada: %s (%s.%s)", name, spec.domain, spec.category)
            except Exception as exc:
                logger.error("Error registrando tool %s: %s", name, exc)

        return self._tools

    def get(self, name: str) -> Any | None:
        """Obtiene una tool por nombre. None si no existe."""
        return self._tools.get(name)

    def get_spec(self, name: str) -> ToolRegistration | None:
        """Obtiene los metadatos de una tool."""
        return self._specs.get(name)

    def list_all(self) -> dict[str, Any]:
        """Retorna todas las tools instanciadas."""
        return dict(self._tools)

    def list_by_domain(self, domain: str) -> dict[str, Any]:
        """Retorna las tools de un dominio específico."""
        return {
            name: tool
            for name, tool in self._tools.items()
            if self._specs.get(name) and self._specs[name].domain == domain
        }

    def list_domains(self) -> list[str]:
        """Lista de dominios únicos con tools registradas."""
        return sorted({spec.domain for spec in self._specs.values()})

    def list_by_category(self, category: str) -> dict[str, Any]:
        """Retorna las tools de una categoría específica."""
        return {
            name: tool
            for name, tool in self._tools.items()
            if self._specs.get(name) and self._specs[name].category == category
        }

    def list_categories(self) -> list[str]:
        """Lista de categorías únicas."""
        return sorted({spec.category for spec in self._specs.values()})

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def get_tools_registry() -> ToolsRegistry:
    """Factory del singleton ToolsRegistry."""
    return ToolsRegistry()
