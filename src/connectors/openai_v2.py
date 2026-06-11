"""
Conector OpenAI v2 — GPT y DALL-E via OpenAI API (Enhanced)
===============================================================

Permite generar texto con GPT-4/GPT-3.5, imagenes con DALL-E,
embeddings y audio con Whisper/TTS via la API de OpenAI.
"""

from __future__ import annotations

from typing import Any

from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class OpenaiV2Connector(BaseConnector):
    """Conector mejorado para OpenAI: GPT, DALL-E, Embeddings, Whisper y TTS."""

    name = "openai_v2"
    version = "2.0.0"
    description = "Genera texto con GPT, imagenes con DALL-E, embeddings y audio via OpenAI"
    category = "ai_data"
    icon = "sparkles"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api.openai.com/v1"
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
        """Establece conexion con la API de OpenAI."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("OpenaiV2Connector: API Key no configurada")
            return False

        api_key = self._get_api_key()
        if not api_key:
            logger.error("OpenaiV2Connector: No se pudo extraer la API Key del auth provider")
            return False

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=api_key)
        self._connected = True
        self._log_operation("connect", "API Key configurada, HttpClient inicializado")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector OpenAI v2.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "chat_completion": self._chat_completion,
            "create_image": self._create_image,
            "create_embedding": self._create_embedding,
            "transcribe_audio": self._transcribe_audio,
            "generate_speech": self._generate_speech,
            "list_models": self._list_models,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que la API Key de OpenAI este configurada."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con OpenAI."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _chat_completion(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una respuesta de chat usando GPT.

        Args:
            params: Debe contener 'messages' (lista de dicts con role y content), opcionalmente 'model', 'temperature', 'max_tokens'
        """
        messages = params.get("messages", [])
        model = params.get("model", "gpt-4")
        if not messages:
            return {"success": False, "error": "Parametro requerido: messages"}

        self._log_operation("chat_completion", f"model={model}, messages={len(messages)}")

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
                return {"success": False, "error": f"OpenAI API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"OpenaiV2Connector.chat_completion: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"OpenaiV2Connector.chat_completion: error: {e}")
            return {"success": False, "error": str(e)}

    def _create_image(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera una imagen usando DALL-E.

        Args:
            params: Debe contener 'prompt' y opcionalmente 'model', 'n', 'size', 'quality'
        """
        prompt = params.get("prompt", "")
        model = params.get("model", "dall-e-3")
        n = params.get("n", 1)
        size = params.get("size", "1024x1024")
        if not prompt:
            return {"success": False, "error": "Parametro requerido: prompt"}

        self._log_operation("create_image", f"model={model}, size={size}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "n": n,
                "size": size,
            }
            if "quality" in params:
                body["quality"] = params["quality"]
            if "response_format" in params:
                body["response_format"] = params["response_format"]

            response = self._http.post("/images/generations", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"OpenAI API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"OpenaiV2Connector.create_image: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"OpenaiV2Connector.create_image: error: {e}")
            return {"success": False, "error": str(e)}

    def _create_embedding(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera embeddings usando text-embedding.

        Args:
            params: Debe contener 'input' y opcionalmente 'model'
        """
        input_text = params.get("input", "")
        model = params.get("model", "text-embedding-3-small")
        if not input_text:
            return {"success": False, "error": "Parametro requerido: input"}

        self._log_operation("create_embedding", f"model={model}")

        try:
            body: dict[str, Any] = {
                "model": model,
                "input": input_text,
            }
            if "encoding_format" in params:
                body["encoding_format"] = params["encoding_format"]
            if "dimensions" in params:
                body["dimensions"] = params["dimensions"]

            response = self._http.post("/embeddings", json=body, timeout=60)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"OpenAI API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"OpenaiV2Connector.create_embedding: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"OpenaiV2Connector.create_embedding: error: {e}")
            return {"success": False, "error": str(e)}

    def _transcribe_audio(self, params: dict[str, Any]) -> dict[str, Any]:
        """Transcribe audio usando Whisper.

        Uses the requests library directly since Whisper API requires
        multipart/form-data which HttpClient doesn't support natively.

        Args:
            params: Debe contener 'file' (ruta o base64) y opcionalmente 'model', 'language'
        """
        file_path = params.get("file", "")
        model = params.get("model", "whisper-1")
        if not file_path:
            return {"success": False, "error": "Parametro requerido: file"}

        self._log_operation("transcribe_audio", f"model={model}")

        try:
            import base64
            import os

            import requests as req_lib

            api_key = self._get_api_key()
            url = f"{self._base_url}/audio/transcriptions"

            # Handle file: could be a path or base64-encoded data
            files_payload = None
            if os.path.isfile(file_path):
                files_payload = {"file": (os.path.basename(file_path), open(file_path, "rb"))}
            else:
                # Assume base64-encoded audio
                try:
                    audio_bytes = base64.b64decode(file_path)
                    files_payload = {"file": ("audio.wav", audio_bytes)}
                except Exception:
                    return {"success": False, "error": "El parametro 'file' debe ser una ruta de archivo valida o base64"}

            form_data = {"model": model}
            if "language" in params:
                form_data["language"] = params["language"]

            resp = req_lib.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files=files_payload,
                data=form_data,
                timeout=120,
            )

            if not 200 <= resp.status_code < 300:
                return {"success": False, "error": f"OpenAI API error ({resp.status_code}): {resp.text}"}

            data = resp.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"OpenaiV2Connector.transcribe_audio: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"OpenaiV2Connector.transcribe_audio: error: {e}")
            return {"success": False, "error": str(e)}

    def _generate_speech(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera audio a partir de texto usando TTS.

        Args:
            params: Debe contener 'input', 'voice' y opcionalmente 'model', 'speed'
        """
        input_text = params.get("input", "")
        voice = params.get("voice", "alloy")
        model = params.get("model", "tts-1")
        if not input_text:
            return {"success": False, "error": "Parametro requerido: input"}

        self._log_operation("generate_speech", f"voice={voice}")

        try:
            import base64

            body: dict[str, Any] = {
                "model": model,
                "input": input_text,
                "voice": voice,
            }
            if "speed" in params:
                body["speed"] = params["speed"]
            if "response_format" in params:
                body["response_format"] = params["response_format"]

            # TTS returns binary audio, so we use HttpClient but handle the raw response
            response = self._http.post(
                "/audio/speech",
                json=body,
                timeout=120,
                headers={"Accept": "audio/mpeg"},
            )

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"OpenAI API error ({response.status_code}): {error_body}"}

            # Response is binary audio data
            audio_base64 = ""
            if response.raw:
                audio_base64 = base64.b64encode(response.raw).decode("utf-8")

            return {
                "success": True,
                "audio_base64": audio_base64,
                "content_type": "audio/mpeg",
                "model": model,
                "voice": voice,
            }

        except HTTPClientError as e:
            logger.error(f"OpenaiV2Connector.generate_speech: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"OpenaiV2Connector.generate_speech: error: {e}")
            return {"success": False, "error": str(e)}

    def _list_models(self, params: dict[str, Any]) -> dict[str, Any]:
        """Lista los modelos disponibles en OpenAI."""
        self._log_operation("list_models")

        try:
            response = self._http.get("/models", timeout=30)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"OpenAI API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, **data}

        except HTTPClientError as e:
            logger.error(f"OpenaiV2Connector.list_models: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"OpenaiV2Connector.list_models: error: {e}")
            return {"success": False, "error": str(e)}


OPENAI_V2_SCHEMA = ConnectorSchema(
    name="openai_v2",
    version="2.0.0",
    description="Genera texto con GPT, imagenes con DALL-E, embeddings y audio via OpenAI",
    category="ai_data",
    icon="sparkles",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="chat_completion", description="Genera respuesta de chat", category="write"),
        ActionDefinition(name="create_image", description="Genera imagen con DALL-E", category="write"),
        ActionDefinition(name="create_embedding", description="Genera embeddings", category="write"),
        ActionDefinition(name="transcribe_audio", description="Transcribe audio con Whisper", category="read"),
        ActionDefinition(name="generate_speech", description="Genera audio con TTS", category="write"),
        ActionDefinition(name="list_models", description="Lista modelos disponibles", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_key"], description="OpenAI API Key")
    ],
)
