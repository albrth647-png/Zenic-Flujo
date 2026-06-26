"""Tests para los 3 specialists de comunicaciones: Notification, Email, Chat.

Cubre para cada specialist:
- get_card() retorna AgentCard con domain='comunicaciones'.
- handle() integra route + invoke + return.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.hat.level3_specialists.base.cards import AgentCard
from src.hat.level3_specialists.comunicaciones.chat_specialist import ChatSpecialist
from src.hat.level3_specialists.comunicaciones.email_specialist import EmailSpecialist
from src.hat.level3_specialists.comunicaciones.notification_specialist import (
    NotificationSpecialist,
)


class TestNotificationSpecialist:
    """Tests para NotificationSpecialist."""

    @pytest.fixture
    def mock_notification(self) -> MagicMock:
        """Notification tool mockeada."""
        tool = MagicMock()
        tool.send_email.return_value = {"status": "sent"}
        tool.send_notification.return_value = {"status": "sent"}
        tool.send_whatsapp.return_value = {"status": "sent"}
        tool.configure_smtp.return_value = {"status": "ok"}
        tool.test_connection.return_value = {"status": "ok"}
        tool.get_status.return_value = {"smtp": "ok", "whatsapp": "ok"}
        return tool

    @pytest.fixture
    def specialist(self, mock_notification: MagicMock) -> NotificationSpecialist:
        """NotificationSpecialist con tool mockeada."""
        return NotificationSpecialist(tools={"notification": mock_notification})

    def test_get_card_returns_correct_metadata(
        self, specialist: NotificationSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='comunicaciones'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.domain == "comunicaciones"
        assert card.tier == "specialist"
        assert "send_email" in card.capabilities
        assert "whatsapp" in card.orbital_keywords

    @pytest.mark.parametrize("message,expected_action", [
        ("enviar email", "send_email"),
        ("correo electrónico", "send_email"),
        ("smtp config", "send_email"),
        ("enviar whatsapp", "send_whatsapp"),
        ("wa message", "send_whatsapp"),
        ("probar conexión", "test_connection"),
        ("test smtp", "test_connection"),
        ("cumpleanos", "send_birthday_emails"),
        ("birthday campaign", "send_birthday_emails"),
    ])
    def test_route_action_routes_correctly(
        self, specialist: NotificationSpecialist,
        message: str, expected_action: str,
    ) -> None:
        """route_action() selecciona la action correcta."""
        _, action_name, _ = specialist.route_action({
            "description": message,
            "params": {},
        })
        assert action_name == expected_action

    def test_handle_returns_completed(self, specialist: NotificationSpecialist) -> None:
        """handle() retorna status='completed'."""
        result = specialist.handle({"description": "enviar email", "params": {}})
        assert result["status"] == "completed"


class TestEmailSpecialist:
    """Tests para EmailSpecialist."""

    @pytest.fixture
    def mock_gmail(self) -> MagicMock:
        """Gmail tool mockeada."""
        tool = MagicMock()
        tool.send_email.return_value = {"status": "sent"}
        tool.list_emails.return_value = [{"id": 1}]
        tool.get_email.return_value = {"id": 1}
        return tool

    @pytest.fixture
    def specialist(self, mock_gmail: MagicMock) -> EmailSpecialist:
        """EmailSpecialist con tool mockeada."""
        return EmailSpecialist(tools={"gmail": mock_gmail})

    def test_get_card_returns_correct_metadata(
        self, specialist: EmailSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='comunicaciones'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.domain == "comunicaciones"
        assert card.tier == "specialist"

    def test_handle_returns_completed(self, specialist: EmailSpecialist) -> None:
        """handle() retorna status='completed'."""
        result = specialist.handle({"description": "enviar email", "params": {}})
        assert result["status"] == "completed"


class TestChatSpecialist:
    """Tests para ChatSpecialist."""

    @pytest.fixture
    def mock_chat_tools(self) -> dict[str, MagicMock]:
        """Slack + Telegram tools mockeadas."""
        return {
            "slack": MagicMock(),
            "telegram": MagicMock(),
        }

    @pytest.fixture
    def specialist(self, mock_chat_tools: dict[str, MagicMock]) -> ChatSpecialist:
        """ChatSpecialist con tools mockeadas."""
        return ChatSpecialist(tools=mock_chat_tools)

    def test_get_card_returns_correct_metadata(
        self, specialist: ChatSpecialist,
    ) -> None:
        """get_card() retorna AgentCard con domain='comunicaciones'."""
        card = specialist.get_card()
        assert isinstance(card, AgentCard)
        assert card.domain == "comunicaciones"
        assert card.tier == "specialist"
