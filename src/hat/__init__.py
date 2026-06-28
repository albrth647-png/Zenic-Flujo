"""
HAT — Arquitectura de 5 Niveles
================================

Estructura:
- NIVEL 1: level1_orchestrator/ — Orquestador central Orbital (HATRouter)
- NIVEL 2: level2_supervisors/ — 3 sub-orquestadores independientes
- NIVEL 3: level3_specialists/ — 9 specialists (1 responsabilidad cada uno)
- NIVEL 4: level4_workers/ — ~101 workers (más extenso que N3)
- NIVEL 5: level5_tools/ — 19 tools ZF reales (base final)

Punto de entrada público: HATRouter (Nivel 1)
Inicialización: bootstrap_hat() o get_hat_router()
"""

# Lazy imports para evitar circular deps al cargar el paquete
__all__ = ["HATRouter", "bootstrap_hat", "get_hat_router"]
__version__ = "2.0.0"


def __getattr__(name):
    """PEP 562 lazy attribute access."""
    if name == "HATRouter":
        from src.hat.level1_orchestrator.tick_router import HATRouter
        return HATRouter
    if name == "bootstrap_hat":
        from src.hat.bootstrap import bootstrap_hat
        return bootstrap_hat
    if name == "get_hat_router":
        from src.hat.bootstrap import get_hat_router
        return get_hat_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
