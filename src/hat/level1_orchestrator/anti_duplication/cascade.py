"""
HAT-ORBITAL Anti-Doble-Llamada — Cascade Orquestador.

Ejecuta las 3 capas en cascada, ordenadas de más barata a más cara.
Si cualquier capa detecta duplicado, se cortocircuita el flujo.

Orden de capas (cheapest → most expensive):
1. Exact Match     (~1ms)  — hash idéntico ya completado → devuelve cache
2. Idempotency     (~3ms)  — hash en ejecución → suscríbete al resultado
3. TTL Freshness   (<1ms)  — mismo hash despachado hace <2s → descarta (doble-click)

M2 eliminó semantic_dedup (Jaccard false positives).
M9 eliminó circuit_breaker (pertenece a level4_workers, no al cascade anti-dup).

Coste total peor caso: ~5ms. Probabilidad de doble despacho: <0.01%.
"""

from __future__ import annotations

from collections.abc import Callable

from src.hat.level1_orchestrator.anti_duplication._types import AntiDupResult
from src.hat.level1_orchestrator.anti_duplication.exact_match import ExactMatchLayer
from src.hat.level1_orchestrator.anti_duplication.idempotency import IdempotencyLayer
from src.hat.level1_orchestrator.anti_duplication.ttl_freshness import TTLFreshnessLayer
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository
from src.core.logging import setup_logging

logger = setup_logging(__name__)


class AntiDuplicationCascade:
    """Orquesta las 3 capas anti-doble-llamada en cascada."""

    def __init__(self, repo: LedgerRepository | None = None) -> None:
        self._repo = repo if repo is not None else LedgerRepository()
        self._exact_match = ExactMatchLayer(repo=self._repo)
        self._idempotency = IdempotencyLayer(repo=self._repo)
        self._ttl_freshness = TTLFreshnessLayer(repo=self._repo)
        # M2 eliminated semantic_dedup (Jaccard false positives).
        # M9 eliminated circuit_breaker from cascade — it lives in level4_workers now.

    def clear_cache(self) -> None:
        """Limpia caches de todas las capas. Útil para tests."""
        self._exact_match.clear_cache()
        self._ttl_freshness.clear_cache()

    def check(
        self,
        intent_hash: str,
        user_id: str,
        session_id: str,
        message: str,
        domain: str,
    ) -> AntiDupResult:
        """Ejecuta las 3 capas en orden. Cortocircuito en primer duplicado.

        Args:
            intent_hash: Hash sha256 del intent.
            user_id: ID del usuario.
            session_id: ID de la sesión.
            message: Texto original del usuario.
            domain: Dominio destino del dispatch.

        Returns:
            AntiDupResult con duplicate, action, layer_hit, reason, y campos según action.
        """
        layers = self._build_layer_sequence(
            intent_hash, user_id, session_id, message, domain,
        )
        for layer_name, check_fn in layers:
            result: AntiDupResult = check_fn()
            if result.get("duplicate"):
                result["layer_hit"] = layer_name
                logger.info(
                    "AntiDupCascade: layer %s triggered (action=%s, reason=%s)",
                    layer_name, result.get("action"), result.get("reason"),
                )
                return result
        return {
            "duplicate": False,
            "action": "proceed",
            "layer_hit": "none",
            "reason": "all layers passed",
        }

    def _build_layer_sequence(
        self,
        intent_hash: str,
        user_id: str,
        session_id: str,
        message: str,
        domain: str,
    ) -> list[tuple[str, Callable[[], AntiDupResult]]]:
        """Construye la secuencia de capas con sus check functions."""
        return [
            ("exact_match", lambda: self._exact_match.check(intent_hash)),
            ("idempotency", lambda: self._idempotency.check(intent_hash)),
            ("ttl_freshness", lambda: self._ttl_freshness.check(
                intent_hash, user_id, session_id,
            )),
        ]
