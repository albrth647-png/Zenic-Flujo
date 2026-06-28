"""
Conector Anthropic — Claude via Anthropic API
==================================================

Permite generar texto con Claude, analizar documentos
y gestionar conversaciones via la API de Anthropic.
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)

# Anthropic API version header — update when new API versions are released
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicConnector(BaseConnector):
    """Conector para Anthropic: Claude, analisis y conversaciones."""

    name = "anthropic"
    version = "1.0.0"
    description = "Genera texto con Claude y analiza documentos via Anthropic"
    category = "ai_data"
    icon = "brain"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.anthropic.com/v1"
        self._http: HttpClient | None = None

    def _get_api_key(self) -> str:
        """Extract API key from the auth provider."""
        if not self._auth_provider:
            return ""
        # Try to access _api_key directly (APIKeyAuth)
        api_key = getattr(self._auth_provider, "_api_key", "")
        if api_key:
            return api_key
        # Fallback: use apply_auth and extract from headers
        auth_request: dict[str, Any] = {"headers": {}, "params": {}}
        self._auth_provider.apply_auth(auth_request)
        headers = auth_request.get("headers", {})
        api_key = headers.get("X-API-Key", headers.get("Authorization", "").replace("Bearer ", ""))
        return api_key

    def connect(self) -> bool:
        """Establece conexion con la API de Anthropic."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("AnthropicConnector: API Key no configurada")
            return False

        api_key = self._get_api_key()
        if not api_key:
            logger.error("AnthropicConnector: No se pudo extraer la API Key del auth provider")
            return False

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
            default_headers={
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )
        # Anthropic uses x-api-key header instead of Bearer auth
        self._http.set_auth("ApiKey", token=api_key)

        self._connected = True
        self._log_operation("connect", "API Key configurada, HttpClient inicializado")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector Anthropic.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "create_message": self._create_message,
            "analyze_document": self._analyze_document,
            "count_tokens": self._count_tokens,
            "list_models": self._list_models,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que la API Key de Anthropic este configurada."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con Anthropic."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _create_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Crea un mensaje con Claude.

        Args:
            params: Debe contener 'messages' y 'max_tokens', opcionalmente 'model', 'system', 'temperature'
        """
        messages = params.get("messages", [])
        max_tokens = params.get("max_tokens", 4096)
        model = params.get("model", "claude-3-5-sonnet-20241022")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("create_message", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if "system" in params:
                body["system"] = params["system"]
            if "temperature" in params:
                body["temperature"] = params["temperature"]
            if "top_p" in params:
                body["top_p"] = params["top_p"]
            if "stream" in params:
                body["stream"] = False  # Force non-streaming for simplicity

            response = self._http.post("/messages", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"Anthropic API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"AnthropicConnector.create_message: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"AnthropicConnector.create_message: error: {e}")
            return {"success": False, "error": str(e)}

    def _analyze_document(self, params: dict[str, Any]) -> dict[str, Any]:
        """Analiza un documento con Claude (vision).

        This uses the same /messages endpoint with vision content
        (image blocks in the messages array).

        Args:
            params: Debe contener 'messages' con contenido de imagen (base64) y 'max_tokens'
        """
        messages = params.get("messages", [])
        max_tokens = params.get("max_tokens", 4096)
        model = params.get("model", "claude-3-5-sonnet-20241022")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("analyze_document", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if "system" in params:
                body["system"] = params["system"]
            if "temperature" in params:
                body["temperature"] = params["temperature"]

            response = self._http.post("/messages", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"Anthropic API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"AnthropicConnector.analyze_document: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"AnthropicConnector.analyze_document: error: {e}")
            return {"success": False, "error": str(e)}

    def _count_tokens(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cuenta los tokens de un mensaje.

        Args:
            params: Debe contener 'messages' y 'model'
        """
        messages = params.get("messages", [])
        model = params.get("model", "claude-3-5-sonnet-20241022")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("count_tokens", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if "system" in params:
                body["system"] = params["system"]
            if "tools" in params:
                body["tools"] = params["tools"]

            response = self._http.post("/messages/count_tokens", json=body, timeout=30)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"Anthropic API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"AnthropicConnector.count_tokens: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"AnthropicConnector.count_tokens: error: {e}")
            return {"success": False, "error": str(e)}

    def _list_models(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los modelos disponibles de Anthropic.

        Note: Anthropic does not have a public /models endpoint like OpenAI.
        Returns a static list of known Claude models.
        """
        self._log_operation("list_models")
        # Anthropic doesn't expose a /models listing endpoint yet.
        # Return the known models statically.
        return {
            "success": True,
            "models": [
                {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet", "created_at": "2024-10-22"},
                {"id": "claude-3-5-haiku-20241022", "display_name": "Claude 3.5 Haiku", "created_at": "2024-10-22"},
                {"id": "claude-3-opus-20240229", "display_name": "Claude 3 Opus", "created_at": "2024-02-29"},
                {"id": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku", "created_at": "2024-03-07"},
            ],
        }


ANTHROPIC_SCHEMA = ConnectorSchema(
    name="anthropic",
    version="1.0.0",
    description="Genera texto con Claude y analiza documentos via Anthropic",
    category="ai_data",
    icon="brain",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="create_message", description="Crea un mensaje con Claude", category="write"),
        ActionDefinition(name="analyze_document", description="Analiza un documento", category="write"),
        ActionDefinition(name="count_tokens", description="Cuenta tokens", category="read"),
        ActionDefinition(name="list_models", description="Lista modelos", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_key"], description="Anthropic API Key")
    ],
)
