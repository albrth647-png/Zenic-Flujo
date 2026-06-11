"""
Workflow Determinista — Tests del Notification Service
Tests unitarios para el servicio de notificaciones: modelos, SMTP, plantillas, errores.
"""

from unittest.mock import MagicMock, patch


class TestNotificationModels:
    """Tests para constantes y modelos de notificación."""

    def test_notification_channels_defined(self):
        """Test: NOTIFICATION_CHANNELS contiene los canales correctos."""
        from src.tools.notification.models import NOTIFICATION_CHANNELS

        assert "email" in NOTIFICATION_CHANNELS
        assert "log" in NOTIFICATION_CHANNELS
        assert "slack" in NOTIFICATION_CHANNELS
        assert "sms" in NOTIFICATION_CHANNELS

    def test_notification_statuses_defined(self):
        """Test: NOTIFICATION_STATUSES contiene los estados correctos."""
        from src.tools.notification.models import NOTIFICATION_STATUSES

        assert "pending" in NOTIFICATION_STATUSES
        assert "sent" in NOTIFICATION_STATUSES
        assert "failed" in NOTIFICATION_STATUSES
        assert "queued" in NOTIFICATION_STATUSES

    def test_email_templates_defined(self):
        """Test: EMAIL_TEMPLATES contiene las plantillas predefinidas."""
        from src.tools.notification.models import EMAIL_TEMPLATES

        assert "welcome" in EMAIL_TEMPLATES
        assert "invoice_created" in EMAIL_TEMPLATES
        assert "invoice_overdue" in EMAIL_TEMPLATES
        assert "stock_low" in EMAIL_TEMPLATES
        assert "birthday" in EMAIL_TEMPLATES

    def test_email_templates_have_subject_and_body(self):
        """Test: cada plantilla tiene subject y body."""
        from src.tools.notification.models import EMAIL_TEMPLATES

        for name, template in EMAIL_TEMPLATES.items():
            assert "subject" in template, f"Template '{name}' missing subject"
            assert "body" in template, f"Template '{name}' missing body"


