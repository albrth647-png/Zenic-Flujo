"""
Metricas de Agentes — ejecuciones, tool calls, memoria, instancias activas.

Responsabilidad:
- ``record_agent_execution``: contador por agent_id+action+status e
  histograma de duracion.
- ``record_agent_tool_call``: contador por agent_id+tool+status.
- ``record_agent_memory_operation``: contador por agent_id+operation.
- ``set_agent_active_count``: gauge de agentes activos.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class AgentMetricsMixin:
    """Metricas de agentes (ejecuciones, tools, memoria, activos)."""

    # Atributos provistos por ``TelemetryService``.
    _metrics: Any

    def record_agent_execution(
        self,
        agent_id: str,
        action: str,
        status: str,
        duration: float,
    ) -> None:
        """
        Registra la ejecucion de un agente.

        Args:
            agent_id: ID del agente
            action: Accion ejecutada
            status: Estado (started, completed, failed)
            duration: Duracion en segundos
        """
        self._metrics.increment_counter(
            "agent_executions_total",
            labels={"agent_id": agent_id, "action": action, "status": status},
        )
        self._metrics.observe_histogram(
            "agent_execution_duration_seconds",
            duration,
            labels={"agent_id": agent_id, "action": action},
        )

    def record_agent_tool_call(self, agent_id: str, tool: str, status: str) -> None:
        """
        Registra una llamada a herramienta por parte de un agente.

        Args:
            agent_id: ID del agente
            tool: Nombre de la herramienta
            status: Estado (success, error)
        """
        self._metrics.increment_counter(
            "agent_tool_calls_total",
            labels={"agent_id": agent_id, "tool": tool, "status": status},
        )

    def record_agent_memory_operation(self, agent_id: str, operation: str) -> None:
        """
        Registra una operacion de memoria de agente.

        Args:
            agent_id: ID del agente
            operation: Tipo de operacion (read, write, delete)
        """
        self._metrics.increment_counter(
            "agent_memory_operations_total",
            labels={"agent_id": agent_id, "operation": operation},
        )

    def set_agent_active_count(self, count: int) -> None:
        """
        Establece el gauge de agentes activos.

        Args:
            count: Numero de agentes activos
        """
        self._metrics.set_gauge("agent_active_instances", float(count))
