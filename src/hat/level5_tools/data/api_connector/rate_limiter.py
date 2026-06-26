"""
Rate Limiter — Token Bucket por dominio.
Sprint 5.1 del Roadmap Competitivo.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

from src.core.logging import setup_logging

logger = setup_logging(__name__)


class RateLimiter:
    """
    Rate limiter usando token bucket algorithm.

    Cada dominio tiene su propio bucket con:
    - max_tokens: máximo de requests permitidos en la ventana
    - window_seconds: duración de la ventana en segundos
    - tokens: tokens disponibles actualmente
    - last_refill: timestamp del último rellenado

    Thread-safe mediante RLock.
    """

    def __init__(self, max_tokens: int = 60, window_seconds: int = 60):
        self._max_tokens = max_tokens
        self._window_seconds = window_seconds
        self._buckets: dict[str, dict] = {}
        self._lock = threading.RLock()

    def _get_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception as e:
            logger.warning("No se pudo parsear dominio de URL: %s", e)
            return "unknown"

    def _get_bucket(self, domain: str) -> dict:
        if domain not in self._buckets:
            self._buckets[domain] = {
                "tokens": self._max_tokens,
                "last_refill": time.time(),
                "max_tokens": self._max_tokens,
                "total_requests": 0,
                "blocked_requests": 0,
            }
        return self._buckets[domain]

    def _refill(self, bucket: dict) -> None:
        now = time.time()
        elapsed = now - bucket["last_refill"]
        tokens_to_add = (elapsed / self._window_seconds) * bucket["max_tokens"]
        bucket["tokens"] = min(bucket["max_tokens"], bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now

    def acquire(self, url: str, cost: int = 1) -> bool:
        domain = self._get_domain(url)
        with self._lock:
            bucket = self._get_bucket(domain)
            self._refill(bucket)
            if bucket["tokens"] >= cost:
                bucket["tokens"] -= cost
                bucket["total_requests"] += 1
                return True
            bucket["blocked_requests"] += 1
            logger.warning(f"Rate limit excedido para {domain}: {bucket['tokens']:.1f}/{bucket['max_tokens']} tokens")
            return False

    def get_status(self, url: str | None = None) -> dict:
        with self._lock:
            if url:
                domain = self._get_domain(url)
                bucket = self._get_bucket(domain)
                self._refill(bucket)
                return {
                    "domain": domain,
                    "tokens_remaining": round(bucket["tokens"], 1),
                    "max_tokens": bucket["max_tokens"],
                    "total_requests": bucket["total_requests"],
                    "blocked_requests": bucket["blocked_requests"],
                }
            return {
                domain: {
                    "tokens_remaining": round(b["tokens"], 1),
                    "max_tokens": b["max_tokens"],
                    "total_requests": b["total_requests"],
                    "blocked_requests": b["blocked_requests"],
                }
                for domain, b in self._buckets.items()
            }

    def reset(self, url: str | None = None) -> None:
        with self._lock:
            if url:
                domain = self._get_domain(url)
                self._buckets.pop(domain, None)
            else:
                self._buckets.clear()
