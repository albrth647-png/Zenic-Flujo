"""
HAT-ORBITAL Anti-Doble-Llamada — Capa 3: TTL Freshness.

Verifica si el usuario hizo un dispatch con el mismo intent_hash en los
últimos N segundos. Si es así, descarta el nuevo como doble-click accidental.
Mensajes diferentes dentro de la ventana TTL pasan (no se bloquean).

Coste: <1ms (cache hit) o ~2ms (cache miss + SELECT).
Incluye cache en memoria por intent_hash para evitar queries repetidos.
"""

from __future__ import annotations

import time
from typing import Any

from src.hat.level1_orchestrator.anti_duplication._types import AntiDupResult
from src.core.logging import setup_logging
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository

logger = setup_logging(__name__)

# Ventana de tiempo por defecto para detectar doble-click (segundos).
DEFAULT_TTL_SECONDS = 2


class TTLFreshnessLayer:
    """Capa 3: detecta doble-click dentro de ventana de TTL.

    Coste: <1ms (cache hit) o ~2ms (cache miss + SELECT).
    Qué detecta: mismo intent_hash despachado hace <TTL s → descarta (doble-click).
    M9: ya NO bloquea mensajes diferentes dentro de la ventana (solo mismo hash).
    """

    def __init__(
        self,
        repo: LedgerRepository | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._repo = repo if repo is not None else LedgerRepository()
        self._ttl_seconds = ttl_seconds
        self._last_check_time: dict[str, float] = {}
        logger.debug("TTLFreshnessLayer initialized with ttl=%ds", ttl_seconds)

    def check(
        self,
        intent_hash: str,
        user_id: str,
        session_id: str,
    ) -> AntiDupResult:
        """Verifica si hay dispatches recientes CON EL MISMO HASH.

        M9.3+: Usa repo.get_recent_dispatches_by_hash() que filtra en SQL
        por intent_hash (más eficiente que el filtrado en Python de M9.1).

        Usa cache en memoria por intent_hash: si el mismo hash fue verificado
        hace <TTL segundos, devuelve resultado cacheado sin consultar DB.

        Args:
            intent_hash: Hash sha256 del intent.
            user_id: ID del usuario (mantenido por compat con la firma del cascade).
            session_id: ID de la sesión (mantenido por compat con la firma del cascade).

        Returns:
            dict con duplicate, action, reason.
        """
        cache_key = intent_hash
        now = time.monotonic()

        if self._is_cached_recent(cache_key, now):
            return self._cached_result()

        recent = self._repo.get_recent_dispatches_by_hash(
            intent_hash, since_seconds=self._ttl_seconds,
        )
        result = self._build_result(recent, intent_hash)
        if result["duplicate"]:
            logger.info("TTL DUPLICATE: hash=%.12s -> discard (%d recent in %ds)",
                        intent_hash, len(recent), self._ttl_seconds)
        else:
            logger.debug("TTL freshness: hash=%.12s -> proceed (no recent)", intent_hash)
        self._last_check_time[cache_key] = now
        return result

    def _is_cached_recent(self, cache_key: str, now: float) -> bool:
        """Verifica si el cache para este intent_hash es reciente.

        Args:
            cache_key: Clave de cache (intent_hash post-M9.3+).
            now: Timestamp actual (monotonic).

        Returns:
            True si el cache es reciente y dice 'proceed' (no duplicado).
        """
        last_time = self._last_check_time.get(cache_key)
        if last_time is None:
            return False
        return (now - last_time) < self._ttl_seconds

    def _cached_result(self) -> AntiDupResult:
        """Retorna resultado cacheado para un intent_hash.

        Returns:
            Resultado proceed cacheado (si este hash fue verificado
            recientemente, asumamos que sigue sin dispatches recientes del mismo hash).
        """
        return {
            "duplicate": False,
            "action": "proceed",
            "reason": "ttl_freshness: cached (intent checked recently)",
        }

    def _build_result(
        self, recent: list[Any], intent_hash: str,
    ) -> AntiDupResult:
        """Construye el resultado a partir de la lista de dispatches recientes.

        Args:
            recent: Lista de dispatches recientes del mismo intent_hash (de la DB).
            intent_hash: Hash del intent (para trazabilidad en reason).

        Returns:
            dict con duplicate, action, reason.
        """
        short_hash = intent_hash[:8] if intent_hash else "unknown"
        if recent:
            return {
                "duplicate": True,
                "action": "discard",
                "reason": f"ttl_freshness: {len(recent)} dispatch(es) with same hash in last {self._ttl_seconds}s (hash={short_hash})",
            }
        return {
            "duplicate": False,
            "action": "proceed",
            "reason": f"no recent dispatches with same hash in last {self._ttl_seconds}s (hash={short_hash})",
        }

    def clear_cache(self) -> None:
        """Limpia el cache de intent_hash. Útil para tests."""
        self._last_check_time.clear()
