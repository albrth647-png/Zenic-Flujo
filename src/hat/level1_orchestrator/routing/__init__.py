"""HAT-ORBITAL Nivel 1 — Routing facade.

Punto único de entrada al subsystem de routing del Nivel 1. Expone:

- :class:`OrbitalRouter` — routing por resonancia ORBITAL (top-3 dominios).
- :class:`KeywordRouter` — keyword override + FSM desambiguación.
- :func:`route_message` — helper de un solo call que combina ambos routers.

Uso típico desde ``HATRouter.handle()``::

    from src.hat.level1_orchestrator.routing import OrbitalRouter, KeywordRouter

    orbital = OrbitalRouter(ctx=ctx, session_id=session_id)
    top3 = orbital.route(message)

    keyword = KeywordRouter(active_domain=active_domain)
    domain = keyword.disambiguate(top3, message)

Implementado en M8 siguiendo IMPLEMENTATION_PLAN.md §M8.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.hat.level1_orchestrator.routing.keyword_router import KeywordRouter
from src.hat.level1_orchestrator.routing.orbital_router import OrbitalRouter

if TYPE_CHECKING:
    from src.orbital.context import OrbitalContext


__all__ = [
    "KeywordRouter",
    "OrbitalRouter",
    "route_message",
]


def route_message(
    ctx: OrbitalContext,
    session_id: str,
    message: str,
    active_domain: str | None = None,
) -> tuple[str, list[tuple[str, float]]]:
    """Helper que combina OrbitalRouter + KeywordRouter en un solo call.

    Flujo:
    1. ``OrbitalRouter.route(message)`` → top-3 dominios por resonancia.
    2. ``KeywordRouter.disambiguate(top3, message)`` → dominio ganador.

    Args:
        ctx: OrbitalContext singleton.
        session_id: ID de la sesión (para namespacing OVC).
        message: Texto del usuario.
        active_domain: Dominio activo del Ledger (opcional).

    Returns:
        Tupla ``(domain, top3)`` donde:
        - ``domain`` es el dominio ganador (o ``'clarify'`` si no resuelve).
        - ``top3`` es la lista de tuplas ``(domain, resonance)`` retornada
          por OrbitalRouter.
    """
    orbital = OrbitalRouter(ctx=ctx, session_id=session_id)
    top3 = orbital.route(message)

    keyword = KeywordRouter(active_domain=active_domain)
    domain = keyword.disambiguate(top3, message)

    return domain, top3
