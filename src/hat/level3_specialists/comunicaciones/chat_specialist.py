"""
HAT NIVEL 3 — ChatSpecialist
============================

UNA SOLA RESPONSABILIDAD: Chat (Slack + Telegram).

Coordina los workers del Nivel 4 para las tools Slack y Telegram (Nivel 5):
- slack: send_message, list_channels, upload_file, get_user_info
- telegram: send_message, send_photo, get_updates, get_chat

Routing por keywords:
- "slack" → slack.send_message
- "telegram", "bot" → telegram.send_message
- "canales slack" → slack.list_channels
- Default → slack.send_message
"""

from __future__ import annotations
from typing import Any

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.base.specialist_agent import SpecialistAgent, Subtask, SpecialistResult


class ChatSpecialist(SpecialistAgent):
    """Specialist con UNA responsabilidad: chat (Slack + Telegram)."""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        super().__init__(
            specialist_name="chat_specialist",
            responsibility="chat_slack_telegram",
            tools=tools or {},
        )

    def get_card(self) -> AgentCard:
        return AgentCard(
            agent_id="chat_specialist",
            agent_name="Chat Specialist",
            domain="comunicaciones",
            tier="specialist",
            capabilities=[
                "slack.send_message", "slack.list_channels",
                "slack.upload_file", "slack.get_user_info",
                "telegram.send_message", "telegram.send_photo",
                "telegram.get_updates", "telegram.get_chat",
            ],
            cost_per_call=0.0,
            avg_latency_ms=400,
            orbital_keywords=[
                "chat", "slack", "telegram", "bot",
                "mensaje", "canales", "channels", "canal",
                "foto", "photo", "updates",
            ],
            orbital_amplitude=1.0,
            orbital_velocity=0.15,
        )

    def route_action(self, subtask: Subtask) -> tuple[str, str, dict[str, Any]]:
        """Decide qué tool y action ejecutar según el subtask.

        Precedencia: 'telegram' antes que 'slack' (es más específico, no debe
        caer al default slack.send_message); 'canales slack' antes que 'slack'.
        """
        desc = (subtask.get("description") or "").lower()
        params = {k: v for k, v in subtask.get("params", {}).items() if k not in ("query", "message")}

        # ── Telegram ──────────────────────────────────────────
        if "telegram" in desc or " bot" in f" {desc}" or desc.startswith("bot "):
            if any(kw in desc for kw in ["foto", "photo"]):
                return "telegram", "send_photo", params
            if any(kw in desc for kw in ["updates", "actualizaciones"]):
                return "telegram", "get_updates", params
            if any(kw in desc for kw in ["get chat", "get_chat", "info chat"]):
                return "telegram", "get_chat", params
            # Default telegram: send_message
            return "telegram", "send_message", params

        # ── Slack ─────────────────────────────────────────────
        if "slack" in desc:
            if any(kw in desc for kw in ["canales", "channels", "listar canales"]):
                return "slack", "list_channels", params
            if any(kw in desc for kw in ["subir archivo", "upload", "archivo"]):
                return "slack", "upload_file", params
            if any(kw in desc for kw in ["user info", "usuario", "get_user"]):
                return "slack", "get_user_info", params
            # Default slack: send_message
            return "slack", "send_message", params

        # Default global: slack.send_message
        return "slack", "send_message", params

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
