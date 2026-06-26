"""Tests para communications tools: Notification, Gmail, Slack, Telegram.

Cubre:
- NotificationService: send_email, send_whatsapp, configure_smtp, test_connection.
- GmailService: send_email, list_emails.
- SlackService: send_message.
- TelegramService: send_message.
"""
from __future__ import annotations

import pytest

from src.hat.level5_tools.communications.gmail_service import GmailService
from src.hat.level5_tools.communications.notification.service import NotificationService
from src.hat.level5_tools.communications.slack_service import SlackService
from src.hat.level5_tools.communications.telegram_service import TelegramService


class TestNotificationService:
    """Tests para NotificationService."""

    @pytest.fixture
    def notification(self) -> NotificationService:
        """NotificationService con mocks."""
        service = NotificationService()
        return service

    def test_notification_has_send_email(self, notification: NotificationService) -> None:
        """NotificationService tiene método send_email."""
        assert hasattr(notification, "send_email")

    def test_notification_has_send_whatsapp(self, notification: NotificationService) -> None:
        """NotificationService tiene método send_whatsapp."""
        assert hasattr(notification, "send_whatsapp")

    def test_notification_has_configure_smtp(self, notification: NotificationService) -> None:
        """NotificationService tiene método configure_smtp."""
        assert hasattr(notification, "configure_smtp")

    def test_notification_has_test_connection(self, notification: NotificationService) -> None:
        """NotificationService tiene método test_connection."""
        assert hasattr(notification, "test_connection")


class TestGmailService:
    """Tests para GmailService."""

    @pytest.fixture
    def gmail(self) -> GmailService:
        """GmailService instance."""
        return GmailService()

    def test_gmail_has_send_email(self, gmail: GmailService) -> None:
        """GmailService tiene método send_email."""
        assert hasattr(gmail, "send_email")

    def test_gmail_has_get_status(self, gmail: GmailService) -> None:
        """GmailService tiene método get_status."""
        assert hasattr(gmail, "get_status")


class TestSlackService:
    """Tests para SlackService."""

    @pytest.fixture
    def slack(self) -> SlackService:
        """SlackService instance."""
        return SlackService()

    def test_slack_has_send_message(self, slack: SlackService) -> None:
        """SlackService tiene método send_message."""
        assert hasattr(slack, "send_message")

    def test_slack_has_get_status(self, slack: SlackService) -> None:
        """SlackService tiene método get_status."""
        assert hasattr(slack, "get_status")


class TestTelegramService:
    """Tests para TelegramService."""

    @pytest.fixture
    def telegram(self) -> TelegramService:
        """TelegramService instance."""
        return TelegramService()

    def test_telegram_has_send_message(self, telegram: TelegramService) -> None:
        """TelegramService tiene método send_message."""
        assert hasattr(telegram, "send_message")

    def test_telegram_has_get_status(self, telegram: TelegramService) -> None:
        """TelegramService tiene método get_status."""
        assert hasattr(telegram, "get_status")
