"""
Ollama Connector — LLM local con Ollama
============================================

Sprint 6 del Roadmap Competitivo.
Integración con Ollama para correr LLMs localmente.
Usa requests para comunicarse con la API de Ollama.
"""

from __future__ import annotations

import time

from src.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from src.core.logging import setup_logging
from typing import Any

logger = setup_logging(__name__)


class OllamaService:
    """
    Conector Ollama — LLMs locales.

    Proporciona:
    - chat: Chat con modelos locales
    - generate: Generación de texto simple
    - embeddings: Embeddings locales
    - list_models: Listar modelos instalados
    - pull_model: Descargar un modelo

    Uso en workflow:
    {
        "tool": "ollama",
        "action": "chat",
        "params": {
            "model": "llama3.2",
            "messages": [
                {"role": "user", "content": "$input.consulta"}
            ]
        }
    }
    """

    def __init__(self, base_url: str | None = None, default_model: str | None = None):
        self._base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self._default_model = default_model or OLLAMA_MODEL

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        stream: bool = False,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Chat con modelo local vía Ollama.

        Args:
            messages: Lista de mensajes
            model: Modelo (default: configuración global)
            temperature: Temperatura
            stream: Si True, retorna stream URL (no implementado)
            timeout: Timeout

        Returns:
            dict con {content, model, total_duration, eval_count}
        """
        model = model or self._default_model
        timeout = timeout or OLLAMA_TIMEOUT
        start_time = time.time()

        try:
            import requests

            resp = requests.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "options": {
                        "temperature": temperature,
                    },
                    "stream": stream,
                },
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Ollama error {resp.status_code}: {resp.text}")

            data = resp.json()

            # Extraer contenido del último mensaje
            content = ""
            if "message" in data:
                content = data["message"].get("content", "")

            return {
                "content": content,
                "model": data.get("model", model),
                "total_duration": data.get("total_duration", 0),
                "load_duration": data.get("load_duration", 0),
                "eval_count": data.get("eval_count", 0),
                "eval_duration": data.get("eval_duration", 0),
                "done": data.get("done", True),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except requests.exceptions.ConnectionError:
            return self._error(f"No se pudo conectar a Ollama en {self._base_url}. ¿Está Ollama corriendo?")
        except Exception as e:
            logger.error(f"Ollama chat error: {e}")
            return self._error(str(e))

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.7,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Generación de texto simple (sin historial de chat).

        Args:
            prompt: Prompt de texto
            model: Modelo
            system: System prompt opcional
            temperature: Temperatura
            timeout: Timeout

        Returns:
            dict con {response, model, eval_count, duration_ms}
        """
        model = model or self._default_model
        timeout = timeout or OLLAMA_TIMEOUT
        start_time = time.time()

        try:
            import requests

            payload = {
                "model": model,
                "prompt": prompt,
                "options": {"temperature": temperature},
            }
            if system:
                payload["system"] = system

            resp = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=timeout,
            )

            if resp.status_code != 200:
                return self._error(f"Ollama error {resp.status_code}: {resp.text}")

            data = resp.json()
            return {
                "response": data.get("response", ""),
                "model": data.get("model", model),
                "total_duration": data.get("total_duration", 0),
                "eval_count": data.get("eval_count", 0),
                "done": data.get("done", True),
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except requests.exceptions.ConnectionError:
            return self._error(f"No se pudo conectar a Ollama en {self._base_url}")
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            return self._error(str(e))

    def embeddings(self, input_text: str | list[str], model: str | None = None, timeout: int | None = None) -> dict[str, Any]:
        """
        Genera embeddings usando Ollama.

        Args:
            input_text: Texto o lista de textos
            model: Modelo de embeddings
            timeout: Timeout

        Returns:
            dict con {embeddings, model, duration_ms}
        """
        model = model or self._default_model
        timeout = timeout or OLLAMA_TIMEOUT
        start_time = time.time()
        inputs = [input_text] if isinstance(input_text, str) else input_text

        try:
            import requests

            embeddings_list = []
            for text in inputs:
                resp = requests.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                    timeout=timeout,
                )
                if resp.status_code != 200:
                    return self._error(f"Ollama embeddings error: {resp.text}")
                data = resp.json()
                embeddings_list.append(data.get("embedding", []))

            return {
                "embeddings": embeddings_list,
                "model": model,
                "count": len(embeddings_list),
                "dimension": len(embeddings_list[0]) if embeddings_list else 0,
                "duration_ms": self._elapsed(start_time),
            }

        except ImportError:
            return self._error("requests library no instalada")
        except requests.exceptions.ConnectionError:
            return self._error(f"No se pudo conectar a Ollama en {self._base_url}")
        except Exception as e:
            logger.error(f"Ollama embeddings error: {e}")
            return self._error(str(e))

    def list_models(self, timeout: int = 15) -> dict[str, Any]:
        """
        Lista modelos instalados en Ollama.

        Returns:
            dict con {models: [{name, modified_at, size}], count}
        """
        try:
            import requests

            resp = requests.get(
                f"{self._base_url}/api/tags",
                timeout=timeout,
            )
            if resp.status_code != 200:
                return self._error(f"Error listando modelos: {resp.text}")

            data = resp.json()
            models = [
                {"name": m["name"], "modified_at": m.get("modified_at", ""), "size": m.get("size", 0)}
                for m in data.get("models", [])
            ]
            return {"models": models, "count": len(models)}

        except ImportError:
            return self._error("requests library no instalada")
        except requests.exceptions.ConnectionError:
            return self._error(f"No se pudo conectar a Ollama en {self._base_url}")
        except Exception as e:
            return self._error(str(e))

    def pull_model(self, model: str, timeout: int = 300) -> dict[str, Any]:
        """
        Descarga un modelo en Ollama.

        Args:
            model: Nombre del modelo (ej: llama3.2)
            timeout: Timeout largo para descarga

        Returns:
            dict con {status, model}
        """
        try:
            import requests

            resp = requests.post(
                f"{self._base_url}/api/pull",
                json={"name": model},
                timeout=timeout,
            )
            if resp.status_code != 200:
                return self._error(f"Error descargando modelo: {resp.text}")

            return {"status": "downloaded", "model": model}

        except ImportError:
            return self._error("requests library no instalada")
        except requests.exceptions.ConnectionError:
            return self._error(f"No se pudo conectar a Ollama en {self._base_url}")
        except Exception as e:
            return self._error(str(e))

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"error": message, "status": "failed"}

    @staticmethod
    def _elapsed(start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    @staticmethod
    def get_health(base_url: str | None = None) -> dict[str, Any]:
        """Verifica si Ollama está corriendo."""
        url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        try:
            import requests

            resp = requests.get(f"{url}/api/tags", timeout=5)
            return {"status": "ok" if resp.status_code == 200 else "error", "base_url": url}
        except ImportError:
            return {"status": "error", "message": "requests no instalada"}
        except Exception as e:
            return {"status": "error", "message": str(e), "base_url": url}

    @staticmethod
    def get_tool_definition() -> dict[str, Any]:
        return {
            "tool": "ollama",
            "name": "Ollama (LLM Local)",
            "description": "LLMs locales con Ollama",
            "actions": {
                "chat": {
                    "name": "Chat",
                    "description": "Chat con modelo local",
                    "params": [
                        {"name": "messages", "type": "list", "required": True, "label": "Mensajes"},
                        {"name": "model", "type": "string", "default": "llama3.2", "label": "Modelo"},
                        {"name": "temperature", "type": "number", "default": 0.7, "label": "Temperatura"},
                    ],
                },
                "generate": {
                    "name": "Generar texto",
                    "description": "Generación de texto simple",
                    "params": [
                        {"name": "prompt", "type": "string", "required": True, "label": "Prompt"},
                        {"name": "model", "type": "string", "default": "llama3.2", "label": "Modelo"},
                    ],
                },
                "embeddings": {
                    "name": "Embeddings",
                    "description": "Embeddings locales",
                    "params": [
                        {"name": "input_text", "type": "string", "required": True, "label": "Texto"},
                    ],
                },
            },
        }
