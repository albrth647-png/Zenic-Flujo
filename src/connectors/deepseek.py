"""
Conector DeepSeek — IA via DeepSeek API
============================================

Permite generar texto, razonamiento y codificacion
via la API de DeepSeek (OpenAI-compatible).
"""

from __future__ import annotations

from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class DeepseekConnector(BaseConnector):
    """Conector para DeepSeek: generacion de texto y razonamiento."""

    name = "deepseek"
    version = "1.0.0"
    description = "Genera texto y razonamiento avanzado via DeepSeek AI"
    category = "ai_data"
    icon = "sparkles"
    author = "Zenic-Flijo"

    # legítimo: wrapper genérico. **kwargs se pasa a super().__init__ (skill §1.2)
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.deepseek.com/v1"
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
        """Establece conexion con la API de DeepSeek."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("DeepseekConnector: API Key no configurada")
            return False

        api_key = self._get_api_key()
        if not api_key:
            logger.error("DeepseekConnector: No se pudo extraer la API Key del auth provider")
            return False

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=api_key)

        self._connected = True
        self._log_operation("connect", "API Key configurada, HttpClient inicializado")
        return True

    # legítimo: execute() retorna JSON dinámico de API externa (skill §9.1)
    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector DeepSeek.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "chat_completion": self._chat_completion,
            "reasoning_completion": self._reasoning_completion,
            "code_completion": self._code_completion,
            "list_models": self._list_models,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que la API Key de DeepSeek este configurada."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con DeepSeek."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _chat_completion(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una respuesta de chat con DeepSeek.

        DeepSeek's API is OpenAI-compatible, using the /chat/completions endpoint.

        Args:
            params: Debe contener 'messages' y opcionalmente 'model', 'temperature', 'max_tokens'
        """
        messages = params.get("messages", [])
        model = params.get("model", "deepseek-chat")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("chat_completion", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if "temperature" in params:
                body["temperature"] = params["temperature"]
            if "max_tokens" in params:
                body["max_tokens"] = params["max_tokens"]
            if "top_p" in params:
                body["top_p"] = params["top_p"]
            if "frequency_penalty" in params:
                body["frequency_penalty"] = params["frequency_penalty"]
            if "presence_penalty" in params:
                body["presence_penalty"] = params["presence_penalty"]
            if "stream" in params:
                body["stream"] = False  # Force non-streaming for simplicity

            response = self._http.post("/chat/completions", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"DeepSeek API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"DeepseekConnector.chat_completion: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"DeepseekConnector.chat_completion: error: {e}")
            return {"success": False, "error": str(e)}

    def _reasoning_completion(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una respuesta con razonamiento extendido (DeepSeek-R1).

        Uses the /chat/completions endpoint with deepseek-reasoner model.
        The response includes a reasoning_content field in the message.

        Args:
            params: Debe contener 'messages' y opcionalmente 'model', 'max_tokens'
        """
        messages = params.get("messages", [])
        model = params.get("model", "deepseek-reasoner")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("reasoning_completion", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if "max_tokens" in params:
                body["max_tokens"] = params["max_tokens"]
            if "temperature" in params:
                body["temperature"] = params["temperature"]
            if "top_p" in params:
                body["top_p"] = params["top_p"]
            if "stream" in params:
                body["stream"] = False  # Force non-streaming for simplicity

            response = self._http.post("/chat/completions", json=body, timeout=180)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"DeepSeek API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"DeepseekConnector.reasoning_completion: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"DeepseekConnector.reasoning_completion: error: {e}")
            return {"success": False, "error": str(e)}

    def _code_completion(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera completacion de codigo con DeepSeek-Coder.

        Uses the /chat/completions endpoint with deepseek-coder model.

        Args:
            params: Debe contener 'messages' (con prompt de codigo), opcionalmente 'model', 'temperature'
        """
        messages = params.get("messages", [])
        model = params.get("model", "deepseek-coder")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("code_completion", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if "temperature" in params:
                body["temperature"] = params["temperature"]
            if "max_tokens" in params:
                body["max_tokens"] = params["max_tokens"]
            if "top_p" in params:
                body["top_p"] = params["top_p"]
            if "stream" in params:
                body["stream"] = False  # Force non-streaming for simplicity

            response = self._http.post("/chat/completions", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"DeepSeek API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"DeepseekConnector.code_completion: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"DeepseekConnector.code_completion: error: {e}")
            return {"success": False, "error": str(e)}

    def _list_models(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los modelos disponibles de DeepSeek.

        DeepSeek's API is OpenAI-compatible and provides a /models endpoint.
        """
        self._log_operation("list_models")

        try:
            response = self._http.get("/models", timeout=30)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"DeepSeek API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"DeepseekConnector.list_models: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"DeepseekConnector.list_models: error: {e}")
            return {"success": False, "error": str(e)}


DEEPSEEK_SCHEMA = ConnectorSchema(
    name="deepseek",
    version="1.0.0",
    description="Genera texto y razonamiento avanzado via DeepSeek AI",
    category="ai_data",
    icon="sparkles",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="chat_completion", description="Chat con DeepSeek", category="write"),
        ActionDefinition(name="reasoning_completion", description="Razonamiento extendido", category="write"),
        ActionDefinition(name="code_completion", description="Completacion de codigo", category="write"),
        ActionDefinition(name="list_models", description="Lista modelos", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_key"], description="DeepSeek API Key")
    ],
)
