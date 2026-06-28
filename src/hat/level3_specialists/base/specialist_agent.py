"""
HAT NIVEL 3 — SpecialistAgent Base ABC
=======================================

Clase base abstracta para los 9 specialists del Nivel 3.

Cada specialist tiene UNA SOLA RESPONSABILIDAD:
- CrmSpecialist → gestión de clientes/leads
- InvoiceSpecialist → facturación
- InventorySpecialist → inventario/stock
- NotificationSpecialist → notificaciones (email+WhatsApp)
- EmailSpecialist → Gmail
- ChatSpecialist → Slack + Telegram
- DataSpecialist → DataKeeper + Sheets + Drive + PostgreSQL
- ApiSpecialist → ApiConnector
- CodeSpecialist → CodeRunner + LogicGate + Autopilot + OpenAI + Ollama

Hereda de CardPublisherMixin para poder publicar AgentCards al OVC + DB.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import Any, TypedDict

from src.core.logging import setup_logging
from src.hat.level3_specialists.base.card_publisher import CardPublisherMixin
from src.hat.level3_specialists.base.cards import AgentCard

logger = setup_logging(__name__)


class Subtask(TypedDict):
    """Subtarea recibida del supervisor (L2) para que el specialist (L3) la procese."""
    dispatch_id: str
    user_id: str
    session_id: str
    description: str
    parent_intent: str | None
    params: dict[str, Any]
    orbital_resonance: float


class SpecialistResult(TypedDict, total=False):
    """Resultado devuelto por el specialist (L3) al supervisor (L2).

    Según ``status`` puede llevar:
    - ``'completed'``: ``action``, ``result``, ``specialist``, ``duration_ms``
    - ``'failed'``: ``error``, ``specialist``, ``duration_ms``
    """
    status: str
    action: str
    # legítimo: resultado dinámico de dispatch HAT, tipo depende del especialista
    result: Any
    error: str
    specialist: str
    duration_ms: int


class SpecialistAgent(ABC, CardPublisherMixin):
    """Base abstracta para Specialists del Nivel 3.

    Hereda de CardPublisherMixin para poder publicar AgentCards.

    Subclases concretas (CrmSpecialist, InvoiceSpecialist, ...) DEBEN:
    1. Implementar `get_card()` retornando AgentCard con keywords del dominio
    2. Implementar `route_action(subtask)` decidiendo qué tool/worker invocar
    3. Implementar `handle(subtask)` ejecutando: route → invoke tool → return result
    """

    def __init__(
        self,
        specialist_name: str,
        responsibility: str,
        tools: dict[str, Any] | None = None,
    ) -> None:
        self.specialist_name = specialist_name
        self.responsibility = responsibility
        self._tools = tools or {}

    @abstractmethod
    def get_card(self) -> AgentCard:
        """Retorna la AgentCard que describe las capacidades de este specialist."""
        ...

    @abstractmethod
    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask.

        Returns:
            Tupla (tool_name, action_name, params)
        """
        ...

    def handle(self, subtask: Subtask) -> SpecialistResult:
        """Punto de entrada — invocado por el supervisor (Nivel 2).

        Flujo:
        1. Publicar AgentCard (idempotente)
        2. route_action() → decide qué tool y action invocar
        3. Invocar tool directamente (Nivel 5)
        4. Retornar resultado estructurado

        M10.4 — Metrics: registra ``record_agent_execution`` en ``finally``
        (best-effort, nunca rompe el flujo principal).
        """
        import time
        start = time.monotonic()
        action_name = "unknown"
        result: SpecialistResult | None = None

        try:
            # 1. Publicar card (idempotente — se skip si ya existe)
            with contextlib.suppress(Exception):
                self.publish_card()

            # 2. Decidir acción
            tool_name, action_name, params = self.route_action(subtask)

            # 3. Invocar tool (Nivel 5) directamente
            tool = self._tools.get(tool_name)
            if tool is None:
                result = SpecialistResult(
                    status="failed",
                    error=f"tool '{tool_name}' not available",
                    specialist=self.specialist_name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                return result

            method = getattr(tool, action_name, None)
            if method is None:
                result = SpecialistResult(
                    status="failed",
                    error=f"action '{action_name}' not found in tool '{tool_name}'",
                    specialist=self.specialist_name,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                return result

            tool_result = method(**params) if params else method()

            # 4. Retornar resultado
            result = SpecialistResult(
                status="completed",
                action=action_name,
                result=tool_result,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return result

        except Exception as exc:
            result = SpecialistResult(
                status="failed",
                error=str(exc),
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return result
        finally:
            # M10.4 — Metrics: best-effort, nunca romper el flujo principal.
            try:
                from src.core.observability.telemetry import TelemetryService
                if result is not None:
                    TelemetryService().record_agent_execution(
                        agent_id=self.specialist_name,
                        action=action_name or "unknown",
                        status=str(result.get("status", "unknown")),
                        duration=float(result.get("duration_ms", 0) or 0) / 1000.0,
                    )
            except Exception as exc:
                logger.debug("Metrics best-effort falló para %s: %s", self.specialist_name, exc)

    @property
    def available_tools(self) -> list[str]:
        """Retorna la lista de nombres de tools disponibles para este specialist."""
        return list(self._tools.keys())

    def __repr__(self) -> str:
        """Retorna representación compacta del specialist."""
        return (
            f"<{type(self).__name__} "
            f"name={self.specialist_name} "
            f"responsibility={self.responsibility}>"
        )
