"""
Response Cache — Caching de respuestas HTTP en memoria.
Sprint 5.3 del Roadmap Competitivo.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time

from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class ResponseCache:
    """
    Cache de respuestas HTTP en memoria.

    Almacena respuestas por URL + método + body hash.
    TTL configurable por dominio o global.
    Thread-safe mediante RLock.
    Límite máximo de entradas para evitar memory leak.
    """

    MAX_ENTRIES = 1000

    def __init__(self, default_ttl_seconds: int = 300):
        self._default_ttl = default_ttl_seconds
        self._cache: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _make_key(self, method: str, url: str, body: dict[str, Any] | None = None) -> str:
        # Hash no criptográfico: cache key para responses de API (B324 mitigado).
        # No es para fines de seguridad — solo para detectar colisiones en cache.
        raw = f"{method.upper()}:{url}"
        if body:
            raw += f":{hashlib.md5(json.dumps(body, sort_keys=True).encode(), usedforsecurity=False).hexdigest()}"
        return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

    def get(self, method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any] | None:
        key = self._make_key(method, url, body)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() > entry["expires_at"]:
                del self._cache[key]
                return None
            entry["hits"] = entry.get("hits", 0) + 1
            logger.debug(f"Cache HIT: {method} {url}")
            return entry["response"]

    def set(self, method: str, url: str, response: dict[str, Any], body: dict[str, Any] | None = None,
            ttl_seconds: int | None = None) -> None:
        if response.get("status_code", 0) >= 400:
            return
        key = self._make_key(method, url, body)
        ttl = ttl_seconds or self._default_ttl
        with self._lock:
            if len(self._cache) >= self.MAX_ENTRIES:
                self._evict()
            self._cache[key] = {
                "response": response,
                "expires_at": time.time() + ttl,
                "created_at": time.time(),
                "ttl": ttl,
                "hits": 0,
            }
            logger.debug(f"Cache SET: {method} {url} (TTL: {ttl}s)")

    def invalidate(self, url_pattern: str | None = None) -> int:
        with self._lock:
            if url_pattern is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            keys_to_delete = [
                k for k, v in self._cache.items()
                if url_pattern.lower() in str(v.get("response", {})).lower()
            ]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    def _evict(self) -> None:
        sorted_entries = sorted(self._cache.items(), key=lambda x: x[1]["created_at"])
        to_remove = max(1, len(sorted_entries) // 10)
        for key, _ in sorted_entries[:to_remove]:
            del self._cache[key]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._cache)
            active = sum(1 for e in self._cache.values() if time.time() <= e["expires_at"])
            total_hits = sum(e.get("hits", 0) for e in self._cache.values())
            return {
                "total_entries": total,
                "active_entries": active,
                "expired_entries": total - active,
                "total_hits": total_hits,
                "max_entries": self.MAX_ENTRIES,
                "default_ttl_seconds": self._default_ttl,
            }
