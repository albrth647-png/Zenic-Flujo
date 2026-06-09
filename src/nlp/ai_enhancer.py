"""
Workflow Determinista — AI Enhancer
Integración opcional con Ollama (LLM local) para mejorar el IntentClassifier.

NO envía datos a terceros. Todo corre 100% local.
Solo se activa si OLLAMA_ENABLED=True en config.
"""
import json
from src.config import OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class AIEnhancer:
    """
    Mejora el clasificador de intenciones usando un LLM local vía Ollama.

    Se usa como respaldo cuando el clasificador determinista por keywords
    no encuentra coincidencias.

    Integración 100% local, sin datos a terceros.
    """

    def __init__(self) -> None:
        self._enabled = OLLAMA_ENABLED
        self._base_url = OLLAMA_BASE_URL.rstrip("/")
        self._model = OLLAMA_MODEL
        self._timeout = OLLAMA_TIMEOUT

    @property
    def enabled(self) -> bool:
        """Indica si el AI Enhancer está habilitado."""
        return self._enabled

    def is_available(self) -> bool:
        """Verifica si Ollama está corriendo y accesible."""
        if not self._enabled:
            return False
        try:
            import requests
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                available = [m["name"] for m in models]
                logger.info(f"Ollama disponible. Modelos: {available}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Ollama no disponible: {e}")
            return False

    def enhance_intents(self, text: str, fallback_intents: list[dict] | None = None) -> list[dict]:
        """
        Usa el LLM para generar sugerencias de workflow a partir de texto libre.

        Args:
            text: Texto del usuario (ej: "Quiero enviar un email a los clientes nuevos")
            fallback_intents: Intents del clasificador determinista (si existen)

        Returns:
            Lista de intents sugeridos por el LLM
        """
        if not self._enabled:
            return fallback_intents or []

        try:
            prompt = self._build_prompt(text)
            response = self._query_ollama(prompt)
            ai_intents = self._parse_response(response)

            if ai_intents:
                logger.info(f"AI generó {len(ai_intents)} sugerencias para: {text[:50]}")
                return ai_intents

            return fallback_intents or []

        except Exception as e:
            logger.warning(f"Error en AI Enhancer: {e}")
            return fallback_intents or []

    def _build_prompt(self, text: str) -> str:
        """Construye el prompt para el LLM."""
        return f"""Eres un asistente que genera definiciones de workflows de automatización.
Dado el texto del usuario, genera sugerencias de workflow en formato JSON.

Texto del usuario: "{text}"

Responde SOLO con un array JSON de sugerencias. Cada sugerencia debe tener:
- "name": nombre descriptivo del workflow
- "description": descripción corta
- "trigger_type": "manual", "schedule", o "event"
- "steps": array de pasos con "tool" (crm, invoice, inventory, notification, system) y "action"

Ejemplo:
[
  {{
    "name": "enviar_email_bienvenida",
    "description": "Enviar email de bienvenida a nuevos clientes",
    "trigger_type": "manual",
    "steps": [
      {{"tool": "notification", "action": "send_email", "params": {{"to": "$input.email", "subject": "Bienvenido", "body": "Hola"}}}}
    ]
  }}
]

Sugiere entre 1 y 3 workflows relevantes. Responde SOLO JSON, sin texto adicional."""

    def _query_ollama(self, prompt: str) -> str:
        """Envía el prompt a Ollama y retorna la respuesta raw."""
        import requests

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
        }

        resp = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")

    @staticmethod
    def _parse_response(raw: str) -> list[dict]:
        """Parsea la respuesta JSON del LLM."""
        try:
            # Buscar array JSON en la respuesta
            start = raw.find("[")
            end = raw.rfind("]")
            if start != -1 and end != -1:
                json_str = raw[start:end + 1]
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    return parsed
            return []
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Error parseando respuesta AI: {e}")
            return []
