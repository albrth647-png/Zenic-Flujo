"""
HAT NIVEL 3 — NotificationSpecialist
====================================

UNA SOLA RESPONSABILIDAD: Notificaciones (email + WhatsApp).

Coordina los workers del Nivel 4 para la tool Notification (Nivel 5):
- send_email, send_notification, send_birthday_emails
- configure_smtp, test_connection
- send_whatsapp, configure_whatsapp, get_status

Routing por keywords:
- "email", "correo", "smtp" → send_email
- "whatsapp", "wa" → send_whatsapp
- "configurar smtp" → configure_smtp
- "test", "probar" → test_connection
- Default → get_status
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class NotificationSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: notificaciones (email + WhatsApp)."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="notification_specialist",
            responsibility="notificaciones_email_whatsapp",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="notification_specialist",
            agent_name="Notification Specialist",
            domain="comunicaciones",
            tier="specialist",
            capabilities=[
                "send_email", "send_notification", "send_birthday_emails",
                "configure_smtp", "test_connection",
                "send_whatsapp", "configure_whatsapp", "get_status",
            ],
            cost_per_call=0.0,
            avg_latency_ms=500,
            orbital_keywords=[
                "email", "correo", "smtp", "whatsapp", "wa",
                "notificacion", "notificar", "cumpleanos", "birthday",
                "configurar", "probar", "test",
            ],
            orbital_amplitude=1.0,
            orbital_velocity=0.1,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask."""
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # Config SMTP (debe ir antes que 'smtp' suelto)
        if "configurar smtp" in desc or ("configurar" in desc and "smtp" in desc):
            return "notification", "configure_smtp", params
        # Config WhatsApp (debe ir antes que 'whatsapp' suelto)
        if "configurar whatsapp" in desc or ("configurar" in desc and "whatsapp" in desc):
            return "notification", "configure_whatsapp", params
        # WhatsApp send
        if "whatsapp" in desc or " wa " in f" {desc} " or desc.startswith("wa "):
            return "notification", "send_whatsapp", params
        # Test / probar
        if "test" in desc or "probar" in desc:
            return "notification", "test_connection", params
        # Birthday emails
        if "cumple" in desc or "birthday" in desc:
            return "notification", "send_birthday_emails", params
        # Generic notification (channel-aware)
        if any(kw in desc for kw in ["notificar", "notificacion", "notification"]):
            return "notification", "send_notification", params
        # Email
        if any(kw in desc for kw in ["email", "correo", "smtp"]):
            return "notification", "send_email", params

        # Default seguro: estado de la configuración
        return "notification", "get_status", params

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
