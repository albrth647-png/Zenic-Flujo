"""
Workflow Determinista — Tests del WebhookServer
Tests unitarios para el servidor HTTP de webhooks.
"""
import json
import time
import pytest
from unittest.mock import patch, MagicMock


class TestWebhookServer:
    """Tests del WebhookServer."""

    def test_init(self):
        """Verifica inicialización correcta."""
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18081)
        assert server._port == 18081
        assert server._running is False
        assert server._server is None

    def test_start_and_stop(self):
        """Verifica que el servidor arranca y se detiene correctamente."""
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18082)
        server.start()
        assert server.is_running() is True
        time.sleep(0.3)  # Dar tiempo para que el hilo arranque
        server.stop()
        time.sleep(0.3)
        assert server.is_running() is False

    def test_start_with_custom_port(self):
        """Verifica inicio con puerto personalizado."""
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18083)
        server.start(port=18084)
        assert server._port == 18084
        time.sleep(0.2)
        server.stop()

    def test_health_check_get(self):
        """Verifica que GET /webhook/health responde OK."""
        import urllib.request
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18085)
        server.start()
        time.sleep(0.5)
        try:
            url = "http://127.0.0.1:18085/webhook/health"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                assert data["status"] == "ok"
        finally:
            server.stop()

    def test_health_check_post(self):
        """Verifica que POST /webhook/health responde OK."""
        import urllib.request
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18086)
        server.start()
        time.sleep(0.5)
        try:
            url = "http://127.0.0.1:18086/webhook/health"
            req = urllib.request.Request(url, data=b"{}", method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                assert data["status"] == "ok"
        finally:
            server.stop()

    def test_invalid_path_returns_404(self):
        """Verifica que una ruta inválida retorna 404."""
        import urllib.request
        import urllib.error
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18087)
        server.start()
        time.sleep(0.5)
        try:
            url = "http://127.0.0.1:18087/invalid/path"
            req = urllib.request.Request(url, data=b"{}", method="POST")
            req.add_header("Content-Type", "application/json")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == 404
        finally:
            server.stop()

    def test_invalid_workflow_id_returns_400(self):
        """Verifica que un ID de workflow inválido retorna 400."""
        import urllib.request
        import urllib.error
        from src.events.webhook_server import WebhookServer
        server = WebhookServer(port=18088)
        server.start()
        time.sleep(0.5)
        try:
            url = "http://127.0.0.1:18088/webhook/notanumber"
            req = urllib.request.Request(url, data=b"{}", method="POST")
            req.add_header("Content-Type", "application/json")
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == 400
        finally:
            server.stop()


class TestWebhookHandler:
    """Tests unitarios del WebhookHandler."""

    def test_send_json(self):
        """Verifica que _send_json produce respuesta correcta."""
        from src.events.webhook_server import WebhookHandler
        handler = WebhookHandler.__new__(WebhookHandler)
        # Mock los métodos de BaseHTTPRequestHandler
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler._send_json(200, {"test": "ok"})
        handler.send_response.assert_called_once_with(200)
        handler.end_headers.assert_called_once()

    def test_log_message_silenced(self):
        """Verifica que log_message no produce salida."""
        from src.events.webhook_server import WebhookHandler
        handler = WebhookHandler.__new__(WebhookHandler)
        # No debe lanzar ni imprimir nada
        handler.log_message("%s", "test")
