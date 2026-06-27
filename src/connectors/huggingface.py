"""
Conector HuggingFace — Inferencia de Modelos via HuggingFace API
===================================================================

Permite ejecutar inferencia en modelos de NLP, vision, audio
y generacion via la Inference API de HuggingFace.
"""

from __future__ import annotations

import base64
from typing import Any

from src.core.logging import setup_logging
from src.sdk.base import BaseConnector
from src.sdk.http_client import HttpClient, HTTPClientError
from src.sdk.schema import ActionDefinition, AuthRequirement, ConnectorSchema

logger = setup_logging(__name__)


class HuggingfaceConnector(BaseConnector):
    """Conector para HuggingFace: inferencia de modelos de IA."""

    name = "huggingface"
    version = "1.0.0"
    description = "Ejecuta inferencia en modelos de NLP, vision y audio via HuggingFace"
    category = "ai_data"
    icon = "cpu"
    author = "Zenic-Flijo"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url: str = "https://api-inference.huggingface.co/models"
        self._http: HttpClient | None = None

    def _get_api_token(self) -> str:
        """Extract API token from the auth provider."""
        if not self._auth_provider:
            return ""
        # Try to access _api_key directly (APIKeyAuth stores token in _api_key)
        api_token = getattr(self._auth_provider, "_api_key", "")
        if api_token:
            return api_token
        # Fallback: use apply_auth and extract from headers
        auth_request: dict[str, Any] = {"headers": {}, "params": {}}
        self._auth_provider.apply_auth(auth_request)
        headers = auth_request.get("headers", {})
        api_token = headers.get("X-API-Key", headers.get("Authorization", "").replace("Bearer ", ""))
        return api_token

    def connect(self) -> bool:
        """Establece conexion con la Inference API de HuggingFace."""
        if not self._auth_provider or not self._auth_provider.validate():
            logger.error("HuggingfaceConnector: API Token no configurado")
            return False

        api_token = self._get_api_token()
        if not api_token:
            logger.error("HuggingfaceConnector: No se pudo extraer el API Token del auth provider")
            return False

        self._http = HttpClient(
            base_url=self._base_url,
            connector_name=self.name,
        )
        self._http.set_auth("Bearer", token=api_token)

        self._connected = True
        self._log_operation("connect", "API Token configurado, HttpClient inicializado")
        return True

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        """Ejecuta una accion del conector HuggingFace.

        Args:
            action: Nombre de la accion a ejecutar
            params: Parametros de la accion
        """
        action_map: dict[str, Any] = {
            "text_generation": self._text_generation,
            "text_classification": self._text_classification,
            "summarization": self._summarization,
            "translation": self._translation,
            "image_classification": self._image_classification,
            "speech_recognition": self._speech_recognition,
        }
        handler = action_map.get(action)
        if handler is None:
            return {"error": f"Accion '{action}' no soportada", "available": list(action_map.keys())}
        return handler(params)

    def validate(self) -> bool:
        """Valida que el API Token de HuggingFace este configurado."""
        if not self._auth_provider:
            return False
        return self._auth_provider.validate()

    def disconnect(self) -> bool:
        """Cierra la conexion con HuggingFace."""
        self._http = None
        self._connected = False
        self._log_operation("disconnect")
        return True

    def _text_generation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Genera texto usando un modelo de HuggingFace.

        Args:
            params: Debe contener 'model_id' y 'inputs', opcionalmente 'parameters' (max_new_tokens, temperature, etc.)
        """
        model_id = params.get("model_id", "")
        inputs = params.get("inputs", "")
        if not model_id or not inputs:
            return {"success": False, "error": "Parametros requeridos: model_id, inputs"}

        self._log_operation("text_generation", f"model={model_id}")

        try:
            body: dict[str, Any] = {"inputs": inputs}
            if "parameters" in params:
                body["parameters"] = params["parameters"]
            if "options" in params:
                body["options"] = params["options"]

            response = self._http.post(f"/{model_id}", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"HuggingFace API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, "data": data, "model_id": model_id}

        except HTTPClientError as e:
            logger.error(f"HuggingfaceConnector.text_generation: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"HuggingfaceConnector.text_generation: error: {e}")
            return {"success": False, "error": str(e)}

    def _text_classification(self, params: dict[str, Any]) -> dict[str, Any]:
        """Clasifica texto usando un modelo de HuggingFace.

        Args:
            params: Debe contener 'model_id' y 'inputs'
        """
        model_id = params.get("model_id", "")
        inputs = params.get("inputs", "")
        if not model_id or not inputs:
            return {"success": False, "error": "Parametros requeridos: model_id, inputs"}

        self._log_operation("text_classification", f"model={model_id}")

        try:
            body: dict[str, Any] = {"inputs": inputs}
            if "parameters" in params:
                body["parameters"] = params["parameters"]

            response = self._http.post(f"/{model_id}", json=body, timeout=60)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"HuggingFace API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, "data": data, "model_id": model_id}

        except HTTPClientError as e:
            logger.error(f"HuggingfaceConnector.text_classification: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"HuggingfaceConnector.text_classification: error: {e}")
            return {"success": False, "error": str(e)}

    def _summarization(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resume un texto usando un modelo de HuggingFace.

        Args:
            params: Debe contener 'model_id' y 'inputs'
        """
        model_id = params.get("model_id", "")
        inputs = params.get("inputs", "")
        if not model_id or not inputs:
            return {"success": False, "error": "Parametros requeridos: model_id, inputs"}

        self._log_operation("summarization", f"model={model_id}")

        try:
            body: dict[str, Any] = {"inputs": inputs}
            if "parameters" in params:
                body["parameters"] = params["parameters"]

            response = self._http.post(f"/{model_id}", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"HuggingFace API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, "data": data, "model_id": model_id}

        except HTTPClientError as e:
            logger.error(f"HuggingfaceConnector.summarization: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"HuggingfaceConnector.summarization: error: {e}")
            return {"success": False, "error": str(e)}

    def _translation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Traduce texto usando un modelo de HuggingFace.

        Args:
            params: Debe contener 'model_id' y 'inputs'
        """
        model_id = params.get("model_id", "")
        inputs = params.get("inputs", "")
        if not model_id or not inputs:
            return {"success": False, "error": "Parametros requeridos: model_id, inputs"}

        self._log_operation("translation", f"model={model_id}")

        try:
            body: dict[str, Any] = {"inputs": inputs}
            if "parameters" in params:
                body["parameters"] = params["parameters"]

            response = self._http.post(f"/{model_id}", json=body, timeout=120)

            if not response.ok:
                error_body = response.json() or response.body
                return {"success": False, "error": f"HuggingFace API error ({response.status_code}): {error_body}"}

            data = response.json()
            return {"success": True, "data": data, "model_id": model_id}

        except HTTPClientError as e:
            logger.error(f"HuggingfaceConnector.translation: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"HuggingfaceConnector.translation: error: {e}")
            return {"success": False, "error": str(e)}

    def _image_classification(self, params: dict[str, Any]) -> dict[str, Any]:
        """Clasifica una imagen usando un modelo de vision de HuggingFace.

        Uses the requests library directly since the HuggingFace image
        classification API expects binary image data, not JSON.

        Args:
            params: Debe contener 'model_id' y 'image' (base64 o URL)
        """
        model_id = params.get("model_id", "")
        image = params.get("image", "")
        if not model_id or not image:
            return {"success": False, "error": "Parametros requeridos: model_id, image"}

        self._log_operation("image_classification", f"model={model_id}")

        try:
            import requests as req_lib

            api_token = self._get_api_token()
            url = f"{self._base_url}/{model_id}"

            # Determine if image is base64 or a URL
            if image.startswith(("http://", "https://")):
                # Download the image first
                img_response = req_lib.get(image, timeout=30)
                if not img_response.ok:
                    return {"success": False, "error": f"Failed to download image: {img_response.status_code}"}
                image_bytes = img_response.content
            else:
                # Assume base64-encoded image
                try:
                    image_bytes = base64.b64decode(image)
                except Exception:
                    return {"success": False, "error": "El parametro 'image' debe ser una URL o base64"}

            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "image/jpeg",
            }

            resp = req_lib.post(url, headers=headers, data=image_bytes, timeout=60)

            if not 200 <= resp.status_code < 300:
                return {"success": False, "error": f"HuggingFace API error ({resp.status_code}): {resp.text}"}

            data = resp.json()
            return {"success": True, "data": data, "model_id": model_id}

        except HTTPClientError as e:
            logger.error(f"HuggingfaceConnector.image_classification: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"HuggingfaceConnector.image_classification: error: {e}")
            return {"success": False, "error": str(e)}

    def _speech_recognition(self, params: dict[str, Any]) -> dict[str, Any]:
        """Transcribe audio usando un modelo de HuggingFace.

        Uses the requests library directly since the HuggingFace speech
        recognition API expects binary audio data, not JSON.

        Args:
            params: Debe contener 'model_id' y 'audio' (base64 o URL)
        """
        model_id = params.get("model_id", "")
        audio = params.get("audio", "")
        if not model_id or not audio:
            return {"success": False, "error": "Parametros requeridos: model_id, audio"}

        self._log_operation("speech_recognition", f"model={model_id}")

        try:
            import requests as req_lib

            api_token = self._get_api_token()
            url = f"{self._base_url}/{model_id}"

            # Determine if audio is base64 or a URL
            if audio.startswith(("http://", "https://")):
                # Download the audio first
                audio_response = req_lib.get(audio, timeout=30)
                if not audio_response.ok:
                    return {"success": False, "error": f"Failed to download audio: {audio_response.status_code}"}
                audio_bytes = audio_response.content
            else:
                # Assume base64-encoded audio
                try:
                    audio_bytes = base64.b64decode(audio)
                except Exception:
                    return {"success": False, "error": "El parametro 'audio' debe ser una URL o base64"}

            headers = {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "audio/wav",
            }

            resp = req_lib.post(url, headers=headers, data=audio_bytes, timeout=120)

            if not 200 <= resp.status_code < 300:
                return {"success": False, "error": f"HuggingFace API error ({resp.status_code}): {resp.text}"}

            data = resp.json()
            return {"success": True, "data": data, "model_id": model_id}

        except HTTPClientError as e:
            logger.error(f"HuggingfaceConnector.speech_recognition: HTTP error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"HuggingfaceConnector.speech_recognition: error: {e}")
            return {"success": False, "error": str(e)}


HUGGINGFACE_SCHEMA = ConnectorSchema(
    name="huggingface",
    version="1.0.0",
    description="Ejecuta inferencia en modelos de NLP, vision y audio via HuggingFace",
    category="ai_data",
    icon="cpu",
    author="Zenic-Flijo",
    actions=[
        ActionDefinition(name="text_generation", description="Genera texto", category="write"),
        ActionDefinition(name="text_classification", description="Clasifica texto", category="read"),
        ActionDefinition(name="summarization", description="Resume texto", category="write"),
        ActionDefinition(name="translation", description="Traduce texto", category="write"),
        ActionDefinition(name="image_classification", description="Clasifica imagen", category="read"),
        ActionDefinition(name="speech_recognition", description="Transcribe audio", category="read"),
    ],
    auth_requirements=[
        AuthRequirement(auth_type="api_key", required_fields=["api_token"], description="HuggingFace API Token")
    ],
)
