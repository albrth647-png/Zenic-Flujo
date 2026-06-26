"""
HAT Bootstrap — Inicialización del sistema HAT de 5 niveles
============================================================

Punto de entrada para inicializar HAT al arrancar el servidor.
Debe llamarse DESPUÉS de inicializar DatabaseManager y EventBus,
y ANTES de que el HATRouter atienda el primer request.

Flujo de inicialización (5 niveles):
1. NIVEL 5: ToolsRegistry.register_all(event_bus) — instancia 19 tools
2. NIVEL 4: WorkerFactory.generate_all() — auto-genera ~100 workers
3. NIVEL 3: SpecialistFactory.generate_all() — crea 9 specialists
4. NIVEL 3: SpecialistFactory.publish_all_cards() — publica AgentCards al OVC
5. NIVEL 2: Inicializa 3 DomainSupervisors con sus specialists
6. NIVEL 1: Crea HATRouter con supervisors inyectados

Uso (en main.py o api_v2/app.py lifespan):
    from src.hat import bootstrap_hat
    hat_router = bootstrap_hat(event_bus=event_bus)

Resultado: HATRouter listo para atender requests con routing RCC funcional.
"""

from __future__ import annotations

import functools

from src.core.logging import get_logger

logger = get_logger("hat.bootstrap")


def bootstrap_hat(
    event_bus: object = None,
    force: bool = False,
) -> object:
    """Inicializa todo el sistema HAT de 5 niveles.

    Args:
        event_bus: EventBus compartido para tools que lo requieren.
        force: Si True, regenera aunque ya esté inicializado.

    Returns:
        HATRouter listo para atender requests.

    Flujo:
        1. NIVEL 5 (Tools) — instanciar 19 tools
        2. NIVEL 4 (Workers) — generar ~100 workers
        3. NIVEL 3 (Specialists) — crear 9 specialists + publicar AgentCards
        4. NIVEL 2 (Supervisors) — inicializar 3 con sus specialists
        5. NIVEL 1 (HATRouter) — crear con supervisors inyectados
    """
    logger.info("=== HAT Bootstrap iniciando ===")

    # === NIVEL 5: Tools ===
    from src.hat.level5_tools.registry import get_tools_registry
    tools_registry = get_tools_registry()
    tools = tools_registry.register_all(event_bus=event_bus)
    logger.info("Nivel 5 (Tools): %d tools registradas", len(tools))

    # === NIVEL 4: Workers (auto-generados desde tools) ===
    from src.hat.level4_workers.base.worker_factory import WorkerFactory
    worker_factory = WorkerFactory()
    all_workers = worker_factory.generate_all()
    total_workers = sum(len(w) for w in all_workers.values())
    logger.info("Nivel 4 (Workers): %d workers auto-generados", total_workers)

    # === NIVEL 3: Specialists (9) ===
    from src.hat.level3_specialists.operaciones import CrmSpecialist, InvoiceSpecialist, InventorySpecialist
    from src.hat.level3_specialists.comunicaciones import NotificationSpecialist, EmailSpecialist, ChatSpecialist
    from src.hat.level3_specialists.datos_auto import DataSpecialist, ApiSpecialist, CodeSpecialist

    # Crear specialists con tools inyectadas
    specialists_by_domain: dict[str, dict[str, object]] = {
        "operaciones": {
            "crm": CrmSpecialist(tools={"crm": tools.get("crm")}),
            "invoice": InvoiceSpecialist(tools={
                "invoice": tools.get("invoice"),
                "stripe": tools.get("stripe"),
                "mercadopago": tools.get("mercadopago"),
            }),
            "inventory": InventorySpecialist(tools={"inventory": tools.get("inventory")}),
        },
        "comunicaciones": {
            "notification": NotificationSpecialist(tools={"notification": tools.get("notification")}),
            "email": EmailSpecialist(tools={"gmail": tools.get("gmail")}),
            "chat": ChatSpecialist(tools={
                "slack": tools.get("slack"),
                "telegram": tools.get("telegram"),
            }),
        },
        "datos_auto": {
            "data": DataSpecialist(tools={
                "data_keeper": tools.get("data_keeper"),
                "sheets": tools.get("sheets"),
                "drive": tools.get("drive"),
                "postgresql": tools.get("postgresql"),
            }),
            "api": ApiSpecialist(tools={"api_connector": tools.get("api_connector")}),
            "code": CodeSpecialist(tools={
                "code_runner": tools.get("code_runner"),
                "logic_gate": tools.get("logic_gate"),
                "autopilot": tools.get("autopilot"),
                "openai": tools.get("openai"),
                "ollama": tools.get("ollama"),
            }),
        },
    }

    total_specialists = sum(len(s) for s in specialists_by_domain.values())
    logger.info("Nivel 3 (Specialists): %d specialists creados", total_specialists)

    # Publicar AgentCards al OVC + DB (CRÍTICO para routing RCC del Nivel 1)
    cards_published = 0
    for domain_specialists in specialists_by_domain.values():
        for specialist in domain_specialists.values():
            try:
                specialist.publish_card()
                cards_published += 1
            except Exception as exc:
                logger.warning("publish_card falló para %s: %s", specialist.specialist_name, exc)
    logger.info("Agent Cards publicadas: %d", cards_published)

    # === NIVEL 2: Supervisores (3 dominios) ===
    from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
    from src.hat.level2_supervisors.operaciones import OperacionesSupervisor
    from src.hat.level2_supervisors.comunicaciones import ComunicacionesSupervisor
    from src.hat.level2_supervisors.datos_auto import DatosAutoSupervisor

    ledger = LedgerRepository()

    supervisors = {
        "operaciones": OperacionesSupervisor(
            specialists=specialists_by_domain["operaciones"],
            ledger=ledger,
        ),
        "comunicaciones": ComunicacionesSupervisor(
            specialists=specialists_by_domain["comunicaciones"],
            ledger=ledger,
        ),
        "datos_auto": DatosAutoSupervisor(
            specialists=specialists_by_domain["datos_auto"],
            ledger=ledger,
        ),
    }
    logger.info("Nivel 2 (Supervisors): 3 supervisores inicializados")

    # === NIVEL 1: HATRouter ===
    from src.orbital.context import OrbitalContext
    from src.hat.level1_orchestrator.ledger.ovc_bridge import OVCLedgerBridge
    from src.hat.level1_orchestrator.tick_router import HATRouter

    ctx = OrbitalContext()
    bridge = OVCLedgerBridge(repo=ledger, ctx=ctx)

    hat_router = HATRouter(
        ledger=ledger,
        ctx=ctx,
        bridge=bridge,
        supervisors=supervisors,
    )
    logger.info("Nivel 1 (HATRouter): inicializado con %d supervisores", len(supervisors))

    logger.info("=== HAT Bootstrap completo ===")
    logger.info(
        "Sistema listo: 1 HATRouter + 3 Supervisores + %d Specialists + %d Workers + %d Tools",
        total_specialists, total_workers, len(tools),
    )

    return hat_router


@functools.lru_cache(maxsize=1)
def get_hat_router(event_bus: object = None) -> object:
    """Factory singleton para obtener el HATRouter.

    Usa ``functools.lru_cache(maxsize=1)`` para garantizar una sola
    inicialización. Llamadas sucesivas retornan el mismo router.
    En tests, el cache se resetea con ``get_hat_router.cache_clear()``
    (reemplaza el viejo pattern ``global _cached_router``).

    Returns:
        HATRouter inicializado.
    """
    return bootstrap_hat(event_bus=event_bus)
