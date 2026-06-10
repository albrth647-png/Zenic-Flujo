"""
Workflow Determinista — AI Config (Sprint 5)

Configuración multi-proveedor para generación de workflows con IA.
Soporta: Ollama (local), OpenAI (cloud), Anthropic (cloud).
Fallback: si ningún proveedor está disponible, usa el compilador determinista.

NO envía datos a terceros a menos que el usuario active un proveedor cloud.
"""
import os
from dataclasses import dataclass
from enum import Enum
from src.utils.logger import setup_logging

logger = setup_logging(__name__)


class AIProvider(str, Enum):
    """Proveedores de IA soportados."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    NONE = "none"


@dataclass
class ProviderConfig:
    """Configuración de un proveedor de IA."""
    provider: AIProvider
    enabled: bool
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout: int = 30
    max_tokens: int = 2048
    temperature: float = 0.3  # Bajo para respuestas más deterministas

    @property
    def is_configured(self) -> bool:
        """True si el proveedor tiene toda la configuración mínima."""
        if not self.enabled:
            return False
        if self.provider == AIProvider.OLLAMA:
            return bool(self.base_url)
        return bool(self.api_key) and bool(self.model)


class AIConfig:
    """Configuración central de IA para generación de workflows.

    Detecta automáticamente qué proveedores están configurados
    y proporciona fallback ordenado: Ollama → OpenAI → Anthropic → None.
    """

    def __init__(self):
        self.providers: dict[AIProvider, ProviderConfig] = {}
        self.active_provider: AIProvider = AIProvider.NONE
        self.fallback_to_deterministic: bool = True
        self._load_from_env()
        self._detect_active_provider()

    def _load_from_env(self) -> None:
        """Carga configuración de variables de entorno."""
        # ── Ollama (local) ─────────────────────────────
        self.providers[AIProvider.OLLAMA] = ProviderConfig(
            provider=AIProvider.OLLAMA,
            enabled=os.environ.get("WFD_OLLAMA_ENABLED", "false").lower() == "true",
            base_url=os.environ.get("WFD_OLLAMA_URL", "http://localhost:11434"),
            model=os.environ.get("WFD_OLLAMA_MODEL", "llama3.2"),
            timeout=int(os.environ.get("WFD_OLLAMA_TIMEOUT", "30")),
        )

        # ── OpenAI (cloud) ────────────────────────────
        self.providers[AIProvider.OPENAI] = ProviderConfig(
            provider=AIProvider.OPENAI,
            enabled=os.environ.get("WFD_OPENAI_ENABLED", "false").lower() == "true",
            api_key=os.environ.get("WFD_OPENAI_API_KEY", ""),
            model=os.environ.get("WFD_OPENAI_MODEL", "gpt-4o-mini"),
            timeout=int(os.environ.get("WFD_OPENAI_TIMEOUT", "30")),
            max_tokens=int(os.environ.get("WFD_OPENAI_MAX_TOKENS", "2048")),
        )

        # ── Anthropic (cloud) ─────────────────────────
        self.providers[AIProvider.ANTHROPIC] = ProviderConfig(
            provider=AIProvider.ANTHROPIC,
            enabled=os.environ.get("WFD_ANTHROPIC_ENABLED", "false").lower() == "true",
            api_key=os.environ.get("WFD_ANTHROPIC_API_KEY", ""),
            model=os.environ.get("WFD_ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            timeout=int(os.environ.get("WFD_ANTHROPIC_TIMEOUT", "30")),
            max_tokens=int(os.environ.get("WFD_ANTHROPIC_MAX_TOKENS", "2048")),
        )

    def _detect_active_provider(self) -> None:
        """Detecta el mejor proveedor disponible (Ollama primero por privacidad)."""
        # Orden de preferencia: Ollama > OpenAI > Anthropic
        priority = [AIProvider.OLLAMA, AIProvider.OPENAI, AIProvider.ANTHROPIC]

        for provider_type in priority:
            config = self.providers.get(provider_type)
            if config and config.is_configured:
                self.active_provider = provider_type
                logger.info(f"AI provider activo: {provider_type.value} ({config.model})")
                return

        self.active_provider = AIProvider.NONE
        logger.info("Ningún proveedor IA configurado. Modo determinista puro.")

    def get_active_config(self) -> ProviderConfig | None:
        """Retorna la configuración del proveedor activo."""
        if self.active_provider == AIProvider.NONE:
            return None
        return self.providers.get(self.active_provider)

    def is_ai_available(self) -> bool:
        """True si hay un proveedor IA configurado y habilitado."""
        return self.active_provider != AIProvider.NONE

    def set_provider(self, provider: AIProvider, enabled: bool,
                     api_key: str = "", model: str = "") -> None:
        """Actualiza la configuración de un proveedor (para Settings UI)."""
        config = self.providers.get(provider)
        if config:
            config.enabled = enabled
            if api_key:
                config.api_key = api_key
            if model:
                config.model = model
            self._detect_active_provider()

    def get_status(self) -> dict:
        """Retorna estado de todos los proveedores (para API)."""
        return {
            "active_provider": self.active_provider.value,
            "providers": {
                p.value: {
                    "enabled": c.enabled,
                    "configured": c.is_configured,
                    "model": c.model,
                }
                for p, c in self.providers.items()
            },
            "fallback_to_deterministic": self.fallback_to_deterministic,
        }


# ── Instancia global ──────────────────────────────────
_config: AIConfig | None = None


def get_ai_config() -> AIConfig:
    """Retorna la instancia global de AIConfig (singleton lazy)."""
    global _config
    if _config is None:
        _config = AIConfig()
    return _config


def reset_ai_config() -> None:
    """Reinicia la configuración (para tests)."""
    global _config
    _config = None
