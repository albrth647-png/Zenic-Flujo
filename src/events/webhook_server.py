"""
Workflow Determinista — WebhookServer
Servidor HTTP mínimo para recibir webhooks externos.
API Key OBLIGATORIA para todas las peticiones.
"""

import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.core.config import WEBHOOK_API_KEY_ENABLED, WEBHOOK_PORT
from src.core.db import DatabaseManager
from src.core.logging import setup_logging
from src.events.bus import EventBus

logger = setup_logging(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    """Manejador HTTP para webhooks."""

    # Compartidos entre instancias (asignados por WebhookServer)
    event_bus: EventBus | None = None
    db: DatabaseManager | None = None
    results_getter = None  # Callable que retorna resultados tras publish()

    def do_POST(self):
        """Maneja peticiones POST a /webhook/<workflow_id>."""
        path_parts = self.path.strip("/").split("/")

        # GET /webhook/health → health check
        if self.path == "/webhook/health":
            self._send_json(200, {"status": "ok"})
            return

        if len(path_parts) != 2 or path_parts[0] != "webhook":
            self._send_json(404, {"error": "Ruta inválida. Use /webhook/<id>"})
            return

        try:
            workflow_id = int(path_parts[1])
        except ValueError:
            self._send_json(400, {"error": "ID de workflow inválido"})
            return

        # Validar API Key
        if WEBHOOK_API_KEY_ENABLED:
            api_key = self.headers.get("X-API-Key", "")
            stored_key = (self.db or DatabaseManager()).get_setting("webhook_api_key")

            if not api_key or not stored_key or not hmac.compare_digest(api_key, stored_key):
                self._send_json(401, {"error": "API Key inválida o no proporcionada"})
                logger.warning(f"Webhook rechazado: API Key inválida para workflow {workflow_id}")
                if self.db:
                    self.db.audit(
                        "webhook.rejected", f"API Key inválida para workflow {workflow_id}", self.client_address[0]
                    )
                return

        # Leer body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Body debe ser JSON válido"})
            return

        # Publicar evento — pasar body directamente a $input para resolución de variables
        try:
            bus = self.event_bus
            if bus is None:
                self._send_json(500, {"error": "EventBus no configurado"})
                return
            # Pasar datos planos + workflow_id para que $input.nombre funcione
            # y EventBus pueda filtrar por workflow_id si es necesario
            webhook_data = dict(data)
            webhook_data["_workflow_id"] = workflow_id
            bus.publish("webhook.received", webhook_data)

            # Obtener resultados desde el subscriber (si está configurado)
            results = []
            if self.results_getter is not None:
                results = self.results_getter()

            self._send_json(
                200,
                {
                    "status": "processed",
                    "results": results,
                },
            )

            logger.info(f"Webhook procesado para workflow {workflow_id}")
            if self.db:
                self.db.audit("webhook.received", f"Webhook para workflow {workflow_id}", self.client_address[0])

        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            self._send_json(500, {"error": f"Error interno: {e!s}"})

    def do_GET(self):
        """Maneja peticiones GET."""
        if self.path == "/webhook/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "Usa POST /webhook/<id> o GET /webhook/health"})

    def _send_json(self, status_code: int, data: dict) -> None:
        """Envía respuesta JSON."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "127.0.0.1")  # Restrict to local
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, format, *args):
        """Silencia logs HTTP estándar."""


class WebhookServer:
    """
    Servidor de webhooks.

    Se inicia en un hilo separado en el puerto configurado.
    """

    def __init__(
        self,
        port: int = WEBHOOK_PORT,
        event_bus: EventBus | None = None,
        db: DatabaseManager | None = None,
        workflow_subscriber: object | None = None,
    ):
        self._port = port
        self._event_bus = event_bus
        self._db = db
        self._subscriber = workflow_subscriber
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, port: int | None = None) -> None:
        """Inicia el servidor de webhooks."""
        if port:
            self._port = port

        # Configurar dependencias compartidas
        WebhookHandler.event_bus = self._event_bus or EventBus()
        WebhookHandler.db = self._db or DatabaseManager()
        if self._subscriber is not None:
            WebhookHandler.results_getter = lambda: getattr(self._subscriber, 'last_results', [])

        try:
            # Permitir reuso inmediato del puerto tras reinicio (antes del bind)
            HTTPServer.allow_reuse_address = True
            self._server = HTTPServer(("127.0.0.1", self._port), WebhookHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            self._running = True
            logger.info(f"WebhookServer iniciado en puerto {self._port}")
        except OSError as e:
            logger.warning(f"WebhookServer no pudo iniciarse en puerto {self._port}: {e}")
            logger.warning("Los webhooks no estarán disponibles. Los demás servicios continúan funcionando.")

    def stop(self) -> None:
        """Detiene el servidor de webhooks."""
        if self._server:
            self._server.shutdown()
            self._running = False
            logger.info("WebhookServer detenido")

    def is_running(self) -> bool:
        return self._running
