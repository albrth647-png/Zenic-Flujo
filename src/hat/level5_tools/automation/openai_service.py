"""
OpenAI Connector — Chat completions, embeddings, model list
===============================================================

Sprint 6 del Roadmap Competitivo.
Integración con OpenAI API para chat y embeddings.
Usa openai Python SDK si está disponible, fallback a requests.
"""

from __future__ import annotations

import time
from typing import ClassVar, Any

from src.core.logging import setup_logging

logger = setup_logging(__name__)


class OpenAIService:
    """
    Conector OpenAI.

    Proporciona:
    - chat_completion: Chat con modelos GPT
    - embeddings: Generar embeddings de texto
    - list_models: Listar modelos disponibles
    - moderate: Moderación de contenido

    Uso en workflow:
    {
        "tool": "openai",
        "action": "chat_completion",
        "params": {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Eres un asistente útil"},
                {"role": "user", "content": "$input.consulta"}
            ],
            "temperature": 0.7
        }
    }
    """

    DEFAULT_MODEL = "gpt-4o-mini"
    ALLOWED_MODELS: ClassVar[set[str]] = {"gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo", "o1-mini", "o1-preview"}
    EMBEDDING_MODEL = "text-embedding-3-small"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or ""
        self._base_url = "https://api.openai.com/v1"

    def chat_completion(
        self,
        messages: list[dict],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        top_p: float = 1.0,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """
        Chat completion con modelos OpenAI.

        Args:
            messages: Lista de mensajes [{"role": "...", "content": "..."}]
            model: Modelo a usar
            temperature: Temperatura (0.0 - 2.0)
            max_tokens: Máximo de tokens en la respuesta
            top_p: Nucleus sampling
            timeout: Timeout en segundos

        Returns:
            dict con {content, model, usage, finish_reason, duration_ms}
        """
        if not self._api_key:
            return self._error("API key de OpenAI no configurada")

        if model not in self.ALLOWED_MODELS:
            logger.warning(f"Modelo '{model}' no verificado, se intentará igual")

        start_time = time.time()

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            import requests

            resp = requests.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            data = resp.json()

            if resp.status_code != 200:
                error_msg = data.get("error", {}).get("message", str(data))
                return self._error(f"OpenAI API error: {error_msg}")

            choice = data["choices"][0]
            usage = data.get("usage", {})

            return {
                "content": choice["message"]["content"],
                "role": choice["message"].get("role", "assistant"),
                "model": data["model"],
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                "finish_reason": choice.get("finish_reason", "stop"),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            return self._error(str(e))

    def embeddings(self, input_text: str | list[str], model: str = EMBEDDING_MODEL, timeout: int = 30) -> dict[str, Any]:
        """
        Genera embeddings de texto.

        Args:
            input_text: Texto o lista de textos
            model: Modelo de embeddings
            timeout: Timeout en segundos

        Returns:
            dict con {embeddings, model, usage, duration_ms}
        """
        if not self._api_key:
            return self._error("API key de OpenAI no configurada")

        start_time = time.time()
        inputs = [input_text] if isinstance(input_text, str) else input_text

        try:
            import requests

            resp = requests.post(
                f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "input": inputs},
                timeout=timeout,
            )
            data = resp.json()

            if resp.status_code != 200:
                error_msg = data.get("error", {}).get("message", str(data))
                return self._error(f"OpenAI API error: {error_msg}")

            usage = data.get("usage", {})
            return {
                "embeddings": [d["embedding"] for d in data["data"]],
                "model": data["model"],
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                "dimension": len(data["data"][0]["embedding"]) if data["data"] else 0,
                "count": len(data["data"]),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            logger.error(f"OpenAI embeddings error: {e}")
            return self._error(str(e))

    def list_models(self, timeout: int = 15) -> dict[str, Any]:
        """
        Lista modelos disponibles.

        Returns:
            dict con {models: [{id, created, owned_by}], count}
        """
        if not self._api_key:
            return self._error("API key de OpenAI no configurada")

        try:
            import requests

            resp = requests.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=timeout,
            )
            data = resp.json()

            if resp.status_code != 200:
                return self._error(f"Error listando modelos: {data}")

            models = sorted(
                [
                    {"id": m["id"], "created": m.get("created"), "owned_by": m.get("owned_by")}
                    for m in data.get("data", [])
                ],
                key=lambda x: x["id"],
            )
            return {"models": models, "count": len(models)}

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            return self._error(str(e))

    def moderate(self, input_text: str, timeout: int = 15) -> dict[str, Any]:
        """
        Moderación de contenido.

        Args:
            input_text: Texto a moderar
            timeout: Timeout en segundos

        Returns:
            dict con {flagged, categories, scores}
        """
        if not self._api_key:
            return self._error("API key de OpenAI no configurada")

        try:
            import requests

            resp = requests.post(
                f"{self._base_url}/moderations",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"input": input_text},
                timeout=timeout,
            )
            data = resp.json()

            if resp.status_code != 200:
                return self._error(f"Error en moderación: {data}")

            result = data["results"][0]
            return {
                "flagged": result["flagged"],
                "categories": result["categories"],
                "category_scores": result["category_scores"],
            }

        except ImportError:
            return self._error("requests library no instalada")
        except Exception as e:
            return self._error(str(e))

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"error": message, "status": "failed"}

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        return {
            "tool": "openai",
            "name": "OpenAI",
            "description": "Inteligencia Artificial con modelos OpenAI (GPT, embeddings, moderación)",
            "actions": {
                "chat_completion": {
                    "name": "Chat Completion",
                    "description": "Chat con modelos GPT",
                    "params": [
                        {"name": "messages", "type": "list", "required": True, "label": "Mensajes"},
                        {
                            "name": "model",
                            "type": "select",
                            "options": ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"],
                            "default": "gpt-4o-mini",
                            "label": "Modelo",
                        },
                        {"name": "temperature", "type": "number", "default": 0.7, "label": "Temperatura"},
                        {"name": "max_tokens", "type": "number", "default": None, "label": "Máx. tokens"},
                    ],
                },
                "embeddings": {
                    "name": "Embeddings",
                    "description": "Genera vectores de embedding",
                    "params": [
                        {"name": "input_text", "type": "string", "required": True, "label": "Texto"},
                    ],
                },
            },
        }