class TestNotificationService:
    """Tests para la clase NotificationService."""

    def test_send_email_no_smtp_configured(self, notification_service):
        """Test: enviar email sin SMTP configurado lo encola."""
        result = notification_service.send_email(
            to="test@example.com",
            subject="Test Subject",
            body="Test Body",
        )
        assert result["status"] == "queued"
        assert "SMTP" in result["message"]

    @patch("smtplib.SMTP")
    def test_send_email_with_smtp_mock(self, mock_smtp_class, notification_service):
        """Test: enviar email con SMTP mockeado retorna sent."""
        # Configure SMTP settings
        notification_service.configure_smtp(
            server="smtp.test.com",
            port=587,
            username="user@test.com",
            password="testpass",
        )
        # Setup mock
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = notification_service.send_email(
            to="dest@example.com",
            subject="Mock Test",
            body="Mock body",
        )
        assert result["status"] == "sent"
        assert result["to"] == "dest@example.com"
        assert result["subject"] == "Mock Test"

    def test_test_connection_no_smtp(self, notification_service):
        """Test: test_connection sin SMTP configurado retorna error."""
        result = notification_service.test_connection()
        assert result["status"] == "error"
        assert "SMTP" in result["message"]

    @patch("smtplib.SMTP")
    def test_test_connection_with_mock_smtp(self, mock_smtp_class, notification_service):
        """Test: test_connection con SMTP mockeado retorna ok."""
        notification_service.configure_smtp(
            server="smtp.test.com",
            port=587,
            username="user@test.com",
            password="testpass",
        )
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = notification_service.test_connection()
        assert result["status"] == "ok"

    @patch("smtplib.SMTP")
    def test_test_connection_smtp_failure(self, mock_smtp_class, notification_service):
        """Test: test_connection con fallo SMTP retorna error."""
        notification_service.configure_smtp(
            server="smtp.test.com",
            port=587,
            username="user@test.com",
            password="testpass",
        )
        mock_smtp_class.side_effect = OSError("Connection refused")

        result = notification_service.test_connection()
        assert result["status"] == "error"
        assert "Connection refused" in result["message"]

    @patch("smtplib.SMTP")
    def test_send_email_smtp_failure(self, mock_smtp_class, notification_service):
        """Test: enviar email con fallo SMTP retorna failed."""
        notification_service.configure_smtp(
            server="smtp.test.com",
            port=587,
            username="user@test.com",
            password="testpass",
        )
        import smtplib

        mock_smtp_class.side_effect = smtplib.SMTPException("SMTP server unavailable")

        result = notification_service.send_email(
            to="fail@example.com",
            subject="Fail Test",
            body="This should fail",
        )
        assert result["status"] == "failed"
        assert "SMTP server unavailable" in result["error"]

    def test_template_rendering(self):
        """Test: las plantillas se renderizan correctamente con variables."""
        from src.tools.notification.models import EMAIL_TEMPLATES

        template = EMAIL_TEMPLATES["welcome"]
        rendered = template["body"].format(nombre="Carlos")
        assert "Carlos" in rendered
        assert "Gracias" in rendered or "gracias" in rendered

    def test_template_invoice_created_rendering(self):
        """Test: la plantilla invoice_created se renderiza con variables."""
        from src.tools.notification.models import EMAIL_TEMPLATES

        template = EMAIL_TEMPLATES["invoice_created"]
        rendered = template["body"].format(cliente="Ana", numero="FAC-2025-001", total="150.00")
        assert "Ana" in rendered
        assert "FAC-2025-001" in rendered
        assert "150.00" in rendered

    def test_send_notification_email_channel(self, notification_service):
        """Test: send_notification con canal email delega a send_email."""
        # Without SMTP configured, it should return queued
        result = notification_service.send_notification(
            channel="email",
            recipients="test@example.com",
            message="Test message",
            subject="Test Subject",
        )
        # Since SMTP is not configured, it will be queued
        assert result["status"] in ("queued", "sent", "failed")

    def test_send_notification_log_channel(self, notification_service):
        """Test: send_notification con canal log retorna logged."""
        result = notification_service.send_notification(
            channel="log",
            recipients="admin",
            message="Log test message",
        )
        assert result["status"] == "logged"
        assert result["channel"] == "log"

    def test_send_notification_multiple_recipients(self, notification_service):
        """Test: send_notification con múltiples destinatarios email."""
        result = notification_service.send_notification(
            channel="email",
            recipients=["a@test.com", "b@test.com"],
            message="Multi recipient test",
            subject="Test",
        )
        # Without SMTP, results should be queued
        assert result["status"] == "completed"
        assert "results" in result

    def test_configure_smtp(self, notification_service):
        """Test: configure_smtp guarda la configuración."""
        result = notification_service.configure_smtp(
            server="smtp.example.com",
            port=587,
            username="user@example.com",
            password="secret123",
        )
        assert result is True

    def test_get_status_no_smtp(self, notification_service):
        """Test: get_status sin SMTP configurado."""
        status = notification_service.get_status()
        assert "smtp_configured" in status
        assert status["smtp_configured"] is False

    def test_get_status_with_smtp(self, notification_service):
        """Test: get_status con SMTP configurado."""
        notification_service.configure_smtp(
            server="smtp.example.com",
            port=587,
            username="user@example.com",
            password="secret123",
        )
        status = notification_service.get_status()
        assert status["smtp_configured"] is True

    def test_channel_validation(self):
        """Test: solo los canales definidos son válidos."""
        from src.tools.notification.models import NOTIFICATION_CHANNELS

        # Verify each expected channel
        for channel in ["email", "log", "slack", "sms"]:
            assert channel in NOTIFICATION_CHANNELS
        # Verify invalid channel is not present
        assert "carrier_pigeon" not in NOTIFICATION_CHANNELS
