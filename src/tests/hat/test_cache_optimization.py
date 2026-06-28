"""
Tests de cache LRU para ExactMatchLayer y TTLFreshnessLayer (F1-D3).

Verifica que el cache funciona correctamente: cache hit evita DB query,
cache miss consulta DB, y LRU evict funciona cuando se excede el tamaño.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from src.hat.level1_orchestrator.anti_duplication.exact_match import _CACHE_MAX_SIZE, ExactMatchLayer
from src.hat.level1_orchestrator.anti_duplication.ttl_freshness import TTLFreshnessLayer
from src.hat.level1_orchestrator.ledger.repository import LedgerRepository


@pytest.fixture
def repo():
    return LedgerRepository()


@pytest.fixture
def session():
    ts = datetime.now(UTC).strftime("%H%M%S%f")
    return {"user_id": f"cache_user_{ts}", "session_id": f"cache_sess_{ts}"}


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


# ─────────────────────────────────────────────────────────
# ExactMatchLayer cache
# ─────────────────────────────────────────────────────────


class TestExactMatchCache:
    def test_first_check_queries_db(self, repo, session):
        """Primera check para un hash → consulta DB (cache miss)."""
        layer = ExactMatchLayer(repo=repo)
        h = _hash(f"em_cache_miss_{session['session_id']}")
        result = layer.check(h)
        assert result["action"] == "proceed"
        assert len(layer._cache) == 1

    def test_second_check_uses_cache(self, repo, session):
        """Segunda check al mismo hash → cache hit (no consulta DB)."""
        layer = ExactMatchLayer(repo=repo)
        h = _hash(f"em_cache_hit_{session['session_id']}")

        r1 = layer.check(h)
        r2 = layer.check(h)
        assert r1 == r2
        assert len(layer._cache) == 1

    def test_cache_stores_completed_result(self, repo, session):
        """Si el dispatch está completado, el cache guarda el result_cache."""
        h = _hash(f"em_completed_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")
        repo.complete_dispatch(h, {"answer": "cached"})

        layer = ExactMatchLayer(repo=repo)
        r1 = layer.check(h)
        assert r1["duplicate"] is True
        assert r1["cached_result"] == {"answer": "cached"}

        r2 = layer.check(h)
        assert r2["cached_result"] == {"answer": "cached"}

    def test_lru_eviction_when_full(self, repo):
        """Cuando el cache excede _CACHE_MAX_SIZE, el entry más viejo se evicta."""
        layer = ExactMatchLayer(repo=repo)
        for i in range(_CACHE_MAX_SIZE + 5):
            layer.check(_hash(f"lru_{i}"))
        assert len(layer._cache) == _CACHE_MAX_SIZE

    def test_lru_move_to_end_on_access(self, repo, session):
        """Acceder a un entry existente lo mueve al final (más reciente)."""
        layer = ExactMatchLayer(repo=repo)
        h1 = _hash(f"lru_old_{session['session_id']}")
        h2 = _hash(f"lru_new_{session['session_id']}")

        layer.check(h1)
        layer.check(h2)
        assert list(layer._cache.keys())[-1] == h2

        layer.check(h1)
        assert list(layer._cache.keys())[-1] == h1


# ─────────────────────────────────────────────────────────
# TTLFreshnessLayer cache
# ─────────────────────────────────────────────────────────


class TestTTLFreshnessCache:
    def test_first_check_queries_db(self, repo, session):
        """Primera check → DB query."""
        layer = TTLFreshnessLayer(repo=repo, ttl_seconds=10)
        result = layer.check("any", session["user_id"], session["session_id"])
        assert result["action"] == "proceed"
        assert len(layer._last_check_time) == 1

    def test_second_check_within_ttl_uses_cache(self, repo, session):
        """Segunda check dentro de TTL → cache hit (proceed sin DB)."""
        layer = TTLFreshnessLayer(repo=repo, ttl_seconds=10)
        r1 = layer.check("h1", session["user_id"], session["session_id"])
        r2 = layer.check("h2", session["user_id"], session["session_id"])
        # Ambas proceed, pero la 2da usa cache
        assert r1["action"] == "proceed"
        assert r2["action"] == "proceed"
        assert "cached" in r2["reason"]

    def test_cache_keyed_by_session(self, repo):
        """Cache es por sesión: sesión A cacheada no afecta sesión B."""
        layer = TTLFreshnessLayer(repo=repo, ttl_seconds=10)
        ts = datetime.now(UTC).strftime("%H%M%S%f")
        sa = {"user_id": f"sa_{ts}", "session_id": f"sa_s_{ts}"}
        sb = {"user_id": f"sb_{ts}", "session_id": f"sb_s_{ts}"}

        layer.check("h", sa["user_id"], sa["session_id"])
        r_b = layer.check("h", sb["user_id"], sb["session_id"])
        # Sesión B no está cacheada → debe consultar DB
        assert "cached" not in r_b["reason"]

    def test_first_dispatch_registers_then_second_discards(self, repo, session):
        """Tras registrar un dispatch, la 2da check dentro de TTL → discard."""
        h = _hash(f"ttl_disc_{session['session_id']}")
        repo.register_dispatch(h, session["user_id"], session["session_id"], "research")

        layer = TTLFreshnessLayer(repo=repo, ttl_seconds=10)
        r1 = layer.check(h, session["user_id"], session["session_id"])
        assert r1["duplicate"] is True
        assert r1["action"] == "discard"
