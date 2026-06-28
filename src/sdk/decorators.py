"""
Connector SDK — Decoradores para Desarrollo de Conectores
===========================================================

NOTA: Archivo delgado que re-exporta desde src/sdk/decorators/ subpackage.
Las implementaciones completas estan en:
- src/sdk/decorators/action.py
- src/sdk/decorators/ratelimit.py
- src/sdk/decorators/retry.py
- src/sdk/decorators/circuit.py
- src/sdk/decorators/validation.py
- src/sdk/decorators/metrics.py
"""

from __future__ import annotations

from src.sdk.decorators.action import connector_action, get_action_metadata
from src.sdk.decorators.circuit import circuit_breaker
from src.sdk.decorators.metrics import track_metrics
from src.sdk.decorators.ratelimit import rate_limit
from src.sdk.decorators.retry import retry
from src.sdk.decorators.validation import validate_input, validate_output

__all__ = [
    "circuit_breaker",
    "connector_action",
    "get_action_metadata",
    "rate_limit",
    "retry",
    "track_metrics",
    "validate_input",
    "validate_output",
]
