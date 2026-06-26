"""
HAT-ORBITAL Anti-Doble-Llamada — Capa 2: Idempotency Lock.

Verifica si un dispatch con el mismo intent_hash está actualmente en progreso.
Si es así, el caller debe suscribirse al resultado en vez de duplicar el trabajo.

M9.3+: ahora consulta hat_progress (no hat_dispatch_registry) y detecta
cualquier estado activo ('dispatched', 'running', 'in_progress') como
in-progress. Solo 'completed' y 'failed' se consideran terminados.

Coste: ~3ms (1 SELECT + opcional UPDATE).
"""

from __future__ import annotations

from typing import Any

from src.hat.level1_orchestrator.anti_duplication._types import AntiDupResult
from src.core.logging import setup_logging
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository

logger = setup_logging(__name__)

# Estados considerados "activos" (dispatch en curso, no terminado).
# M9.3+: incluye 'dispatched' (nuevo estado inicial de hat_progress) y
# 'in_progress' (legacy de hat_dispatch_registry) por compatibilidad.
_ACTIVE_STATUSES = frozenset({"dispatched", "running", "in_progress"})


class IdempotencyLayer:
    """Capa 2: detecta dispatches in-progress y gestiona subscribers.

    Coste: ~3ms.
    Qué detecta: hash en ejecución → suscríbete al resultado (no dupliques).
    """

    def __init__(self, repo: LedgerRepository | None = None) -> None:
        self._repo = repo if repo is not None else LedgerRepository()
        logger.debug("IdempotencyLayer initialized")

    def check(self, intent_hash: str) -> AntiDupResult:
        """Verifica si el intent_hash tiene un dispatch in-progress.

        Args:
            intent_hash: Hash sha256 del intent del usuario.

        Returns:
            dict con:
                - duplicate: bool — True si hay dispatch in-progress
                - action: 'subscribe' si duplicate, 'proceed' si no
                - subscription_id: str | None — ID para suscribirse
                - reason: str
        """
        dispatch = self._repo.get_dispatch(intent_hash)
        if dispatch is None:
            logger.debug("Idempotency: no dispatch for hash=%.12s", intent_hash)
            return self._build_proceed("no dispatch found")
        if dispatch["status"] in _ACTIVE_STATUSES:
            subscriber_count = self._repo.increment_subscriber(intent_hash)
            logger.info("Idempotency DUPLICATE: hash=%.12s status=%s subscriber=#%d -> subscribe",
                        intent_hash, dispatch['status'], subscriber_count)
            return {
                "duplicate": True,
                "action": "subscribe",
                "subscription_id": f"sub_{intent_hash[:8]}_{subscriber_count}",
                "reason": f"idempotency: dispatch in_progress (status={dispatch['status']}), subscriber #{subscriber_count}",
            }
        logger.debug("Idempotency: hash=%.12s status=%s -> proceed", intent_hash, dispatch['status'])
        return self._build_proceed(f"dispatch status is {dispatch['status']}")

    @staticmethod
    def _build_proceed(reason: str) -> AntiDupResult:
        """Construye respuesta de 'no duplicado, continuar'."""
        return {
            "duplicate": False,
            "action": "proceed",
            "subscription_id": None,
            "reason": reason,
        }

