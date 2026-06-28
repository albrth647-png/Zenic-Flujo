"""
HAT-ORBITAL Anti-Doble-Llamada — Tipos compartidos.

``AntiDupResult`` se define aquí para romper la importación circular entre
``cascade.py`` (importa ``ExactMatchLayer`` de ``exact_match.py``) y
``exact_match.py`` (importaba ``AntiDupResult`` de ``cascade.py``).
"""

from __future__ import annotations

from typing import Any, TypedDict


class AntiDupResult(TypedDict, total=False):
    """Resultado de una capa del cascade anti-doble-llamada.

    Campos según ``action``:
    - ``'return_cache'``: ``cached_result``
    - ``'subscribe'``: ``subscription_id``
    - Siempre: ``duplicate``, ``action``, ``reason``, ``layer_hit``
    """
    duplicate: bool
    action: str
    layer_hit: str
    reason: str
    # legítimo: cache dinámico del dispatch HAT
    cached_result: Any
    subscription_id: str | None
