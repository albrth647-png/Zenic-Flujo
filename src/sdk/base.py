"""
Connector SDK — Clase Base Abstracta del Conector
===================================================

NOTA: Archivo delgado que re-exporta desde src/sdk/base/ subpackage.
La implementacion completa esta en src/sdk/base/connector.py
y src/sdk/base/configs.py.
"""

from __future__ import annotations

from src.sdk.base.configs import CircuitBreakerConfig, CircuitState, RateLimitConfig, RetryConfig
from src.sdk.base.connector import BaseConnector

__all__ = [
    "BaseConnector",
    "CircuitBreakerConfig",
    "CircuitState",
    "RateLimitConfig",
    "RetryConfig",
]
