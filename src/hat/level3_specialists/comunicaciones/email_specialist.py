"""
HAT NIVEL 3 — EmailSpecialist
=============================

UNA SOLA RESPONSABILIDAD: Gmail.

Coordina los workers del Nivel 4 para la tool Gmail (Nivel 5):
- send_email, search_emails, get_message, list_labels
- configure, test_connection, get_status

Routing por keywords:
- "enviar", "send" → send_email
- "buscar", "search" → search_emails
- "leer", "get message" → get_message
- "etiquetas", "labels" → list_labels
- Default → get_status
"""

from __future__ import annotations

from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, SpecialistResult, Subtask


class EmailSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: Gmail."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="email_specialist",
            responsibility="gmail",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="email_specialist",
            agent_name="Email Specialist",
            domain="comunicaciones",
            tier="specialist",
            capabilities=[
                "send_email", "search_emails", "get_message", "list_labels",
                "configure", "test_connection", "get_status",
            ],
            cost_per_call=0.0,
            avg_latency_ms=800,
            orbital_keywords=[
                "gmail", "enviar", "send", "buscar", "search",
                "leer", "get message", "etiquetas", "labels",
                "mensaje", "inbox", "bandeja",
            ],
            orbital_amplitude=1.0,
            orbital_velocity=0.12,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or subtask.get("message") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # Buscar / search
        if any(kw in desc for kw in ["buscar", "search"]):
            return "gmail", "search_emails", params
        # Leer / get message
        if any(kw in desc for kw in ["leer", "get message", "get_message"]):
            return "gmail", "get_message", params
        # Etiquetas / labels
        if any(kw in desc for kw in ["etiquetas", "labels", "label"]):
            return "gmail", "list_labels", params
        # Configurar Gmail
        if any(kw in desc for kw in ["configurar", "configure"]):
            return "gmail", "configure", params
        # Test / probar
        if any(kw in desc for kw in ["test", "probar"]):
            return "gmail", "test_connection", params
        # Enviar / send
        if any(kw in desc for kw in ["enviar", "send", "email", "correo"]):
            return "gmail", "send_email", params

        # Default seguro: estado
        return "gmail", "get_status", params

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
