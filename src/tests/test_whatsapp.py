"""
Tests para Integración WhatsApp (Mejora #6).
"""
import json
import pytest
from unittest.mock import patch, MagicMock


class TestWhatsAppService:
    """Tests para el servicio de WhatsApp."""

    def test_send_text_message_success(self, db_manager):
        """Envía mensaje de texto exitosamente."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        ns.configure_whatsapp(token="EAATestToken", phone_number_id="123456789")

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "messages": [{"id": "wamid.test123"}]
            }
            mock_post.return_value = mock_resp

            result = ns.send_whatsapp(
                to="+521234567890",
                message="Hola desde Workflow Determinista",
            )
            assert result["status"] == "sent"
            assert result["message_id"] == "wamid.test123"
            assert result["to"] == "+521234567890"

    def test_send_whatsapp_not_configured(self, db_manager):
        """Error si WhatsApp no está configurado."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()

        result = ns.send_whatsapp(to="+521234567890", message="Test")
        assert result["status"] == "error"
        assert "no configurado" in result["message"].lower()

    def test_configure_whatsapp(self, db_manager):
        """Configurar credenciales de WhatsApp (token cifrado)."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()

        result = ns.configure_whatsapp(
            token="EAATestToken123",
            phone_number_id="123456789",
        )
        assert result is True

        # Verificar que se guardaron (el token está cifrado, phone_id no)
        from src.data.database_manager import DatabaseManager
        db = DatabaseManager()
        stored_token = db.get_setting("whatsapp_token")
        assert stored_token != "EAATestToken123"  # Debe estar cifrado
        assert "EAATestToken123" not in stored_token  # No en texto plano
        stored_id = db.get_setting("whatsapp_phone_number_id")
        assert str(stored_id) == "123456789"

        # Verificar que se puede descifrar correctamente
        decrypted = ns._decrypt_token(stored_token)
        assert decrypted == "EAATestToken123"

    def test_send_whatsapp_after_configure(self, db_manager):
        """Envía después de configurar credenciales."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        ns.configure_whatsapp(token="EAAToken", phone_number_id="123")

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"messages": [{"id": "wamid.abc"}]}
            mock_post.return_value = mock_resp

            result = ns.send_whatsapp(to="+521234567890", message="Test msg")
            assert result["status"] == "sent"

            # Verificar que se llamó a la API correcta
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert "graph.facebook.com" in args[0]
            assert "123" in args[0]  # phone_number_id en URL
            assert kwargs["json"]["to"] == "+521234567890"
            assert kwargs["json"]["text"]["body"] == "Test msg"

    def test_send_whatsapp_api_error(self, db_manager):
        """Maneja errores de la API de WhatsApp."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        ns.configure_whatsapp(token="EAAToken", phone_number_id="123")

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.json.return_value = {
                "error": {"message": "(#100) Invalid parameter"}
            }
            mock_post.return_value = mock_resp

            result = ns.send_whatsapp(to="+521234567890", message="Test")
            assert result["status"] == "failed"
            assert "error" in result

    def test_send_whatsapp_connection_error(self, db_manager):
        """Maneja errores de conexión."""
        import requests
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        ns.configure_whatsapp(token="EAAToken", phone_number_id="123")

        with patch('requests.post', side_effect=requests.exceptions.ConnectionError("No internet")):
            result = ns.send_whatsapp(to="+521234567890", message="Test")
            assert result["status"] == "failed"
            assert "conexión" in result["message"].lower()

    def test_send_template_message(self, db_manager):
        """Envía mensaje template (para fuera de ventana 24h)."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()
        ns.configure_whatsapp(token="EAAToken", phone_number_id="123")

        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"messages": [{"id": "wamid.template"}]}
            mock_post.return_value = mock_resp

            result = ns.send_whatsapp_template(
                to="+521234567890",
                template_name="hello_world",
                language_code="es",
            )
            assert result["status"] == "sent"
            args, kwargs = mock_post.call_args
            assert kwargs["json"]["type"] == "template"
            assert kwargs["json"]["template"]["name"] == "hello_world"

    def test_whatsapp_get_status(self, db_manager):
        """Verifica estado de configuración WhatsApp."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()

        status = ns.get_whatsapp_status()
        assert status["whatsapp_configured"] is False

        ns.configure_whatsapp(token="EAAToken", phone_number_id="123")
        status = ns.get_whatsapp_status()
        assert status["whatsapp_configured"] is True

    def test_encrypt_decrypt_roundtrip(self, db_manager):
        """Verifica que cifrado y descifrado sean consistentes."""
        from src.tools.notification.service import NotificationService
        ns = NotificationService()

        original = "test-token-123!@#"
        encrypted = ns._encrypt_token(original)
        assert encrypted != original
        assert encrypted != ""

        decrypted = ns._decrypt_token(encrypted)
        assert decrypted == original
