"""Configuration classes for the Connector SDK.

Extracted from src/sdk/base.py to keep the module modular.
"""

from __future__ import annotations


class CircuitState:
    """Estados posibles del circuit breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class RetryConfig:
    """Configuracion de reintentos con backoff exponencial."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def get_delay(self, attempt: int) -> float:
        delay = self.base_delay * (self.backoff_factor**attempt)
        return min(delay, self.max_delay)


class CircuitBreakerConfig:
    """Configuracion del circuit breaker."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout


class RateLimitConfig:
    """Configuracion de rate limiting (sliding window)."""

    def __init__(self, max_calls: int = 60, period_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.period_seconds = period_seconds
