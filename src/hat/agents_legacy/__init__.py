"""HAT Agents Legacy — DEPRECATED.

Este módulo contiene el framework de agents anterior a HAT v2.
Esta marcado como DEPRECATED — no usar en codigo nuevo.

HAT v2 reemplaza esta funcionalidad con:
- Nivel 2: Supervisores (routing por dominio)
- Nivel 3: Specialists (1 responsabilidad cada uno)
- Nivel 4: Workers (auto-generados con circuit breaker)
- Nivel 5: Tools (19 tools ZF reales)

Para nuevo codigo, usar:
    from src.hat import bootstrap_hat
    hat_router = bootstrap_hat(event_bus=event_bus)

Este modulo se mantiene solo para compatibilidad con tests existentes
y el endpoint /api/v2/agents. Se eliminara en una futura version.
"""
import warnings

warnings.warn(
    "src.hat.agents_legacy is deprecated. Use HAT v2 (src.hat.bootstrap_hat) instead.",
    DeprecationWarning,
    stacklevel=2,
)

from src.hat.agents_legacy.base import AgentCapability, AgentConfig, BaseAgent  # noqa: E402
from src.hat.agents_legacy.orchestrator import MultiAgentOrchestrator, OrchestrationPattern  # noqa: E402
from src.hat.agents_legacy.runtime import AgentRuntime  # noqa: E402

__all__ = [
    "AgentCapability",
    "AgentConfig",
    "AgentRuntime",
    "BaseAgent",
    "MultiAgentOrchestrator",
    "OrchestrationPattern",
]
