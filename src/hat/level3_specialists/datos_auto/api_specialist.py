"""
HAT NIVEL 3 — ApiSpecialist
============================

UNA SOLA RESPONSABILIDAD: Integración con APIs externas vía HTTP.

Coordina los workers del Nivel 4 para la tool (Nivel 5):
- api_connector (APIConnectorService): request, xml_parse, xml_generate

Routing por keywords:
- "xml", "parse xml" → api_connector.xml_parse
- "api", "http", "request", "endpoint", "rest" → api_connector.request
- Default: api_connector.request
"""

from __future__ import annotations

from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, SpecialistResult, Subtask


class ApiSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: APIs externas (ApiConnector)."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="api",
            responsibility="apis_externas",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="api",
            agent_name="API",
            domain="datos_auto",
            tier="specialist",
            capabilities=[
                # api_connector
                "request", "xml_parse", "xml_generate",
            ],
            cost_per_call=0.0,
            avg_latency_ms=150,
            orbital_keywords=[
                "api", "apis", "http", "request", "endpoint", "rest",
                "url", "webhook", "xml", "parse xml", "json",
                "integración", "integracion", "servicio externo",
                "conectar api", "llamar api",
            ],
            orbital_amplitude=1.5,
            orbital_velocity=0.05,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or subtask.get("message") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # --- XML routing ---
        if any(kw in desc for kw in ["xml", "parse xml", "parsear xml", "generar xml"]):
            if any(kw in desc for kw in ["generar xml", "xml generate", "crear xml"]):
                return "api_connector", "xml_generate", params
            # Default xml: parse
            return "api_connector", "xml_parse", params

        # --- Default seguro: api_connector.request ---
        # (cubre: "api", "http", "request", "endpoint", "rest" y cualquier otra cosa)
        return "api_connector", "request", params

    def handle(self, subtask: Subtask) -> SpecialistResult:
        """Ejecuta el specialist: route → invoke tool → return result."""
        import time
        start = time.monotonic()

        tool_name, action_name, params = self.route_action(subtask)
        tool = self._tools.get(tool_name)

        if tool is None:
            return SpecialistResult(
                status="failed",
                error=f"tool '{tool_name}' not available",
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        try:
            method = getattr(tool, action_name)
            result = method(**params) if params else method()
            return SpecialistResult(
                status="completed",
                action=action_name,
                result=result,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            return SpecialistResult(
                status="failed",
                error=str(exc),
                action=action_name,
                specialist=self.specialist_name,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
